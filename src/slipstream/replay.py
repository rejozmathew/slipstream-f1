"""Deterministic replay loading."""

import json
from pathlib import Path

from .events import NormalizedEvent, parse_timestamp
from .state import RaceState


def load_events(path: Path) -> list[NormalizedEvent]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [NormalizedEvent.from_mapping(item) for item in raw]
    from .adapters.openf1 import is_openf1_recording, recording_to_events

    if is_openf1_recording(raw):
        return recording_to_events(raw)
    raise ValueError(
        "Replay must contain normalized events or a supported source recording"
    )


def replay(
    events: list[NormalizedEvent],
    *,
    at: str | None = None,
    event_limit: int | None = None,
) -> RaceState:
    if at is not None and event_limit is not None:
        raise ValueError("Replay accepts either at or event_limit, not both")
    selected = events
    if at is not None:
        cutoff = parse_timestamp(at)
        selected = [
            event for event in selected if parse_timestamp(event.occurred_at) <= cutoff
        ]
    if event_limit is not None:
        if event_limit < 1:
            raise ValueError("event_limit must be at least 1")
        selected = selected[:event_limit]
    state = RaceState()
    for event in selected:
        state = state.apply(event)
    return state
