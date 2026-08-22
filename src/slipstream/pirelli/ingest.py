"""Sparse, server-owned public Pirelli acquisition and deterministic normalization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .acquisition import PirelliPublicClient
from .archive import PirelliArchive, save_normalized_release
from .contracts import (
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
    MeetingDiscoveryTarget,
    discover_for_meeting,
    discover_official_assets,
    parse_formula1_feed,
)
from .extractors.html import parse_html
from .extractors.pdf_text import extract_pdf_text
from .extractors.prose import extract_strategy_prose
from .extractors.structured import (
    extract_compound_nominations,
    extract_context_facts,
)
from .extractors.tyre_bank import parse_tyre_bank_text
from .validation import validate_result_against_artifacts

NORMALIZER_VERSION = "slipstream-pirelli-v5-adapted.1"


@dataclass(frozen=True)
class PirelliIngestionTarget:
    meeting: MeetingDiscoveryTarget
    target_session_key: str
    drivers: tuple[WeekendDriverIdentity, ...] = ()


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
    ) -> PirelliIngestionReport:
        retrieved_at = now or datetime.now(timezone.utc)
        rss = await self.client.acquire(
            archive=self.archive,
            meeting_key=target.meeting.meeting_key,
            url=PIRELLI_F1_RSS_URL,
            now=retrieved_at,
        )
        candidates = discover_for_meeting(
            parse_formula1_feed(rss.body.decode("utf-8", errors="replace")),
            target.meeting,
        )
        normalized: list[str] = []
        skipped: list[str] = []
        issues: list[str] = []
        for candidate in candidates:
            if candidate.status != ExtractionStatus.ACCEPTED:
                skipped.append(candidate.entry.url)
                continue
            try:
                release = await self._normalize_release(
                    target, candidate.entry.url, retrieved_at
                )
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

    async def _normalize_release(
        self,
        target: PirelliIngestionTarget,
        url: str,
        retrieved_at: datetime,
    ) -> PirelliRelease | None:
        acquired = await self.client.acquire(
            archive=self.archive,
            meeting_key=target.meeting.meeting_key,
            url=url,
            now=retrieved_at,
        )
        if acquired.artifact.source_type != SourceType.NEWSROOM_HTML:
            return None
        document = parse_html(acquired.body.decode("utf-8", errors="replace"), url)
        self.archive.save_text_representation(
            meeting_key=target.meeting.meeting_key,
            artifact_id=acquired.artifact.artifact_id,
            text=document.article_text,
            representation_tool="pirelli_html_jsonld_semantic_v5",
        )
        artifact = self.archive.load_evidence_artifact(
            meeting_key=target.meeting.meeting_key,
            artifact_id=acquired.artifact.artifact_id,
        )
        if artifact is None:
            return None
        race_scope = FactApplicability(
            meeting_key=target.meeting.meeting_key,
            source_meeting_name=target.meeting.canonical_name,
            session_scope=SessionScope.RACE,
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
            source_url=acquired.artifact.source_url,
            artifact_id=acquired.artifact.artifact_id,
            meeting_aliases=aliases,
            default_applicability=weekend_scope,
        )
        nomination_result = validate_result_against_artifacts(
            nomination_result, {artifact.artifact_id: artifact}
        )
        selections = tuple(
            fact
            for fact in nomination_result.facts
            if nomination_result.accepted and isinstance(fact, CompoundSelection)
        )
        code_map = selections[-1].code_map() if selections else None
        strategy_result = extract_strategy_prose(
            document.article_text,
            source_url=acquired.artifact.source_url,
            artifact_id=acquired.artifact.artifact_id,
            compound_code_map=code_map,
            applicability=race_scope,
        )
        strategy_result = validate_result_against_artifacts(
            strategy_result, {artifact.artifact_id: artifact}
        )
        strategies = tuple(
            fact
            for fact in strategy_result.facts
            if strategy_result.accepted and isinstance(fact, StrategyOption)
        )
        banks: list[TyreBankSnapshot] = []
        asset_ids: list[str] = []
        for candidate in discover_official_assets(document):
            if candidate.status != ExtractionStatus.ACCEPTED:
                continue
            asset = await self.client.acquire(
                archive=self.archive,
                meeting_key=target.meeting.meeting_key,
                url=candidate.url,
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
                applicability=race_scope,
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
        facts = extract_context_facts(
            document.article_text,
            source_url=acquired.artifact.source_url,
            artifact_id=acquired.artifact.artifact_id,
            applicability=weekend_scope,
        )
        if not (selections or strategies or banks or facts):
            return None
        return PirelliRelease(
            release_id=acquired.artifact.artifact_id,
            source_url=acquired.artifact.source_url,
            published_at=acquired.artifact.published_at,
            modified_at=acquired.artifact.modified_at,
            retrieved_at=acquired.artifact.retrieved_at,
            content_hash=acquired.artifact.content_hash,
            source_type=acquired.artifact.source_type,
            extraction_method=ExtractionMethod.HYBRID,
            normalizer_version=NORMALIZER_VERSION,
            artifact_ids=(acquired.artifact.artifact_id, *asset_ids),
            applicability=weekend_scope,
            compound_selections=selections,
            strategies=strategies,
            tyre_bank_snapshots=tuple(banks),
            context_facts=facts,
        )
