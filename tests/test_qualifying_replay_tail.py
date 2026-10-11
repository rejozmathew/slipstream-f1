"""Final qualifying laps remain reachable after the session clock closes."""

import json

import pytest
from fastapi.testclient import TestClient

from slipstream.api import create_app
from slipstream.events import NormalizedEvent
from slipstream.playback import ReplayController


@pytest.mark.parametrize("sprint", [False, True])
def test_qualifying_replay_includes_late_laps_and_result_corrections(tmp_path, sprint):
    def event(kind, time, **payload):
        return {
            "kind": kind,
            "occurred_at": f"2026-10-10T{time}Z",
            "source": "fixture",
            "payload": payload,
        }

    phase = "SQ3" if sprint else "Q3"
    name = "Sprint Qualifying" if sprint else "Qualifying"
    events = [
        event(
            "session",
            "14:00:00",
            key="11384",
            name=name,
            session_type=name,
            started_at="2026-10-10T14:00:00Z",
            ended_at="2026-10-10T14:30:00Z",
            status="RUNNING",
            qualifying_phase=phase,
        ),
        event("driver", "14:00:01", number="44", position=2, last_lap="1:32.000"),
        event("session", "14:30:00", status="FINISHED", qualifying_phase=phase),
        event(
            "timing",
            "14:30:14",
            number="44",
            last_lap="1:31.648",
            lap_observation={
                "lap": 25,
                "started_at": "2026-10-10T14:28:42Z",
                "duration": 91.648,
            },
        ),
        event(
            "timing",
            "14:31:08",
            number="3",
            last_lap="1:31.625",
            lap_observation={
                "lap": 15,
                "started_at": "2026-10-10T14:29:36Z",
                "duration": 91.625,
            },
        ),
        event(
            "timing",
            "14:31:10",
            number="44",
            position=1,
            best_lap="1:31.648",
            qualifying_results=[92.0, 91.8, 91.648],
        ),
        # Repeated results, pit movement, weather and end flags add no finish.
        event(
            "timing",
            "14:32:00",
            number="44",
            position=1,
            best_lap="1:31.648",
            qualifying_results=[92.0, 91.8, 91.648],
            track_position=0.6,
            activity="IN_PIT",
        ),
        event("weather", "14:33:00", track_temperature=35),
        event("session", "14:34:00", status="FINISHED", qualifying_phase=phase),
    ]
    path = tmp_path / "qualifying.json"
    path.write_text(json.dumps(events), encoding="utf-8")
    with TestClient(create_app(path)) as client:
        metadata = client.get("/api/v1/replay").json()
        assert metadata["endTime"] == "2026-10-10T14:31:10Z"
        assert metadata["eventCount"] == len(events)
        with client.websocket_connect("/api/v1/stream") as socket:
            socket.receive_json()
            socket.send_json({"type": "seek", "at": metadata["endTime"]})
            final = socket.receive_json()["data"]["drivers"]
            assert final["3"]["last_lap"] == "1:31.625"
            assert final["44"]["position"] == 1

    replay = ReplayController(
        [NormalizedEvent.from_mapping(row) for row in events],
        start_time=metadata["startTime"],
        end_time=metadata["endTime"],
    )
    replay.seek("2026-10-10T14:29:59Z")
    replay.advance(120)
    assert replay.finished
    assert replay.state.drivers["3"].last_lap == "1:31.625"
    assert replay.state.drivers["44"].position == 1
    assert replay.state.drivers["44"].qualifying_results == [92.0, 91.8, 91.648]
