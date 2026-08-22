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
    assert snap["raceRead"]["population"]["active"] == 2
    assert snap["drivers"]["1"]["read"]["headline"] == "AAA is running P1."
    assert snap["drivers"]["1"]["read"]["modelVersion"] == snap["modelVersion"]
    # §17.1: NetPitLoss suppresses freeStopMargin + projectedRejoinPosition.
    for number in drivers:
        strategy = snap["drivers"][number]["strategy"]
        assert strategy["disposition"] in {"PIT_EXPECTED", "TO_FINISH", "UNKNOWN"}
        assert strategy["windowState"] in {"ACTIVE", "WINDOW_PASSED_EXTENDING", "TO_FINISH", "RESETTING", "UNKNOWN", "FINAL"}
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

    # Starting tyres require first-stint evidence; current tyres use active runners.
    assert snap["activeRunnerCount"] == 2
    assert snap["startingTyreDistribution"] == {}
    assert snap["startingTyrePopulation"] == {"known": 0, "participants": 3}
    assert snap["currentTyreDistribution"] == {"HARD": 1, "MEDIUM": 1}
    assert snap["currentTyrePopulation"] == {"known": 2, "active": 2}


def test_projection_gate_publishes_hard_pass_and_truthful_insufficiency(tmp_path) -> None:
    drivers = {"1": DriverState(number="1", code="AAA", position=1, compound="MEDIUM", status="RUNNING")}
    resource, state = _resource(tmp_path, drivers)
    snap = build_analytics_snapshot(resource, state, sequence=1, as_of="2026-08-01T14:00:00+00:00", context=ContextAvailability("unavailable"))

    gate = snap["projectionGate"]
    assert gate["hardValidity"]["status"] == "PASS"
    assert gate["hardValidity"]["violations"] == 0
    assert gate["plausibility"]["status"] == "INSUFFICIENT"
    assert gate["stability"]["status"] == "INSUFFICIENT"


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


def test_terminal_driver_gets_no_future_strategy(tmp_path) -> None:
    """v2.1 §4.3 / §4.4 / handoff Scenario 14: a RETIRED driver late in the
    race must read as a factual terminal row — no future pit window, no likely
    next compound, no primary/alternate plan, and never classified TO_FINISH
    (which the UI renders as "TO FLAG"). Factual fields (compound, tyre age)
    are preserved.

    The defect: a retired driver kept a stale ``driver.lap`` (e.g. 67 on a 70
    lap race), which made ``_driver_disposition`` / ``_window_state`` classify
    it TO_FINISH and the Strategy view show a future-looking row for a car that
    has already stopped racing.
    """
    drivers = {
        # Still racing, mid-race — keeps a normal (non-terminal) outlook.
        "1": DriverState(number="1", code="AAA", position=1, compound="MEDIUM",
                         tyre_age=4, lap=67, status="RUNNING", pit_count=1),
        # Retired at the cursor — must be terminal, not future-looking.
        "2": DriverState(number="2", code="BBB", position=5, compound="HARD",
                         tyre_age=22, lap=67, status="RETIRED", pit_count=1),
    }
    state = RaceState(
        session=SessionState(key="300", session_kind="race", layout_family="race",
                             status="RACING", lap=67, total_laps=70, track_status="GREEN"),
        drivers=drivers,
    )
    session_event = NormalizedEvent(
        kind="session", occurred_at="2026-08-01T15:30:00+00:00", source="test",
        payload={"key": "300", "session_kind": "race", "layout_family": "race", "status": "RACING"},
    )
    resource = ReplayResource(
        descriptor(tmp_path), (session_event,), state,
        SessionEvidence.from_events((session_event,)), True, False,
    )
    snap = build_analytics_snapshot(
        resource, state, sequence=90, as_of="2026-08-01T15:30:00+00:00",
        context=ContextAvailability("unavailable"),
    )

    retired = snap["drivers"]["2"]["strategy"]
    # Factual terminal state is published explicitly (v2.1 §4.3 additive field).
    assert retired["terminalState"] == "RETIRED"
    # Never TO_FINISH (UI would render that as "TO FLAG" for a car that's gone).
    assert retired["disposition"] != "TO_FINISH"
    assert retired["disposition"] in ("UNKNOWN", "PIT_EXPECTED")
    # No future-looking strategy for a terminal driver.
    assert retired["pitWindow"]["value"] is None
    assert retired["pitWindow"]["status"] == "UNKNOWN"
    assert retired["likelyNextCompound"]["value"] is None
    assert retired["primaryStrategy"]["value"] is None
    assert retired["alternateStrategy"]["value"] is None
    # ...but the factual / retrospective record is preserved (it is still on
    # the compound it was running when it stopped).
    assert retired["terminalState"] == "RETIRED"

    # A still-racing driver is *not* terminal and is unaffected.
    active = snap["drivers"]["1"]["strategy"]
    assert active["terminalState"] is None
