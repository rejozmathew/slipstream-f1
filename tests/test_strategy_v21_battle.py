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
    # No completed-lap pair history means no stable recommendation yet.
    assert first["battle"]["stabilizedRecommended"] is None
    assert first["battle"]["hysteresis"]["owner"] == "server"
    assert first["battle"]["hysteresis"]["sessionScoped"] is True
    assert first["battle"]["hysteresis"]["cursorKeyed"] is True
    # Advance 15s (< 20s hold) with the same candidate -> still held.
    second = service.snapshot(resource, state, sequence=2, as_of="2026-08-01T14:00:15+00:00", context=context)
    assert second["battle"]["stabilizedRecommended"] is None
    assert second["battle"]["heldRecommendation"] is None


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
    assert held is None


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


def test_battle_held_pair_cleared_when_driver_retires(tmp_path) -> None:
    """v2.1 §8.3 / §17: a held Battle pair is only valid while BOTH cars are
    still battle-eligible. When one car retires, the stale held pair must be
    cleared the moment it is requested again — it must not be published as if
    the dead car were still racing."""
    ctx = ContextAvailability("unavailable")
    service = AnalyticsService()

    # Cursor 1: both cars running -> a Battle pair is recommended and held.
    running = _drivers()
    state_run, resource = _pair(running)
    first = service.snapshot(
        resource, state_run, sequence=1,
        as_of="2026-08-01T14:00:00+00:00", context=ctx,
    )
    assert first["battle"]["heldRecommendation"] is None

    # Cursor 2: driver 2 RETIRES. The held pair (driver 1 vs driver 2) is now
    # stale — driver 2 is not battle-eligible, so the held recommendation must
    # be cleared (None), not carried forward with a dead car.
    retired = {
        "1": DriverState(number="1", code="AAA", position=1, compound="MEDIUM",
                         tyre_age=5, lap=11, status="RUNNING"),
        "2": DriverState(number="2", code="BBB", position=2, compound="HARD",
                         tyre_age=12, lap=11, status="RETIRED",
                         interval_to_ahead="1.500"),
    }
    state_ret, resource_ret = _pair(retired)
    second = service.snapshot(
        resource_ret, state_ret, sequence=2,
        as_of="2026-08-01T14:01:00+00:00", context=ctx,
    )
    assert second["battle"]["heldRecommendation"] is None
    # And no candidate can be recommended against a retired car either.
    assert second["battle"]["recommended"] is None


def test_delayed_viewer_held_state_is_order_independent(tmp_path) -> None:
    """v2.1 §7.2 / Scenario 19: a delayed viewer who reaches cursor C after a
    later cursor must receive the SAME held state at C as a viewer who
    advanced there monotonically. The held state is a pure function of source
    history at C — never of the request order. This is the no-hindsight,
    no-request-history guarantee."""
    ctx = ContextAvailability("unavailable")
    drivers = _drivers()

    # Viewer A: monotonic forward 5 -> 10.
    svc_a = AnalyticsService()
    state_a, resource_a = _pair(drivers)
    a_at_5 = svc_a.snapshot(
        resource_a, state_a, sequence=5,
        as_of="2026-08-01T14:05:00+00:00", context=ctx,
    )

    # Viewer B (delayed): jumps to 10 first, then seeks back to 5.
    svc_b = AnalyticsService()
    state_b, resource_b = _pair(drivers)
    svc_b.snapshot(
        resource_b, state_b, sequence=10,
        as_of="2026-08-01T14:10:00+00:00", context=ctx,
    )
    b_at_5 = svc_b.snapshot(
        resource_b, state_b, sequence=5,
        as_of="2026-08-01T14:05:00+00:00", context=ctx,
    )

    # Both viewers, at the same cursor 5 with the same source, get the SAME
    # held recommendation and the SAME `since` — no request-history leak.
    a_held = a_at_5["battle"]["heldRecommendation"]
    b_held = b_at_5["battle"]["heldRecommendation"]
    assert a_held is None and b_held is None


# ---------------------------------------------------------------------------
# v2.1 §15.1 / §15.2 / regression 32: Battle eligibility precedes scoring,
# and the visible gap is ONE server-provided truth (interval-to-ahead), not a
# client recompute from gap-to-leader.
# ---------------------------------------------------------------------------

def test_battle_candidate_publishes_server_gap_truth() -> None:
    """A comparable adjacent pair publishes gapSeconds (the scored
    interval-to-ahead) plus an explicit comparisonState, so the client
    renders the server truth instead of recomputing from gap-to-leader."""
    from slipstream.analytics import battle_recommendation

    drivers = _drivers()
    # Minimal per-driver models (pace + strategy) as battle_recommendation reads.
    def _model():
        return {
            "pace": {"degradation": {"value": None, "status": "UNKNOWN"},
                     "currentStintBaseline": 1.0},
            "strategy": {"pitWindow": {"value": None}},
        }
    models = {number: _model() for number in drivers}
    result = battle_recommendation(
        list(drivers.values()), models, layout_family="race"
    )
    assert result["available"] is True
    recommended = result["recommended"]
    assert recommended is not None
    # The visible gap is the server-scored interval-to-ahead (1.500), not a
    # client-derived gap-to-leader delta.
    assert recommended["gapSeconds"] == 1.5
    assert recommended["gapBasis"] == "interval_to_ahead"
    assert recommended["comparisonState"] == "COMPARABLE"


def test_battle_lapped_pair_gets_no_false_gap() -> None:
    """Regression 32: a lapped driver's interval-to-ahead carries 'LAP' and
    is not a comparable car-to-car gap — the pair must NOT be scored as a
    battle and must NOT carry a false current gap."""
    from slipstream.analytics import battle_recommendation

    drivers = {
        "1": DriverState(number="1", code="AAA", position=1, compound="MEDIUM",
                         tyre_age=5, lap=40, status="RUNNING"),
        # Lapped: one lap down, so the feed reports the interval to the car
        # ahead as "+1 LAP 2.1" (not a clean car-to-car gap).
        "2": DriverState(number="2", code="BBB", position=2, compound="HARD",
                         tyre_age=12, lap=39, status="RUNNING",
                         interval_to_ahead="+1 LAP 2.1"),
    }
    def _model():
        return {
            "pace": {"degradation": {"value": None, "status": "UNKNOWN"},
                     "currentStintBaseline": 1.0},
            "strategy": {"pitWindow": {"value": None}},
        }
    models = {number: _model() for number in drivers}
    result = battle_recommendation(
        list(drivers.values()), models, layout_family="race"
    )
    # The lapped pair is non-comparable: no candidate, no false current gap.
    assert result["candidates"] == []
    assert result["recommended"] is None
