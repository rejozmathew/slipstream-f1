import json
from email.message import Message
from pathlib import Path
from typing import Self
from urllib.error import HTTPError

import pytest

from slipstream.adapters.openf1 import (
    OpenF1Client,
    is_openf1_recording,
    recording_to_events,
)
from slipstream.evidence import SessionEvidence
from slipstream.replay import load_events, replay
from slipstream.serialization import state_envelope
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

    assert state.session.status == "RUNNING"
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
    history = SessionEvidence.from_events(tuple(events)).laps_for_driver(
        "4", at="2025-01-01T12:21:01Z"
    )
    assert not hasattr(hard, "lap_history")
    assert (
        "lap_history"
        not in state_envelope(hard_state, sequence=len(events))["data"]["drivers"]["4"]
    )
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
        for observation in history
    ] == [
        (18, "MEDIUM", 1, False, False, "contaminated", ("neutralized_track",)),
        (19, "MEDIUM", 1, True, False, "contaminated", ("pit_in", "neutralized_track")),
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


def test_safety_car_infringement_does_not_create_whole_track_status() -> None:
    from slipstream.events import NormalizedEvent
    from slipstream.state import RaceState

    state = RaceState().apply(
        NormalizedEvent(
            kind="race_control",
            occurred_at="2025-01-01T12:00:00Z",
            source="openf1",
            payload={
                "category": "Other",
                "message": "CAR 4 UNDER INVESTIGATION - SAFETY CAR INFRINGEMENT",
            },
        )
    )

    assert state.session.track_status is None


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

    assert (
        client.get_object_url("https://example.test/circuit", allow_not_found=True)
        is None
    )


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


def _neutralization_recording(*, close_interval: bool) -> dict[str, object]:
    raw = json.loads(STINT_RECORDING.read_text(encoding="utf-8"))
    endpoints = raw["endpoints"]
    endpoints["laps"] = [
        {
            "date_start": f"2025-01-01T12:0{index}:00Z",
            "driver_number": 4,
            "lap_duration": 60.0,
            "lap_number": index + 1,
        }
        for index in range(4)
    ]
    endpoints["pit"] = []
    endpoints["race_control"] = [
        {
            "category": "Flag",
            "date": "2025-01-01T12:00:15Z",
            "flag": "YELLOW",
            "scope": "Sector",
            "sector": 3,
            "message": "YELLOW IN TRACK SECTOR 3",
        },
        {
            "category": "SafetyCar",
            "date": "2025-01-01T12:01:20Z",
            "lap_number": 2,
            "message": "SAFETY CAR DEPLOYED",
        },
    ]
    if close_interval:
        endpoints["race_control"].append(
            {
                "category": "Flag",
                "date": "2025-01-01T12:03:10Z",
                "lap_number": 4,
                "flag": "CLEAR",
                "scope": "Track",
                "message": "TRACK CLEAR",
            }
        )
    return raw


def test_lap_evidence_uses_scope_aware_neutralization_intervals() -> None:
    events = tuple(recording_to_events(_neutralization_recording(close_interval=True)))
    evidence = SessionEvidence.from_events(events)
    laps = evidence.laps_for_driver("4")

    assert [lap.quality for lap in laps] == [
        "representative",
        "contaminated",
        "contaminated",
        "contaminated",
    ]
    assert "neutralized_track" not in laps[0].contamination_reasons
    assert all("neutralized_track" in lap.contamination_reasons for lap in laps[1:])
    assert (
        len(
            evidence.laps_for_driver(
                "4", event_limit=evidence.lap_observations[1].sequence
            )
        )
        == 2
    )
    assert len(evidence.laps_for_driver("4", at="2025-01-01T12:01:59Z")) == 2


def test_unclosed_neutralization_keeps_unproven_laps_unknown() -> None:
    events = tuple(recording_to_events(_neutralization_recording(close_interval=False)))
    laps = SessionEvidence.from_events(events).laps_for_driver("4")

    assert laps[1].quality == "contaminated"
    assert laps[2].quality == "unknown"
    assert "neutralization_end_unknown" in laps[2].contamination_reasons


def test_openf1_lifecycle_requires_explicit_timestamped_driver_evidence() -> None:
    raw = json.loads(STINT_RECORDING.read_text(encoding="utf-8"))
    raw["endpoints"]["race_control"] = [
        {
            "category": "Other",
            "date": "2025-01-01T12:00:15Z",
            "driver_number": 4,
            "message": "CAR 4 STOPPED ON TRACK",
        },
        {
            "category": "Other",
            "date": "2025-01-01T12:02:15Z",
            "message": "CAR 4 RETIRED",
        },
        {
            "category": "Other",
            "date": "2025-01-01T12:03:15Z",
            "message": "CAR 4 OUTSIDE TRACK LIMITS",
        },
        {
            "category": "Other",
            "date": "2025-01-01T12:04:15Z",
            "message": "DRIVER OUT OF THE RACE",
        },
    ]

    lifecycle_events = [
        event
        for event in recording_to_events(raw)
        if event.kind == "timing"
        and event.payload.get("status") in {"STOPPED", "RETIRED"}
    ]

    assert [
        (event.occurred_at, event.payload["number"], event.payload["status"])
        for event in lifecycle_events
    ] == [
        ("2025-01-01T12:00:15Z", "4", "STOPPED"),
        ("2025-01-01T12:02:15Z", "4", "RETIRED"),
    ]


def test_no_recent_progress_heuristic_is_disabled() -> None:
    from slipstream.events import NormalizedEvent
    from slipstream.state import RaceState

    state = RaceState().apply(
        NormalizedEvent(
            kind="session",
            occurred_at="2026-01-01T12:00:00Z",
            source="test",
            payload={"layout_family": "race", "status": "STARTED"},
        )
    )
    for number in ("1", "2"):
        state = state.apply(
            NormalizedEvent(
                kind="driver",
                occurred_at="2026-01-01T12:00:01Z",
                source="test",
                payload={"number": number, "status": "RUNNING"},
            )
        )
        state = state.apply(
            NormalizedEvent(
                kind="timing",
                occurred_at="2026-01-01T12:01:00Z",
                source="test",
                payload={"number": number, "lap": 1},
            )
        )
    state = state.apply(
        NormalizedEvent(
            kind="timing",
            occurred_at="2026-01-01T12:02:00Z",
            source="test",
            payload={"number": "1", "lap": 2},
        )
    )
    state = state.apply(
        NormalizedEvent(
            kind="timing",
            occurred_at="2026-01-01T12:03:00Z",
            source="test",
            payload={"number": "1", "lap": 3},
        )
    )

    assert state.drivers["2"].activity == "ON_TRACK"
    assert state.drivers["2"].status == "RUNNING"
    assert state.drivers["2"].progress_observed_at_lap == 1


def test_historical_sparse_updates_preserve_full_field_track_progress() -> None:
    raw = json.loads(RECORDING.read_text(encoding="utf-8"))
    numbers = [str(number) for number in range(1, 7)]
    raw["endpoints"]["drivers"] = [
        {
            "driver_number": int(number),
            "full_name": f"Driver {number}",
            "name_acronym": f"D{number}",
            "team_colour": f"{int(number) * 100000:06d}",
            "team_name": f"Team {number}",
        }
        for number in numbers
    ]
    raw["endpoints"]["laps"] = [
        {
            "date_start": f"2023-09-17T13:56:{40 + index:02d}+00:00",
            "driver_number": int(number),
            "lap_duration": 96.0 + index,
            "lap_number": 62,
        }
        for index, number in enumerate(numbers)
    ]
    raw["endpoints"]["position"] = [
        {"date": "2023-09-17T13:56:50+00:00", "driver_number": 1, "position": 1}
    ]
    raw["endpoints"]["intervals"] = [
        {
            "date": "2023-09-17T13:56:51+00:00",
            "driver_number": 1,
            "gap_to_leader": 0,
            "interval": 0,
        }
    ]
    raw["endpoints"]["stints"] = []
    raw["endpoints"]["session_result"] = []
    raw["endpoints"]["race_control"] = []

    state = replay(tuple(recording_to_events(raw)), at="2023-09-17T13:56:55Z")

    assert set(state.drivers) == set(numbers)
    assert all(state.drivers[number].track_position is not None for number in numbers)
    assert state.drivers["1"].track_position != state.drivers["2"].track_position


def test_openf1_red_flag_is_history_only_and_degrades_after_track_clear() -> None:
    raw = json.loads(STINT_RECORDING.read_text(encoding="utf-8"))
    raw["endpoints"]["race_control"] = [
        {
            "category": "Flag",
            "date": "2025-01-01T12:05:00Z",
            "flag": "RED",
            "scope": "Track",
            "message": "RED FLAG - RACE SUSPENDED",
        },
        {
            "category": "Flag",
            "date": "2025-01-01T12:10:00Z",
            "flag": "CLEAR",
            "scope": "Track",
            "message": "TRACK CLEAR",
        },
    ]
    events = recording_to_events(raw)

    during_red = replay(events, at="2025-01-01T12:05:00Z")
    assert during_red.session.status == "RUNNING"
    assert during_red.session.control_status == "UNKNOWN"
    assert during_red.session.display_status == "RED_FLAG"
    assert during_red.race_control[-1].message == "RED FLAG - RACE SUSPENDED"

    after_clear = replay(events, at="2025-01-01T12:10:00Z")
    assert after_clear.session.status == "RUNNING"
    assert after_clear.session.control_status == "UNKNOWN"
    assert after_clear.session.marshal_status == "ALL_CLEAR"
    assert after_clear.session.display_status == "UNKNOWN"
    assert not any(
        event.kind == "session" and event.payload.get("status") == "SUSPENDED"
        for event in events
    )


def test_openf1_final_qualifying_segments_arrive_only_at_session_end() -> None:
    raw = json.loads(STINT_RECORDING.read_text(encoding="utf-8"))
    session = raw["endpoints"]["sessions"][0]
    session.update({"session_name": "Qualifying", "session_type": "Qualifying"})
    raw["endpoints"].update(
        {
            "drivers": [
                {"driver_number": 4, "name_acronym": "NOR", "team_name": "McLaren"},
                {"driver_number": 10, "name_acronym": "GAS", "team_name": "Alpine"},
                {"driver_number": 55, "name_acronym": "SAI", "team_name": "Williams"},
            ],
            "laps": [],
            "position": [],
            "intervals": [],
            "stints": [],
            "pit": [],
            "race_control": [],
            "weather": [],
            "session_result": [
                {
                    "driver_number": 4,
                    "position": 1,
                    "duration": [72.695, 71.628, 71.163],
                },
                {
                    "driver_number": 10,
                    "position": 11,
                    "duration": [73.115, 72.616, None],
                },
                {"driver_number": 55, "position": 17, "duration": [73.574, None, None]},
            ],
        }
    )
    events = recording_to_events(raw)
    end_index = next(
        index
        for index, event in enumerate(events)
        if event.kind == "session"
        and event.occurred_at == session["date_end"]
        and event.payload.get("status") == "FINISHED"
    )

    before_end = replay(events, event_limit=end_index)
    assert all(
        driver.qualifying_results is None for driver in before_end.drivers.values()
    )

    final = replay(events)
    assert final.drivers["4"].qualifying_results == (72.695, 71.628, 71.163)
    assert final.drivers["4"].qualifying_phase_reached == "Q3"
    assert final.drivers["4"].qualifying_eliminated is False
    assert final.drivers["10"].qualifying_results == (73.115, 72.616, None)
    assert final.drivers["10"].qualifying_phase_reached == "Q2"
    assert final.drivers["10"].qualifying_eliminated is True
    assert final.drivers["55"].qualifying_results == (73.574, None, None)
    assert final.drivers["55"].qualifying_phase_reached == "Q1"
    assert final.drivers["55"].qualifying_eliminated is True


def test_openf1_dnf_is_not_fabricated_before_session_end() -> None:
    raw = json.loads(STINT_RECORDING.read_text(encoding="utf-8"))
    session = raw["endpoints"]["sessions"][0]
    session.update({"session_name": "Race", "session_type": "Race"})
    raw["endpoints"].update(
        {
            "drivers": [
                {
                    "driver_number": 18,
                    "name_acronym": "STR",
                    "team_name": "Aston Martin",
                }
            ],
            "laps": [],
            "position": [],
            "intervals": [],
            "stints": [],
            "pit": [],
            "race_control": [],
            "weather": [],
            "session_result": [
                {
                    "driver_number": 18,
                    "position": None,
                    "dnf": True,
                    "dns": False,
                    "dsq": False,
                    "number_of_laps": 45,
                }
            ],
        }
    )
    events = recording_to_events(raw)
    dnf_index = next(
        index
        for index, event in enumerate(events)
        if event.kind == "timing"
        and event.payload.get("number") == "18"
        and event.payload.get("status") == "DNF"
    )

    before_end = replay(events, event_limit=dnf_index)
    at_end = replay(events, event_limit=dnf_index + 1)

    assert before_end.drivers["18"].status not in {
        "RETIRED",
        "DNF",
        "DNS",
        "DSQ",
        "WITHDRAWN",
    }
    assert at_end.drivers["18"].status == "DNF"
    assert events[dnf_index].occurred_at == session["date_end"]
