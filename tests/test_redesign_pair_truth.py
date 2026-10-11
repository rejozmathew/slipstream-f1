"""Server-owned comparison, recommendation gates and completed-stop truth."""

from dataclasses import replace

import pytest

from slipstream.analytics import (
    AnalyticsService,
    _likely_stop_count,
    battle_recommendation,
)
from slipstream.events import NormalizedEvent
from slipstream.evidence import PitEvent, SessionEvidence
from slipstream.library import ReplayResource, SessionDescriptor
from slipstream.pair_truth import pair_comparison
from slipstream.published_strategy import _actual_strategy
from slipstream.race_intelligence import field_distributions, race_read
from slipstream.state import DriverState, RaceState, SessionState
from slipstream.weekend import ContextAvailability


def race():
    return RaceState(
        session=SessionState(key="100", session_kind="race", layout_family="race",
                             status="RUNNING", display_status="GREEN", lap=3),
        drivers={
            "1": DriverState(number="1", position=1, lap=3, source_condition="RUNNING", gap_to_leader="LEADER"),
            "2": DriverState(number="2", position=2, lap=3, source_condition="RUNNING", gap_to_leader="+1.2", interval_to_ahead="+0.7"),
            "3": DriverState(number="3", position=3, lap=3, source_condition="RUNNING", gap_to_leader="+4.3", interval_to_ahead="+0.8"),
        },
    )


def recommendation(state):
    models = {number: {"pace": {"degradation": {"value": None}, "currentStintBaseline": None},
                       "strategy": {"pitWindow": {"value": None}}} for number in state.drivers}
    return battle_recommendation(list(state.drivers.values()), models, "race", state=state)


@pytest.mark.parametrize("display", ["YELLOW", "VSC", "VSC_ENDING", "SAFETY_CAR", "RED_FLAG", "UNKNOWN", "CHEQUERED"])
def test_recommendation_requires_known_green_running(display):
    state = race()
    state = replace(state, session=replace(state.session, display_status=display))
    assert recommendation(state)["recommended"] is None


@pytest.mark.parametrize("lap", [None, 0, 1, 2])
def test_recommendation_starts_at_lap_three(lap):
    state = race()
    state = replace(state, session=replace(state.session, lap=lap))
    assert recommendation(state)["candidates"] == []


def test_positive_recommendation_keeps_existing_twelve_second_scoring_policy():
    state = race()
    state = replace(state, drivers={"1": state.drivers["1"],
        "2": replace(state.drivers["2"], interval_to_ahead="+12.0")})
    assert recommendation(state)["recommended"]["gapSeconds"] == 12
    state = replace(state, drivers={**state.drivers, "2": replace(state.drivers["2"], interval_to_ahead="+12.1")})
    assert recommendation(state)["recommended"] is None


def test_pinned_nonadjacent_pair_gap_uses_only_comparable_server_facts():
    state = race()
    assert pair_comparison(state, state.drivers["1"], state.drivers["3"])["gapSeconds"] == 4.3
    assert pair_comparison(state, state.drivers["1"], state.drivers["2"])["gapSeconds"] == 0.7
    assert pair_comparison(state, state.drivers["1"], state.drivers["2"])["gapBasis"] == "interval_to_ahead"
    for changed in [replace(state.drivers["3"], lap=None), replace(state.drivers["3"], lap=2),
                    replace(state.drivers["3"], gap_to_leader="+1 LAP"),
                    replace(state.drivers["3"], gap_to_leader=None),
                    replace(state.drivers["3"], source_condition="STOPPED"),
                    replace(state.drivers["3"], activity="IN_PIT")]:
        comparison = pair_comparison(state, state.drivers["1"], changed)
        assert comparison["gapSeconds"] is None
        assert comparison["comparisonState"] == "NOT_COMPARABLE"
        assert comparison["reason"]


def test_nonadjacent_pair_does_not_sum_intervals_or_use_lapped_leader_gaps():
    state = race()
    state = replace(state, drivers={**state.drivers,
        "2": replace(state.drivers["2"], position=3, gap_to_leader="+1 LAP"),
        "3": replace(state.drivers["3"], position=5, gap_to_leader="+2 LAP")})
    assert pair_comparison(state, state.drivers["2"], state.drivers["3"])["gapSeconds"] is None
    state = replace(state, drivers={**state.drivers,
        "2": replace(state.drivers["2"], gap_to_leader="+4.7"),
        "3": replace(state.drivers["3"], gap_to_leader="+9.5")})
    result = pair_comparison(state, state.drivers["2"], state.drivers["3"])
    assert result["gapSeconds"] == 4.8
    assert result["gapBasis"] == "leader_gap_difference"


def test_nonadjacent_completed_history_is_cursor_safe_and_incremental():
    def event(kind, seconds, payload):
        return NormalizedEvent(kind, f"2026-08-23T12:00:{seconds:02d}Z", "synthetic", payload)
    events = [event("session", 0, {"key": "100", "session_kind": "race", "layout_family": "race", "status": "RUNNING", "control_status": "NORMAL", "marshal_status": "ALL_CLEAR", "lap": 3})]
    for number, position, gap in [("1", 1, "LEADER"), ("2", 2, "+0.5"), ("3", 3, "+1.3")]:
        events.append(event("driver", 1, {"number": number, "position": position, "lap": 3,
            "source_condition": "RUNNING", "gap_to_leader": gap, "interval_to_ahead": "+0.8"}))
    def lap(seconds, number):
        return event("timing", seconds, {"number": "3", "lap": number, "lap_observation": {
            "lap": number, "started_at": "2026-08-23T12:00:00Z", "duration": 90}})
    events.extend([lap(10, 3), lap(20, 4)])
    events.extend(event("timing", 25, {"number": number, "lap": 4}) for number in ["1", "2"])
    events.append(lap(30, 4))
    events = tuple(events)
    full = SessionEvidence.from_events(events)
    early = SessionEvidence.from_events(events[:5])
    assert full.completed_gap_history("1", "3", event_limit=5) == early.completed_gap_history("1", "3")
    assert [item.sequence for item in full.completed_gap_history("1", "3")] == [5, 9]
    incremental = SessionEvidence()
    state = RaceState()
    for sequence, item in enumerate(events, 1):
        state = state.apply(item)
        incremental = incremental.append(item, sequence=sequence, state=state)
    assert incremental.completed_gaps == full.completed_gaps


def test_pit_entry_does_not_count_as_completed_stop_or_invent_next_compound():
    driver = DriverState(number="1", pit_count=1, compound="MEDIUM", source_condition="IN_PIT")
    actual = _actual_strategy(driver, (), ())
    assert actual["completedStops"] == 0
    assert actual["compounds"] == ["MEDIUM"]
    assert actual["evidenceComplete"] is False
    pit = PitEvent(10, "2026-08-23T12:00:10Z", "1", 3, "MEDIUM", None, pit_lane_duration=20)
    actual = _actual_strategy(replace(driver, source_condition="RUNNING"), (), (pit,))
    assert actual["completedStops"] == 1
    assert actual["compounds"] == ["MEDIUM", None]
    assert actual["evidenceComplete"] is False


def test_completed_repeated_compound_stops_survive_stop_and_next_pit_entry():
    pits = (PitEvent(10, "2026-08-23T12:00:10Z", "1", 3, "MEDIUM", "HARD"),
            PitEvent(20, "2026-08-23T12:00:20Z", "1", 8, "HARD", "HARD"))
    driver = DriverState(number="1", pit_count=2, compound="HARD", source_condition="STOPPED")
    actual = _actual_strategy(driver, (), pits)
    assert actual["compounds"] == ["MEDIUM", "HARD", "HARD"]
    assert actual["completedStops"] == 2
    assert actual["evidenceComplete"]
    assert _actual_strategy(replace(driver, pit_count=3, source_condition="IN_PIT"), (), pits)["completedStops"] == 2


def test_race_read_counts_completed_cursor_pits_not_entry_counters():
    def event(kind, seconds, **payload):
        return NormalizedEvent(kind, f"2026-08-23T12:00:{seconds:02d}Z", "synthetic", payload)

    events = (
        event("session", 0, key="100", session_kind="race", layout_family="race",
              status="RUNNING", control_status="NORMAL", marshal_status="ALL_CLEAR", lap=3),
        event("driver", 0, number="1", position=1, source_condition="RUNNING", compound="MEDIUM"),
        event("driver", 0, number="2", position=2, source_condition="RUNNING", compound="HARD"),
        event("timing", 10, number="1", source_condition="IN_PIT", pit_count=1),
        event("timing", 20, number="1", source_condition="RUNNING", pit_observation={
            "lap": 3, "ordinal": 1, "previous_compound": "MEDIUM", "new_compound": "HARD"}),
        event("timing", 21, number="1", pit_observation={
            "lap": 3, "ordinal": 1, "pit_lane_duration": 20}),
        event("timing", 30, number="1", source_condition="IN_PIT", pit_count=2),
        event("timing", 40, number="1", source_condition="RUNNING", pit_observation={
            "lap": 4, "ordinal": 2, "previous_compound": "HARD", "new_compound": "HARD"}),
        event("timing", 50, number="1", classification="DNF"),
    )
    full = SessionEvidence.from_events(events)
    for cursor, completed in [(4, 0), (5, 1), (6, 1), (7, 1), (8, 2), (4, 0)]:
        state, prefix = SessionEvidence.reduce_events(events[:cursor])
        pits = full.pit_events_for_driver("1", event_limit=cursor)
        assert pits == prefix.pit_events_for_driver("1")
        result = race_read(state, {}, {}, pits, {}, "LIVE", field_distributions(state, {}))
        expected = {"0": 2} if not completed else {"0": 1, str(completed): 1}
        assert result["completedStopDistribution"] == expected
        assert _actual_strategy(state.drivers["1"], (), pits)["completedStops"] == completed
        if cursor == 4:
            assert state.drivers["1"].pit_count == 1
            assert result["summaryFacts"][0] == "2 of 2 running or in-pit drivers have exactly 0 completed stops."
    final_state, _ = SessionEvidence.reduce_events(events)
    result = race_read(final_state, {}, {}, full.pit_events_for_driver("1"), {}, "LIVE",
                       field_distributions(final_state, {}))
    assert result["completedStopDistribution"] == {"0": 1}


@pytest.mark.parametrize("kind,name", [("practice_2", "Practice 2"), ("race", "Race")])
def test_driver_read_matches_completed_history_before_exit_and_after_rewind(tmp_path, kind, name):
    events = (
        NormalizedEvent("session", "2026-08-23T12:00:00Z", "synthetic", {
            "key": "100", "session_kind": kind, "layout_family": "practice" if kind == "practice_2" else "race",
            "status": "RUNNING", "control_status": "NORMAL", "marshal_status": "ALL_CLEAR", "lap": 3}),
        NormalizedEvent("driver", "2026-08-23T12:00:01Z", "synthetic", {
            "number": "1", "code": "VER", "position": 1, "source_condition": "IN_PIT", "pit_count": 1}),
        NormalizedEvent("timing", "2026-08-23T12:00:20Z", "synthetic", {
            "number": "1", "source_condition": "RUNNING", "pit_observation": {
                "lap": 3, "ordinal": 1, "previous_compound": "MEDIUM", "new_compound": "HARD"}}),
    )
    final, evidence = SessionEvidence.reduce_events(events)
    descriptor = SessionDescriptor(
        key="100", year=2026, meeting_key="10", meeting_name="Test GP", session_name=name,
        session_type="Practice" if kind == "practice_2" else "Race", circuit="Ring", location="Here",
        date_start=events[0].occurred_at, date_end="2026-08-23T14:00:00Z", gmt_offset="00:00:00",
        path=tmp_path / "test.json", source="synthetic", capabilities={},
    )
    resource = ReplayResource(descriptor, events, final, evidence, True, False)
    service = AnalyticsService()
    for cursor, expected in [(2, 0), (3, 1), (2, 0)]:
        state, _ = SessionEvidence.reduce_events(events[:cursor])
        snapshot = service.snapshot(resource, state, sequence=cursor, as_of=events[cursor - 1].occurred_at,
                                    context=ContextAvailability("unavailable"))
        driver = snapshot["drivers"]["1"]
        assert state.drivers["1"].pit_count == 1
        assert len(driver["pitEvents"]) == expected
        assert f"Observed completed pit stops: {expected}." in driver["read"]["facts"]


def test_final_observed_stop_count_uses_completed_events_for_this_driver():
    state = race()
    state = replace(state, session=replace(state.session, status="FINISHED"))
    driver = replace(state.drivers["1"], pit_count=2)
    other = PitEvent(4, "2026-08-23T12:00:10Z", "2", 3)
    own = PitEvent(5, "2026-08-23T12:00:20Z", "1", 3)
    assert _likely_stop_count(driver, [], state, (other,))["value"] == 0
    assert _likely_stop_count(driver, [], state, (other, own))["value"] == 1
