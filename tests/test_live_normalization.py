import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from slipstream.api import create_app
from slipstream.catalog import CATALOG_FORMAT
from slipstream.events import NormalizedEvent
from slipstream.evidence import SessionEvidence
from slipstream.live import F1LiveAdapter, LiveSessionMismatch, PublicLiveSession
from slipstream.playback import ReplayController
from slipstream.state import RaceState

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "live"
    / "public-sprint-qualifying-initial.json"
)
RED_FLAG_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "live"
    / "public-dutch-gp-red-flag-suspension.json"
)


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


def red_flag_events() -> tuple:
    adapter = F1LiveAdapter("11353")
    events = []
    for row in red_flag_rows():
        events.extend(adapter.ingest(row))
    return tuple(events)


def red_flag_rows() -> list[dict[str, object]]:
    return json.loads(RED_FLAG_FIXTURE.read_text(encoding="utf-8"))["rows"]


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
    assert driver.x is None and driver.y is None
    assert driver.track_position is None
    assert driver.availability["track_position"] == "unavailable"

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


def test_current_aborted_status_outranks_stale_started_marker() -> None:
    adapter = F1LiveAdapter("11353")
    adapter.ingest(
        {
            "received_at": "2026-08-23T13:24:46Z",
            "stream": "SessionInfo",
            "source_timestamp": None,
            "initial": True,
            "payload": {"Key": 11353, "Name": "Race", "Type": "Race"},
        }
    )
    events = adapter.ingest(
        {
            "received_at": "2026-08-23T13:24:47Z",
            "stream": "SessionStatus",
            "source_timestamp": None,
            "initial": False,
            "payload": {"Status": "Aborted", "Started": "Started"},
        }
    )

    assert events[0].payload == {"status": "SUSPENDED"}


def test_real_dutch_red_flag_fixture_separates_control_and_marshal_state() -> None:
    controller = ReplayController(red_flag_events())

    before_start = controller.seek("2026-08-23T13:03:28Z")
    assert before_start.session.status == "UNKNOWN"

    started = controller.seek("2026-08-23T13:03:29Z")
    assert started.session.status == "RUNNING"

    yellow = controller.seek("2026-08-23T13:04:57Z")
    assert yellow.session.marshal_status == "YELLOW"
    assert yellow.session.display_status == "YELLOW"

    suspended = controller.seek("2026-08-23T13:05:28Z")
    assert suspended.session.status == "SUSPENDED"
    assert suspended.session.control_status == "RED_FLAG"
    assert suspended.session.display_status == "RED_FLAG"

    track_clear = controller.seek("2026-08-23T13:08:00.500Z")
    assert track_clear.session.status == "SUSPENDED"
    assert track_clear.session.control_status == "RED_FLAG"
    assert track_clear.session.marshal_status == "ALL_CLEAR"
    assert track_clear.session.display_status == "RED_FLAG"

    later_yellow = controller.seek("2026-08-23T13:08:29Z")
    assert later_yellow.session.marshal_status == "YELLOW"
    assert later_yellow.session.control_status == "RED_FLAG"
    assert later_yellow.session.display_status == "RED_FLAG"

    rewound = controller.seek("2026-08-23T13:05:00Z")
    assert rewound.session.status == "RUNNING"
    assert rewound.session.marshal_status == "YELLOW"
    assert rewound.session.control_status != "RED_FLAG"
    assert rewound.session.display_status == "YELLOW"


def test_exact_dutch_session_status_restart_clears_red_flag_latch() -> None:
    adapter = F1LiveAdapter("11353")
    events = []
    for row in red_flag_rows():
        events.extend(adapter.ingest(row))
    restart = adapter.ingest(
        {
            "received_at": "2026-08-23T13:33:00.200Z",
            "stream": "SessionData",
            "source_timestamp": "2026-08-23T13:33:00.088Z",
            "initial": False,
            "payload": {
                "StatusSeries": {
                    "99": {
                        "Utc": "2026-08-23T13:33:00.088Z",
                        "SessionStatus": "Started",
                    }
                }
            },
        }
    )
    events.extend(restart)
    controller = ReplayController(events)

    suspended = controller.seek("2026-08-23T13:32:59Z")
    assert suspended.session.status == "SUSPENDED"
    assert suspended.session.display_status == "RED_FLAG"

    assert any(
        event.occurred_at == "2026-08-23T13:33:00.088000Z"
        and event.kind == "session"
        and event.payload.get("status") == "RUNNING"
        for event in restart
    )
    resumed = controller.seek("2026-08-23T13:33:00.088Z")
    assert resumed.session.status == "RUNNING"
    assert resumed.session.control_status == "NORMAL"
    assert resumed.session.display_status == "GREEN"


def test_suspended_race_remains_a_live_capable_source() -> None:
    live = PublicLiveSession()
    asyncio.run(live.apply_rows("11353", red_flag_rows()))

    view = live.view("11353")
    assert live.state.session.status == "SUSPENDED"
    assert live.state.session.display_status == "RED_FLAG"
    assert view.status == "LIVE"
    assert view.phase == "LIVE"
    assert view.connected is True


def test_all_clear_ends_safety_car_control_but_not_red_flag_control() -> None:
    state = RaceState().apply(
        NormalizedEvent(
            kind="session",
            occurred_at="2026-08-23T13:00:00Z",
            source="f1-signalr-public",
            payload={"control_status": "SAFETY_CAR"},
        )
    )
    state = state.apply(
        NormalizedEvent(
            kind="session",
            occurred_at="2026-08-23T13:01:00Z",
            source="f1-signalr-public",
            payload={"marshal_status": "ALL_CLEAR", "control_status": "NORMAL"},
        )
    )

    assert state.session.control_status == "NORMAL"
    assert state.session.display_status == "GREEN"


def test_naive_provider_utc_race_control_timestamp_is_canonical_and_orderable() -> None:
    adapter = F1LiveAdapter("11344")
    session_events = adapter.ingest(
        {
            "received_at": "2026-08-23T13:04:08Z",
            "stream": "SessionInfo",
            "source_timestamp": None,
            "initial": True,
            "payload": {"Key": 11344, "Name": "Race"},
        }
    )
    race_control_events = adapter.ingest(
        {
            "received_at": "2026-08-23T13:04:09Z",
            "stream": "RaceControlMessages",
            "source_timestamp": None,
            "initial": True,
            "payload": {
                "Messages": {
                    "1": {
                        "Utc": "2026-08-23T12:12:06",
                        "Category": "Other",
                        "Message": "PIT LANE OPEN",
                    }
                }
            },
        }
    )

    assert race_control_events[0].occurred_at == "2026-08-23T12:12:06Z"
    controller = ReplayController((*session_events, *race_control_events))
    assert [event.kind for event in controller.events] == ["race_control", "session"]


def test_public_live_session_applies_fixture_deterministically() -> None:
    live = PublicLiveSession()
    asyncio.run(live.apply_rows("11344", fixture_rows()))

    view = live.view("11344")
    assert view.status == "LIVE"
    assert view.connected is True
    assert view.sequence == len(live.events)
    assert live.state.drivers["12"].position == 5


@pytest.mark.parametrize(
    ("session_key", "rows"),
    [("11344", fixture_rows()), ("11353", red_flag_rows())],
)
def test_live_head_matches_full_reducer_and_evidence_at_every_arrival_prefix(
    session_key: str,
    rows: list[dict[str, object]],
) -> None:
    adapter = F1LiveAdapter(session_key)
    live = PublicLiveSession()

    for row in rows:
        live._apply(
            adapter.ingest(row),
            str(row.get("received_at") or "2026-08-23T00:00:00Z"),
        )
        controller = ReplayController(live.events)
        controller.seek_cursor(len(live.events))
        assert live.state == controller.state
        assert live.evidence == SessionEvidence.from_events(live.events)


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
                    "path": [[0, 0], [10, 0], [5, 10]],
                    "source": "catalog-cache",
                    "availability": {"path": "available"},
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
    assert live_state["data"]["circuit"]["path"] == [
        [0.0, 0.0],
        [10.0, 0.0],
        [5.0, 10.0],
    ]
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


def test_live_rows_without_explicit_completion_remain_in_progress(
    tmp_path: Path,
) -> None:
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


def test_two_live_viewers_own_independent_cursor_safe_delays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_REFRESH", "0")
    now = datetime(2026, 8, 21, 15, 30, tzinfo=UTC)
    catalog = {
        "format": CATALOG_FORMAT,
        "schema_version": 1,
        "source": "openf1",
        "updated_at": "2026-08-21T15:00:00Z",
        "years": [2026],
        "meetings": {"1292": {"meeting_key": 1292, "meeting_name": "Dutch Grand Prix"}},
        "sessions": [
            {
                "session_key": 11344,
                "meeting_key": 1292,
                "session_name": "Sprint Qualifying",
                "session_type": "Sprint Qualifying",
                "date_start": "2026-08-21T15:00:00Z",
                "date_end": "2026-08-21T17:14:00Z",
                "gmt_offset": "02:00:00",
                "year": 2026,
            }
        ],
    }
    (tmp_path / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    rows = fixture_rows()
    for row in rows:
        if row["stream"] == "SessionInfo":
            row["payload"]["SessionStatus"] = "Started"
        if row["stream"] == "SessionStatus":
            row["payload"] = {"Started": "Started", "Status": "Started"}
    rows.extend(
        [
            {
                "received_at": "2026-08-22T01:15:10Z",
                "stream": "TimingData",
                "source_timestamp": "2026-08-22T01:15:10Z",
                "initial": False,
                "payload": {
                    "Lines": {
                        "12": {
                            "RacingNumber": "12",
                            "Position": "5",
                            "NumberOfLaps": 16,
                            "LastLapTime": {"Value": "1:11.700"},
                            "InPit": False,
                        }
                    }
                },
            },
            {
                "received_at": "2026-08-22T01:15:20Z",
                "stream": "TimingData",
                "source_timestamp": "2026-08-22T01:15:20Z",
                "initial": False,
                "payload": {
                    "Lines": {
                        "12": {
                            "RacingNumber": "12",
                            "Position": "5",
                            "NumberOfLaps": 17,
                            "LastLapTime": {"Value": "1:11.600"},
                            "InPit": False,
                        }
                    }
                },
            },
        ]
    )
    live = PublicLiveSession()
    asyncio.run(live.apply_rows("11344", rows))

    with (
        TestClient(
            create_app(
                tmp_path,
                now=lambda: now,
                public_live=True,
                live_session=live,
                prepare_weekend_context=lambda **_: {},
            )
        ) as client,
        client.websocket_connect(
            "/api/v1/stream?session_key=11344&mode=live"
        ) as viewer_live,
        client.websocket_connect(
            "/api/v1/stream?session_key=11344&mode=live"
        ) as viewer_delayed,
    ):
        latest = viewer_live.receive_json()
        delayed_initial = viewer_delayed.receive_json()
        viewer_delayed.send_json({"type": "delay", "seconds": 15})
        delayed = viewer_delayed.receive_json()
        latest_again = viewer_live.receive_json()

    assert latest["seq"] == delayed_initial["seq"]
    assert delayed["seq"] < latest["seq"]
    assert delayed["data"]["drivers"]["12"]["lap"] == 15
    assert latest["data"]["drivers"]["12"]["lap"] == 17
    assert delayed["analytics"]["sequence"] == delayed["seq"]
    assert latest["analytics"]["sequence"] == latest["seq"]
    assert delayed["live"]["delaySeconds"] == 15
    assert latest_again["live"]["delaySeconds"] == 0
    assert latest_again["seq"] == latest["seq"]


def test_live_product_phase_history_separates_transport_from_completion() -> None:
    async def scenario() -> tuple[str, ...]:
        async def rows():
            yield {
                "received_at": "2026-08-22T01:14:59Z",
                "stream": "SessionInfo",
                "source_timestamp": None,
                "initial": True,
                "payload": {"Key": 11344, "Name": "Race"},
            }
            yield {
                "received_at": "2026-08-22T01:15:00Z",
                "stream": "SessionStatus",
                "source_timestamp": None,
                "initial": True,
                "payload": {"Status": "Started"},
            }
            await asyncio.sleep(1)

        live = PublicLiveSession(
            row_source=rows,
            stale_after=0.01,
            maximum_backoff=0.01,
        )
        await live.start("11344", scheduled_start="2026-08-22T00:00:00+00:00")
        await asyncio.sleep(0.06)
        phases = live.phase_history
        assert live.view("11344").phase == "RECONNECTING"
        assert live.view("11344").replay_ready is False
        await live.stop()
        return phases

    phases = asyncio.run(scenario())
    assert {"CONNECTING", "LIVE", "STALE", "RECONNECTING"}.issubset(phases)
    assert not {"FINALIZING", "COMPLETE", "REPLAY_READY"}.intersection(phases)


def test_pre_event_and_completed_phase_paths_are_explicit(tmp_path: Path) -> None:
    future = datetime(2026, 8, 22, 2, 0, tzinfo=UTC)

    async def pre_event() -> str:
        async def no_rows():
            if False:
                yield {}

        live = PublicLiveSession(
            row_source=no_rows,
            now=lambda: datetime(2026, 8, 22, 1, 0, tzinfo=UTC),
        )
        await live.start("11344", scheduled_start=future.isoformat())
        await asyncio.sleep(0)
        phase = live.view("11344").phase
        await live.stop()
        return phase

    assert asyncio.run(pre_event()) == "PRE_EVENT"

    live = PublicLiveSession(
        normalized_recording_dir=tmp_path,
        finalization_drain=0,
    )
    asyncio.run(live.apply_rows("11344", fixture_rows()))
    assert live.phase_history[-3:] == ("FINALIZING", "COMPLETE", "REPLAY_READY")
