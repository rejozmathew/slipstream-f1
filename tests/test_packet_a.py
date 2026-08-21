import pytest

from slipstream.lifecycle import (
    terminal_state,
    is_active_participant,
    is_battle_eligible,
)
from slipstream.state import DriverState, RaceState, SessionState, CircuitState
from slipstream.analytics import _strategy_validity, _driver_strategy, _race_strategy
from slipstream.adapters.openf1 import recording_to_events

def _fake_recording(endpoints: dict) -> dict:
    return {
        "format": "slipstream.openf1-recording.v1",
        "generated_at": "2023-01-01T12:00:00Z",
        "endpoints": {
            "sessions": [{"session_key": 1, "date_start": "2023-01-01T12:00:00Z", "date_end": "2023-01-01T14:00:00Z", "session_name": "Race", "session_type": "Race"}],
            **endpoints
        }
    }

def _make_driver(status: str) -> DriverState:
    return DriverState(number="1", status=status, position=1)

def test_terminal_state_stopped_is_none():
    from slipstream.lifecycle import terminal_state
    assert terminal_state(_make_driver("STOPPED")) is None

def test_finished_terminal_semantics():
    from slipstream.lifecycle import terminal_state, is_active_participant, is_battle_eligible
    driver = _make_driver("FINISHED")
    assert terminal_state(driver) == "FINISHED"
    assert not is_active_participant(driver)
    assert not is_battle_eligible(driver)

def test_retired_excluded_from_battle():
    from slipstream.lifecycle import terminal_state, is_active_participant, is_battle_eligible
    driver = _make_driver("RETIRED")
    assert terminal_state(driver) == "RETIRED"
    assert not is_active_participant(driver)
    assert not is_battle_eligible(driver)

def test_retired_never_resumes():
    recording = _fake_recording({
        "drivers": [{"driver_number": 1, "name_acronym": "MAX"}],
        "race_control": [
            {"date": "2023-01-01T12:10:00Z", "driver_number": 1, "message": "RETIRED"}
        ],
        "laps": [
            {"date_start": "2023-01-01T12:15:00Z", "driver_number": 1, "lap_number": 5, "lap_duration": 90.0}
        ],
        "session_result": [
            {"date": "2023-01-01T14:00:00Z", "driver_number": 1, "status": "RETIRED"}
        ]
    })
    events = recording_to_events(recording)
    has_running = False
    saw_retired = False
    for e in events:
        if e.kind == "driver" and e.payload.get("status") == "RETIRED":
            saw_retired = True
        if saw_retired and e.kind == "timing" and e.payload.get("status") == "RUNNING":
            has_running = True
    assert not has_running, "RETIRED should not resume even with lap event"

def test_stopped_remains_stopped_after_noise():
    recording = _fake_recording({
        "drivers": [{"driver_number": 1, "name_acronym": "MAX"}],
        "race_control": [
            {"date": "2023-01-01T12:10:00Z", "driver_number": 1, "message": "STOPPED ON TRACK"}
        ],
        "session_result": [
            {"date": "2023-01-01T12:15:00Z", "driver_number": 1, "position": 2},
            {"date": "2023-01-01T14:00:00Z", "driver_number": 1, "status": "STOPPED"}
        ]
    })
    events = recording_to_events(recording)
    has_running = False
    for e in events:
        if e.kind == "timing" and e.payload.get("status") == "RUNNING":
            has_running = True
    assert not has_running, "STOPPED should not resume on pure position noise"

def test_stopped_resumes_after_genuine_progress():
    recording = _fake_recording({
        "drivers": [{"driver_number": 1, "name_acronym": "MAX"}],
        "race_control": [
            {"date": "2023-01-01T12:10:00Z", "driver_number": 1, "message": "STOPPED ON TRACK"}
        ],
        "laps": [
            {"date_start": "2023-01-01T12:15:00Z", "driver_number": 1, "lap_number": 5, "lap_duration": 90.0}
        ],
        "position": [
            {"date": "2023-01-01T14:00:00Z", "driver_number": 1, "status": "FINISHED"}
        ]
    })
    events = recording_to_events(recording)
    has_running = False
    for e in events:
        if e.kind == "timing" and e.payload.get("status") == "RUNNING":
            has_running = True
    assert has_running, "STOPPED should resume on genuine progress (lap completed)"


def test_retired_receives_no_future_strategy():
    driver = _make_driver("RETIRED")
    state = RaceState(
        session=SessionState(key="1", name="Race", session_kind="race", status="STARTED"),
        circuit=CircuitState(key="1", name="Monza"),
        drivers={"1": driver},
    )
    strategy = _driver_strategy(driver, [], (), {}, (), {}, {"degradation": {}}, {"degradation": {}}, state, "LIVE_OUTLOOK")
    assert strategy["pitWindow"]["status"] == "UNKNOWN"
    assert strategy["likelyNextCompound"]["status"] == "UNKNOWN"
    assert strategy["primaryStrategy"]["status"] == "UNKNOWN"
    assert strategy["alternateStrategy"]["status"] == "UNKNOWN"
    assert strategy["terminalState"] == "RETIRED"


def test_chequered_race_no_future_strategy():
    driver = _make_driver("FINISHED")
    state = RaceState(
        session=SessionState(key="1", name="Race", session_kind="race", status="FINISHED"),
        circuit=CircuitState(key="1", name="Monza"),
        drivers={"1": driver},
    )
    race_strat = _race_strategy({}, {}, None, {}, state, "LIVE_OUTLOOK")
    assert race_strat["pitWindow"]["status"] == "UNKNOWN"


def test_chequered_driver_no_to_flag():
    # If a race is FINISHED, window_state shouldn't return TO_FINISH.
    # Wait, the prompt says "CHEQUERED driver table cannot show TO_FLAG", which comes from _driver_disposition / _window_state returning UNKNOWN.
    from slipstream.analytics import _window_state, _driver_disposition
    driver = _make_driver("FINISHED")
    state = RaceState(
        session=SessionState(key="1", name="Race", session_kind="race", status="FINISHED"),
        circuit=CircuitState(key="1", name="Monza"),
        drivers={"1": driver},
    )
    assert _window_state(driver, state, {}) == "UNKNOWN"
    assert _driver_disposition(driver, state, {}) == "UNKNOWN"


def test_vocabularies_aligned():
    import json
    from pathlib import Path
    from slipstream.context_types import STRATEGY_VALIDITY_STATES, WINDOW_STATES, DISPOSITION_STATES
    
    protocol_ts = Path("web/domain/protocol.ts").read_text()
    
    # Asserting elements exist in the typescript file
    for val in STRATEGY_VALIDITY_STATES:
        assert f'"{val}"' in protocol_ts, f"{val} missing from protocol.ts validity"
    for val in WINDOW_STATES:
        assert f'"{val}"' in protocol_ts, f"{val} missing from protocol.ts window states"
    for val in DISPOSITION_STATES:
        assert f'"{val}"' in protocol_ts, f"{val} missing from protocol.ts disposition"

