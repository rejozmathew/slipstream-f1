"""Bounded manual and quiet historical Pirelli Race backfill."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..catalog import recent_seasons
from .archive import list_normalized_releases
from .config import (
    DEFAULT_PIRELLI_HISTORY_YEARS,
    NORMALIZER_VERSION,
    validate_history_years,
)
from .contracts import SessionScope
from .coordinator import build_ingestion_target
from .discovery import FeedEntry
from .ingest import PirelliIngestionService
from .metadata import (
    metadata_descriptors,
    metadata_path,
    sync_pirelli_metadata,
)
from .store import PirelliEvidenceStore

logger = logging.getLogger(__name__)
BACKFILL_STATE_FORMAT = "slipstream.pirelli.backfill-state.v1"


def _fact_applies_to_target(
    fact: object,
    *,
    meeting_key: str,
    session_scope: SessionScope,
    target_session_key: str,
) -> bool:
    applicability = fact.applicability
    if applicability.meeting_key != meeting_key:
        return False
    if applicability.session_scope == SessionScope.WEEKEND:
        return True
    if applicability.session_scope in {SessionScope.UNKNOWN, session_scope}:
        return (
            applicability.session_scope == session_scope
            and applicability.target_session_key == target_session_key
        )
    return False


def _release_applies_to_target(
    release: object,
    *,
    meeting_key: str,
    session_scope: SessionScope,
    target_session_key: str,
) -> bool:
    facts = (
        *release.compound_selections,
        *release.strategies,
        *release.tyre_bank_snapshots,
        *release.context_facts,
    )
    return any(
        _fact_applies_to_target(
            fact,
            meeting_key=meeting_key,
            session_scope=session_scope,
            target_session_key=target_session_key,
        )
        for fact in facts
    )


def _target_releases_use_current_normalizer(
    store: PirelliEvidenceStore, descriptor: object, availability: object
) -> bool:
    """Check the cutoff-admitted releases backing this target, not the meeting."""

    if getattr(availability, "status", None) != "PRESENT":
        return False
    meeting_key = str(descriptor.meeting_key)
    if getattr(availability, "model_admissible", True):
        releases = store.releases_as_of(
            meeting_key, evidence_cutoff=descriptor.date_start
        )
    else:
        releases = store.display_releases_as_of(
            meeting_key, evidence_cutoff=descriptor.date_start
        )
    relevant = tuple(
        release
        for release in releases
        if _release_applies_to_target(
            release,
            meeting_key=meeting_key,
            session_scope=SessionScope.RACE,
            target_session_key=str(descriptor.key),
        )
    )
    return bool(relevant) and all(
        release.normalizer_version == NORMALIZER_VERSION for release in relevant
    )


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
    replay_library = library
    resource_loader = None
    if replay_library is None:
        metadata = sync_pirelli_metadata(
            metadata_path(data_root), selected_years, now=now
        )
        descriptor_values = metadata_descriptors(metadata)
    else:
        descriptor_values = tuple(replay_library.descriptors.values())
        resource_loader = (
            None if getattr(replay_library, "metadata_only", False) else replay_library.get
        )
    descriptors = {descriptor.key: descriptor for descriptor in descriptor_values}
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
    shared_feed: tuple[FeedEntry, ...] | None = None
    shared_feed_loaded = False
    items: list[PirelliBackfillItem] = []
    for meeting_key, descriptor in by_meeting.items():
        if dry_run:
            items.append(_item(descriptor, "PLANNED", attempted=False))
            continue

        existing_availability = store.load(
            meeting_key=meeting_key,
            target_session_key=str(descriptor.key),
            evidence_cutoff=descriptor.date_start,
            session_scope=SessionScope.RACE,
        )
        current_normalizer = _target_releases_use_current_normalizer(
            store, descriptor, existing_availability
        )
        attempted = (
            force
            or existing_availability.status != "PRESENT"
            or not current_normalizer
        )
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
                    resource_loader,
                )
                if (
                    not current_normalizer
                    and isinstance(ingestion, PirelliIngestionService)
                ):
                    repaired = await ingestion.renormalize_archived(target)
                    if repaired.issues:
                        issue = "; ".join(repaired.issues)
                    existing_availability = store.load(
                        meeting_key=meeting_key,
                        target_session_key=str(descriptor.key),
                        evidence_cutoff=descriptor.date_start,
                        session_scope=SessionScope.RACE,
                    )
                    current_normalizer = _target_releases_use_current_normalizer(
                        store, descriptor, existing_availability
                    )
                needs_network = (
                    force
                    or not current_normalizer
                    or existing_availability.status != "PRESENT"
                )
                if isinstance(ingestion, PirelliIngestionService):
                    if needs_network:
                        if not shared_feed_loaded:
                            try:
                                shared_feed = await ingestion.discovery_entries(
                                    now=retrieved_at
                                )
                            except Exception:  # noqa: BLE001 - per-event fallback remains
                                shared_feed = ()
                            shared_feed_loaded = True
                        refresh = await ingestion.refresh(
                            target,
                            now=retrieved_at,
                            feed_entries=shared_feed,
                        )
                    else:
                        refresh = None
                else:
                    refresh = await ingestion.refresh(target, now=retrieved_at)
                if refresh is not None and refresh.issues:
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


@dataclass(frozen=True)
class HistoricalBackfillResult:
    status: str
    meeting_key: str | None = None
    issue: str | None = None


class PirelliHistoricalCoordinator:
    """Fill at most one old meeting per low-frequency pass."""

    def __init__(
        self,
        data_root: Path,
        service: PirelliIngestionService,
        *,
        history_years: int = DEFAULT_PIRELLI_HISTORY_YEARS,
        interval: timedelta = timedelta(hours=6),
        retry_after: timedelta = timedelta(hours=24),
        metadata_sync: Any = sync_pirelli_metadata,
    ) -> None:
        self.data_root = data_root
        self.store = PirelliEvidenceStore(data_root)
        self.service = service
        self.history_years = validate_history_years(history_years)
        self.interval = interval
        self.retry_after = retry_after
        self.metadata_sync = metadata_sync
        self._lock = asyncio.Lock()
        self._priority: str | None = None
        self._priority_revision = 0
        self._wake: asyncio.Event | None = None
        self._wake_loop: asyncio.AbstractEventLoop | None = None

    def prioritize(self, meeting_key: str) -> None:
        self._priority = str(meeting_key)
        self._priority_revision += 1
        if self._wake is not None and self._wake_loop is not None:
            self._wake_loop.call_soon_threadsafe(self._wake.set)

    async def run_once(
        self,
        *,
        now: datetime | None = None,
        descriptors: tuple[object, ...] | None = None,
    ) -> HistoricalBackfillResult:
        if self._lock.locked():
            return HistoricalBackfillResult("BUSY")
        async with self._lock:
            clock = (now or datetime.now(UTC)).astimezone(UTC)
            years = tuple(recent_seasons(self.history_years, now=clock))
            if descriptors is None and _retry_pending(
                self.data_root, "__metadata__", clock
            ):
                return HistoricalBackfillResult(
                    "DEFERRED", issue="historical metadata retry is not due"
                )
            try:
                available = descriptors
                if available is None:
                    metadata = await asyncio.to_thread(
                        self.metadata_sync,
                        metadata_path(self.data_root),
                        years,
                        now=clock,
                    )
                    available = metadata_descriptors(metadata)
                selected = self._select(available, now=clock)
                if selected is None:
                    return HistoricalBackfillResult("IDLE")
                meeting_key = str(selected.meeting_key)
                priority_revision = self._priority_revision
                self._record_attempt(meeting_key, clock, status="RUNNING")
                report = await sync_pirelli_backfill(
                    self.data_root,
                    years=(int(selected.year),),
                    meeting_keys=(meeting_key,),
                    force=False,
                    now=clock,
                    library=_DescriptorLibrary(available),
                    service=self.service,
                )
                item = report.items[0] if report.items else None
                if item is None:
                    status, issue = "ABSENT", "selected meeting produced no report"
                else:
                    status, issue = item.status, item.issue
                self._record_attempt(meeting_key, clock, status=status, issue=issue)
                if (
                    self._priority == meeting_key
                    and self._priority_revision == priority_revision
                ):
                    self._priority = None
                return HistoricalBackfillResult(status, meeting_key, issue)
            except Exception as error:  # noqa: BLE001 - catch-up never blocks product
                meeting_key = (
                    str(selected.meeting_key) if "selected" in locals() and selected else None
                )
                issue = f"{type(error).__name__}: {error}"
                self._record_attempt(
                    meeting_key or "__metadata__",
                    clock,
                    status="FAILURE",
                    issue=issue,
                )
                logger.warning("Historical Pirelli catch-up failed: %s", issue)
                return HistoricalBackfillResult("FAILURE", meeting_key, issue)

    async def run_forever(
        self,
        clock: Any = lambda: datetime.now(UTC),
        *,
        initial_delay: float = 60.0,
    ) -> None:
        self._wake_loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        try:
            if initial_delay > 0:
                await asyncio.sleep(initial_delay)
            while True:
                self._wake.clear()
                await self.run_once(now=clock())
                if self._priority is None:
                    self._wake.clear()
                try:
                    await asyncio.wait_for(
                        self._wake.wait(),
                        timeout=max(self.interval.total_seconds(), 60.0),
                    )
                except TimeoutError:
                    pass
        finally:
            self._wake = None
            self._wake_loop = None

    def _select(
        self, descriptors: tuple[object, ...], *, now: datetime
    ) -> object | None:
        state = _read_backfill_state(self.data_root)
        candidates: list[object] = []
        by_meeting: dict[str, object] = {}
        for descriptor in sorted(descriptors, key=lambda item: item.date_start):
            if getattr(descriptor, "session_kind", None) != "race":
                continue
            if _as_utc(descriptor.date_end) >= now - timedelta(days=2):
                continue
            by_meeting[str(descriptor.meeting_key)] = descriptor
        for meeting_key, descriptor in by_meeting.items():
            if self._covered(descriptor):
                continue
            row = state.get("meetings", {}).get(meeting_key, {})
            retry_at = _optional_utc(row.get("nextAttemptAt"))
            if retry_at is not None and retry_at > now:
                continue
            candidates.append(descriptor)
        if self._priority is not None:
            prioritized = next(
                (
                    item
                    for item in candidates
                    if str(item.meeting_key) == self._priority
                ),
                None,
            )
            if prioritized is not None:
                return prioritized
        return candidates[0] if candidates else None

    def _covered(self, descriptor: object) -> bool:
        availability = self.store.load(
            meeting_key=str(descriptor.meeting_key),
            target_session_key=str(descriptor.key),
            evidence_cutoff=descriptor.date_start,
            session_scope=SessionScope.RACE,
        )
        return _target_releases_use_current_normalizer(
            self.store, descriptor, availability
        )

    def _record_attempt(
        self,
        meeting_key: str,
        attempted_at: datetime,
        *,
        status: str,
        issue: str | None = None,
    ) -> None:
        try:
            state = _read_backfill_state(self.data_root)
            meetings = state.setdefault("meetings", {})
            meetings[meeting_key] = {
                "lastAttemptAt": attempted_at.isoformat(),
                "nextAttemptAt": (attempted_at + self.retry_after).isoformat(),
                "status": status,
                "issue": issue,
            }
            _write_backfill_state(self.data_root, state)
        except (OSError, TypeError, ValueError) as error:
            logger.warning("Could not persist historical Pirelli retry state: %s", error)


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


class _DescriptorLibrary:
    metadata_only = True

    def __init__(self, descriptors: tuple[object, ...]) -> None:
        self.descriptors = {str(item.key): item for item in descriptors}

    def get(self, _key: str) -> None:
        return None


def _as_utc(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _optional_utc(value: object) -> datetime | None:
    if not isinstance(value, (str, datetime)):
        return None
    try:
        return _as_utc(value)
    except ValueError:
        return None


def _backfill_state_path(data_root: Path) -> Path:
    return data_root / ".slipstream" / "pirelli-backfill-state.json"


def _read_backfill_state(data_root: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            _backfill_state_path(data_root).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict) or payload.get("format") != BACKFILL_STATE_FORMAT:
        return {"format": BACKFILL_STATE_FORMAT, "meetings": {}}
    if not isinstance(payload.get("meetings"), dict):
        payload["meetings"] = {}
    return payload


def _write_backfill_state(data_root: Path, payload: dict[str, Any]) -> None:
    path = _backfill_state_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)


def _retry_pending(data_root: Path, meeting_key: str, now: datetime) -> bool:
    row = _read_backfill_state(data_root).get("meetings", {}).get(meeting_key, {})
    retry_at = _optional_utc(row.get("nextAttemptAt"))
    return retry_at is not None and retry_at > now
