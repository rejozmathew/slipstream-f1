"""v2.1 Phase D: server-side Battle hysteresis + PaceDelta MAD scale.

Pins the deterministic, session-scoped + cursor-keyed hysteresis (no viewer
state) and the server-computed pace-delta chart scale. Mirrors the prior
client rule (20s hold, 8 score margin) but is now SERVER-owned.
"""

from pathlib import Path

from slipstream.analytics import AnalyticsService, _pace_scale
from slipstream.events import NormalizedEvent
from slipstream.evidence import SessionEvidence
from slipstream.library import ReplayResource, SessionDescriptor
from slipstream.state import DriverState, RaceState, SessionState
from slipstream.weekend import ContextAvailability


def _descriptor(tmp_path: Path) -> SessionDescriptor:
    return SessionDescriptor(
        key="300", year=2026, meeting_key="30", meeting_name="Context GP",
        session_name="Race", session_type="Race", circuit="Ring", location="Somewhere",
        date_start="2026-08-01T14:00:00+00:00", date_end="2026-08-01T16:00:00+00:00",
        gmt_offset="00:00:00", path=tmp_path / "race.json", source="test", capabilities={},
    )


def _pair(drivers: dict[str, DriverState]) -> tuple[RaceState, ReplayResource]:
    session_event = NormalizedEvent(
        kind="session", occurred_at="2026-08-01T14:00:00+00:00", source="test",
        payload={"key": "300", "session_kind": "race", "layout_family": "race", "status": "STARTED"},
    )
    state = RaceState(
        session=SessionState(key="300", session_kind="race", layout_family="race", status="STARTED"),
        drivers=drivers,
    )
    resource = ReplayResource(
        _descriptor(Path("/tmp")), (session_event,), state,
        SessionEvidence.from_events((session_event,)), True, False,
    )
    return state, resource


def _drivers() -> dict[str, DriverState]:
    return {
        "1": DriverState(number="1", code="AAA", position=1, compound="MEDIUM", tyre_age=5, lap=10, status="RUNNING"),
        "2": DriverState(number="2", code="BBB", position=2, compound="HARD", tyre_age=12, lap=10,
                        status="RUNNING", interval_to_ahead="1.500"),
    }


def test_battle_hysteresis_holds_within_window(tmp_path) -> None:
    drivers = _drivers()
    state, resource = _pair(drivers)
    service = AnalyticsService()
    context = ContextAvailability("unavailable")
    first = service.snapshot(resource, state, sequence=1, as_of="2026-08-01T14:00:00+00:00", context=context)
    # First candidate is held immediately.
    assert first["battle"]["stabilizedRecommended"] is not None
    assert first["battle"]["hysteresis"]["owner"] == "server"
    assert first["battle"]["hysteresis"]["sessionScoped"] is True
    assert first["battle"]["hysteresis"]["cursorKeyed"] is True
    # Advance 15s (< 20s hold) with the same candidate -> still held.
    second = service.snapshot(resource, state, sequence=2, as_of="2026-08-01T14:00:15+00:00", context=context)
    assert second["battle"]["stabilizedRecommended"] == first["battle"]["stabilizedRecommended"]
    assert second["battle"]["heldRecommendation"]["since"] == first["battle"]["heldRecommendation"]["since"]


def test_battle_hysteresis_resets_on_backward_seek(tmp_path) -> None:
    drivers = _drivers()
    state, resource = _pair(drivers)
    service = AnalyticsService()
    context = ContextAvailability("unavailable")
    service.snapshot(resource, state, sequence=5, as_of="2026-08-01T14:05:00+00:00", context=context)
    service.snapshot(resource, state, sequence=6, as_of="2026-08-01T14:06:00+00:00", context=context)
    # Backward seek to an earlier cursor invalidates the held state (Scenario 19 /
    # §20: no hindsight leakage; a later cursor must not leak forward).
    backward = service.snapshot(resource, state, sequence=5, as_of="2026-08-01T14:05:00+00:00", context=context)
    held = backward["battle"]["heldRecommendation"]
    # After a backward reset the held state is re-seeded from the candidate at
    # this cursor (its `since` is this cursor's time, not the forward-seek time).
    assert held is not None
    from slipstream.analytics import _as_of_ms
    assert held["since"] == _as_of_ms("2026-08-01T14:05:00+00:00")


def test_pace_scale_is_server_owned_and_deterministic() -> None:
    samples = [
        {"quality": "representative", "delta": 0.10},
        {"quality": "representative", "delta": 0.35},
        {"quality": "representative", "delta": 0.55},
        {"quality": "contaminated", "delta": 9.0},  # excluded
    ]
    scale = _pace_scale(samples)
    # Deterministic, bounded by the robust (MAD-retained) max; floor 0.25s.
    assert scale >= 0.25
    assert scale <= 0.55
    # Same input -> same output (pure).
    assert scale == _pace_scale(list(samples))
    # Floor on empty.
    assert _pace_scale([]) == 0.25
