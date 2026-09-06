"""Post-race presentation and suspension capture regressions."""

from dataclasses import replace

import pytest

from slipstream.analytics import _driver_read
from slipstream.events import parse_timestamp
from slipstream.evidence import SessionEvidence
from slipstream.live import F1LiveAdapter
from slipstream.published_strategy import _actual_strategy
from slipstream.state import DriverState


@pytest.mark.parametrize(
    "position,headline", [(2, "RUS finished P2."), (None, "RUS finished.")]
)
def test_finished_driver_read_uses_available_classification(position, headline):
    model = {
        "strategy": {
            "finishAssessment": {"canFinish": True},
            "projectionGate": {"publishAllowed": False},
        }
    }
    driver = DriverState(
        number="63", code="RUS", position=position, classification="FINISHED"
    )
    read = _driver_read(driver, model)
    assert read["headline"] == headline
    assert not any(
        "flag" in fact or "projection" in fact or "terminal" in fact
        for fact in read["facts"]
    )


@pytest.mark.parametrize("status", ["RUNNING", "STOPPED", "DNF", "DNS", "DSQ"])
def test_other_driver_states_are_not_presented_as_finished(status):
    driver = DriverState(number="63", code="RUS", position=2, status=status)
    assert "finished" not in _driver_read(driver, {})["headline"]


@pytest.mark.parametrize("position", [2, None])
def test_chequered_read_waits_for_driver_classification_and_rewinds(position):
    driver = DriverState(number="63", code="RUS", position=position, status="RUNNING")
    live = {"strategy": {"lifecycle": "LIVE"}}
    final = {
        "strategy": {
            "lifecycle": "FINAL",
            "finishAssessment": {"canFinish": True},
            "projectionGate": {"publishAllowed": False},
        }
    }
    before = _driver_read(driver, live)
    pending = _driver_read(driver, final)
    assert pending["headline"] == (
        "RUS is P2; final classification pending."
        if position
        else "RUS: final classification pending."
    )
    assert not any("flag" in fact or "projection" in fact for fact in pending["facts"])
    finished = _driver_read(replace(driver, classification="FINISHED"), final)
    assert finished["headline"] == ("RUS finished P2." if position else "RUS finished.")
    assert _driver_read(driver, live) == before
    assert driver.classification is None
    assert "pending" not in _driver_read(driver, final, race_session=False)["headline"]


@pytest.mark.parametrize("status", ["DNF", "DNS", "DSQ", "STOPPED"])
def test_final_session_preserves_explicit_driver_status(status):
    driver = DriverState(number="63", code="RUS", position=2, status=status)
    headline = _driver_read(driver, {"strategy": {"lifecycle": "FINAL"}})["headline"]
    assert status in headline
    assert "pending" not in headline


@pytest.mark.parametrize("session_lifecycle", ["LIVE", "FINAL"])
@pytest.mark.parametrize(
    "condition,expected",
    [
        ("STOPPED", "STR is STOPPED."),
        ("RETIRED_INDICATED", "STR is reported RETIRED."),
    ],
)
def test_driver_read_uses_source_condition_and_allows_recovery(
    session_lifecycle, condition, expected
):
    driver = DriverState(
        number="18",
        code="STR",
        position=20,
        status="RUNNING",
        source_condition=condition,
        source_stopped=True,
        source_retired=condition == "RETIRED_INDICATED",
    )
    model = {
        "strategy": {
            "lifecycle": session_lifecycle,
            "finishAssessment": {"canFinish": True},
            "projectionGate": {"publishAllowed": False},
        }
    }
    read = _driver_read(driver, model)
    assert read["headline"] == expected
    assert not any("flag" in fact or "projection" in fact for fact in read["facts"])
    assert driver.classification is None
    resumed = replace(
        driver, source_condition="RUNNING", source_stopped=False, source_retired=False
    )
    assert (
        _driver_read(resumed, {"strategy": {"lifecycle": "LIVE"}})["headline"]
        == "STR is running P20."
    )
    assert _driver_read(driver, model)["headline"] == expected
    classified = replace(driver, classification="DNF")
    assert _driver_read(classified, model)["headline"] == "STR did not finish (DNF)."


@pytest.mark.parametrize("late_join", [False, True])
def test_suspension_tyre_change_requires_observed_stop_increment(late_join):
    """A baseline count cannot invent a stop; a recorded increment survives red."""
    adapter = F1LiveAdapter("11361")
    events = []

    def feed(topic, payload, timestamp):
        events.extend(
            adapter.ingest(
                {
                    "stream": topic,
                    "payload": payload,
                    "source_timestamp": timestamp,
                    "received_at": timestamp,
                }
            )
        )

    start = "2026-09-06T13:27:36Z" if late_join else "2026-09-06T13:00:00Z"
    feed("SessionInfo", {"Key": 11361, "Name": "Race", "Type": "Race"}, start)
    feed(
        "TimingAppData",
        {
            "Lines": {
                "63": {
                    "Stints": {
                        "0": {
                            "Compound": "MEDIUM",
                            "TotalLaps": 3,
                            "StartLaps": 0,
                        }
                    }
                }
            }
        },
        start,
    )
    feed(
        "TimingData",
        {
            "Lines": {
                "63": {
                    "Position": "2",
                    "NumberOfLaps": 3,
                    "NumberOfPitStops": 1 if late_join else 0,
                    "InPit": late_join,
                }
            }
        },
        start,
    )
    feed(
        "SessionStatus",
        {"Status": "Aborted"},
        "2026-09-06T13:27:37Z" if late_join else "2026-09-06T13:07:42Z",
    )
    if not late_join:
        feed(
            "TimingData",
            {"Lines": {"63": {"NumberOfPitStops": 1, "InPit": True}}},
            "2026-09-06T13:08:00Z",
        )
    feed("SessionStatus", {"Status": "Started"}, "2026-09-06T13:39:00Z")
    change = {
        "Lines": {
            "63": {
                "Stints": {
                    "1": {
                        "Compound": "HARD",
                        "TotalLaps": 0,
                        "StartLaps": 0,
                    }
                }
            }
        }
    }
    feed("TimingAppData", change, "2026-09-06T13:39:13Z")
    feed("TimingAppData", change, "2026-09-06T13:39:14Z")
    feed(
        "PitLaneTimeCollection",
        {"PitTimes": {"63": {"Lap": 4, "Duration": "1873.0"}}},
        "2026-09-06T13:39:15Z",
    )
    ordered = tuple(
        sorted(events, key=lambda event: parse_timestamp(event.occurred_at))
    )
    state, evidence = SessionEvidence.reduce_events(ordered)
    pits = evidence.pit_events_for_driver("63")
    assert state.drivers["63"].pit_count == 1
    assert state.drivers["63"].compound == "HARD"
    assert len(pits) == (0 if late_join else 1)
    actual = _actual_strategy(state.drivers["63"], (), pits)
    assert actual["evidenceComplete"] is (not late_join)
    if not late_join:
        assert actual["compounds"] == ["MEDIUM", "HARD"]
        assert pits[0].lap == 4
        assert pits[0].stop_duration is None
        assert pits[0].pit_lane_duration is None
        assert pits[0].ordinal == 1
    for sequence, event in enumerate(ordered, 1):
        if parse_timestamp(event.occurred_at) < parse_timestamp("2026-09-06T13:39:13Z"):
            assert evidence.pit_events_for_driver("63", event_limit=sequence) == ()
