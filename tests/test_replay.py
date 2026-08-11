from pathlib import Path

from slipstream.events import NormalizedEvent
from slipstream.replay import load_events, replay
from slipstream.terminal import render

ROOT = Path(__file__).parent


def test_sample_replay_matches_golden_terminal_output() -> None:
    state = replay(load_events(ROOT / "fixtures" / "replays" / "sample-session.json"))
    assert render(state) == (ROOT / "golden" / "sample-session.txt").read_text(
        encoding="utf-8"
    )


def test_timing_can_arrive_before_driver_metadata() -> None:
    events = load_events(ROOT / "fixtures" / "replays" / "sample-session.json")
    state = replay([events[0], events[3]])
    assert state.drivers["4"].position == 1
    assert state.drivers["4"].name is None


def test_driver_metadata_preserves_earlier_timing_state() -> None:
    events = load_events(ROOT / "fixtures" / "replays" / "sample-session.json")
    state = replay([events[0], events[3], events[1]])

    assert state.drivers["4"].position == 1
    assert state.drivers["4"].name == "Lando Norris"


def test_session_clock_uses_source_offset_for_every_event() -> None:
    events = [
        NormalizedEvent(
            "session",
            "2025-01-01T12:00:00Z",
            "test",
            {"gmt_offset": "-05:00:00", "status": "STARTED"},
        ),
        NormalizedEvent(
            "weather",
            "2025-01-01T12:30:00Z",
            "test",
            {"air_temperature": 20.0},
        ),
    ]

    state = replay(events)

    assert state.session.local_time == "2025-01-01T07:30:00-05:00"
