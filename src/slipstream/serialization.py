"""Versioned transport serialization for canonical race state."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, replace
from typing import Any

from .events import NormalizedEvent
from .qualifying import cursor_qualifying_phase
from .session_clock import state_at_session_clock
from .state import RaceState


def state_envelope(
    state: RaceState,
    *,
    sequence: int,
    session_time: str | None = None,
    playing: bool = False,
    analytics: dict[str, Any] | None = None,
    events: Sequence[NormalizedEvent] = (),
) -> dict[str, Any]:
    clock = session_time or state.updated_at
    if events:
        state = state_at_session_clock(events, state, sequence, clock)
        state = replace(state, session=replace(
            state.session, qualifying_phase=cursor_qualifying_phase(events, state, sequence),
        ))
    envelope = {
        "v": 1,
        "seq": sequence,
        "type": "state.snapshot",
        "sessionTime": clock,
        "sourceTime": clock,
        "playback": {"playing": playing},
        "data": asdict(state),
    }
    if analytics is not None:
        envelope["analytics"] = analytics
    return envelope
