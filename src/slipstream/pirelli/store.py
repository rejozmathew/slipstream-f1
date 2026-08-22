"""Low-frequency, immutable Pirelli evidence storage and replay-safe loading."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .archive import PirelliArchive, list_normalized_releases
from .contracts import PirelliRelease, SessionScope
from .snapshot import PirelliEvidenceSnapshot, aggregate_releases


def _utc(value: str | datetime) -> datetime:
    parsed = (
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(value, str)
        else value
    )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class PirelliAvailability:
    status: str
    snapshot: PirelliEvidenceSnapshot | None = None
    error: str | None = None


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
            published = release.published_at
            if published is None or _utc(published) > cutoff:
                continue
            retrieved = _utc(release.retrieved_at)
            if retrieved > cutoff:
                if release.modified_at is None or _utc(release.modified_at) > cutoff:
                    continue
            admitted.append(release)
        return tuple(admitted)

    def load(
        self,
        *,
        meeting_key: str,
        target_session_key: str,
        evidence_cutoff: str | datetime,
        session_scope: SessionScope = SessionScope.RACE,
    ) -> PirelliAvailability:
        releases = self.releases_as_of(
            meeting_key, evidence_cutoff=evidence_cutoff
        )
        snapshot = aggregate_releases(
            releases,
            meeting_key=str(meeting_key),
            session_scope=session_scope,
        )
        if not snapshot.release_ids:
            return PirelliAvailability("ABSENT", error="no_admissible_pirelli_release")
        if snapshot.latest_strategy_release is None and not snapshot.compound_selections:
            return PirelliAvailability(
                "ABSENT", snapshot=snapshot, error="no_admissible_published_strategy"
            )
        return PirelliAvailability("PRESENT", snapshot=snapshot)
