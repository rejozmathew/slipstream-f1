"""Opening and incident regressions; raw feed examples here are synthetic."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from slipstream.api import create_app
from slipstream.events import NormalizedEvent, parse_timestamp
from slipstream.library import ReplayLibrary
from slipstream.live import F1LiveAdapter, PublicLiveSession
from slipstream.live_recording import NormalizedLiveRecorder
from slipstream.replay import load_events, replay


def event(at, payload, kind="session"):
    return NormalizedEvent(kind, at, "f1-signalr-public", payload)


def session_events():
    return [
        event(
            "2026-09-05T14:00:00Z",
            {
                "key": "11357",
                "name": "Qualifying",
                "session_type": "Qualifying",
                "session_kind": "qualifying",
                "layout_family": "qualifying",
                "started_at": "2026-09-05T14:00:00Z",
                "ended_at": "2026-09-05T15:00:00Z",
                "gmt_offset": "02:00:00",
                "status": "RUNNING",
                "qualifying_phase": "Q1",
            },
        ),
        event(
            "2026-09-05T14:12:52Z",
            {
                "key": "11357",
                "started_at": "2026-09-05T16:00:00",
                "ended_at": "2026-09-05T17:00:00",
                "gmt_offset": "02:00:00",
            },
        ),
        event("2026-09-05T14:18:00Z", {"status": "FINISHED"}),
        event("2026-09-05T14:25:00Z", {"status": "RUNNING", "qualifying_phase": "Q2"}),
        event(
            "2026-09-05T14:28:53Z",
            {"number": "30", "best_lap": "1:22.828", "lap": 12},
            "timing",
        ),
    ]


def test_legacy_live_identity_uses_provider_offset_once(tmp_path):
    path = tmp_path / "live-11357.json"
    path.write_text(json.dumps([asdict(e) for e in session_events()]))
    state = replay(load_events(path))
    assert parse_timestamp(state.session.started_at) == datetime(
        2026, 9, 5, 14, tzinfo=UTC
    )
    library = ReplayLibrary(path)
    descriptor = library.descriptors["11357"]
    assert parse_timestamp(descriptor.date_start) == datetime(
        2026, 9, 5, 14, tzinfo=UTC
    )
    with TestClient(create_app(path, public_live=False)) as client:
        metadata = client.get("/api/v1/replay").json()
        assert metadata["durationSeconds"] >= 0
        assert parse_timestamp(metadata["endTime"]) >= parse_timestamp(
            "2026-09-05T14:28:53Z"
        )


def test_live_source_normalizes_provider_local_identity():
    adapter = F1LiveAdapter("11357")
    events = adapter.ingest(
        {
            "stream": "SessionInfo",
            "source_timestamp": "2026-09-05T14:00:00Z",
            "payload": {
                "Key": 11357,
                "Name": "Qualifying",
                "Type": "Qualifying",
                "StartDate": "2026-09-05T16:00:00",
                "EndDate": "2026-09-05T17:00:00",
                "GmtOffset": "02:00:00",
            },
        }
    )
    state = replay(list(events))
    assert parse_timestamp(state.session.started_at) == datetime(
        2026, 9, 5, 14, tzinfo=UTC
    )


def test_q2_catchup_and_partial_restart_keep_collecting(tmp_path):
    async def scenario():
        queued = asyncio.Queue()

        async def rows():
            while True:
                yield await queued.get()

        live = PublicLiveSession(
            row_source=rows, normalized_recording_dir=tmp_path, finalization_drain=0.01
        )
        await live.start("11357", seed_events=session_events())
        try:
            await asyncio.sleep(0.04)
            assert not live.view("11357").replay_ready
            assert live.view("11357").phase not in {
                "FINALIZING",
                "COMPLETE",
                "REPLAY_READY",
            }
            await queued.put(
                {
                    "stream": "SessionInfo",
                    "source_timestamp": "2026-09-05T14:29:00Z",
                    "payload": {
                        "Key": 11357,
                        "Name": "Qualifying",
                        "Type": "Qualifying",
                    },
                }
            )
            await queued.put(
                {
                    "stream": "TimingData",
                    "source_timestamp": "2026-09-05T14:29:01Z",
                    "payload": {
                        "Lines": {
                            "30": {
                                "NumberOfLaps": 13,
                                "BestLapTime": {"Value": "1:22.000"},
                            }
                        }
                    },
                }
            )
            for _ in range(50):
                if live.state.drivers.get("30") and live.state.drivers["30"].lap == 13:
                    break
                await asyncio.sleep(0.005)
            assert live.state.drivers["30"].lap == 13
            assert not (tmp_path / "live-11357.json").exists()
        finally:
            await live.stop()

    asyncio.run(scenario())


def test_recorder_orders_actual_instants_and_coalesces_batch_duplicates(tmp_path):
    recorder = NormalizedLiveRecorder(tmp_path, "11357")
    later = event("2026-09-05T14:00:00.031000Z", {"status": "RUNNING"})
    earlier = event("2026-09-05T14:00:00Z", {"status": "SCHEDULED"})
    same = event("2026-09-05T16:00:00+02:00", {"qualifying_phase": "Q1"})
    accepted = recorder.append((later, earlier, same, later))
    assert len(accepted) == 3
    recorded = load_events(recorder.finalize())
    assert [e.payload for e in recorded] == [
        earlier.payload,
        same.payload,
        later.payload,
    ]


def test_replay_orders_before_applying_event_count():
    later = event("2026-09-05T14:00:00.031000Z", {"status": "RUNNING"})
    earlier = event("2026-09-05T14:00:00Z", {"status": "SCHEDULED"})
    assert replay([later, earlier]).session.status == "RUNNING"
    assert replay([later, earlier], event_limit=1).session.status == "SCHEDULED"


def test_recording_discovery_does_not_reduce_or_scan_operational_json(
    tmp_path, monkeypatch
):
    path = tmp_path / "live-11357.json"
    path.write_text(json.dumps([asdict(e) for e in session_events()]))
    operational = tmp_path / ".slipstream" / "pirelli"
    operational.mkdir(parents=True)
    (operational / "not-a-recording.json").write_text(path.read_text())

    def forbidden(*args, **kwargs):
        raise AssertionError("Discovery must not run the replay reducer")

    monkeypatch.setattr("slipstream.state.RaceState.apply", forbidden)
    library = ReplayLibrary(tmp_path)
    assert library.descriptors["11357"].path == path
