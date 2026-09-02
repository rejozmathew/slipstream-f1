"""Application-owned sparse Pirelli refresh coordinator."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from .contracts import SessionScope, WeekendDriverIdentity
from .discovery import MeetingDiscoveryTarget, pirelli_event_tag
from .ingest import PirelliIngestionService, PirelliIngestionTarget
from .schedule import scheduled_refresh_reason

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PirelliRefreshState:
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_reason: str | None = None
    last_error: str | None = None


class PirelliRuntimeCoordinator:
    """Own one low-frequency refresh loop outside browser request handling."""

    def __init__(self, service: PirelliIngestionService) -> None:
        self.service = service
        self._states: dict[str, PirelliRefreshState] = {}

    @property
    def states(self) -> dict[str, PirelliRefreshState]:
        return dict(self._states)

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
        if (
            default is not None
            and getattr(default, "session_kind", None) in {"race", "sprint"}
            and -timedelta(days=2)
            <= _as_utc(default.date_start) - _as_utc(now)
            <= timedelta(days=8)
        ):
            near.append(default)
        by_meeting: dict[str, list[object]] = {}
        for item in near:
            targets = by_meeting.setdefault(str(item.meeting_key), [])
            if not any(str(existing.key) == str(item.key) for existing in targets):
                targets.append(item)
        for meeting_key, meeting_targets in list(by_meeting.items())[:2]:
            inventory = sorted(
                (
                    item
                    for item in descriptors.values()
                    if str(item.meeting_key) == meeting_key
                ),
                key=lambda item: item.date_start,
            )
            race = next(
                (item for item in inventory if item.session_kind == "race"), None
            )
            state = self._states.get(meeting_key, PirelliRefreshState())
            reason = scheduled_refresh_reason(
                now=_as_utc(now),
                weekend_start=_as_utc(inventory[0].date_start),
                weekend_end=_as_utc(inventory[-1].date_end),
                session_ends=tuple(
                    (str(item.session_kind), _as_utc(item.date_end))
                    for item in inventory
                ),
                race_start=_as_utc(race.date_start) if race is not None else None,
                race_end=_as_utc(race.date_end) if race is not None else None,
                last_success_at=state.last_success_at,
                last_attempt_at=state.last_attempt_at,
                last_error=state.last_error,
            )
            if reason is None:
                continue
            attempted = _as_utc(now)
            self._states[meeting_key] = replace(
                state, last_attempt_at=attempted, last_reason=reason
            )
            await self._refresh_meeting(
                meeting_key,
                meeting_targets,
                inventory,
                resource_loader,
                attempted,
                reason,
            )

    async def _refresh_meeting(
        self,
        meeting_key: str,
        meeting_targets: list[object],
        inventory: list[object],
        resource_loader: Callable[[str], object],
        attempted: datetime,
        reason: str,
    ) -> None:
        issues: list[str] = []
        try:
            for descriptor in sorted(meeting_targets, key=lambda item: item.date_start):
                target = self._target(
                    meeting_key, descriptor, inventory, resource_loader
                )
                report = await self.service.refresh(target, now=attempted)
                issues.extend(report.issues)
            if issues:
                raise RuntimeError("; ".join(issues))
        except Exception as error:  # noqa: BLE001 - observable state is retried
            message = f"{type(error).__name__}: {error}"
            self._states[meeting_key] = replace(
                self._states[meeting_key], last_error=message
            )
            logger.warning(
                "Pirelli refresh failed for meeting %s (%s): %s",
                meeting_key,
                reason,
                message,
            )
            return
        self._states[meeting_key] = replace(
            self._states[meeting_key], last_success_at=attempted, last_error=None
        )
        logger.info(
            "Pirelli refresh completed for meeting %s (%s)", meeting_key, reason
        )

    def _target(
        self,
        meeting_key: str,
        descriptor: object,
        inventory: list[object],
        resource_loader: Callable[[str], object],
    ) -> PirelliIngestionTarget:
        return build_ingestion_target(
            meeting_key,
            descriptor,
            inventory,
            resource_loader,
        )

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
            except Exception:
                logger.exception("Unexpected Pirelli coordinator failure")
            await asyncio.sleep(30 * 60)


def _as_utc(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def build_ingestion_target(
    meeting_key: str,
    descriptor: object,
    inventory: list[object],
    resource_loader: Callable[[str], object] | None,
) -> PirelliIngestionTarget:
    """Build the shared runtime/manual ingestion target for one session."""

    drivers: tuple[WeekendDriverIdentity, ...] = ()
    if resource_loader is not None:
        resource = resource_loader(str(descriptor.key))
        drivers = tuple(
            WeekendDriverIdentity(
                driver_number=driver.number,
                driver_code=driver.code or driver.number,
                full_name=driver.name or driver.code or driver.number,
                aliases=tuple(
                    value for value in (driver.code, driver.name) if value is not None
                ),
            )
            for driver in resource.final_state.drivers.values()
        )
    event_tag = pirelli_event_tag(
        int(descriptor.year), str(descriptor.meeting_name)
    )
    country = getattr(descriptor, "country", None)
    country_tag = (
        pirelli_event_tag(int(descriptor.year), f"{country} Grand Prix")
        if country
        else None
    )
    return PirelliIngestionTarget(
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
            exact_tag=event_tag,
            tag_aliases=(country_tag,)
            if country_tag is not None and country_tag != event_tag
            else (),
        ),
        target_session_key=str(descriptor.key),
        session_scope=(
            SessionScope.SPRINT
            if descriptor.session_kind == "sprint"
            else SessionScope.RACE
        ),
        drivers=drivers,
    )
