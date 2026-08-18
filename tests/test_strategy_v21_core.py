"""v2.1 Phase C: strategy-core behavior pins (disposition, windowState, validity,
NetPitLoss suppression, field distributions, projection gate)."""

from pathlib import Path

from slipstream.analytics import build_analytics_snapshot
from slipstream.events import NormalizedEvent
from slipstream.evidence import SessionEvidence
from slipstream.library import ReplayResource, SessionDescriptor
from slipstream.state import DriverState, RaceState, SessionState
from slipstream.weekend import ContextAvailability


def descriptor(tmp_path: Path, *, kind: str = "Race") -> SessionDescriptor:
    return SessionDescriptor(
        key="300", year=2026, meeting_key="30", meeting_name="Context GP",
        session_name=kind, session_type="Race", circuit="Ring", location="Somewhere",
        date_start="2026-08-01T14:00:00+00:00", date_end="2026-08-01T16:00:00+00:00",
        gmt_offset="00:00:00", path=tmp_path / "race.json", source="test",
        capabilities={},
    )


def _resource(tmp_path, drivers: dict[str, DriverState]) -> tuple[ReplayResource, RaceState]:
    session_event = NormalizedEvent(
        kind="session", occurred_at="2026-08-01T14:00:00+00:00", source="test",
        payload={"key": "300", "session_kind": "race", "layout_family": "race", "status": "STARTED"},
    )
    state = RaceState(
        session=SessionState(key="300", session_kind="race", layout_family="race", status="STARTED"),
        drivers=drivers,
    )
    resource = ReplayResource(
        descriptor(tmp_path), (session_event,), state,
        SessionEvidence.from_events((session_event,)), True, False,
    )
    return resource, state


def test_snapshot_publishes_phase_c_contract_fields(tmp_path) -> None:
    drivers = {
        "1": DriverState(number="1", code="AAA", position=1, compound="MEDIUM", tyre_age=5, lap=10, status="RUNNING"),
        "2": DriverState(number="2", code="BBB", position=2, compound="HARD", tyre_age=12, lap=10, status="RUNNING"),
    }
    resource, state = _resource(tmp_path, drivers)
    snap = build_analytics_snapshot(resource, state, sequence=1, as_of="2026-08-01T14:00:00+00:00", context=ContextAvailability("unavailable"))

    # Race-level v2.1 fields (Phase C computed, not placeholders).
    assert snap["strategyValidity"] in {"VALID", "UNAVAILABLE", "NOT_APPLICABLE"}
    assert snap["projectionGate"]["hardValidity"]["violations"] == 0
    assert snap["projectionGate"]["hardValidity"]["status"] == "PASS"
    assert snap["activeRunnerCount"] == 2
    assert "startingTyreDistribution" in snap
    assert "stopDistribution" in snap
    assert "observedSequences" in snap
    # §17.1: NetPitLoss suppresses freeStopMargin + projectedRejoinPosition.
    for number in drivers:
        strategy = snap["drivers"][number]["strategy"]
        assert strategy["disposition"] in {"CONTINUE", "STOP_NOW", "STOP_WINDOW_OPEN", "STOP_WINDOW_CLOSED", "UNKNOWN"}
        assert strategy["windowState"] in {"OPEN", "CLOSED", "UNKNOWN"}
        assert strategy["dryTyreRequirement"] in {"UNSATISFIED", "SATISFIED", "NOT_APPLICABLE", "UNKNOWN"}
        # Suppressed until NetPitLoss exists.
        assert strategy["freeStopMargin"]["value"] is None
        assert strategy["freeStopMargin"]["status"] == "UNKNOWN"
        assert strategy["projectedRejoinPosition"]["value"] is None
        assert strategy["projectedRejoinPosition"]["status"] == "UNKNOWN"
        # §17: undercut downgraded to descriptive (FAVOURABLE/NEUTRAL/UNFAVOURABLE or UNKNOWN).
        assert strategy["undercutStrength"]["value"] in {"FAVOURABLE", "NEUTRAL", "UNFAVOURABLE", None}


def test_field_distributions_excludes_retired_runners(tmp_path) -> None:
    drivers = {
        "1": DriverState(number="1", code="AAA", position=1, compound="MEDIUM", status="RUNNING"),
        "2": DriverState(number="2", code="BBB", position=2, compound="HARD", status="RUNNING"),
        "3": DriverState(number="3", code="CCC", position=3, compound="SOFT", status="RETIRED"),
    }
    resource, state = _resource(tmp_path, drivers)
    snap = build_analytics_snapshot(resource, state, sequence=1, as_of="2026-08-01T14:00:00+00:00", context=ContextAvailability("unavailable"))

    # Retired driver excluded from active-runner field distributions.
    assert snap["activeRunnerCount"] == 2
    dist = snap["startingTyreDistribution"]
    assert dist.get("MEDIUM") == 1
    assert dist.get("HARD") == 1
    assert dist.get("SOFT") is None


def test_projection_gate_publishes_hard_pass_and_not_modelled(tmp_path) -> None:
    drivers = {"1": DriverState(number="1", code="AAA", position=1, compound="MEDIUM", status="RUNNING")}
    resource, state = _resource(tmp_path, drivers)
    snap = build_analytics_snapshot(resource, state, sequence=1, as_of="2026-08-01T14:00:00+00:00", context=ContextAvailability("unavailable"))

    gate = snap["projectionGate"]
    assert gate["hardValidity"]["status"] == "PASS"
    assert gate["hardValidity"]["violations"] == 0
    assert gate["plausibility"]["status"] == "NOT_MODELLED"
    assert gate["stability"]["status"] == "NOT_MODELLED"


def test_sprint_pit_lanes_excluded_from_race_pit_loss(tmp_path) -> None:
    from slipstream.analytics import _pit_loss_metric
    from slipstream.evidence import PitEvent

    context = {
        "meeting_key": "30",
        "sessions": [
            {"meeting_key": "30", "session_kind": "sprint",
             "lap_observations": [{"pit_lane_duration": 85.0}, {"pit_lane_duration": 90.0}]},
            {"meeting_key": "30", "session_kind": "practice_2",
             "lap_observations": [{"pit_lane_duration": 219.0}]},
        ],
    }
    race_events = (
        PitEvent(1, "2026-08-01T14:00:00Z", "1", 20, pit_lane_duration=21.0),
        PitEvent(2, "2026-08-01T14:01:00Z", "2", 21, pit_lane_duration=22.0),
    )
    observed = _pit_loss_metric(race_events, context, session_kind="race")
    assert observed["value"] == 21.5
    assert all("85" not in item and "219" not in item for item in observed["evidenceBasis"])
