"""Representative public patches; never protected telemetry or an assumed timer."""

import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from slipstream.analytics import AnalyticsService, build_analytics_snapshot
from slipstream.api import create_app
from slipstream.catalog import CATALOG_FORMAT
from slipstream.events import NormalizedEvent
from slipstream.library import ReplayLibrary
from slipstream.live import PUBLIC_TOPICS, F1LiveAdapter, PublicLiveSession
from slipstream.playback import ReplayController
from slipstream.replay import replay
from slipstream.serialization import state_envelope
from slipstream.session_clock import cursor_session_clock
from slipstream.weekend import ContextAvailability

START = datetime(2026, 9, 4, 12, tzinfo=UTC)


def at(seconds):
    return (START + timedelta(seconds=seconds)).isoformat()


def row(stream, payload, seconds=0):
    return {
        "stream": stream,
        "payload": payload,
        "received_at": at(seconds),
        "source_timestamp": at(seconds),
    }


def session_row(name="Practice 2"):
    return row(
        "SessionInfo",
        {
            "Key": 999,
            "Name": name,
            "Type": name,
            "StartDate": at(0),
            "EndDate": at(3600),
            "Meeting": {"Key": 1293, "Name": "Italian Grand Prix"},
        },
    )


def normalize(rows):
    adapter = F1LiveAdapter("999")
    return tuple(event for item in rows for event in adapter.ingest(item))


def resource_for(tmp_path, events):
    path = tmp_path / "session.json"
    path.write_text(json.dumps([asdict(event) for event in events]), encoding="utf-8")
    return ReplayLibrary(path).get()


def segments():
    return [{"Segments": [{"Status": 0} for _ in range(8)]} for _ in range(3)]


def test_public_position_requires_full_inventory_and_known_progress():
    assert "Position.z" not in PUBLIC_TOPICS and "CarData.z" not in PUBLIC_TOPICS
    initial = [
        session_row(),
        row(
            "TimingData",
            {
                "Lines": {
                    "1": {
                        "RacingNumber": "1",
                        "NumberOfLaps": 4,
                        "InPit": False,
                    }
                }
            },
        ),
    ]
    assert replay(normalize(initial)).drivers["1"].track_position is None
    for inventory in [segments()[:2], [{"Segments": {"3": {"Status": 2049}}}] * 3]:
        events = normalize(
            [*initial, row("TimingData", {"Lines": {"1": {"Sectors": inventory}}}, 1)]
        )
        assert replay(events).drivers["1"].track_position is None

    base = [*initial, row("TimingData", {"Lines": {"1": {"Sectors": segments()}}}, 2)]
    for status in (0, 9999, None):
        events = normalize(
            [
                *base,
                row(
                    "TimingData",
                    {
                        "Lines": {
                            "1": {
                                "Sectors": {
                                    "1": {"Segments": {"3": {"Status": status}}}
                                },
                            }
                        }
                    },
                    3,
                ),
            ]
        )
        assert replay(events).drivers["1"].track_position is None
    events = normalize(
        [
            *base,
            row(
                "TimingData",
                {
                    "Lines": {
                        "1": {
                            "Sectors": {
                                "1": {
                                    "Segments": {
                                        "3": {"Status": 2049},
                                        "1": {"Status": 2048},
                                    }
                                }
                            },
                        }
                    }
                },
                3,
            ),
        ]
    )
    driver = replay(events).drivers["1"]
    assert driver.track_position == pytest.approx(12 / 24)
    assert driver.availability["track_position"] == "available"
    assert driver.x is None and driver.y is None and driver.z is None


def test_source_clock_utc_sparse_stop_resume_and_absence():
    events = normalize(
        [
            session_row(),
            row(
                "ExtrapolatedClock",
                {
                    "Remaining": "00:42:17",
                    "Utc": at(0),
                    "Extrapolating": True,
                },
                10,
            ),
            row("ExtrapolatedClock", {"Extrapolating": False}, 20),
            row("ExtrapolatedClock", {"Extrapolating": True}, 90),
        ]
    )
    initial = replay(events, event_limit=2)
    assert initial.session.session_clock == "00:42:07"
    stopped = replay(events, event_limit=3)
    assert cursor_session_clock(events, stopped, 3, at(80)) == "00:41:57"
    assert stopped.session.session_clock_running is False
    assert cursor_session_clock(events, replay(events), 4, at(100)) == "00:41:47"
    for invalid in (None, "NaN", "00:99:00", ""):
        absent = normalize(
            [session_row(), row("ExtrapolatedClock", {"Remaining": invalid})]
        )
        assert (
            cursor_session_clock(absent, replay(absent), len(absent), at(500)) is None
        )
    missing = normalize([session_row()])
    assert cursor_session_clock(missing, replay(missing), 1, at(500)) is None


def test_fresh_remaining_without_utc_is_not_backdated_to_merged_anchor():
    events = normalize(
        [
            session_row(),
            row(
                "ExtrapolatedClock",
                {
                    "Remaining": "00:10:00",
                    "Utc": at(0),
                    "Extrapolating": True,
                },
            ),
            row("ExtrapolatedClock", {"Remaining": "00:09:00"}, 60),
        ]
    )
    assert replay(events).session.session_clock == "00:09:00"
    assert (
        cursor_session_clock(events, replay(events), len(events), at(77)) == "00:08:43"
    )


def test_accumulated_sparse_segment_prefixes_do_not_prove_inventory():
    rows = [session_row()]
    for sector in range(3):
        rows.append(
            row(
                "TimingData",
                {
                    "Lines": {
                        "1": {
                            "Sectors": {
                                str(sector): {"Segments": {"0": {"Status": 2049}}}
                            },
                        }
                    }
                },
                sector,
            )
        )
    assert replay(normalize(rows)).drivers["1"].track_position is None


def test_legacy_qualifying_phase_uses_only_same_cursor_server_analytics(tmp_path):
    events = normalize([session_row("Qualifying")]) + (
        NormalizedEvent(
            "race_control",
            at(10),
            "fixture",
            {"category": "SessionStatus", "message": "SESSION STARTED"},
        ),
    )
    resource = resource_for(tmp_path, events)
    state = replay(events)
    analytics = build_analytics_snapshot(
        resource,
        state,
        sequence=len(events),
        as_of=at(10),
        context=ContextAvailability("absent", None),
    )
    assert state.session.qualifying_phase == "UNKNOWN"
    envelope = state_envelope(
        state, sequence=len(events), events=events, analytics=analytics
    )
    assert envelope["data"]["session"]["qualifying_phase"] == "Q1"
    assert state.session.qualifying_phase == "UNKNOWN"
    rest = state_envelope(state, sequence=len(events), events=events)
    assert rest["data"]["session"]["qualifying_phase"] == "Q1"
    other_cursor = state_envelope(
        state, sequence=len(events) - 1, events=events, analytics=analytics
    )
    assert other_cursor["data"]["session"]["qualifying_phase"] == "UNKNOWN"


@pytest.mark.parametrize(
    "name",
    ["Practice 1", "Practice 2", "Practice 3", "Qualifying", "Sprint Qualifying"],
)
def test_timed_sessions_have_no_actionable_race_dry_rule(tmp_path, name):
    events = normalize(
        [
            session_row(name),
            row(
                "TimingData",
                {
                    "Lines": {
                        "1": {"RacingNumber": "1", "NumberOfLaps": 3, "Position": "1"},
                    }
                },
            ),
        ]
    ) + (
        NormalizedEvent(
            "timing", at(1), "fixture", {"number": "1", "compound": "SOFT"}
        ),
    )
    resource = resource_for(tmp_path, events)
    model = build_analytics_snapshot(
        resource,
        replay(events),
        sequence=len(events),
        as_of=at(1),
        context=ContextAvailability("absent", None),
    )
    assert (
        model["sportingRules"]["dryTyreRequirement"]["perDriverState"]["1"]
        == "NOT_APPLICABLE"
    )
    assert model["drivers"]["1"]["strategy"]["dryTyreRequirement"] == "NOT_APPLICABLE"
    assert (
        model["publishedStrategy"]["drivers"]["1"]["dryTyreRequirement"]
        == "NOT_APPLICABLE"
    )
    assert not any(
        "Future" in fact or "Same-race" in fact
        for fact in model["drivers"]["1"]["read"]["facts"]
    )


@pytest.mark.parametrize(
    "name,expected", [("Race", "UNSATISFIED"), ("Sprint", "NOT_APPLICABLE")]
)
def test_verified_race_and_sprint_dry_rule_unchanged(tmp_path, name, expected):
    events = normalize([session_row(name)]) + (
        NormalizedEvent("driver", at(0), "fixture", {"number": "1"}),
        NormalizedEvent(
            "timing", at(1), "fixture", {"number": "1", "compound": "SOFT"}
        ),
    )
    resource = resource_for(tmp_path, events)
    model = build_analytics_snapshot(
        resource,
        replay(events),
        sequence=len(events),
        as_of=at(1),
        context=ContextAvailability("absent", None),
    )
    assert (
        model["sportingRules"]["dryTyreRequirement"]["perDriverState"]["1"] == expected
    )


@pytest.mark.parametrize(
    "kind,prefix", [("qualifying", "Q"), ("sprint_qualifying", "SQ")]
)
def test_qualifying_clock_cache_and_phases_use_exact_cursor(tmp_path, kind, prefix):
    events = [
        NormalizedEvent(
            "session",
            at(0),
            "fixture",
            {
                "key": "999",
                "name": "Sprint Qualifying" if prefix == "SQ" else "Qualifying",
                "session_type": "Qualifying",
                "session_kind": kind,
                "layout_family": "qualifying",
                "started_at": at(0),
                "qualifying_phase": f"{prefix}1",
                "session_clock": "00:10:00",
                "session_clock_running": True,
            },
        )
    ]
    for phase, seconds in [(2, 300), (3, 600)]:
        events.append(
            NormalizedEvent(
                "session",
                at(seconds),
                "fixture",
                {
                    "qualifying_phase": f"{prefix}{phase}",
                    "session_clock": "00:08:00",
                },
            )
        )
    resource = resource_for(tmp_path, events)
    service = AnalyticsService()
    for phase, seconds in [(1, 0), (2, 300), (3, 600)]:
        state = replay(events, event_limit=phase)
        for elapsed in (3, 17):
            snapshot = service.snapshot(
                resource,
                state,
                sequence=phase,
                as_of=at(seconds + elapsed),
                context=ContextAvailability("absent", None),
            )
            envelope = state_envelope(
                state, events=events, sequence=phase, session_time=at(seconds + elapsed)
            )
            expected = f"00:{9 if phase == 1 else 7:02d}:{60 - elapsed:02d}"
            assert snapshot["qualifying"]["phase"] == f"{prefix}{phase}"
            assert snapshot["qualifying"]["sessionClock"] == expected
            assert envelope["data"]["session"]["session_clock"] == expected


def test_delayed_live_clock_positions_and_facts_share_cursor(tmp_path: Path):
    rows = [
        session_row(),
        row("SessionStatus", {"Status": "Started"}),
        row(
            "ExtrapolatedClock",
            {"Remaining": "00:50:00", "Utc": at(0), "Extrapolating": True},
        ),
        row(
            "TimingData",
            {
                "Lines": {
                    "1": {
                        "RacingNumber": "1",
                        "Position": "1",
                        "NumberOfLaps": 1,
                        "InPit": False,
                    }
                }
            },
        ),
        row("WeatherData", {"AirTemp": "20"}, 20),
        row(
            "TimingData",
            {"Lines": {"1": {"NumberOfLaps": 2, "GapToLeader": "+0.123"}}},
            60,
        ),
        row("TimingData", {"Lines": {"1": {"Sectors": segments()}}}, 180),
        row(
            "TimingData",
            {"Lines": {"1": {"Sectors": {"1": {"Segments": {"3": {"Status": 2049}}}}}}},
            200,
        ),
        row("WeatherData", {"AirTemp": "25"}, 270),
        row("TimingData", {"Lines": {"1": {"NumberOfLaps": 4}}}, 300),
    ]
    live = PublicLiveSession()
    asyncio.run(live.apply_rows("999", rows))
    (tmp_path / "catalog.json").write_text(
        json.dumps(
            {
                "format": CATALOG_FORMAT,
                "schema_version": 1,
                "source": "fixture",
                "years": [2026],
                "updated_at": at(0),
                "meetings": {
                    "1293": {"meeting_key": 1293, "meeting_name": "Italian Grand Prix"}
                },
                "sessions": [
                    {
                        "session_key": 999,
                        "meeting_key": 1293,
                        "session_name": "Practice 2",
                        "session_type": "Practice",
                        "date_start": at(0),
                        "date_end": at(3600),
                        "year": 2026,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with TestClient(
        create_app(
            tmp_path,
            now=lambda: START + timedelta(seconds=300),
            public_live=True,
            live_session=live,
            prepare_weekend_context=lambda **_: {},
        )
    ) as client:
        capabilities = client.get("/api/v1/capabilities?session_key=999").json()
        assert capabilities["positionMode"] == "timing_estimate"
        assert capabilities["capabilities"]["positions"] is True
        assert capabilities["capabilities"]["location_xy"] is False
        with client.websocket_connect(
            "/api/v1/stream?session_key=999&mode=live"
        ) as viewer:
            latest = viewer.receive_json()
            viewer.send_json({"type": "delay", "seconds": 137})
            delayed = viewer.receive_json()
            viewer.send_json({"type": "delay", "seconds": 300})
            maximum = viewer.receive_json()
            for invalid in (301, -1, "NaN", "bad", None):
                viewer.send_json({"type": "delay", "seconds": invalid})
                assert viewer.receive_json()["type"] == "error"
                assert viewer.receive_json()["live"]["delaySeconds"] == 300
            viewer.send_json({"type": "reset"})
            reset = viewer.receive_json()
    assert latest["data"]["session"]["session_clock"] == "00:45:00"
    assert delayed["data"]["session"]["session_clock"] == "00:47:17"
    assert delayed["sessionTime"] == at(163)
    assert delayed["live"]["delaySeconds"] == 137
    assert delayed["data"]["drivers"]["1"]["lap"] == 2
    assert delayed["data"]["weather"]["air_temperature"] == 20
    assert delayed["analytics"]["sequence"] == delayed["seq"]
    assert delayed["analytics"]["asOf"] == delayed["sessionTime"]
    assert delayed["live"]["positionMode"] == "unavailable"
    assert latest["live"]["positionMode"] == "timing_estimate"
    assert maximum["data"]["session"]["session_clock"] == "00:50:00"
    assert reset["live"]["delaySeconds"] == 0
    assert reset["data"] == latest["data"]
    controller = ReplayController(live.events)
    controller.seek_delay(137)
    replay_snapshot = state_envelope(
        controller.state,
        events=controller.events,
        sequence=controller.cursor,
        session_time=controller.playhead,
    )
    assert json.loads(json.dumps(replay_snapshot["data"])) == delayed["data"]


def test_fractional_sparse_clock_updates_do_not_accumulate_rounding_drift():
    rows = [
        session_row(),
        row(
            "ExtrapolatedClock",
            {
                "Remaining": "00:10:00",
                "Utc": at(0),
                "Extrapolating": True,
            },
        ),
    ]
    rows.extend(
        row("ExtrapolatedClock", {"Utc": at(value)}, value)
        for value in (0.25, 0.5, 0.75, 1)
    )
    events = normalize(rows)
    assert (
        cursor_session_clock(events, replay(events), len(events), at(1)) == "00:09:59"
    )
