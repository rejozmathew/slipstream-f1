"""v2.1 Phase F: Scenario 26 data-ownership contract (no cross-session leakage).

The spec §5.5 / §26 requires v2.1 to *define* the data-ownership contract that
Milestone 4 will enforce: hysteresis / stabilization state is
**target-session-owned**, session-scoped and cursor-keyed, and must NOT leak
between sessions or into viewer state. Actual Admin deletion is an M4 non-goal.

These tests pin the contract surface:

1. The analytics cache signature includes the session key (no cross-session
   collision).
2. Battle hysteresis is session-scoped: two distinct sessions never share a
   held state.
3. The snapshot publishes an explicit `dataOwnership` block (owner,
   session-scoped, cursor-keyed, M4 downstream deletion).
"""

from pathlib import Path

from slipstream.analytics import AnalyticsService, build_analytics_snapshot
from slipstream.events import NormalizedEvent
from slipstream.evidence import SessionEvidence
from slipstream.library import ReplayResource, SessionDescriptor
from slipstream.state import DriverState, RaceState, SessionState
from slipstream.weekend import ContextAvailability


def descriptor(tmp_path: Path, *, key: str, name: str) -> SessionDescriptor:
    return SessionDescriptor(
        key=key, year=2026, meeting_key=key, meeting_name=name,
        session_name="Race", session_type="Race", circuit="Ring", location="Somewhere",
        date_start="2026-08-01T14:00:00+00:00", date_end="2026-08-01T16:00:00+00:00",
        gmt_offset="00:00:00", path=tmp_path / f"{key}.json", source="test",
        capabilities={},
    )


def _resource(
    tmp_path: Path, *, key: str, name: str, drivers: dict[str, DriverState]
) -> tuple[ReplayResource, RaceState]:
    session_event = NormalizedEvent(
        kind="session", occurred_at="2026-08-01T14:00:00+00:00", source="test",
        payload={"key": key, "session_kind": "race", "layout_family": "race", "status": "STARTED"},
    )
    state = RaceState(
        session=SessionState(key=key, session_kind="race", layout_family="race", status="STARTED"),
        drivers=drivers,
    )
    resource = ReplayResource(
        descriptor(tmp_path, key=key, name=name),
        (session_event,), state,
        SessionEvidence.from_events((session_event,)), True, False,
    )
    return resource, state


def test_cache_signature_is_session_keyed(tmp_path) -> None:
    """Same factual content in two sessions must not collide in the analytics
    cache — the session key is part of the signature. §7.1 additionally
    requires the cursor (sequence) to be part of the signature so analytics
    at cursor X cannot reuse evidence fetched at cursor Y."""
    from slipstream.analytics import _signature

    drivers_a = {"1": DriverState(number="1", code="AAA", position=1, compound="MEDIUM", status="RUNNING"),
                 "2": DriverState(number="2", code="BBB", position=2, compound="HARD", status="RUNNING")}
    drivers_b = {"1": DriverState(number="1", code="AAA", position=1, compound="MEDIUM", status="RUNNING"),
                 "2": DriverState(number="2", code="BBB", position=2, compound="HARD", status="RUNNING")}
    ra, sa = _resource(tmp_path, key="300", name="Context GP A", drivers=drivers_a)
    rb, sb = _resource(tmp_path, key="301", name="Context GP B", drivers=drivers_b)
    ctx = ContextAvailability("unavailable")
    sig_a = _signature(ra, sa, ctx, sequence=50)
    sig_b = _signature(rb, sb, ctx, sequence=50)
    # Session key must be part of the signature — otherwise two sessions with
    # identical state would collide.
    assert "300" in sig_a
    assert "301" in sig_b
    assert sig_a != sig_b
    # §7.1: the cursor must be part of the signature — otherwise a cached
    # snapshot at cursor 50 would be returned for a request at cursor 60.
    sig_a_60 = _signature(ra, sa, ctx, sequence=60)
    assert sig_a != sig_a_60


def test_hysteresis_is_session_scoped_no_cross_session_leakage(tmp_path) -> None:
    """Scenario 26: hysteresis state is target-session-owned. Two distinct
    sessions with the same driver numbers must not share a held Battle
    recommendation."""
    drivers = {
        "1": DriverState(number="1", code="AAA", position=1, compound="MEDIUM", status="RUNNING"),
        "2": DriverState(number="2", code="BBB", position=2, compound="HARD", status="RUNNING", interval_to_ahead="1.2s"),
    }
    service = AnalyticsService()
    ra, sa = _resource(tmp_path, key="300", name="Context GP A", drivers=drivers)
    rb, sb = _resource(tmp_path, key="301", name="Context GP B", drivers=drivers)

    # Advance session A at a cursor where the candidate is stable.
    snap_a = service.snapshot(ra, sa, sequence=100, as_of="2026-08-01T14:00:00+00:00", context=ContextAvailability("unavailable"))
    # Advance session B at the same cursor with the same driver state.
    snap_b = service.snapshot(rb, sb, sequence=100, as_of="2026-08-01T14:00:00+00:00", context=ContextAvailability("unavailable"))

    # Both sessions must be independent — the held state is keyed by session.
    a_held = snap_a["battle"]["heldRecommendation"]
    b_held = snap_b["battle"]["heldRecommendation"]
    # Both should have a held recommendation (candidate is stable at this cursor).
    assert a_held is not None, "session A should hold a Battle recommendation"
    assert b_held is not None, "session B should hold a Battle recommendation"
    # The held states are independent objects (not the same dict reference).
    assert a_held is not b_held
    # Ownership metadata is published and correct.
    assert snap_a["battle"]["hysteresis"]["sessionScoped"] is True
    assert snap_a["battle"]["hysteresis"]["cursorKeyed"] is True
    assert snap_a["battle"]["hysteresis"]["owner"] == "server"
    assert snap_b["battle"]["hysteresis"]["sessionScoped"] is True
    assert snap_b["battle"]["hysteresis"]["owner"] == "server"


def test_snapshot_publishes_data_ownership_contract(tmp_path) -> None:
    """v2.1 §5.5 / §26: the snapshot must explicitly publish the data-ownership
    contract (owner = target session, session-scoped, cursor-keyed, M4
    downstream deletion)."""
    drivers = {"1": DriverState(number="1", code="AAA", position=1, compound="MEDIUM", status="RUNNING")}
    resource, state = _resource(tmp_path, key="300", name="Context GP", drivers=drivers)
    snap = build_analytics_snapshot(
        resource, state, sequence=1, as_of="2026-08-01T14:00:00+00:00",
        context=ContextAvailability("unavailable"),
    )
    ownership = snap["dataOwnership"]
    assert ownership["owner"] == "target_session"
    assert ownership["sessionScoped"] is True
    assert ownership["cursorKeyed"] is True
    assert ownership["sessionKey"] == "300"
    # M4 downstream deletion is a non-goal for v2.1 — the contract is defined,
    # not enforced.
    assert ownership["adminDeletion"]["status"] == "MILESTONE_4"
    assert "evidenceBasis" in ownership
