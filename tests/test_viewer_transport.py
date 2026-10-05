"""Viewer transport regressions; sporting/source authority remains unchanged."""

import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from slipstream.api import _handle_message, create_app
from slipstream.catalog import CATALOG_FORMAT
from slipstream.events import NormalizedEvent
from slipstream.live import PublicLiveSession
from slipstream.live_viewer import LiveViewer
from slipstream.playback import ReplayController

START = datetime(2026, 8, 23, 12, tzinfo=UTC)


def at(seconds):
    return START + timedelta(seconds=seconds)


def test_pause_holds_source_cursor_and_resume_retains_accrued_delay():
    viewer = LiveViewer(30)
    assert viewer.update(at(100), at(0)) == at(70)
    viewer.pause()
    assert viewer.update(at(160), at(0)) == at(70)
    assert viewer.delay == viewer.requested_delay == 90
    viewer.play()
    assert viewer.update(at(180), at(0)) == at(90)
    viewer.set_delay(0)
    assert viewer.update(at(180), at(0)) == at(180)
    assert not viewer.paused


def test_short_buffer_exposes_requested_and_effective_delay_separately():
    viewer = LiveViewer(300)
    assert viewer.update(at(192), at(0)) == at(0)
    assert viewer.payload()["delaySeconds"] == 192
    assert viewer.payload()["requestedDelaySeconds"] == 300
    assert viewer.payload()["availableDelaySeconds"] == 192
    assert viewer.update(at(340), at(0)) == at(40)


def test_max_pause_automatically_resumes_with_notice_and_one_generation():
    viewer = LiveViewer()
    viewer.update(at(100), at(0))
    viewer.pause()
    assert viewer.update(at(399), at(0)) == at(100)
    assert viewer.paused
    assert viewer.update(at(400), at(0)) == at(100)
    assert not viewer.paused
    assert viewer.notice and "5:00" in viewer.notice
    assert viewer.generation == 1
    assert viewer.update(at(401), at(0)) == at(101)
    assert viewer.generation == 1


def test_stale_freezes_and_reconnect_jumps_silently_at_same_delay():
    viewer = LiveViewer(30)
    viewer.update(at(100), at(0))
    assert viewer.update(at(200), at(0), stale=True) == at(70)
    assert viewer.update(at(210), at(0), stale=True) == at(70)
    assert viewer.update(at(230), at(0)) == at(200)
    assert viewer.delay == 30
    assert viewer.generation == 1
    assert viewer.notice is None
    assert viewer.update(at(230), at(0)) == at(200)


@pytest.mark.parametrize("delay", [-1, 301, float("inf"), float("nan")])
def test_invalid_live_delays_are_rejected(delay):
    with pytest.raises(ValueError):
        LiveViewer(delay)


@pytest.fixture
def live_client(tmp_path, monkeypatch):
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_REFRESH", "0")
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_BACKFILL", "0")
    catalog = {
        "format": CATALOG_FORMAT, "schema_version": 1, "source": "openf1",
        "updated_at": at(0).isoformat(), "years": [2026],
        "meetings": {"M": {"meeting_key": "M", "meeting_name": "Synthetic GP"}},
        "sessions": [{
            "session_key": "100", "meeting_key": "M", "year": 2026,
            "session_name": "Race", "session_type": "Race",
            "date_start": at(0).isoformat(), "date_end": at(7200).isoformat(),
        }],
    }
    (tmp_path / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    live = PublicLiveSession()
    asyncio.run(live.apply_rows("100", [{
        "stream": "SessionInfo", "received_at": at(0).isoformat(),
        "source_timestamp": at(0).isoformat(), "initial": True,
        "payload": {"Key": 100, "Name": "Race", "Type": "Race",
                    "StartDate": at(0).isoformat(), "EndDate": at(7200).isoformat()},
    }]))

    def advance(seconds, lap):
        live._apply([NormalizedEvent("driver", at(seconds).isoformat(), "synthetic",
                                    {"number": "1", "lap": lap, "position": 1})],
                    received_at=at(seconds).isoformat())

    advance(100, 1)
    advance(130, 2)
    with TestClient(create_app(tmp_path, now=lambda: at(1000), public_live=True,
                               live_session=live, prepare_weekend_context=lambda **_: {})) as client:
        yield client, advance


def receive_until(socket, predicate):
    for _ in range(20):
        envelope = socket.receive_json()
        if predicate(envelope):
            return envelope
    raise AssertionError("Expected viewer snapshot was not received")


def test_websocket_pause_isolated_and_rest_resume_keeps_the_inclusive_cursor(live_client):
    client, advance = live_client
    with (client.websocket_connect("/api/v1/stream?session_key=100&mode=live") as paused,
          client.websocket_connect("/api/v1/stream?session_key=100&mode=live") as other):
        initial = paused.receive_json()
        other.receive_json()
        paused.send_json({"type": "pause"})
        held = receive_until(paused, lambda item: item.get("live", {}).get("paused"))
        advance(160, 3)
        paused.send_json({"type": "snapshot"})
        held = receive_until(paused, lambda item: item.get("live", {}).get("delaySeconds") == 30)
        assert held["seq"] == initial["seq"]
        assert held["sessionTime"] == initial["sessionTime"]
        assert held["analytics"]["sequence"] == held["seq"]
        assert held["data"]["drivers"]["1"]["lap"] == 2
        assert not held["playback"]["playing"]
        other.send_json({"type": "snapshot"})
        latest = receive_until(other, lambda item: item.get("seq", 0) > held["seq"])
        assert latest["data"]["drivers"]["1"]["lap"] == 3
        assert latest["live"]["delaySeconds"] == 0
        fallback = client.get("/api/v1/state", params={"session_key": "100", "mode": "live",
            "delay_seconds": 30, "live_paused_at": held["sessionTime"]}).json()
        assert fallback["seq"] == held["seq"]
        assert fallback["live"]["paused"]
        paused.send_json({"type": "play", "speed": 1})
        resumed = receive_until(paused, lambda item: item.get("playback", {}).get("playing"))
        assert resumed["live"]["requestedDelaySeconds"] == 30


def test_websocket_live_rejects_seek_and_speed_but_accepts_pause(live_client):
    client, _ = live_client
    with client.websocket_connect("/api/v1/stream?session_key=100&mode=live") as socket:
        socket.receive_json()
        for command in [{"type": "seek_relative", "seconds": -10}, {"type": "play", "speed": 2}]:
            socket.send_json(command)
            assert receive_until(socket, lambda item: item["type"] == "error")["error"]
        socket.send_json({"type": "pause"})
        assert receive_until(socket, lambda item: item.get("live", {}).get("paused"))["live"]["paused"]


def test_paused_reconnect_past_buffer_limit_resumes_with_explicit_notice(live_client):
    client, advance = live_client
    advance(500, 4)
    with client.websocket_connect(
        "/api/v1/stream?session_key=100&mode=live&delay_seconds=30&live_paused_at=2026-08-23T12:02:10Z"
    ) as socket:
        snapshot = socket.receive_json()
        assert snapshot["playback"]["playing"]
        assert snapshot["live"]["delaySeconds"] == 300
        assert snapshot["live"]["notice"]


def test_return_restores_exact_event_cursor_and_clock_without_same_time_leak():
    events = [
        NormalizedEvent("session", at(0).isoformat(), "synthetic", {"key": "100", "name": "Race"}),
        NormalizedEvent("driver", at(10).isoformat(), "synthetic", {"number": "1", "name": "First"}),
        NormalizedEvent("timing", at(10).isoformat(), "synthetic", {"number": "1", "lap": 1}),
        NormalizedEvent("timing", at(20).isoformat(), "synthetic", {"number": "1", "lap": 2}),
    ]
    controller = ReplayController(events)
    controller.seek_cursor(4)
    snapshots = []

    class Socket:
        async def send_json(self, envelope):
            snapshots.append(envelope)

    async def compute(function, *args):
        return function(*args)

    async def run():
        async def send(cursor, playhead):
            await _handle_message(Socket(), controller, {"type": "seek", "seq": cursor,
                "playhead": at(playhead).isoformat()}, asyncio.Lock(), lambda: None, compute)
        await send(2, 10)
        assert snapshots[-1]["seq"] == 2
        assert snapshots[-1]["playback"]["navigationGeneration"] == 1
        assert snapshots[-1]["data"]["drivers"]["1"]["lap"] is None
        await send(3, 15)
        assert snapshots[-1]["seq"] == 3
        assert snapshots[-1]["sessionTime"] == at(15).isoformat()
        assert snapshots[-1]["playback"]["navigationGeneration"] == 2
        await send(2, 11)
        assert snapshots[-1]["type"] == "error"
        assert controller.cursor == 3
        assert controller.playhead == at(15).isoformat()
        assert controller.navigation_generation == 2
        await _handle_message(Socket(), controller, {"type": "snapshot"},
                              asyncio.Lock(), lambda: None, compute)
        assert snapshots[-1]["playback"]["navigationGeneration"] == 2

    asyncio.run(run())


def test_story_history_is_paged_at_explicit_cursor_and_recording_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_REFRESH", "0")
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_BACKFILL", "0")
    events = [NormalizedEvent("session", at(0).isoformat(), "synthetic", {
        "key": "100", "name": "Race", "session_kind": "race", "status": "RUNNING",
        "display_status": "GREEN", "control_status": "NORMAL", "marshal_status": "ALL_CLEAR",
    })]
    for index, status in enumerate(["VSC", "NORMAL", "SAFETY_CAR", "NORMAL", "RED_FLAG", "NORMAL"], 1):
        events.append(NormalizedEvent("session", at(index * 10).isoformat(), "synthetic", {
            "control_status": status, "marshal_status": "ALL_CLEAR", "status": "RUNNING",
        }))
    path = tmp_path / "story.json"
    path.write_text(json.dumps([asdict(event) for event in events]), encoding="utf-8")
    with TestClient(create_app(path, public_live=False)) as client:
        assert client.get("/api/v1/story").status_code == 422
        assert client.get("/api/v1/story", params={"seq": 2, "limit": 101}).status_code == 422
        assert client.get("/api/v1/story", params={"seq": 999}).status_code == 422
        assert client.get("/api/v1/story", params={"seq": 2, "recording_version": "old"}).status_code == 409
        first = client.get("/api/v1/story", params={"seq": 5, "limit": 2}).json()
        assert first["sessionKey"] == "100"
        assert first["sequence"] == 5
        assert first["hasMore"]
        second = client.get("/api/v1/story", params={"seq": 5, "limit": 2,
            "offset": first["nextOffset"], "recording_version": first["recordingVersion"]}).json()
        assert second["revision"] == first["revision"]
        assert not ({event["id"] for event in first["events"]} & {event["id"] for event in second["events"]})
        assert all(event["availableSequence"] <= 5 and event["availableAt"] <= at(40).isoformat()
                   for event in first["events"] + second["events"])
