"""Bounded manual Pirelli historical Race backfill over the replay catalog."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..library import ReplayLibrary
from .archive import list_normalized_releases
from .contracts import SessionScope
from .coordinator import build_ingestion_target
from .ingest import PirelliIngestionService
from .store import PirelliEvidenceStore


@dataclass(frozen=True)
class PirelliBackfillItem:
    meeting_key: str
    meeting_name: str
    year: int
    session_key: str
    status: str
    attempted: bool
    normalized_release_count: int = 0
    issue: str | None = None


@dataclass(frozen=True)
class PirelliBackfillReport:
    years: tuple[int, ...]
    dry_run: bool
    items: tuple[PirelliBackfillItem, ...]

    @property
    def selected(self) -> int:
        return len(self.items)

    @property
    def meetings_attempted(self) -> int:
        return sum(item.attempted for item in self.items)

    def count(self, status: str) -> int:
        return sum(item.status == status for item in self.items)


async def sync_pirelli_backfill(
    data_root: Path,
    *,
    years: tuple[int, ...],
    meeting_keys: tuple[str, ...] = (),
    force: bool = False,
    dry_run: bool = False,
    now: datetime | None = None,
    library: Any | None = None,
    service: PirelliIngestionService | Any | None = None,
) -> PirelliBackfillReport:
    """Sync Race-only Pirelli releases through the existing archive/store path."""

    selected_years = tuple(sorted(set(years)))
    if not selected_years:
        raise ValueError("at least one season is required")
    selected_meetings = {str(value) for value in meeting_keys}
    replay_library = library or ReplayLibrary(data_root)
    descriptors = dict(replay_library.descriptors)
    races = [
        descriptor
        for descriptor in descriptors.values()
        if descriptor.session_kind == "race"
        and int(descriptor.year) in selected_years
        and (not selected_meetings or str(descriptor.meeting_key) in selected_meetings)
    ]
    by_meeting: dict[str, object] = {}
    for descriptor in sorted(races, key=lambda item: item.date_start):
        by_meeting[str(descriptor.meeting_key)] = descriptor

    store = PirelliEvidenceStore(data_root)
    ingestion = service or PirelliIngestionService(store.archive)
    retrieved_at = now or datetime.now(UTC)
    items: list[PirelliBackfillItem] = []
    for meeting_key, descriptor in by_meeting.items():
        if dry_run:
            items.append(_item(descriptor, "PLANNED", attempted=False))
            continue

        existing = list_normalized_releases(store.archive, meeting_key)
        attempted = force or not existing
        issue: str | None = None
        if attempted:
            inventory = sorted(
                (
                    item
                    for item in descriptors.values()
                    if str(item.meeting_key) == meeting_key
                ),
                key=lambda item: item.date_start,
            )
            try:
                target = build_ingestion_target(
                    meeting_key,
                    descriptor,
                    inventory,
                    replay_library.get,
                )
                refresh = await ingestion.refresh(target, now=retrieved_at)
                if refresh.issues:
                    issue = "; ".join(refresh.issues)
            except Exception as error:  # noqa: BLE001 - one meeting must not stop a sweep
                items.append(
                    _item(
                        descriptor,
                        "FAILURE",
                        attempted=True,
                        issue=f"{type(error).__name__}: {error}",
                    )
                )
                continue

        normalized = list_normalized_releases(store.archive, meeting_key)
        availability = store.load(
            meeting_key=meeting_key,
            target_session_key=str(descriptor.key),
            evidence_cutoff=descriptor.date_start,
            session_scope=SessionScope.RACE,
        )
        if availability.status == "PRESENT":
            status = "PRESENT"
        elif normalized and not store.releases_as_of(
            meeting_key, evidence_cutoff=descriptor.date_start
        ):
            status = "PROVENANCE_REJECTED"
        elif issue and not normalized:
            status = "FAILURE"
        else:
            status = "ABSENT"
        items.append(
            _item(
                descriptor,
                status,
                attempted=attempted,
                normalized_release_count=len(normalized),
                issue=issue,
            )
        )
    return PirelliBackfillReport(selected_years, dry_run, tuple(items))


def format_pirelli_backfill_report(report: PirelliBackfillReport) -> str:
    lines = [
        f"Pirelli Race sync seasons: {', '.join(str(year) for year in report.years)}",
        f"Selected: {report.selected}",
        f"Meetings attempted: {report.meetings_attempted}",
        f"PRESENT: {report.count('PRESENT')}",
        f"ABSENT: {report.count('ABSENT')}",
        f"Provenance-rejected: {report.count('PROVENANCE_REJECTED')}",
        f"Failures: {report.count('FAILURE')}",
    ]
    if report.dry_run:
        lines.append(f"Planned: {report.count('PLANNED')}")
    for item in report.items:
        suffix = f" · {item.issue}" if item.issue else ""
        lines.append(
            f"[{item.status}] {item.year} {item.meeting_name} "
            f"(meeting {item.meeting_key}, session {item.session_key}){suffix}"
        )
    return "\n".join(lines)


def _item(
    descriptor: object,
    status: str,
    *,
    attempted: bool,
    normalized_release_count: int = 0,
    issue: str | None = None,
) -> PirelliBackfillItem:
    return PirelliBackfillItem(
        meeting_key=str(descriptor.meeting_key),
        meeting_name=str(descriptor.meeting_name),
        year=int(descriptor.year),
        session_key=str(descriptor.key),
        status=status,
        attempted=attempted,
        normalized_release_count=normalized_release_count,
        issue=issue,
    )
