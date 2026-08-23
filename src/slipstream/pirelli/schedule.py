"""Low-frequency session-aware acquisition scheduling policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class RefreshTrigger:
    at: datetime
    reason: str


@dataclass(frozen=True)
class RefreshPolicy:
    startup_stale_after: timedelta = timedelta(hours=12)
    pre_weekend_interval: timedelta = timedelta(hours=24)
    after_session_delay: timedelta = timedelta(hours=1)
    race_morning_lead: timedelta = timedelta(hours=6)
    final_pre_race_lead: timedelta = timedelta(minutes=75)
    post_race_delay: timedelta = timedelta(hours=2)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def startup_refresh_due(
    *,
    now: datetime,
    last_refresh_at: datetime | None,
    policy: RefreshPolicy = RefreshPolicy(),  # noqa: B008
) -> bool:
    if last_refresh_at is None:
        return True
    return _aware(now) - _aware(last_refresh_at) >= policy.startup_stale_after


def pre_weekend_refresh_due(
    *,
    now: datetime,
    weekend_start: datetime,
    last_refresh_at: datetime | None,
    policy: RefreshPolicy = RefreshPolicy(),  # noqa: B008
) -> bool:
    """Occasional refresh in the week leading into a meeting; never page-driven."""
    now = _aware(now)
    start = _aware(weekend_start)
    if not timedelta(0) < start - now <= timedelta(days=7):
        return False
    if last_refresh_at is None:
        return True
    return now - _aware(last_refresh_at) >= policy.pre_weekend_interval


def planned_weekend_triggers(
    *,
    session_ends: tuple[tuple[str, datetime], ...],
    race_start: datetime | None,
    race_end: datetime | None,
    policy: RefreshPolicy = RefreshPolicy(),  # noqa: B008
) -> tuple[RefreshTrigger, ...]:
    triggers = [
        RefreshTrigger(_aware(end) + policy.after_session_delay, f"post_session:{kind}")
        for kind, end in session_ends
    ]
    if race_start:
        race_start = _aware(race_start)
        triggers += [
            RefreshTrigger(race_start - policy.race_morning_lead, "race_morning"),
            RefreshTrigger(race_start - policy.final_pre_race_lead, "final_pre_race"),
        ]
    if race_end:
        triggers.append(
            RefreshTrigger(
                _aware(race_end) + policy.post_race_delay, "post_race_archive"
            )
        )
    return tuple(
        sorted(
            {(item.at, item.reason): item for item in triggers}.values(),
            key=lambda item: item.at,
        )
    )
