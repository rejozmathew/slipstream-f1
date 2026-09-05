"""Synthetic finalization failures and delayed FP3-to-Qualifying ownership."""

import asyncio
import json
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from slipstream.api import create_app
from slipstream.catalog import CATALOG_FORMAT
from slipstream.events import NormalizedEvent
from slipstream.live import PublicLiveSession
from slipstream.live_recording import NormalizedLiveRecorder


def test_publication_failure_is_visible_and_retries(tmp_path, monkeypatch):
    original = NormalizedLiveRecorder.finalize
    attempts = []

    def flaky(recorder):
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError("SYNTHETIC transient disk failure")
        return original(recorder)

    monkeypatch.setattr(NormalizedLiveRecorder, "finalize", flaky)

    async def rows():
        while True:
            await asyncio.sleep(1)
            yield {}

    async def run():
        live = PublicLiveSession(
            row_source=rows,
            normalized_recording_dir=tmp_path,
            finalization_drain=0,
            maximum_backoff=0.03,
        )
        await live.start(
            "100",
            seed_events=[
                NormalizedEvent(
                    "session",
                    "2026-09-05T14:00:00Z",
                    "synthetic",
                    {
                        "key": "100",
                        "name": "Qualifying",
                        "session_kind": "qualifying",
                        "session_complete": True,
                        "status": "FINISHED",
                    },
                )
            ],
        )
        try:
            for _ in range(100):
                if live.view("100").error:
                    break
                await asyncio.sleep(0.002)
            assert "retrying" in live.view("100").error
            for _ in range(100):
                if live.view("100").replay_ready:
                    break
                await asyncio.sleep(0.005)
            assert live.view("100").replay_ready
            assert live.view("100").error is None
            assert len(attempts) == 2
        finally:
            await live.stop()

    asyncio.run(run())


@pytest.mark.parametrize("failed_publication", [False, True])
def test_fp3_delayed_tail_survives_qualifying_target_and_rest_reconnect(
    tmp_path, monkeypatch, failed_publication
):
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_REFRESH", "0")
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_BACKFILL", "0")
    clock = [datetime(2026, 9, 5, 13, 59, 58, tzinfo=UTC)]
    finish = threading.Event()
    allow_publication = threading.Event()
    if not failed_publication:
        allow_publication.set()
    original_finalize = NormalizedLiveRecorder.finalize

    def finalize(recorder):
        if recorder.session_key == "100" and not allow_publication.is_set():
            raise OSError("SYNTHETIC publication unavailable while next session begins")
        return original_finalize(recorder)

    monkeypatch.setattr(NormalizedLiveRecorder, "finalize", finalize)
    catalog = {
        "format": CATALOG_FORMAT,
        "schema_version": 1,
        "source": "openf1",
        "updated_at": "2026-09-05T13:00:00Z",
        "years": [2026],
        "meetings": {},
        "sessions": [
            {
                "session_key": "100",
                "meeting_key": "M",
                "session_name": "Practice 3",
                "session_type": "Practice",
                "date_start": "2026-09-05T13:00:00Z",
                "date_end": "2026-09-05T14:00:00Z",
                "year": 2026,
            },
            {
                "session_key": "200",
                "meeting_key": "M",
                "session_name": "Qualifying",
                "session_type": "Qualifying",
                "date_start": "2026-09-05T14:00:00Z",
                "date_end": "2026-09-05T15:00:00Z",
                "year": 2026,
            },
        ],
    }
    (tmp_path / "catalog.json").write_text(json.dumps(catalog))

    def row(stream, payload, at):
        return {
            "stream": stream,
            "payload": payload,
            "source_timestamp": at,
            "received_at": at,
        }

    async def rows():
        key = live.target_session_key
        yield row(
            "SessionInfo",
            {
                "Key": int(key),
                "Name": "Practice 3" if key == "100" else "Qualifying",
                "Type": "Practice" if key == "100" else "Qualifying",
            },
            "2026-09-05T13:00:00Z" if key == "100" else "2026-09-05T14:00:01Z",
        )
        yield row(
            "SessionStatus",
            {"Status": "Started"},
            "2026-09-05T13:00:00Z" if key == "100" else "2026-09-05T14:00:01Z",
        )
        if key == "100":
            yield row(
                "TimingData",
                {"Lines": {"44": {"NumberOfLaps": 11}}},
                "2026-09-05T13:57:00Z",
            )
            yield row(
                "TimingData",
                {"Lines": {"44": {"NumberOfLaps": 12}}},
                "2026-09-05T13:59:58Z",
            )
            while not finish.is_set():
                await asyncio.sleep(0.005)
            yield row(
                "TimingData",
                {"Lines": {"44": {"NumberOfLaps": 99}}},
                "2026-09-05T14:00:00Z",
            )
            yield row("SessionStatus", {"Status": "Finalised"}, "2026-09-05T14:00:00Z")
        else:
            yield row(
                "TimingData",
                {"Lines": {"44": {"NumberOfLaps": 1}}},
                "2026-09-05T14:00:02Z",
            )
        while True:
            await asyncio.sleep(1)
            yield row("Heartbeat", {}, "2026-09-05T14:00:02Z")

    live = PublicLiveSession(
        row_source=rows,
        now=lambda: clock[0],
        finalization_drain=0.01,
        maximum_backoff=0.01,
    )
    with TestClient(
        create_app(
            tmp_path,
            now=lambda: clock[0],
            public_live=True,
            live_session=live,
            prepare_weekend_context=lambda **_: {},
        )
    ) as client:
        for _ in range(100):
            if live.state.drivers.get("44") and live.state.drivers["44"].lap == 12:
                break
            time.sleep(0.005)
        with client.websocket_connect(
            "/api/v1/stream?session_key=100&mode=live&delay_seconds=137"
        ) as viewer:
            first = viewer.receive_json()
            assert first["data"]["drivers"]["44"]["lap"] == 11
            clock[0] += timedelta(seconds=2)
            finish.set()
            for _ in range(200):
                if live.target_session_key == "200" and live.state.drivers.get("44"):
                    break
                time.sleep(0.005)
            assert live.target_session_key == "200"
            assert live.state.drivers["44"].lap == 1
            delayed = client.get(
                "/api/v1/state?session_key=100&mode=live&delay_seconds=137"
            ).json()
            assert delayed["data"]["session"]["key"] == "100"
            assert delayed["data"]["drivers"]["44"]["lap"] == 11
            assert delayed.get("handoff") is None
            if failed_publication:
                assert delayed["live"]["phase"] == "FINALIZING"
                assert "retrying" in delayed["live"]["error"]
                assert not delayed["live"]["replayReady"]
            allow_publication.set()
            for _ in range(100):
                if live.view("100").replay_ready:
                    break
                time.sleep(0.005)
            assert live.view("100").replay_ready
            clock[0] += timedelta(seconds=140)
            viewer.send_json({"type": "snapshot"})
            for _ in range(10):
                final = viewer.receive_json()
                if final.get("handoff"):
                    break
            assert final["handoff"] == "REPLAY_READY"
            assert final["data"]["session"]["key"] == "100"
            assert final["data"]["drivers"]["44"]["lap"] == 99
            assert final["analytics"]["sequence"] == final["seq"]
            assert live.target_session_key == "200"
