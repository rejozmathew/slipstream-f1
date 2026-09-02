"""Sparse, server-owned public Pirelli acquisition and deterministic normalization."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from .acquisition import PirelliPublicClient
from .archive import (
    PirelliArchive,
    list_normalized_derivations,
    save_normalized_release,
)
from .config import NORMALIZER_VERSION
from .contracts import (
    ArtifactVersion,
    CompoundSelection,
    ExtractionMethod,
    ExtractionStatus,
    FactApplicability,
    PirelliRelease,
    SessionScope,
    SourceType,
    StrategyOption,
    TyreBankSnapshot,
    WeekendDriverIdentity,
)
from .discovery import (
    PIRELLI_F1_RSS_URL,
    FeedEntry,
    MeetingDiscoveryTarget,
    ReleaseCandidate,
    ReleasePurpose,
    classify_release_purpose,
    discover_for_meeting,
    discover_official_assets,
    entries_from_event_archive,
    entries_from_event_feed,
    parse_formula1_feed,
    pirelli_event_archive_urls,
    pirelli_event_rss_url,
    pirelli_event_tags,
)
from .extractors.base import HtmlDocument
from .extractors.html import parse_html
from .extractors.pdf_text import extract_pdf_text
from .extractors.prose import extract_strategy_prose
from .extractors.structured import (
    extract_compound_nominations,
    extract_context_facts,
    is_multi_event_nomination_article,
)
from .extractors.tyre_bank import parse_tyre_bank_text
from .validation import validate_result_against_artifacts

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PirelliIngestionTarget:
    meeting: MeetingDiscoveryTarget
    target_session_key: str
    session_scope: SessionScope = SessionScope.RACE
    drivers: tuple[WeekendDriverIdentity, ...] = ()

    def __post_init__(self) -> None:
        if self.session_scope not in {SessionScope.RACE, SessionScope.SPRINT}:
            raise ValueError("Pirelli strategy ingestion targets Race or Sprint only")


@dataclass(frozen=True)
class PirelliIngestionReport:
    normalized_release_ids: tuple[str, ...]
    skipped_release_urls: tuple[str, ...]
    issues: tuple[str, ...]


class PirelliIngestionService:
    """Run one bounded refresh for a meeting; never called by browser render paths."""

    def __init__(
        self,
        archive: PirelliArchive,
        client: PirelliPublicClient | None = None,
    ) -> None:
        self.archive = archive
        self.client = client or PirelliPublicClient()

    async def refresh(
        self,
        target: PirelliIngestionTarget,
        *,
        now: datetime | None = None,
        feed_entries: tuple[FeedEntry, ...] | None = None,
    ) -> PirelliIngestionReport:
        retrieved_at = now or datetime.now(UTC)
        normalized: list[str] = []
        normalized_purposes: set[ReleasePurpose] = set()
        skipped: list[str] = []
        issues: list[str] = []
        seen_urls: set[str] = set()

        async def consume(entries: tuple[FeedEntry, ...]) -> None:
            candidates = discover_for_meeting(entries, target.meeting)
            for candidate in candidates:
                if candidate.entry.url in seen_urls:
                    continue
                seen_urls.add(candidate.entry.url)
                if candidate.status != ExtractionStatus.ACCEPTED:
                    skipped.append(candidate.entry.url)
                    continue
                try:
                    release = await self._normalize_release(
                        target, candidate, retrieved_at
                    )
                except Exception as error:  # noqa: BLE001 - one source is isolated
                    issues.append(
                        f"{candidate.entry.url}: {type(error).__name__}: {error}"
                    )
                    continue
                if release is None:
                    skipped.append(candidate.entry.url)
                    continue
                save_normalized_release(
                    self.archive,
                    meeting_key=target.meeting.meeting_key,
                    release=release,
                )
                normalized.append(release.release_id)
                if target.session_scope == SessionScope.RACE and release.strategies:
                    normalized_purposes.add(ReleasePurpose.RACE_STRATEGY)
                elif any(
                    fact.category == "STRATEGY_OUTLOOK"
                    for fact in release.context_facts
                ):
                    normalized_purposes.add(ReleasePurpose.PREVIEW)
                else:
                    normalized_purposes.add(candidate.purpose)

        def exact_sources_needed() -> bool:
            if target.session_scope != SessionScope.RACE:
                return not normalized
            return not normalized_purposes.intersection(
                {ReleasePurpose.PREVIEW, ReleasePurpose.RACE_STRATEGY}
            )

        entries = feed_entries
        if entries is None:
            try:
                entries = await self.discovery_entries(now=retrieved_at)
            except Exception as error:  # noqa: BLE001 - global feed is optional
                logger.debug("Pirelli global discovery feed failed: %s", error)
                entries = ()
        await consume(entries)
        if exact_sources_needed():
            try:
                await consume(
                    await self.event_archive_entries(
                        target.meeting, now=retrieved_at
                    )
                )
            except Exception as error:  # noqa: BLE001 - exact archive is optional
                logger.debug("Pirelli event archive discovery failed: %s", error)
                issues.append(
                    f"event archive discovery: {type(error).__name__}: {error}"
                )
        if exact_sources_needed():
            try:
                await consume(
                    await self.event_rss_entries(target.meeting, now=retrieved_at)
                )
            except Exception as error:  # noqa: BLE001 - exact feed is optional
                logger.debug("Pirelli event RSS discovery failed: %s", error)
                issues.append(f"event RSS discovery: {type(error).__name__}: {error}")
        return PirelliIngestionReport(tuple(normalized), tuple(skipped), tuple(issues))

    async def discovery_entries(
        self,
        *,
        now: datetime | None = None,
        archive_key: str = "_discovery",
    ) -> tuple[FeedEntry, ...]:
        """Acquire a fresh feed snapshot; callers may reuse it for one sweep."""

        retrieved_at = now or datetime.now(UTC)
        rss = await self.client.acquire(
            archive=self.archive,
            meeting_key=archive_key,
            url=PIRELLI_F1_RSS_URL,
            now=retrieved_at,
        )
        return parse_formula1_feed(rss.body.decode("utf-8", errors="replace"))

    async def discovery_entries_for_meeting(
        self, target: MeetingDiscoveryTarget, *, now: datetime | None = None
    ) -> tuple[FeedEntry, ...]:
        """Use RSS as a fast path, then isolate fallback to this one event."""

        try:
            feed = await self.discovery_entries(now=now)
            if any(
                candidate.status == ExtractionStatus.ACCEPTED
                for candidate in discover_for_meeting(feed, target)
            ):
                return feed
        except Exception:  # noqa: BLE001 - shared feed is optional
            return await self.event_archive_entries(target, now=now)
        return await self.event_archive_entries(target, now=now)

    async def event_archive_entries(
        self, target: MeetingDiscoveryTarget, *, now: datetime | None = None
    ) -> tuple[FeedEntry, ...]:
        error: Exception | None = None
        for url in pirelli_event_archive_urls(target):
            try:
                acquired = await self.client.acquire(
                    archive=self.archive,
                    meeting_key=target.meeting_key,
                    url=url,
                    now=now or datetime.now(UTC),
                )
                document = parse_html(
                    acquired.body.decode("utf-8", errors="replace"),
                    acquired.artifact.source_url,
                )
                entries = entries_from_event_archive(document, target)
                if entries:
                    return entries
            except Exception as caught:  # noqa: BLE001 - tag aliases are isolated
                error = caught
        if error is not None:
            raise error
        return ()

    async def event_rss_entries(
        self, target: MeetingDiscoveryTarget, *, now: datetime | None = None
    ) -> tuple[FeedEntry, ...]:
        """Use one exact official event/tag feed after archive cards are insufficient."""

        error: Exception | None = None
        for tag in pirelli_event_tags(target):
            try:
                acquired = await self.client.acquire(
                    archive=self.archive,
                    meeting_key=target.meeting_key,
                    url=pirelli_event_rss_url(tag),
                    now=now or datetime.now(UTC),
                )
                entries = entries_from_event_feed(
                    acquired.body.decode("utf-8", errors="replace"), tag
                )
                if entries:
                    return entries
            except Exception as caught:  # noqa: BLE001 - tag aliases are isolated
                error = caught
        if error is not None:
            raise error
        return ()

    async def _normalize_release(
        self,
        target: PirelliIngestionTarget,
        candidate: ReleaseCandidate,
        retrieved_at: datetime,
        *,
        archived: tuple[ArtifactVersion, HtmlDocument] | None = None,
        acquire_linked_assets: bool = True,
    ) -> PirelliRelease | None:
        if archived is None:
            url = candidate.entry.url
            acquired = await self.client.acquire(
                archive=self.archive,
                meeting_key=target.meeting.meeting_key,
                url=url,
                now=retrieved_at,
            )
            if acquired.artifact.source_type != SourceType.NEWSROOM_HTML:
                return None
            artifact_version = acquired.artifact
            body = acquired.body
            document = parse_html(body.decode("utf-8", errors="replace"), url)
        else:
            artifact_version, document = archived
            if artifact_version.source_type != SourceType.NEWSROOM_HTML:
                return None
        if _article_body_incomplete(document, candidate.entry.title):
            archived = self._complete_archived_html(
                target.meeting.meeting_key,
                source_url=artifact_version.source_url,
                expected_title=document.title or candidate.entry.title,
            )
            if archived is not None:
                artifact_version, _archived_body, document = archived
            elif acquire_linked_assets:
                recovered = await self._recover_from_event_archive(
                    target,
                    candidate,
                    retrieved_at=retrieved_at,
                    excluded_url=artifact_version.source_url,
                )
                if recovered is not None:
                    artifact_version, _recovered_body, document = recovered
        if _index_like_source(artifact_version.source_url) or _article_body_incomplete(
            document, candidate.entry.title
        ):
            return None
        self.archive.save_discovery_provenance(
            meeting_key=target.meeting.meeting_key,
            artifact_id=artifact_version.artifact_id,
            match_reason=candidate.match_reason,
        )
        purpose = classify_release_purpose(
            candidate.entry.title,
            f"{candidate.entry.summary} {document.article_text}",
        )
        self.archive.save_text_representation(
            meeting_key=target.meeting.meeting_key,
            artifact_id=artifact_version.artifact_id,
            text=document.article_text,
            representation_tool="pirelli_html_jsonld_semantic_v5",
        )
        evidence_artifact = self.archive.load_evidence_artifact(
            meeting_key=target.meeting.meeting_key,
            artifact_id=artifact_version.artifact_id,
        )
        if evidence_artifact is None:
            return None
        target_scope = FactApplicability(
            meeting_key=target.meeting.meeting_key,
            source_meeting_name=target.meeting.canonical_name,
            session_scope=target.session_scope,
            target_session_key=target.target_session_key,
        )
        weekend_scope = FactApplicability(
            meeting_key=target.meeting.meeting_key,
            source_meeting_name=target.meeting.canonical_name,
            session_scope=SessionScope.WEEKEND,
            target_session_key=target.target_session_key,
        )
        short_meeting_name = re.sub(
            r"\s+Grand\s+Prix$", "", target.meeting.canonical_name, flags=re.IGNORECASE
        ).strip()
        aliases = {
            target.meeting.canonical_name: target.meeting.meeting_key,
            **(
                {short_meeting_name: target.meeting.meeting_key}
                if short_meeting_name
                else {}
            ),
            **{alias: target.meeting.meeting_key for alias in target.meeting.aliases},
        }
        nomination_result = extract_compound_nominations(
            document.article_text,
            source_url=artifact_version.source_url,
            artifact_id=artifact_version.artifact_id,
            meeting_aliases=aliases,
            default_applicability=weekend_scope,
            exact_event_scope=(
                "exact_event_tag" in candidate.match_reason
                or (
                    candidate.match_reason
                    in {
                        "meeting_alias_in_title",
                        "meeting_alias_in_archived_source",
                    }
                    and not is_multi_event_nomination_article(
                        f"{document.title}. {document.article_text}"
                    )
                )
            ),
        )
        nomination_result = validate_result_against_artifacts(
            nomination_result,
            {evidence_artifact.artifact_id: evidence_artifact},
        )
        selections = tuple(
            fact
            for fact in nomination_result.facts
            if nomination_result.accepted and isinstance(fact, CompoundSelection)
        )
        code_map = selections[-1].code_map() if selections else None
        purpose_scope = _strategy_scope(purpose)
        strategies: tuple[StrategyOption, ...] = ()
        if purpose_scope == target.session_scope:
            strategy_result = extract_strategy_prose(
                document.article_text,
                source_url=artifact_version.source_url,
                artifact_id=artifact_version.artifact_id,
                compound_code_map=code_map,
                applicability=target_scope,
            )
            strategy_result = validate_result_against_artifacts(
                strategy_result,
                {evidence_artifact.artifact_id: evidence_artifact},
            )
            strategies = tuple(
                fact
                for fact in strategy_result.facts
                if strategy_result.accepted and isinstance(fact, StrategyOption)
            )
        banks: list[TyreBankSnapshot] = []
        asset_ids: list[str] = []
        for asset_candidate in discover_official_assets(document):
            if (
                target.session_scope != SessionScope.RACE
                or asset_candidate.status != ExtractionStatus.ACCEPTED
                or not acquire_linked_assets
            ):
                continue
            asset = await self.client.acquire(
                archive=self.archive,
                meeting_key=target.meeting.meeting_key,
                url=asset_candidate.url,
                now=retrieved_at,
            )
            asset_ids.append(asset.artifact.artifact_id)
            if asset.artifact.source_type != SourceType.PDF:
                continue
            try:
                pages = extract_pdf_text(asset.body)
            except RuntimeError:
                continue
            text = "\n".join(page.text for page in pages if page.text)
            self.archive.save_text_representation(
                meeting_key=target.meeting.meeting_key,
                artifact_id=asset.artifact.artifact_id,
                text=text,
                page_texts=tuple(page.text for page in pages),
                representation_tool="pypdf-native-text",
            )
            result = parse_tyre_bank_text(
                text,
                artifact_id=asset.artifact.artifact_id,
                source_url=asset.artifact.source_url,
                method=ExtractionMethod.PDF_TEXT,
                weekend_drivers=target.drivers,
                applicability=target_scope,
            )
            evidence = self.archive.load_evidence_artifact(
                meeting_key=target.meeting.meeting_key,
                artifact_id=asset.artifact.artifact_id,
            )
            if evidence is not None:
                result = validate_result_against_artifacts(
                    result, {evidence.artifact_id: evidence}
                )
            banks.extend(
                fact
                for fact in result.facts
                if result.accepted and isinstance(fact, TyreBankSnapshot)
            )
        context_scope = (
            target_scope
            if purpose in {ReleasePurpose.COMPOUND_NOMINATION, ReleasePurpose.PREVIEW}
            and not (
                purpose == ReleasePurpose.COMPOUND_NOMINATION
                and is_multi_event_nomination_article(
                    f"{document.title}. {document.article_text}"
                )
            )
            else target_scope
            if purpose_scope == target.session_scope
            else None
        )
        facts = (
            extract_context_facts(
                document.article_text,
                source_url=artifact_version.source_url,
                artifact_id=artifact_version.artifact_id,
                applicability=context_scope,
                meeting_aliases=aliases,
                sections=document.article_sections,
            )
            if context_scope is not None
            else ()
        )
        if not (selections or strategies or banks or facts):
            return None
        return PirelliRelease(
            release_id=artifact_version.artifact_id,
            source_url=artifact_version.source_url,
            published_at=artifact_version.published_at,
            modified_at=artifact_version.modified_at,
            retrieved_at=artifact_version.retrieved_at,
            content_hash=artifact_version.content_hash,
            source_type=artifact_version.source_type,
            extraction_method=ExtractionMethod.HYBRID,
            normalizer_version=NORMALIZER_VERSION,
            artifact_ids=(artifact_version.artifact_id, *asset_ids),
            applicability=weekend_scope,
            compound_selections=selections,
            strategies=strategies,
            tyre_bank_snapshots=tuple(banks),
            context_facts=facts,
        )

    async def renormalize_archived(
        self,
        target: PirelliIngestionTarget,
        *,
        artifact_ids: tuple[str, ...] = (),
    ) -> PirelliIngestionReport:
        """Re-run current extraction against immutable local source material."""

        selected_ids = set(artifact_ids)
        current_sources = {
            (release.release_id, release.content_hash)
            for release in list_normalized_derivations(
                self.archive, target.meeting.meeting_key
            )
            if release.normalizer_version == NORMALIZER_VERSION
        }
        normalized: list[str] = []
        skipped: list[str] = []
        issues: list[str] = []
        for artifact in self.archive.list_versions(target.meeting.meeting_key):
            if selected_ids and artifact.artifact_id not in selected_ids:
                continue
            if artifact.source_type != SourceType.NEWSROOM_HTML:
                continue
            if (artifact.artifact_id, artifact.content_hash) in current_sources:
                continue
            document = self._archived_document(
                target.meeting.meeting_key, artifact
            )
            if document is None or _index_like_source(artifact.source_url):
                skipped.append(artifact.source_url)
                continue
            candidate = self._archived_candidate(target, artifact, document)
            if candidate is None:
                skipped.append(artifact.source_url)
                continue
            try:
                release = await self._normalize_release(
                    target,
                    candidate,
                    artifact.retrieved_at,
                    archived=(artifact, document),
                    acquire_linked_assets=False,
                )
            except Exception as error:  # noqa: BLE001 - maintenance is per artifact
                issues.append(
                    f"{artifact.source_url}: {type(error).__name__}: {error}"
                )
                continue
            if release is None:
                skipped.append(artifact.source_url)
                continue
            source_key = (release.release_id, release.content_hash)
            if source_key in current_sources:
                continue
            save_normalized_release(
                self.archive,
                meeting_key=target.meeting.meeting_key,
                release=release,
            )
            current_sources.add(source_key)
            normalized.append(release.release_id)
        return PirelliIngestionReport(
            tuple(normalized), tuple(skipped), tuple(issues)
        )

    def _archived_candidate(
        self,
        target: PirelliIngestionTarget,
        artifact: ArtifactVersion,
        document: HtmlDocument,
    ) -> ReleaseCandidate | None:
        """Reconstruct only discovery scope that the archive can still prove."""

        exact_event = self.archive.has_exact_event_discovery(
            target.meeting.meeting_key, artifact.artifact_id
        )
        entry = FeedEntry(
            document.title or "",
            artifact.source_url,
            artifact.published_at,
            tuple(pirelli_event_tags(target.meeting)) if exact_event else (),
            document.article_text,
        )
        candidates = discover_for_meeting((entry,), target.meeting)
        accepted = next(
            (
                candidate
                for candidate in candidates
                if candidate.status == ExtractionStatus.ACCEPTED
            ),
            None,
        )
        if accepted is not None:
            return accepted

        # Legacy archives predate discovery-provenance records. They remain
        # reprocessable only when the immutable article itself names this event.
        haystack = f"{document.title} {document.article_text}".casefold()
        aliases = {
            target.meeting.canonical_name.casefold(),
            *(alias.casefold() for alias in target.meeting.aliases),
        }
        if not any(alias and alias in haystack for alias in aliases):
            return None
        purpose = classify_release_purpose(document.title, document.article_text)
        return ReleaseCandidate(
            ExtractionStatus.ACCEPTED,
            entry,
            purpose,
            "meeting_alias_in_archived_source",
            70,
        )

    def _archived_document(
        self, meeting_key: str, artifact: ArtifactVersion
    ) -> HtmlDocument | None:
        body = self.archive.load_asset_bytes(meeting_key, artifact.artifact_id)
        if body is not None:
            return parse_html(
                body.decode("utf-8", errors="replace"), artifact.source_url
            )
        evidence = self.archive.load_evidence_artifact(
            meeting_key=meeting_key, artifact_id=artifact.artifact_id
        )
        if evidence is None or not evidence.text:
            return None
        text = " ".join(evidence.text.split())
        sections = tuple(
            part.strip()
            for part in re.split(r"(?:\r?\n){2,}|(?<=[.!?])\s+", evidence.text)
            if part.strip()
        )
        return HtmlDocument(
            title="",
            article_text=text,
            published_at_text=None,
            modified_at_text=None,
            links=(),
            tables=(),
            article_sections=sections or (text,),
        )

    def _complete_archived_html(
        self,
        meeting_key: str,
        *,
        source_url: str,
        expected_title: str,
    ) -> tuple[ArtifactVersion, bytes, HtmlDocument] | None:
        """Recover a complete immutable version of one exact official URL.

        Presspage can close an older article response mid-document. Reuse is
        bounded to a previously archived, complete HTML version with the same
        canonical URL and article title; no cross-article fallback is allowed.
        """

        expected = " ".join(expected_title.casefold().split())
        candidates = []
        for version in self.archive.list_versions(meeting_key):
            if (
                version.source_type != SourceType.NEWSROOM_HTML
                or version.source_url.rstrip("/") != source_url.rstrip("/")
            ):
                continue
            body = self.archive.load_asset_bytes(meeting_key, version.artifact_id)
            if body is None or not body.rstrip().lower().endswith(b"</html>"):
                continue
            document = parse_html(
                body.decode("utf-8", errors="replace"), version.source_url
            )
            title = " ".join(document.title.casefold().split())
            if expected and title != expected:
                continue
            if _article_body_incomplete(document, expected_title):
                continue
            candidates.append((version, body, document))
        return max(
            candidates,
            key=lambda item: (item[0].retrieved_at, len(item[1])),
            default=None,
        )

    async def _recover_from_event_archive(
        self,
        target: PirelliIngestionTarget,
        candidate: ReleaseCandidate,
        *,
        retrieved_at: datetime,
        excluded_url: str,
    ) -> tuple[ArtifactVersion, bytes, HtmlDocument] | None:
        """Try one exact-title alternate from the supported official event archive."""

        try:
            entries = await self.event_archive_entries(
                target.meeting, now=retrieved_at
            )
        except Exception:  # noqa: BLE001 - bounded recovery is optional
            return None
        expected = _normalized_title(candidate.entry.title)
        attempted = False
        for entry in entries:
            if entry.url.rstrip("/") == excluded_url.rstrip("/"):
                continue
            if expected and _normalized_title(entry.title) != expected:
                continue
            if attempted:
                break
            attempted = True
            try:
                acquired = await self.client.acquire(
                    archive=self.archive,
                    meeting_key=target.meeting.meeting_key,
                    url=entry.url,
                    now=retrieved_at,
                )
            except Exception as error:  # noqa: BLE001 - one alternate is isolated
                logger.debug("Pirelli article recovery alternate failed: %s", error)
                continue
            if acquired.artifact.source_type != SourceType.NEWSROOM_HTML:
                continue
            document = parse_html(
                acquired.body.decode("utf-8", errors="replace"),
                acquired.artifact.source_url,
            )
            if _index_like_source(
                acquired.artifact.source_url
            ) or _article_body_incomplete(document, entry.title):
                continue
            return acquired.artifact, acquired.body, document
        return None


def _strategy_scope(purpose: ReleasePurpose) -> SessionScope:
    if purpose == ReleasePurpose.RACE_STRATEGY:
        return SessionScope.RACE
    if purpose == ReleasePurpose.SPRINT:
        return SessionScope.SPRINT
    return SessionScope.UNKNOWN


def _normalized_title(value: str) -> str:
    return " ".join(value.casefold().split())


def _article_body_incomplete(document: HtmlDocument, expected_title: str) -> bool:
    body = " ".join(document.article_text.split())
    if len(body) < 20 or len(body.split()) < 5:
        return True
    expected = _normalized_title(expected_title)
    normalized_body = _normalized_title(body)
    return bool(
        expected
        and (
            normalized_body == expected
            or (expected in normalized_body and len(normalized_body) - len(expected) < 100)
        )
    )


def _index_like_source(source_url: str) -> bool:
    parsed = urlparse(source_url)
    path = parsed.path.rstrip("/").casefold()
    query = parse_qs(parsed.query)
    if not path:
        return True
    if {"h", "t"}.issubset(query):
        return True
    return path in {"/news", "/newsroom", "/archive", "/formula-1"}
