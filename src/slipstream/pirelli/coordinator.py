"""Application-owned sparse Pirelli refresh coordinator."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from .contracts import WeekendDriverIdentity
from .discovery import MeetingDiscoveryTarget
from .ingest import PirelliIngestionService, PirelliIngestionTarget
from .schedule import startup_refresh_due


class PirelliRuntimeCoordinator:
    """Own one low-frequency refresh loop outside browser request handling."""

    def __init__(self, service: PirelliIngestionService) -> None:
        self.service = service
        self._attempted_at: dict[str, datetime] = {}

    async def refresh_relevant(
        self,
        descriptors: dict[str, object],
        *,
        default_key: str,
        resource_loader: Callable[[str], object],
        now: datetime,
    ) -> None:
        races = [
            item
            for item in descriptors.values()
            if getattr(item, "session_kind", None) in {"race", "sprint"}
        ]
        near = [
            item
            for item in races
            if -timedelta(days=2)
            <= _as_utc(item.date_start) - _as_utc(now)
            <= timedelta(days=8)
        ]
        default = descriptors.get(default_key)
        if default is not None and getattr(default, "session_kind", None) in {
            "race",
            "sprint",
        }:
            near.append(default)
        by_meeting = {str(item.meeting_key): item for item in near}
        for descriptor in list(by_meeting.values())[:2]:
            meeting_key = str(descriptor.meeting_key)
            last_attempt = self._attempted_at.get(meeting_key)
            archived = self.service.archive.list_versions(meeting_key)
            last_archive = max((item.retrieved_at for item in archived), default=None)
            last_refresh = max(
                (item for item in (last_attempt, last_archive) if item is not None),
                default=None,
            )
            if not startup_refresh_due(now=now, last_refresh_at=last_refresh):
                continue
            self._attempted_at[meeting_key] = _as_utc(now)
            inventory = sorted(
                (
                    item
                    for item in descriptors.values()
                    if str(item.meeting_key) == meeting_key
                ),
                key=lambda item: item.date_start,
            )
            resource = resource_loader(str(descriptor.key))
            drivers = tuple(
                WeekendDriverIdentity(
                    driver_number=driver.number,
                    driver_code=driver.code or driver.number,
                    full_name=driver.name or driver.code or driver.number,
                    aliases=tuple(
                        value
                        for value in (driver.code, driver.name)
                        if value is not None
                    ),
                )
                for driver in resource.final_state.drivers.values()
            )
            target = PirelliIngestionTarget(
                MeetingDiscoveryTarget(
                    meeting_key=meeting_key,
                    canonical_name=str(descriptor.meeting_name),
                    season=int(descriptor.year),
                    weekend_start=_as_utc(inventory[0].date_start),
                    weekend_end=_as_utc(inventory[-1].date_end),
                    aliases=tuple(
                        dict.fromkeys(
                            value
                            for value in (
                                getattr(descriptor, "location", None),
                                getattr(descriptor, "circuit", None),
                            )
                            if value
                        )
                    ),
                ),
                target_session_key=str(descriptor.key),
                drivers=drivers,
            )
            await self.service.refresh(target, now=_as_utc(now))

    async def run_forever(
        self,
        descriptors: Callable[[], dict[str, object]],
        default_key: Callable[[], str],
        resource_loader: Callable[[str], object],
        clock: Callable[[], datetime],
    ) -> None:
        while True:
            try:
                await self.refresh_relevant(
                    descriptors(),
                    default_key=default_key(),
                    resource_loader=resource_loader,
                    now=clock(),
                )
            except Exception:  # noqa: BLE001, S110 - optional context never stops replay
                pass
            await asyncio.sleep(30 * 60)


def _as_utc(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
