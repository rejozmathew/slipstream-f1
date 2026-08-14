import json
from email.message import Message
from pathlib import Path
from typing import Self
from urllib.error import HTTPError

import pytest

from slipstream.adapters.openf1 import OpenF1Client, is_openf1_recording
from slipstream.replay import load_events, replay
from slipstream.terminal import render

ROOT = Path(__file__).parent
RECORDING = ROOT / "fixtures" / "openf1" / "session-9165.json"
STINT_RECORDING = ROOT / "fixtures" / "openf1" / "stint-transition.json"


def test_openf1_recording_normalizes_to_golden_state() -> None:
    state = replay(load_events(RECORDING))

    assert state.schema_version == 1
    assert state.session.key == "9165"
    assert state.session.circuit == "Marina Bay"
    assert state.session.gmt_offset == "08:00:00"
    assert state.session.local_time == "2023-09-17T22:00:00+08:00"
    assert state.circuit.key == "61"
    assert state.circuit.name == "Marina Bay Street Circuit"
    assert state.circuit.year == 2023
    assert len(state.circuit.path) == 55
    assert state.circuit.availability["path"] == "available"
    assert state.weather.air_temperature == 28.8
    assert state.weather.track_temperature == 34.1
    assert state.weather.rainfall is False
    assert state.weather.availability["wind_speed"] == "available"
    assert state.drivers["4"].interval_to_ahead == "+0.812"
    assert state.drivers["4"].track_position == 0.999
    assert state.drivers["4"].availability["track_position"] == "available"
    assert state.drivers["4"].availability["speed"] == "unsupported"
    assert render(state) == (ROOT / "golden" / "openf1-session-9165.txt").read_text(
        encoding="utf-8"
    )


def test_replay_can_render_a_deterministic_point_in_time() -> None:
    state = replay(load_events(RECORDING), at="2023-09-17T13:59:10Z")

    assert state.session.status == "STARTED"
    assert state.session.total_laps == 62
    assert state.updated_at == "2023-09-17T13:59:00+00:00"
    assert state.drivers["55"].position == 1
    assert state.drivers["4"].gap_to_leader == "+0.812"

    before_weather = replay(load_events(RECORDING), at="2023-09-17T13:00:00Z")
    assert before_weather.weather.air_temperature is None
    assert before_weather.weather.availability["air_temperature"] == "unavailable"

    start = replay(load_events(RECORDING), at="2023-09-17T12:00:00Z")
    assert start.drivers["55"].compound == "HARD"
    assert start.drivers["55"].stint_laps == 0


def test_recording_format_is_explicit() -> None:
    raw = json.loads(RECORDING.read_text(encoding="utf-8"))
    assert is_openf1_recording(raw)
    assert raw["source_capabilities"]["authenticated"] is False
    assert raw["source_capabilities"]["weather"] is True
    assert raw["source_capabilities"]["circuit_shape"] is True


def test_stint_and_pit_state_changes_at_replay_boundaries() -> None:
    events = load_events(STINT_RECORDING)

    medium = replay(events, at="2025-01-01T12:19:30Z").drivers["4"]
    after_pit_state = replay(events, at="2025-01-01T12:20:30Z")
    hard_state = replay(events, at="2025-01-01T12:21:01Z")
    after_pit = after_pit_state.drivers["4"]
    hard = hard_state.drivers["4"]

    assert (medium.compound, medium.tyre_age, medium.stint_laps) == ("MEDIUM", 19, 19)
    assert after_pit.pit_count == 1
    assert (hard.compound, hard.tyre_age, hard.stint_laps, hard.pit_count) == (
        "HARD",
        1,
        1,
        1,
    )
    assert hard.availability["interval_to_ahead"] == "unsupported"
    assert [
        (
            observation.lap,
            observation.compound,
            observation.stint_number,
            observation.pit_in,
            observation.pit_out,
            observation.quality,
            observation.contamination_reasons,
        )
        for observation in hard.lap_history
    ] == [
        (18, "MEDIUM", 1, False, False, "representative", ()),
        (19, "MEDIUM", 1, True, False, "contaminated", ("pit_in",)),
        (20, "HARD", 2, False, True, "contaminated", ("pit_out",)),
    ]
    checkpoints = {
        "lap_19": {
            "compound": medium.compound,
            "tyre_age": medium.tyre_age,
            "stint_laps": medium.stint_laps,
            "pit_count": medium.pit_count,
            "track_status": replay(
                events, at="2025-01-01T12:19:30Z"
            ).session.track_status,
        },
        "after_pit": {
            "compound": after_pit.compound,
            "tyre_age": after_pit.tyre_age,
            "stint_laps": after_pit.stint_laps,
            "pit_count": after_pit.pit_count,
            "track_status": after_pit_state.session.track_status,
        },
        "lap_20": {
            "compound": hard.compound,
            "tyre_age": hard.tyre_age,
            "stint_laps": hard.stint_laps,
            "pit_count": hard.pit_count,
            "track_status": hard_state.session.track_status,
        },
    }
    expected = json.loads((ROOT / "golden" / "stint-transition.json").read_text())
    assert checkpoints == expected


def test_unknown_recording_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "unknown.json"
    path.write_text('{"format": "other.v1"}', encoding="utf-8")

    with pytest.raises(ValueError, match="supported source recording"):
        load_events(path)


def test_driver_scoped_black_and_white_flag_does_not_become_track_status() -> None:
    from slipstream.events import NormalizedEvent
    from slipstream.state import RaceState

    state = RaceState().apply(
        NormalizedEvent(
            kind="race_control",
            occurred_at="2025-01-01T12:00:00Z",
            source="openf1",
            payload={
                "category": "Flag",
                "message": "BLACK AND WHITE FLAG FOR CAR 1",
                "flag": "BLACK AND WHITE",
                "scope": "Driver",
                "driver_number": "1",
            },
        )
    )

    assert state.session.track_status is None
    assert state.race_control[-1].scope == "Driver"


def test_optional_openf1_endpoint_accepts_not_found() -> None:
    def not_found(*args: object, **kwargs: object) -> None:
        raise HTTPError("https://example.test", 404, "Not Found", Message(), None)

    client = OpenF1Client(opener=not_found, minimum_interval=0)

    assert client.get("intervals", session_key=9161, allow_not_found=True) == []


def test_optional_linked_circuit_accepts_empty_list() -> None:
    class EmptyResponse:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"[]"

    client = OpenF1Client(
        opener=lambda *args, **kwargs: EmptyResponse(), minimum_interval=0
    )

    assert client.get_object_url(
        "https://example.test/circuit", allow_not_found=True
    ) is None


def test_optional_historical_location_normalizes_precise_car_coordinates(
    tmp_path: Path,
) -> None:
    raw = json.loads(RECORDING.read_text(encoding="utf-8"))
    raw["source_capabilities"]["location_xy"] = True
    raw["endpoints"]["location"] = [
        {
            "date": "2023-09-17T13:59:05+00:00",
            "session_key": 9165,
            "meeting_key": 1219,
            "driver_number": 55,
            "x": 1113,
            "y": -663,
            "z": 188,
        }
    ]
    path = tmp_path / "with-location.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    state = replay(load_events(path), at="2023-09-17T13:59:10Z")

    assert (state.drivers["55"].x, state.drivers["55"].y) == (1113.0, -663.0)
    assert state.drivers["55"].z == 188.0
    assert state.drivers["55"].availability["location_xy"] == "available"
