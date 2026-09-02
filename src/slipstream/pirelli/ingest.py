"""Sparse, server-owned public Pirelli acquisition and deterministic normalization."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from .acquisition import PirelliPublicClient
from .archive import PirelliArchive, save_normalized_release
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
    parse_formula1_feed,
    pirelli_event_archive_url,
)
from .extractors.base import HtmlDocument
from .extractors.html import parse_html
from .extractors.pdf_text import extract_pdf_text
from .extractors.prose import extract_strategy_prose
from .extractors.structured import (
    extract_compound_nominations,
    extract_context_facts,
)
from .extractors.tyre_bank import parse_tyre_bank_text
from .validation import validate_result_against_artifacts

NORMALIZER_VERSION = "slipstream-pirelli-v5-adapted.3"
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
        entries = feed_entries
        if entries is None:
            entries = await self.discovery_entries_for_meeting(
                target.meeting, now=retrieved_at
            )
        candidates = discover_for_meeting(
            entries,
            target.meeting,
        )
        if not any(
            candidate.status == ExtractionStatus.ACCEPTED
            for candidate in candidates
        ):
            entries = await self.event_archive_entries(target.meeting, now=retrieved_at)
            candidates = discover_for_meeting(entries, target.meeting)
        normalized: list[str] = []
        skipped: list[str] = []
        issues: list[str] = []
        for candidate in candidates:
            if candidate.status != ExtractionStatus.ACCEPTED:
                skipped.append(candidate.entry.url)
                continue
            try:
                release = await self._normalize_release(target, candidate, retrieved_at)
            except Exception as error:  # noqa: BLE001 - one source cannot break replay
                issues.append(f"{candidate.entry.url}: {type(error).__name__}: {error}")
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
        acquired = await self.client.acquire(
            archive=self.archive,
            meeting_key=target.meeting_key,
            url=pirelli_event_archive_url(target),
            now=now or datetime.now(UTC),
        )
        document = parse_html(
            acquired.body.decode("utf-8", errors="replace"),
            acquired.artifact.source_url,
        )
        return entries_from_event_archive(document, target)

    async def _normalize_release(
        self,
        target: PirelliIngestionTarget,
        candidate: ReleaseCandidate,
        retrieved_at: datetime,
    ) -> PirelliRelease | None:
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
        if _article_body_incomplete(document, candidate.entry.title):
            archived = self._complete_archived_html(
                target.meeting.meeting_key,
                source_url=artifact_version.source_url,
                expected_title=document.title or candidate.entry.title,
            )
            if archived is not None:
                artifact_version, _archived_body, document = archived
            else:
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
        aliases = {
            target.meeting.canonical_name: target.meeting.meeting_key,
            **{alias: target.meeting.meeting_key for alias in target.meeting.aliases},
        }
        nomination_result = extract_compound_nominations(
            document.article_text,
            source_url=artifact_version.source_url,
            artifact_id=artifact_version.artifact_id,
            meeting_aliases=aliases,
            default_applicability=weekend_scope,
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
            weekend_scope
            if purpose in {ReleasePurpose.COMPOUND_NOMINATION, ReleasePurpose.PREVIEW}
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
