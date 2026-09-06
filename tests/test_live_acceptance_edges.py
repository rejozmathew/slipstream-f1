"""Synthetic C02/C03/C05/C10 inputs through production adapter/lifecycle paths."""

import asyncio
import itertools
import json
import threading
import time
from dataclasses import asdict
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from slipstream.api import create_app
from slipstream.events import NormalizedEvent
from slipstream.live import F1LiveAdapter, PublicLiveSession, decode_signalr_text

IDENTITY = NormalizedEvent(
    "session",
    "2026-09-05T14:00:00Z",
    "synthetic",
    {
        "key": "11357",
        "name": "Qualifying",
        "session_kind": "qualifying",
        "started_at": "2026-09-05T14:00:00Z",
        "ended_at": "2026-09-05T15:00:00Z",
        "status": "RUNNING",
        "qualifying_phase": "Q1",
    },
)


async def idle_rows():
    while True:
        await asyncio.sleep(10)
        yield {}


def apply_raw(live, adapter, topic, payload, at):
    raw = (
        json.dumps({"type": 1, "target": "feed", "arguments": [topic, payload, at]})
        + "\x1e"
    )
    rows, _ = decode_signalr_text(raw, received_at="2026-09-05T14:29:00Z")
    for row in rows:
        live._apply(adapter.ingest(row), received_at=row["received_at"])


@pytest.mark.parametrize("order", list(itertools.permutations(range(3))))
def test_q2_history_topic_delivery_orders_keep_collecting(tmp_path, order):
    async def run():
        live = PublicLiveSession(
            row_source=idle_rows,
            normalized_recording_dir=tmp_path,
            finalization_drain=0,
        )
        await live.start("11357", seed_events=[IDENTITY])
        adapter = F1LiveAdapter("11357")
        topics = [
            (
                "SessionData",
                {
                    "StatusSeries": {
                        "0": {
                            "Utc": "2026-09-05T14:18:00Z",
                            "SessionStatus": "Finished",
                        },
                        "1": {
                            "Utc": "2026-09-05T14:25:00Z",
                            "SessionStatus": "Started",
                        },
                    },
                    "Series": {"1": {"QualifyingPart": 2}},
                },
                "2026-09-05T14:28:53Z",
            ),
            ("SessionStatus", {"Status": "Started"}, "2026-09-05T14:28:53Z"),
            (
                "RaceControlMessages",
                {
                    "Messages": {
                        "0": {
                            "Utc": "2026-09-05T14:18:00Z",
                            "Category": "Flag",
                            "Flag": "CHEQUERED",
                            "Scope": "Track",
                            "Message": "CHEQUERED FLAG",
                        }
                    }
                },
                "2026-09-05T14:28:53Z",
            ),
        ]
        try:
            apply_raw(
                live,
                adapter,
                "SessionInfo",
                {"Key": 11357, "Name": "Qualifying", "Type": "Qualifying"},
                "2026-09-05T14:00:00Z",
            )
            for index in order:
                apply_raw(live, adapter, *topics[index])
                await asyncio.sleep(0.002)
                assert not live._completion_observed
            apply_raw(
                live,
                adapter,
                "TimingData",
                {"Lines": {"44": {"NumberOfLaps": 13}}},
                "2026-09-05T14:29:00Z",
            )
            assert live.state.drivers["44"].lap == 13
            assert live.state.session.status == "RUNNING"
            assert live.state.session.qualifying_phase == "Q2"
            assert not live.view("11357").replay_ready
        finally:
            await live.stop()

    asyncio.run(run())


def test_full_qualifying_segments_and_explicit_red_flag_restart(tmp_path):
    async def run():
        live = PublicLiveSession(
            row_source=idle_rows,
            normalized_recording_dir=tmp_path,
            finalization_drain=0,
        )
        await live.start("11357", seed_events=[IDENTITY])
        adapter = F1LiveAdapter("11357")
        try:
            apply_raw(
                live,
                adapter,
                "SessionInfo",
                {"Key": 11357, "Name": "Qualifying", "Type": "Qualifying"},
                "2026-09-05T14:00:00Z",
            )
            steps = [
                (18, 1, "Finished", "FINISHED"),
                (24, 2, "Inactive", "SCHEDULED"),
                (25, 2, "Started", "RUNNING"),
                (27, 2, "Aborted", "SUSPENDED"),
                (28, 2, "Started", "RUNNING"),
                (35, 2, "Finished", "FINISHED"),
                (40, 3, "Started", "RUNNING"),
            ]
            for minute, part, status, expected in steps:
                at = f"2026-09-05T14:{minute:02}:00Z"
                apply_raw(
                    live,
                    adapter,
                    "SessionData",
                    {"Series": {str(part): {"QualifyingPart": part}}},
                    at,
                )
                apply_raw(live, adapter, "SessionStatus", {"Status": status}, at)
                await asyncio.sleep(0.002)
                assert live.state.session.status == expected
                assert not live._completion_observed
                assert not live.view("11357").replay_ready
            apply_raw(
                live,
                adapter,
                "SessionStatus",
                {"Status": "Finished"},
                "2026-09-05T14:55:00Z",
            )
            assert live._completion_observed
        finally:
            await live.stop()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("phase", "status"), [("Q1", "RUNNING"), ("Q1", "FINISHED"), ("Q2", "RUNNING")]
)
def test_restart_from_partial_canonical_file_at_each_segment(tmp_path, phase, status):
    events = [
        IDENTITY,
        NormalizedEvent(
            "session",
            "2026-09-05T14:18:00Z",
            "synthetic",
            {"qualifying_phase": phase, "status": status},
        ),
    ]
    path = tmp_path / "live-11357.json"
    original = json.dumps([asdict(event) for event in events])
    path.write_text(original)

    async def run():
        live = PublicLiveSession(
            row_source=idle_rows,
            normalized_recording_dir=tmp_path,
            finalization_drain=0,
        )
        await live.start("11357", seed_events=[IDENTITY])
        try:
            task = live._task
            await live.start("11357", seed_events=[IDENTITY])
            assert live._task is task
            assert not live._completion_observed
            assert live.state.session.qualifying_phase == phase
            live._apply(
                [
                    NormalizedEvent(
                        "timing",
                        "2026-09-05T14:29:00Z",
                        "synthetic",
                        {"number": "44", "lap": 13},
                    )
                ],
                received_at="2026-09-05T14:29:00Z",
            )
            assert live.state.drivers["44"].lap == 13
            assert path.read_text() == original
        finally:
            await live.stop()

    asyncio.run(run())


def test_slow_optional_seed_and_failed_catalog_do_not_gate_http_or_live(
    tmp_path, monkeypatch
):
    seed_entered, release_seed, catalog_called = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )

    def slow_seed(*_):
        seed_entered.set()
        assert release_seed.wait(5)

    def failed_catalog():
        catalog_called.set()
        raise OSError("SYNTHETIC unavailable external catalog")

    monkeypatch.setattr("slipstream.api.import_bundled_pirelli_seed", slow_seed)
    (tmp_path / "live-11357.json").write_text(json.dumps([asdict(IDENTITY)]))
    live = PublicLiveSession(row_source=idle_rows)
    app = create_app(
        tmp_path,
        now=lambda: datetime(2026, 9, 5, 14, 10, tzinfo=UTC),
        live_session=live,
        refresh_catalog=failed_catalog,
    )
    try:
        with TestClient(app) as client:
            assert seed_entered.wait(1)
            assert client.get("/api/v1/catalog").status_code == 200
            for _ in range(100):
                if live.target_session_key:
                    break
                time.sleep(0.005)
            assert live.target_session_key == "11357"
            with client.websocket_connect(
                "/api/v1/stream?session_key=11357&mode=replay"
            ) as viewer:
                frame = viewer.receive_json()
                assert frame["playbackReady"]
                assert frame["data"]["session"]["key"] == "11357"
            release_seed.set()
            assert catalog_called.wait(1)
            for _ in range(100):
                catalog = client.get("/api/v1/catalog").json()
                if catalog["initialization"]["status"] == "retrying":
                    break
                time.sleep(0.005)
            assert catalog["initialization"] == {
                "status": "retrying",
                "error": "OSError",
            }
            assert live.target_session_key == "11357"
    finally:
        release_seed.set()
