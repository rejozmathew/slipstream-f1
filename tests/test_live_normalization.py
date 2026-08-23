import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from slipstream.api import create_app
from slipstream.catalog import CATALOG_FORMAT
from slipstream.live import F1LiveAdapter, LiveSessionMismatch, PublicLiveSession
from slipstream.state import RaceState

FIXTURE = Path(__file__).parent / "fixtures" / "live" / "public-sprint-qualifying-initial.json"


def fixture_rows() -> list[dict[str, object]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["rows"]


def normalized_fixture() -> tuple[RaceState, tuple]:
    adapter = F1LiveAdapter("11344")
    state = RaceState()
    events = []
    for row in fixture_rows():
        emitted = adapter.ingest(row)
        events.extend(emitted)
        for event in emitted:
            state = state.apply(event)
    return state, tuple(events)


def test_real_public_fixture_normalizes_into_canonical_race_state() -> None:
    state, events = normalized_fixture()

    assert state.session.key == "11344"
    assert state.session.meeting_name == "Dutch Grand Prix"
    assert state.session.name == "Sprint Qualifying"
    assert state.session.session_kind == "sprint_qualifying"
    assert state.session.layout_family == "qualifying"
    assert state.session.status == "FINISHED"
    assert state.session.track_status == "YELLOW"

    driver = state.drivers["12"]
    assert (driver.code, driver.name, driver.team) == (
        "ANT",
        "Kimi ANTONELLI",
        "Mercedes",
    )
    assert driver.position == 5
    assert driver.lap == 15
    assert driver.compound == "SOFT"
    assert driver.tyre_age == 3
    assert driver.stint_laps == 3
    assert driver.pit_count == 3
    assert driver.last_lap == "1:11.794"
    assert driver.best_lap == "1:11.794"
    assert driver.status == "STOPPED"
    assert driver.x is None and driver.y is None and driver.track_position is None

    assert state.weather.air_temperature == 18.9
    assert state.weather.track_temperature == 30.1
    assert state.weather.humidity == 59.6
    assert state.weather.rainfall is False
    assert {event.source for event in events} == {"f1-signalr-public"}
    assert all(event.received_at == "2026-08-22T01:15:00Z" for event in events)


def test_live_adapter_rejects_a_different_provider_session() -> None:
    row = next(row for row in fixture_rows() if row["stream"] == "SessionInfo")
    with pytest.raises(LiveSessionMismatch, match="does not match"):
        F1LiveAdapter("different-session").ingest(row)


def test_public_live_session_applies_fixture_deterministically() -> None:
    live = PublicLiveSession()
    asyncio.run(live.apply_rows("11344", fixture_rows()))

    view = live.view("11344")
    assert view.status == "LIVE"
    assert view.connected is True
    assert view.sequence == len(live.events)
    assert live.state.drivers["12"].position == 5


def test_api_separates_live_transport_from_replay_availability(tmp_path: Path) -> None:
    now = datetime(2026, 8, 21, 15, 30, tzinfo=UTC)
    catalog = {
        "format": CATALOG_FORMAT,
        "schema_version": 1,
        "source": "openf1",
        "updated_at": "2026-08-21T15:00:00Z",
        "years": [2026],
        "meetings": {
            "1292": {
                "meeting_key": 1292,
                "meeting_name": "Dutch Grand Prix",
                "location": "Zandvoort",
                "circuit_short_name": "Zandvoort",
                "circuit": {
                    "key": "55",
                    "name": "Zandvoort",
                    "year": 2026,
                    "rotation": 0,
                    "path": [],
                    "source": None,
                    "availability": {"path": "unavailable"},
                },
            }
        },
        "sessions": [
            {
                "session_key": 11344,
                "meeting_key": 1292,
                "session_name": "Sprint Qualifying",
                "session_type": "Sprint Qualifying",
                "circuit_short_name": "Zandvoort",
                "location": "Zandvoort",
                "date_start": "2026-08-21T15:00:00Z",
                "date_end": "2026-08-21T17:14:00Z",
                "gmt_offset": "02:00:00",
                "year": 2026,
            }
        ],
    }
    (tmp_path / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    live = PublicLiveSession()
    asyncio.run(live.apply_rows("11344", fixture_rows()))

    with TestClient(
        create_app(tmp_path, now=lambda: now, public_live=True, live_session=live)
    ) as client:
        catalog_payload = client.get("/api/v1/catalog").json()
        live_state = client.get("/api/v1/state?session_key=11344&mode=live").json()
        replay_state = client.get("/api/v1/state?session_key=11344&mode=replay").json()
        capabilities = client.get("/api/v1/capabilities?session_key=11344").json()

    selected = catalog_payload["sessions"][0]
    assert catalog_payload["liveSessionKey"] == "11344"
    assert selected["liveAvailable"] is True
    assert selected["liveConnected"] is True
    assert selected["available"] is False
    assert live_state["mode"] == "live"
    assert live_state["live"]["status"] == "LIVE"
    assert live_state["data"]["drivers"]["12"]["position"] == 5
    assert replay_state["mode"] == "replay"
    assert replay_state["data"]["drivers"] == {}
    assert capabilities["replayAvailable"] is False
    assert capabilities["liveAvailable"] is True
    assert capabilities["liveConnected"] is True
    assert capabilities["positionMode"] == "unavailable"
    assert capabilities["capabilities"]["location_xy"] is False


def test_completed_live_fixture_is_atomically_exposed_as_immediate_replay(
    tmp_path: Path,
) -> None:
    refreshed: list[Path] = []
    live = PublicLiveSession(
        normalized_recording_dir=tmp_path,
        finalization_drain=0,
        on_recording_finalized=lambda path: not refreshed.append(path),
    )

    asyncio.run(live.apply_rows("11344", fixture_rows()))

    final_path = tmp_path / "live-11344.json"
    assert live.view("11344").phase == "REPLAY_READY"
    assert live.view("11344").replay_ready is True
    assert refreshed == [final_path]
    assert final_path.is_file()
    assert not (tmp_path / "live-11344.in-progress.jsonl").exists()
    recorded = json.loads(final_path.read_text(encoding="utf-8"))
    assert len(recorded) == len(live.events)
    rebuilt = RaceState()
    for raw in recorded:
        from slipstream.events import NormalizedEvent

        rebuilt = rebuilt.apply(NormalizedEvent.from_mapping(raw))
    assert rebuilt == live.state


def test_live_rows_without_explicit_completion_remain_in_progress(tmp_path: Path) -> None:
    rows = fixture_rows()
    for row in rows:
        if row["stream"] == "SessionInfo":
            row["payload"]["SessionStatus"] = "Started"
        if row["stream"] == "SessionStatus":
            row["payload"] = {"Started": "Started", "Status": "Started"}
    live = PublicLiveSession(
        normalized_recording_dir=tmp_path,
        finalization_drain=0,
    )

    asyncio.run(live.apply_rows("11344", rows))

    assert live.view("11344").phase == "LIVE"
    assert not (tmp_path / "live-11344.json").exists()
    assert (tmp_path / "live-11344.in-progress.jsonl").is_file()