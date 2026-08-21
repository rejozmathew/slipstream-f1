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
    analytics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clock = session_time or state.updated_at
    state_dict = asdict(state)
    from .lifecycle import display_status_label
    for number, driver_dict in state_dict["drivers"].items():
        driver = state.drivers[number]
        driver_dict["display_status"] = display_status_label(driver)
    
    envelope = {
        "v": 1,
        "seq": sequence,
        "type": "state.snapshot",
        "sessionTime": clock,
        "sourceTime": clock,
        "playback": {"playing": playing},
        "data": state_dict,
    }
    if analytics is not None:
        envelope["analytics"] = analytics
    return envelope
