"""Versioned transport serialization for canonical race state."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .state import RaceState


def state_envelope(
    state: RaceState,
    *,
    sequence: int,
    session_time: str | None = None,
    playing: bool = False,
) -> dict[str, Any]:
    clock = session_time or state.updated_at
    return {
        "v": 1,
        "seq": sequence,
        "type": "state.snapshot",
        "sessionTime": clock,
        "sourceTime": clock,
        "playback": {"playing": playing},
        "data": asdict(state),
    }
