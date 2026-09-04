"""Source-backed remaining time at a viewer's inclusive event cursor."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace

from .events import NormalizedEvent, parse_timestamp
from .state import RaceState


def extrapolate_clock(
    clock: str | None,
    *,
    running: bool | None,
    observed_at: str | None,
    as_of: str | None,
    preserve_fraction: bool = False,
) -> str | None:
    if not isinstance(clock, str) or not re.fullmatch(
        r"\d{2}:[0-5]\d:[0-5]\d(?:\.\d+)?", clock
    ):
        return None
    hours, minutes, seconds = (float(part) for part in clock.split(":"))
    remaining = hours * 3600 + minutes * 60 + seconds
    if running and observed_at and as_of:
        try:
            remaining -= max(
                0,
                (parse_timestamp(as_of) - parse_timestamp(observed_at)).total_seconds(),
            )
        except (ValueError, TypeError):
            return None
    remaining = max(0.0, remaining)
    seconds_text = (
        f"{remaining % 60:09.6f}".rstrip("0").rstrip(".")
        if preserve_fraction
        else f"{int(remaining) % 60:02d}"
    )
    return (
        f"{int(remaining) // 3600:02d}:{int(remaining) % 3600 // 60:02d}:{seconds_text}"
    )


def cursor_session_clock(
    events: Sequence[NormalizedEvent],
    state: RaceState,
    sequence: int,
    as_of: str | None = None,
) -> str | None:
    limit = min(max(sequence, 0), len(events))
    observation = next(
        (
            events[index]
            for index in range(limit - 1, -1, -1)
            if events[index].kind == "session"
            and "session_clock" in events[index].payload
        ),
        None,
    )
    return extrapolate_clock(
        observation.payload["session_clock"]
        if observation
        else state.session.session_clock,
        running=state.session.session_clock_running,
        observed_at=observation.occurred_at if observation else None,
        as_of=as_of or (events[limit - 1].occurred_at if limit else None),
    )


def state_at_session_clock(
    events: Sequence[NormalizedEvent],
    state: RaceState,
    sequence: int,
    as_of: str | None = None,
) -> RaceState:
    return replace(
        state,
        session=replace(
            state.session,
            session_clock=cursor_session_clock(
                events,
                state,
                sequence,
                as_of,
            ),
        ),
    )
