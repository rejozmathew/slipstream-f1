import json
from pathlib import Path

from fastapi.testclient import TestClient

from slipstream.api import create_app
from slipstream.catalog import CATALOG_FORMAT

RECORDING = Path(__file__).parent / "fixtures" / "openf1" / "session-9165.json"
NORMALIZED_REPLAY = (
    Path(__file__).parent / "fixtures" / "replays" / "sample-session.json"
)


def test_versioned_state_and_capabilities_endpoints() -> None:
    with TestClient(create_app(RECORDING)) as client:
        state = client.get("/api/v1/state")
        capabilities = client.get("/api/v1/capabilities")
        replay = client.get("/api/v1/replay")

    assert state.status_code == 200
    assert state.json()["v"] == 1
    assert state.json()["type"] == "state.snapshot"
    assert state.json()["data"]["session"]["key"] == "9165"
    assert state.json()["data"]["session"]["local_time"].endswith("+08:00")
    assert state.json()["data"]["weather"]["track_temperature"] == 34.1
    assert state.json()["data"]["circuit"]["name"] == "Marina Bay Street Circuit"
    assert len(state.json()["data"]["circuit"]["path"]) == 55
    assert capabilities.json()["source"] == "openf1"
    assert replay.json()["eventCount"] > 0
    assert replay.json()["startTime"] <= replay.json()["endTime"]
    assert replay.json()["durationSeconds"] > 0


def test_driver_history_is_on_demand_and_outside_race_state() -> None:
    with TestClient(create_app(RECORDING)) as client:
        state = client.get("/api/v1/state").json()
        history = client.get("/api/v1/driver-history?session_key=9165&driver_number=55")

    assert history.status_code == 200
    payload = history.json()
    assert payload["v"] == 1
    assert payload["driverNumber"] == "55"
    assert payload["available"] is True
    assert payload["observations"][0]["lap"] == 62
    assert payload["observations"][0]["occurredAt"]
    assert "quality" in payload["observations"][0]
    assert "lap_history" not in state["data"]["drivers"]["55"]


def test_catalog_exposes_season_weekend_and_session_metadata() -> None:
    with TestClient(create_app(RECORDING)) as client:
        catalog = client.get("/api/v1/catalog").json()

    assert catalog["defaultSessionKey"] == "9165"
    assert catalog["sessions"] == [
        {
            "sessionKey": "9165",
            "year": 2023,
            "meetingKey": "1219",
            "meetingName": "Singapore Grand Prix",
            "sessionName": "Race",
            "sessionType": "Race",
            "sessionKind": "race",
            "layoutFamily": "race",
            "circuit": "Marina Bay",
            "location": "Singapore",
            "dateStart": "2023-09-17T12:00:00+00:00",
            "dateEnd": "2023-09-17T14:00:00+00:00",
            "gmtOffset": "08:00:00",
            "available": True,
            "isLive": False,
            "liveAvailable": False,
            "liveConnected": False,
            "liveStale": False,
            "liveStatus": "OFFLINE",
            "livePhase": "UNAVAILABLE",
            "replayReady": True,
            "downloadable": True,
            "circuitShapeAvailable": True,
            "positionMode": "timing_estimate",
        }
    ]


def test_recording_directory_can_switch_between_library_sessions() -> None:
    with TestClient(create_app(RECORDING.parent)) as client:
        catalog = client.get("/api/v1/catalog").json()
        selected = client.get("/api/v1/state?session_key=100").json()

    assert {item["sessionKey"] for item in catalog["sessions"]} == {"100", "9165"}
    assert selected["data"]["session"]["key"] == "100"


def test_web_build_is_served_without_shadowing_api(tmp_path: Path) -> None:
    web_dir = tmp_path / "web"
    (web_dir / "assets").mkdir(parents=True)
    (web_dir / "index.html").write_text(
        "<!doctype html><title>Slipstream F1</title><div id='root'></div>",
        encoding="utf-8",
    )
    (web_dir / "assets" / "app.js").write_text("// built asset", encoding="utf-8")

    with TestClient(create_app(RECORDING, web_dir=web_dir)) as client:
        index = client.get("/")
        browser_route = client.get("/replay/9165")
        asset = client.get("/assets/app.js")
        state = client.get("/api/v1/state")
        missing_api = client.get("/api/v1/missing")

    assert index.status_code == 200
    assert "Slipstream F1" in index.text
    assert browser_route.status_code == 200
    assert browser_route.text == index.text
    assert asset.text == "// built asset"
    assert state.status_code == 200
    assert missing_api.status_code == 404


def test_api_only_mode_has_no_browser_routes() -> None:
    with TestClient(create_app(RECORDING)) as client:
        assert client.get("/").status_code == 404
        assert client.get("/api/v1/state").status_code == 200


def test_websocket_uses_per_client_seek_cursor() -> None:
    with (
        TestClient(create_app(RECORDING)) as client,
        client.websocket_connect("/api/v1/stream") as socket,
    ):
        initial = socket.receive_json()
        socket.send_json({"type": "seek", "at": "2023-09-17T13:59:10Z"})
        sought = socket.receive_json()

    assert initial["data"]["session"]["status"] == "RUNNING"
    assert initial["analytics"]["type"] == "analytics.snapshot"
    assert initial["analytics"]["sequence"] == initial["seq"]
    assert sought["data"]["session"]["status"] == "RUNNING"
    assert sought["seq"] > initial["seq"]


def test_websocket_seeks_by_event_cursor() -> None:
    with (
        TestClient(create_app(RECORDING)) as client,
        client.websocket_connect("/api/v1/stream") as socket,
    ):
        socket.receive_json()
        socket.send_json({"type": "seek", "seq": 1})
        sought = socket.receive_json()

    assert sought["seq"] == 1
    assert sought["data"]["session"]["status"] == "RUNNING"


def test_websocket_delay_is_per_client() -> None:
    with (
        TestClient(create_app(RECORDING)) as client,
        client.websocket_connect("/api/v1/stream") as delayed_socket,
        client.websocket_connect("/api/v1/stream") as current_socket,
    ):
        delayed_initial = delayed_socket.receive_json()
        current_initial = current_socket.receive_json()
        delayed_socket.send_json({"type": "delay", "seconds": 3600})
        delayed = delayed_socket.receive_json()
        current_socket.send_json({"type": "snapshot"})
        current = current_socket.receive_json()

    assert delayed["sessionTime"] > delayed_initial["sessionTime"]
    assert current_initial["seq"] == delayed_initial["seq"]
    assert current["seq"] == delayed_initial["seq"]
    assert current["sessionTime"] == current_initial["sessionTime"]


def test_websocket_play_advances_clock_and_pause_stops_it() -> None:
    with (
        TestClient(create_app(NORMALIZED_REPLAY)) as client,
        client.websocket_connect("/api/v1/stream") as socket,
    ):
        initial = socket.receive_json()
        socket.send_json({"type": "play", "speed": 120})
        playing = socket.receive_json()
        socket.send_json({"type": "pause"})
        paused = socket.receive_json()

    assert playing["sessionTime"] > initial["sessionTime"]
    assert playing["playback"]["playing"] is True
    assert paused["playback"]["playing"] is False


def test_historical_replay_uses_factual_terminal_and_can_rewind_after_finish(
    tmp_path: Path,
) -> None:
    recording = [
        {
            "kind": "session",
            "occurred_at": "2026-08-23T13:00:00Z",
            "source": "fixture",
            "payload": {
                "key": "11353",
                "name": "Race",
                "meeting_name": "Dutch Grand Prix",
                "session_type": "Race",
                "started_at": "2026-08-23T13:00:00Z",
                "ended_at": "2026-08-23T15:00:00Z",
                "status": "RUNNING",
            },
        },
        {
            "kind": "timing",
            "occurred_at": "2026-08-23T14:59:59Z",
            "source": "fixture",
            "payload": {"number": "1", "lap": 66, "status": "RUNNING"},
        },
        {
            "kind": "timing",
            "occurred_at": "2026-08-23T15:05:00Z",
            "source": "fixture",
            "payload": {"number": "1", "lap": 71, "status": "RUNNING"},
        },
        {
            "kind": "session",
            "occurred_at": "2026-08-23T15:08:13Z",
            "source": "fixture",
            "payload": {
                "status": "FINISHED",
                "control_status": "CHEQUERED",
                "lap": 72,
            },
        },
        {
            "kind": "race_control",
            "occurred_at": "2026-08-23T15:20:00Z",
            "source": "fixture",
            "payload": {"category": "Other", "message": "POST SESSION ACCESS"},
        },
    ]
    path = tmp_path / "dutch-11353.json"
    path.write_text(json.dumps(recording), encoding="utf-8")

    with (
        TestClient(create_app(path)) as client,
        client.websocket_connect("/api/v1/stream") as socket,
    ):
        metadata = client.get("/api/v1/replay").json()
        socket.receive_json()
        socket.send_json({"type": "seek", "at": metadata["endTime"]})
        finished = socket.receive_json()
        socket.send_json({"type": "seek", "at": "2026-08-23T14:59:59Z"})
        rewound = socket.receive_json()

    assert metadata["endTime"] == "2026-08-23T15:08:13Z"
    assert metadata["durationSeconds"] == 7693
    assert finished["playback"]["playing"] is False
    assert finished["data"]["session"]["status"] == "FINISHED"
    assert rewound["playback"]["playing"] is False
    assert rewound["data"]["session"]["status"] == "RUNNING"
    assert rewound["data"]["session"]["lap"] == 66
    assert rewound["seq"] < finished["seq"]
    assert rewound["analytics"]["sequence"] == rewound["seq"]


def test_catalog_session_can_be_downloaded_and_used_without_restart(
    tmp_path: Path,
) -> None:
    catalog = {
        "format": CATALOG_FORMAT,
        "schema_version": 1,
        "source": "openf1",
        "updated_at": "2026-08-11T00:00:00Z",
        "years": [2023],
        "meetings": {
            "999": {
                "meeting_key": 999,
                "meeting_name": "Download Grand Prix",
                "circuit_short_name": "Marina Bay",
            }
        },
        "sessions": [
            {
                "session_key": 999,
                "meeting_key": 999,
                "session_name": "Race",
                "session_type": "Race",
                "circuit_short_name": "Marina Bay",
                "location": "Singapore",
                "date_start": "2023-09-17T12:00:00+00:00",
                "date_end": "2023-09-17T14:00:00+00:00",
                "gmt_offset": "08:00:00",
                "year": 2023,
            }
        ],
    }
    recording = json.loads(RECORDING.read_text(encoding="utf-8"))
    recording["session_key"] = 999
    recording["endpoints"]["sessions"][0]["session_key"] = 999
    recording["endpoints"]["sessions"][0]["meeting_key"] = 999
    recording["endpoints"]["meetings"][0]["meeting_key"] = 999
    recording["endpoints"]["meetings"][0]["meeting_name"] = "Download Grand Prix"
    (tmp_path / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")

    with TestClient(
        create_app(tmp_path, capture_session=lambda session_key: recording)
    ) as client:
        before = client.get("/api/v1/catalog").json()
        downloaded = client.post("/api/v1/download?session_key=999")
        after = client.get("/api/v1/catalog").json()
        state = client.get("/api/v1/state?session_key=999").json()

    assert before["downloadsEnabled"] is True
    assert before["sessions"][0]["available"] is False
    assert downloaded.status_code == 200
    assert downloaded.json()["status"] == "available"
    assert after["sessions"][0]["available"] is True
    assert state["data"]["session"]["key"] == "999"
    assert (tmp_path / "openf1-999.json").exists()


def test_delete_replay_keeps_durable_context_and_redownload_restores_it(
    tmp_path: Path,
) -> None:
    catalog = {
        "format": CATALOG_FORMAT,
        "schema_version": 1,
        "source": "openf1",
        "updated_at": "2026-08-11T00:00:00Z",
        "years": [2023],
        "meetings": {
            "999": {
                "meeting_key": 999,
                "meeting_name": "Durable Grand Prix",
                "circuit_short_name": "Durable Circuit",
                "circuit": {
                    "key": "77",
                    "name": "Durable Circuit",
                    "path": [[0, 0], [1, 0], [0, 1]],
                    "source": "catalog",
                    "availability": {"path": "available"},
                },
            }
        },
        "sessions": [
            {
                "session_key": 999,
                "meeting_key": 999,
                "session_name": "Race",
                "session_type": "Race",
                "date_start": "2023-09-17T12:00:00+00:00",
                "date_end": "2023-09-17T14:00:00+00:00",
                "year": 2023,
            }
        ],
    }
    recording = json.loads(RECORDING.read_text(encoding="utf-8"))
    recording["session_key"] = 999
    recording["endpoints"]["sessions"][0].update(session_key=999, meeting_key=999)
    recording["endpoints"]["meetings"][0].update(
        meeting_key=999, meeting_name="Durable Grand Prix"
    )
    (tmp_path / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    (tmp_path / "openf1-999.json").write_text(json.dumps(recording), encoding="utf-8")
    pirelli = tmp_path / ".slipstream" / "pirelli" / "999" / "keep.json"
    source = tmp_path / ".slipstream" / "sources" / "999.json"
    context = tmp_path / ".slipstream" / "weekend-context" / "999" / "999.json"
    raw = tmp_path / ".slipstream" / "raw-timing" / "999" / "TimingData.jsonStream"
    unrelated = tmp_path / "unrelated.json"
    pirelli.parent.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    context.parent.mkdir(parents=True)
    raw.parent.mkdir(parents=True)
    pirelli.write_text("{}", encoding="utf-8")
    source.write_text("{}", encoding="utf-8")
    context.write_text("{}", encoding="utf-8")
    raw.write_text("raw", encoding="utf-8")
    unrelated.write_text(
        json.dumps(
            [
                {
                    "kind": "session",
                    "occurred_at": "2023-09-17T12:00:00Z",
                    "source": "fixture",
                    "payload": {"key": "1000", "name": "Other"},
                }
            ]
        ),
        encoding="utf-8",
    )

    with TestClient(
        create_app(
            tmp_path,
            capture_session=lambda _session_key: recording,
            prepare_weekend_context=lambda **_: {},
        )
    ) as client:
        before = client.get("/api/v1/catalog").json()["sessions"][0]
        deleted = client.delete("/api/v1/replay?session_key=999")
        after = client.get("/api/v1/catalog").json()["sessions"][0]
        restored = client.post("/api/v1/download?session_key=999")
        final = client.get("/api/v1/catalog").json()["sessions"][0]

    assert before["available"] is True
    assert deleted.status_code == 200
    assert after["available"] is False
    assert after["circuitShapeAvailable"] is True
    assert pirelli.is_file()
    assert source.is_file()
    assert not context.exists()
    assert not raw.exists()
    assert unrelated.is_file()
    assert restored.status_code == 200
    assert final["available"] is True


def test_download_never_reports_available_for_an_unusable_recording(tmp_path: Path) -> None:
    catalog = {
        "format": CATALOG_FORMAT,
        "schema_version": 1,
        "source": "openf1",
        "updated_at": "2026-08-11T00:00:00Z",
        "years": [2023],
        "meetings": {"999": {"meeting_key": 999, "meeting_name": "Test"}},
        "sessions": [
            {
                "session_key": 999,
                "meeting_key": 999,
                "session_name": "Race",
                "session_type": "Race",
                "date_start": "2023-09-17T12:00:00+00:00",
                "date_end": "2023-09-17T14:00:00+00:00",
                "year": 2023,
            }
        ],
    }
    (tmp_path / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")

    with TestClient(
        create_app(
            tmp_path,
            capture_session=lambda _session_key: {
                "format": "invalid-recording",
                "session_key": 999,
            },
        )
    ) as client:
        response = client.post("/api/v1/download?session_key=999")
        after = client.get("/api/v1/catalog").json()["sessions"][0]

    assert response.status_code == 502
    assert after["available"] is False
