"""Low-frequency, immutable Pirelli evidence storage and replay-safe loading."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from .archive import PirelliArchive, list_normalized_releases
from .contracts import ArtifactVersion, NormalizedFact, PirelliRelease, SessionScope
from .snapshot import PirelliEvidenceSnapshot, aggregate_releases


def _utc(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class PirelliAvailability:
    status: str
    snapshot: PirelliEvidenceSnapshot | None = None
    error: str | None = None
    model_admissible: bool = True
    evidence_tier: str = "STRICT_MODEL"
    provenance_label: str | None = None


class PirelliEvidenceStore:
    """Own archived public artifacts and normalized releases under the data root."""

    def __init__(self, data_root: Path) -> None:
        self.archive = PirelliArchive(data_root)

    def releases_as_of(
        self,
        meeting_key: str,
        *,
        evidence_cutoff: str | datetime,
    ) -> tuple[PirelliRelease, ...]:
        """Admit only an exact source version proven to exist by the cutoff.

        A release retrieved after the cutoff is admissible only when its source supplied
        an unambiguous modification timestamp at or before the cutoff. Unknown dates fail
        closed; current source content is never projected backwards into a replay.
        """

        cutoff = _utc(evidence_cutoff)
        admitted: list[PirelliRelease] = []
        for release in list_normalized_releases(self.archive, str(meeting_key)):
            parent = self.archive.get_version(str(meeting_key), release.release_id)
            if parent is None or not _artifact_admissible(parent, cutoff):
                continue
            selections = tuple(
                fact
                for fact in release.compound_selections
                if self._fact_admissible(str(meeting_key), fact, cutoff)
            )
            strategies = tuple(
                fact
                for fact in release.strategies
                if self._fact_admissible(str(meeting_key), fact, cutoff)
            )
            banks = tuple(
                fact
                for fact in release.tyre_bank_snapshots
                if self._fact_admissible(str(meeting_key), fact, cutoff)
            )
            facts = tuple(
                fact
                for fact in release.context_facts
                if self._fact_admissible(str(meeting_key), fact, cutoff)
            )
            if not (selections or strategies or banks or facts):
                continue
            admitted_ids = tuple(
                artifact_id
                for artifact_id in release.artifact_ids
                if (version := self.archive.get_version(str(meeting_key), artifact_id))
                is not None
                and _artifact_admissible(version, cutoff)
            )
            admitted.append(
                replace(
                    release,
                    artifact_ids=admitted_ids,
                    compound_selections=selections,
                    strategies=strategies,
                    tyre_bank_snapshots=banks,
                    context_facts=facts,
                )
            )
        return tuple(admitted)

    def display_releases_as_of(
        self,
        meeting_key: str,
        *,
        evidence_cutoff: str | datetime,
    ) -> tuple[PirelliRelease, ...]:
        """Admit official pre-race facts for display, never model evidence.

        This tier permits a later archive retrieval only when Pirelli supplies
        a publication timestamp at or before the target race start. Exact
        meeting and fact applicability are still enforced by the snapshot.
        """

        cutoff = _utc(evidence_cutoff)
        admitted: list[PirelliRelease] = []
        for release in list_normalized_releases(self.archive, str(meeting_key)):
            parent = self.archive.get_version(str(meeting_key), release.release_id)
            if (
                release.applicability.meeting_key != str(meeting_key)
                or parent is None
                or not _artifact_display_admissible(parent, cutoff)
            ):
                continue
            selections = tuple(
                fact
                for fact in release.compound_selections
                if self._fact_display_admissible(str(meeting_key), fact, cutoff)
            )
            strategies = tuple(
                fact
                for fact in release.strategies
                if self._fact_display_admissible(str(meeting_key), fact, cutoff)
            )
            banks = tuple(
                fact
                for fact in release.tyre_bank_snapshots
                if self._fact_display_admissible(str(meeting_key), fact, cutoff)
            )
            facts = tuple(
                fact
                for fact in release.context_facts
                if self._fact_display_admissible(str(meeting_key), fact, cutoff)
            )
            if not (selections or strategies or banks or facts):
                continue
            admitted.append(
                replace(
                    release,
                    artifact_ids=tuple(
                        artifact_id
                        for artifact_id in release.artifact_ids
                        if (
                            version := self.archive.get_version(
                                str(meeting_key), artifact_id
                            )
                        )
                        is not None
                        and _artifact_display_admissible(version, cutoff)
                    ),
                    compound_selections=selections,
                    strategies=strategies,
                    tyre_bank_snapshots=banks,
                    context_facts=facts,
                )
            )
        return tuple(admitted)

    def _fact_admissible(
        self, meeting_key: str, fact: NormalizedFact, cutoff: datetime
    ) -> bool:
        artifact_ids = {item.artifact_id for item in fact.source_evidence}
        if not artifact_ids:
            return False
        return all(
            (version := self.archive.get_version(meeting_key, artifact_id)) is not None
            and _artifact_admissible(version, cutoff)
            for artifact_id in artifact_ids
        )

    def _fact_display_admissible(
        self, meeting_key: str, fact: NormalizedFact, cutoff: datetime
    ) -> bool:
        artifact_ids = {item.artifact_id for item in fact.source_evidence}
        if not artifact_ids:
            return False
        return all(
            (version := self.archive.get_version(meeting_key, artifact_id)) is not None
            and _artifact_display_admissible(version, cutoff)
            for artifact_id in artifact_ids
        )

    def load(
        self,
        *,
        meeting_key: str,
        target_session_key: str,
        evidence_cutoff: str | datetime,
        session_scope: SessionScope = SessionScope.RACE,
    ) -> PirelliAvailability:
        releases = self.releases_as_of(meeting_key, evidence_cutoff=evidence_cutoff)
        strict = _availability_for_releases(
            releases,
            meeting_key=meeting_key,
            target_session_key=target_session_key,
            session_scope=session_scope,
        )
        if strict.status == "PRESENT":
            return strict
        display_releases = self.display_releases_as_of(
            meeting_key, evidence_cutoff=evidence_cutoff
        )
        display = _availability_for_releases(
            display_releases,
            meeting_key=meeting_key,
            target_session_key=target_session_key,
            session_scope=session_scope,
            model_admissible=False,
            evidence_tier="DISPLAY_ONLY_OFFICIAL_HISTORICAL",
            provenance_label="PUBLISHED PRE-RACE · ARCHIVED LATER",
        )
        return display if display.status == "PRESENT" else strict


def _availability_for_releases(
    releases: tuple[PirelliRelease, ...],
    *,
    meeting_key: str,
    target_session_key: str,
    session_scope: SessionScope,
    model_admissible: bool = True,
    evidence_tier: str = "STRICT_MODEL",
    provenance_label: str | None = None,
) -> PirelliAvailability:
    snapshot = aggregate_releases(
        releases,
        meeting_key=str(meeting_key),
        session_scope=session_scope,
        target_session_key=target_session_key,
    )
    if not snapshot.release_ids:
        return PirelliAvailability(
            "ABSENT",
            error="no_admissible_pirelli_release",
            model_admissible=model_admissible,
            evidence_tier=evidence_tier,
        )
    if snapshot.latest_strategy_release is None and not snapshot.compound_selections:
        return PirelliAvailability(
            "ABSENT",
            snapshot=snapshot,
            error="no_admissible_published_strategy",
            model_admissible=model_admissible,
            evidence_tier=evidence_tier,
        )
    return PirelliAvailability(
        "PRESENT",
        snapshot=snapshot,
        model_admissible=model_admissible,
        evidence_tier=evidence_tier,
        provenance_label=provenance_label,
    )


def _artifact_admissible(artifact: ArtifactVersion, cutoff: datetime) -> bool:
    published = artifact.published_at
    if published is not None and _utc(published) > cutoff:
        return False
    retrieved = _utc(artifact.retrieved_at)
    if retrieved <= cutoff:
        return True
    modified = artifact.modified_at
    return modified is not None and _utc(modified) <= cutoff


def _artifact_display_admissible(
    artifact: ArtifactVersion, cutoff: datetime
) -> bool:
    host = (urlparse(artifact.source_url).hostname or "").casefold()
    return (
        host in {"press.pirelli.com", "content.presspage.com"}
        and artifact.published_at is not None
        and _utc(artifact.published_at) <= cutoff
    )
