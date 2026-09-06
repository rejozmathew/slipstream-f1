"""Reliability regressions and boundary tests adapted from review validation.

Covers:
1. Cancelled playback worker mutating a later seek (ensuring cancellation waits
   for in-flight worker, preserves compute slot, and leaves subsequent seek intact).
2. Overrun restart recovery for still-running sessions past scheduled end.
3. Boundary: terminal journal not restarted.
4. Boundary: stale journal not resumed long after scheduled end.
5. Unknown completeness existing partial file not reported as successful re-download.
6. Fresh catalog refresh not blocked behind optional Pirelli seed import.
7. Boundary: catalog ready and accessible while optional seed import is blocked.
8. Missed completion packet retains proven old live viewer state across target rollover.

All tests use synthetic test fixtures, temporary storage (tmp_path), and disabled
live/Pirelli networking.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import threading
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from slipstream.api import _play, _stop_playback, create_app
from slipstream.catalog import CATALOG_FORMAT
from slipstream.events import NormalizedEvent
from slipstream.library import ReplayLibrary
from slipstream.live import PublicLiveSession
from slipstream.live_recording import NormalizedLiveRecorder
from slipstream.playback import ReplayController


def write_catalog(root: Path, key: str = "11357") -> None:
    payload = {
        "format": CATALOG_FORMAT,
        "source": "openf1",
        "meetings": {},
        "sessions": [
            {
                "session_key": key,
                "meeting_key": "1293",
                "year": 2026,
                "session_name": "Qualifying",
                "session_type": "Qualifying",
                "date_start": "2026-09-05T14:00:00Z",
                "date_end": "2026-09-05T15:00:00Z",
            }
        ],
    }
    (root / "catalog.json").write_text(json.dumps(payload), encoding="utf-8")


def event(t: str, **payload: object) -> NormalizedEvent:
    return NormalizedEvent("session", t, "SYNTHETIC-REVIEW", payload)


def partial_events() -> list[NormalizedEvent]:
    return [
        event(
            "2026-09-05T14:00:00Z",
            key="11357",
            name="Qualifying",
            session_type="Qualifying",
            session_kind="qualifying",
            started_at="2026-09-05T14:00:00Z",
            ended_at="2026-09-05T15:00:00Z",
            status="RUNNING",
        ),
        event("2026-09-05T15:01:00Z", qualifying_phase="Q3", status="RUNNING"),
    ]


def quiet_env(monkeypatch) -> None:
    for feature in ("SEED", "BACKFILL", "REFRESH"):
        monkeypatch.setenv(f"SLIPSTREAM_PIRELLI_{feature}", "0")


async def idle_rows():
    while True:
        await asyncio.sleep(3600)
        yield {}


# ---------------------------------------------------------------------------
# 1. Playback cancellation worker safety & seek integrity
# ---------------------------------------------------------------------------


def test_cancelled_playback_worker_cannot_change_a_new_cursor(
    tmp_path: Path, monkeypatch
) -> None:
    """Cancel while an actual advance is in progress, then seek backward.

    The cancellation fix must wait for any running worker before cancellation
    finishes, holding the compute slot until the worker completes. Releasing
    the worker via a separate background task while stop is pending verifies
    that cancellation does not return early, the compute slot is held, and
    a subsequent backward seek to cursor 0 remains intact.
    """
    quiet_env(monkeypatch)
    write_catalog(tmp_path)
    app = create_app(tmp_path, public_live=False)
    endpoint = next(r.endpoint for r in app.routes if r.path == "/api/v1/state")
    compute = inspect.getclosurevars(endpoint).nonlocals["compute"]
    events = [event("2026-09-05T14:00:00Z", key="11357")]
    events += [
        NormalizedEvent(
            "timing",
            f"2026-09-05T14:00:00.{n}00000Z",
            "SYNTHETIC-REVIEW",
            {"number": "44", "lap": n},
        )
        for n in range(1, 6)
    ]
    controller = ReplayController(events)
    controller.start()
    entered = threading.Event()
    release = threading.Event()
    done = threading.Event()
    original = controller._apply_next
    first = True

    def controlled_apply():
        nonlocal first
        if first:
            first = False
            entered.set()
            if not release.wait(3):
                raise TimeoutError("Reviewer interleaving watchdog")
        return original()

    controller._apply_next = controlled_apply
    advance = controller.advance

    def marked_advance(seconds: float):
        try:
            return advance(seconds)
        finally:
            done.set()

    controller.advance = marked_advance

    class Socket:
        async def send_json(self, payload: object) -> None:
            pass

    async def run():
        controller.is_playing = True
        task = asyncio.create_task(
            _play(Socket(), controller, 1, asyncio.Lock(), lambda: None, compute)
        )
        releaser = None
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            # Worker is in progress inside compute(controller.advance, ...)
            stop_task = asyncio.create_task(_stop_playback(task, controller))
            # Yield briefly to let stop_playback execute cancellation request
            await asyncio.sleep(0.02)

            # Cancellation fix must hold the compute slot and wait for worker
            cancellation_waits_for_worker = not stop_task.done()
            compute_lock = inspect.getclosurevars(compute).nonlocals.get("compute_lock")
            compute_slot_held = (
                compute_lock._value < 2 if compute_lock is not None else True
            )

            # Release worker via a separate background task while stop is pending
            async def release_worker():
                await asyncio.sleep(0.05)
                release.set()

            releaser = asyncio.create_task(release_worker())
            await stop_task
            await releaser
            assert await asyncio.to_thread(done.wait, 2)

            assert cancellation_waits_for_worker, (
                "Cancellation finished before running worker completed"
            )
            assert compute_slot_held, (
                "Cancellation released compute slot before running worker completed"
            )

            # The UI has now paused and sent a backward seek to cursor 0.
            # Production compute helper ensures the completed seek remains intact.
            await compute(controller.seek_cursor, 0)
            assert controller.cursor == 0, (
                "Cancelled playback changed a later requested cursor"
            )
            assert controller.state.drivers == {}
        finally:
            release.set()
            if releaser and not releaser.done():
                await releaser
            await _stop_playback(task, controller)

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 2. Overrun restart recovery & boundary tests
# ---------------------------------------------------------------------------


def test_restart_recovers_still_running_session_after_scheduled_end(
    tmp_path: Path, monkeypatch
) -> None:
    """Server restart recovers an active session whose journal is still running past scheduled end."""
    quiet_env(monkeypatch)
    write_catalog(tmp_path)
    recorder = NormalizedLiveRecorder(tmp_path, "11357")
    recorder.append(tuple(partial_events()))
    live = PublicLiveSession(
        row_source=idle_rows,
        now=lambda: datetime(2026, 9, 5, 15, 2, tzinfo=UTC),
    )
    app = create_app(
        tmp_path,
        public_live=True,
        live_session=live,
        now=lambda: datetime(2026, 9, 5, 15, 2, tzinfo=UTC),
    )
    with TestClient(app) as client:
        time.sleep(0.08)
        response = client.get("/api/v1/catalog").json()
        assert response["liveSessionKey"] == "11357"


def test_restart_does_not_recover_terminal_journal_after_scheduled_end(
    tmp_path: Path, monkeypatch
) -> None:
    """Boundary: a journal that reached terminal status is not restarted as an active live session."""
    quiet_env(monkeypatch)
    write_catalog(tmp_path)
    recorder = NormalizedLiveRecorder(tmp_path, "11357")
    events = [
        event(
            "2026-09-05T14:00:00Z",
            key="11357",
            name="Qualifying",
            session_type="Qualifying",
            session_kind="qualifying",
            started_at="2026-09-05T14:00:00Z",
            ended_at="2026-09-05T15:00:00Z",
            status="RUNNING",
        ),
        event("2026-09-05T15:01:00Z", qualifying_phase="Q3", status="FINISHED"),
    ]
    recorder.append(tuple(events))
    live = PublicLiveSession(
        row_source=idle_rows,
        now=lambda: datetime(2026, 9, 5, 15, 2, tzinfo=UTC),
    )
    app = create_app(
        tmp_path,
        public_live=True,
        live_session=live,
        now=lambda: datetime(2026, 9, 5, 15, 2, tzinfo=UTC),
    )
    with TestClient(app) as client:
        time.sleep(0.08)
        response = client.get("/api/v1/catalog").json()
        assert response["liveSessionKey"] is None


def test_restart_does_not_resume_stale_journal(tmp_path: Path, monkeypatch) -> None:
    """Boundary: non-terminal journal from hours ago must not be resumed past reasonable overrun."""
    quiet_env(monkeypatch)
    write_catalog(tmp_path)
    recorder = NormalizedLiveRecorder(tmp_path, "11357")
    recorder.append(tuple(partial_events()))
    # 3 hours after scheduled end and last recorded event
    stale_time = datetime(2026, 9, 5, 18, 0, tzinfo=UTC)
    live = PublicLiveSession(row_source=idle_rows, now=lambda: stale_time)
    app = create_app(
        tmp_path,
        public_live=True,
        live_session=live,
        now=lambda: stale_time,
    )
    with TestClient(app) as client:
        time.sleep(0.08)
        response = client.get("/api/v1/catalog").json()
        assert response["liveSessionKey"] is None


# ---------------------------------------------------------------------------
# 3. Unknown completeness re-download validation
# ---------------------------------------------------------------------------


def test_existing_partial_file_is_not_reported_as_successful_redownload(
    tmp_path: Path, monkeypatch
) -> None:
    """A direct historical download request must verify that an existing file is complete."""
    quiet_env(monkeypatch)
    write_catalog(tmp_path)
    events = partial_events()
    events[-1] = event("2026-09-05T14:28:00Z", status="RUNNING", qualifying_phase="Q2")
    (tmp_path / "live-11357.json").write_text(
        json.dumps([asdict(e) for e in events]), encoding="utf-8"
    )
    calls: list[int] = []
    acquired = threading.Event()

    def capture(key: int):
        calls.append(key)
        acquired.set()
        raise RuntimeError("SYNTHETIC acquisition sentinel")

    with TestClient(
        create_app(
            tmp_path,
            public_live=False,
            capture_session=capture,
            now=lambda: datetime(2026, 9, 5, 16, 0, tzinfo=UTC),
        )
    ) as client:
        initial = client.post("/api/v1/download?session_key=11357").json()
        metadata = client.get("/api/v1/replay?session_key=11357").json()
        assert metadata["complete"] is not True
        assert initial["status"] != "AVAILABLE", (
            "Uninspected partial file was accepted as complete"
        )
        assert acquired.wait(1), "The requested replacement acquisition must run"
        assert calls == [11357]


def test_unknown_but_complete_recording_is_inspected_without_redownload(
    tmp_path, monkeypatch
):
    quiet_env(monkeypatch)
    write_catalog(tmp_path)
    events = partial_events() + [
        event("2026-09-05T15:02:00Z", status="FINISHED", qualifying_phase="Q3")
    ]
    (tmp_path / "live-11357.json").write_text(
        json.dumps([asdict(item) for item in events]), encoding="utf-8"
    )
    calls = []

    def capture(key):
        calls.append(key)
        raise AssertionError("A verified complete replay needs no replacement")

    with TestClient(
        create_app(
            tmp_path,
            public_live=False,
            capture_session=capture,
            now=lambda: datetime(2026, 9, 5, 16, tzinfo=UTC),
        )
    ) as client:
        client.post("/api/v1/download?session_key=11357").raise_for_status()
        for _ in range(100):
            job = client.get("/api/v1/jobs").json()["jobs"][0]
            if job["status"] in {"AVAILABLE", "FAILED"}:
                break
            time.sleep(0.005)
        assert job["status"] == "AVAILABLE"
        assert calls == []


@pytest.mark.parametrize(
    "fault", ["wrong-key", "missing-key", "future", "old", "late-schedule"]
)
def test_startup_recovery_rejects_unverified_or_outdated_journals(tmp_path, fault):
    write_catalog(tmp_path)
    events = partial_events()
    if fault == "wrong-key":
        events[0] = event("2026-09-05T14:00:00Z", key="999", status="RUNNING")
    elif fault == "missing-key":
        events[0] = event("2026-09-05T14:00:00Z", status="RUNNING")
    elif fault == "future":
        events[-1] = event("2026-09-06T15:01:00Z", status="RUNNING")
    elif fault == "old":
        events = [event("2026-09-05T10:00:00Z", key="11357", status="RUNNING")]
    else:
        events[-1] = event("2026-09-05T23:00:00Z", status="RUNNING")
    NormalizedLiveRecorder(tmp_path, "11357").append(tuple(events))
    now = datetime(2026, 9, 5, 23 if fault == "late-schedule" else 15, 2, tzinfo=UTC)
    assert ReplayLibrary(tmp_path, now=lambda: now).recoverable_live_key() is None


def test_recording_version_identifies_publication_without_changing_opened_resource(
    tmp_path,
):
    write_catalog(tmp_path)
    path = tmp_path / "live-11357.json"
    events = partial_events()
    path.write_text(json.dumps([asdict(item) for item in events]), encoding="utf-8")
    library = ReplayLibrary(tmp_path)
    opened = library.get("11357")
    original_version = opened.recording_version
    events.append(
        event("2026-09-05T15:02:00Z", status="FINISHED", qualifying_phase="Q3")
    )
    path.write_text(json.dumps([asdict(item) for item in events]), encoding="utf-8")
    published_version = library.catalog()["sessions"][0]["recordingVersion"]
    assert published_version != original_version
    assert opened.recording_version == original_version
    replacement = library.get("11357")
    assert replacement is not opened
    assert replacement.recording_version == published_version
    assert len(opened.events) < len(replacement.events)


# ---------------------------------------------------------------------------
# 4. Optional seed gating catalog & boundary tests
# ---------------------------------------------------------------------------


def test_existing_openf1_replay_is_verified_without_repeated_downloads(
    tmp_path: Path, monkeypatch
) -> None:
    quiet_env(monkeypatch)
    original = Path(__file__).parent / "fixtures" / "openf1" / "session-9165.json"
    (tmp_path / "openf1-9165.json").write_bytes(original.read_bytes())
    calls = []

    def unexpected_download(key):
        calls.append(key)
        raise AssertionError("A verified complete replay must not be downloaded again")

    with TestClient(
        create_app(tmp_path, capture_session=unexpected_download)
    ) as client:
        response = client.post("/api/v1/download?session_key=9165")
        assert response.status_code == 202
        for _ in range(100):
            job = client.get("/api/v1/jobs").json()["jobs"][0]
            if job["status"] in {"AVAILABLE", "FAILED"}:
                break
            time.sleep(0.01)
        assert job["status"] == "AVAILABLE"
        assert client.get("/api/v1/replay?session_key=9165").json()["complete"] is True
        assert (
            client.post("/api/v1/download?session_key=9165").json()["status"]
            == "AVAILABLE"
        )
    assert calls == []


def test_publication_during_open_does_not_label_old_events_with_new_version(
    tmp_path: Path, monkeypatch
) -> None:
    import slipstream.library as library_module

    write_catalog(tmp_path)
    path = tmp_path / "live-11357.json"
    events = partial_events()
    path.write_text(json.dumps([asdict(item) for item in events]), encoding="utf-8")
    library = ReplayLibrary(tmp_path)
    original_version = library.descriptors["11357"].recording_version
    read_descriptor = library_module._read_descriptor
    replaced = False

    def replace_after_read(candidate, raw=None):
        nonlocal replaced
        descriptor = read_descriptor(candidate, raw)
        if raw is not None and not replaced:
            replaced = True
            replacement = [
                *events,
                event("2026-09-05T15:02:00Z", status="FINISHED", qualifying_phase="Q3"),
            ]
            path.write_text(
                json.dumps([asdict(item) for item in replacement]), encoding="utf-8"
            )
        return descriptor

    monkeypatch.setattr(library_module, "_read_descriptor", replace_after_read)
    first = library.get("11357")
    published_version = library.catalog()["sessions"][0]["recordingVersion"]
    assert first.recording_version == original_version
    assert first.recording_version != published_version
    second = library.get("11357")
    assert second is not first
    assert second.recording_version == published_version
    assert len(second.events) == len(first.events) + 1


def test_fresh_catalog_refresh_does_not_wait_for_optional_seed(
    tmp_path: Path, monkeypatch
) -> None:
    """Required catalog refresh must not block behind optional Pirelli seed import."""
    quiet_env(monkeypatch)
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_SEED", "1")
    entered = threading.Event()
    release = threading.Event()
    refreshed = threading.Event()

    def seed(*args: object) -> None:
        entered.set()
        if not release.wait(3):
            raise TimeoutError("Reviewer seed watchdog")

    def refresh() -> None:
        write_catalog(tmp_path)
        refreshed.set()

    monkeypatch.setattr("slipstream.api.import_bundled_pirelli_seed", seed)
    app = create_app(
        tmp_path,
        public_live=True,
        live_session=PublicLiveSession(
            row_source=idle_rows,
            now=lambda: datetime(2026, 9, 5, 14, 10, tzinfo=UTC),
        ),
        now=lambda: datetime(2026, 9, 5, 14, 10, tzinfo=UTC),
        refresh_catalog=refresh,
    )
    with TestClient(app) as client:
        try:
            assert entered.wait(1)
            independently_refreshed = refreshed.wait(0.15)
            client.get("/api/v1/catalog").json()
            release.set()
            assert refreshed.wait(1), "Control check: refresh runs after seed release"
            assert independently_refreshed, (
                "Required catalog refresh waits behind optional seed import"
            )
        finally:
            release.set()


def test_catalog_ready_while_optional_seed_blocked(tmp_path: Path, monkeypatch) -> None:
    """Boundary: catalog endpoint serves valid catalog while optional seed remains blocked."""
    quiet_env(monkeypatch)
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_SEED", "1")
    entered = threading.Event()
    release = threading.Event()
    refreshed = threading.Event()

    def seed(*args: object) -> None:
        entered.set()
        if not release.wait(3):
            raise TimeoutError("Reviewer seed watchdog")

    def refresh() -> None:
        write_catalog(tmp_path)
        refreshed.set()

    monkeypatch.setattr("slipstream.api.import_bundled_pirelli_seed", seed)
    app = create_app(
        tmp_path,
        public_live=True,
        live_session=PublicLiveSession(
            row_source=idle_rows,
            now=lambda: datetime(2026, 9, 5, 14, 10, tzinfo=UTC),
        ),
        now=lambda: datetime(2026, 9, 5, 14, 10, tzinfo=UTC),
        refresh_catalog=refresh,
    )
    with TestClient(app) as client:
        try:
            assert entered.wait(1)
            # When catalog refresh is unblocked, it finishes independently of seed
            assert refreshed.wait(1), "Catalog refresh did not execute"
            data = {}
            for _ in range(50):
                response = client.get("/api/v1/catalog")
                assert response.status_code == 200
                data = response.json()
                if (
                    data["initialization"]["status"] == "ready"
                    and len(data["sessions"]) > 0
                ):
                    break
                time.sleep(0.01)
            assert data["initialization"]["status"] == "ready"
            assert len(data["sessions"]) == 1
            assert data["sessions"][0]["sessionKey"] == "11357"
        finally:
            release.set()


# ---------------------------------------------------------------------------
# 5. Missed completion old live-view retention across target rollover
# ---------------------------------------------------------------------------


def test_old_live_viewer_does_not_become_empty_when_completion_packet_was_missed(
    tmp_path: Path, monkeypatch
) -> None:
    """Real API/collector target rollover with missing old terminal packet retains proven timing."""
    quiet_env(monkeypatch)
    clock = [datetime(2026, 9, 5, 13, 59, 58, tzinfo=UTC)]
    payload = {
        "format": CATALOG_FORMAT,
        "source": "openf1",
        "meetings": {},
        "sessions": [
            {
                "session_key": "100",
                "meeting_key": "M",
                "year": 2026,
                "session_name": "Practice 3",
                "session_type": "Practice",
                "date_start": "2026-09-05T13:00:00Z",
                "date_end": "2026-09-05T14:00:00Z",
            },
            {
                "session_key": "200",
                "meeting_key": "M",
                "year": 2026,
                "session_name": "Qualifying",
                "session_type": "Qualifying",
                "date_start": "2026-09-05T14:00:00Z",
                "date_end": "2026-09-05T15:00:00Z",
            },
        ],
    }
    (tmp_path / "catalog.json").write_text(json.dumps(payload), encoding="utf-8")

    def raw(topic: str, data: dict, at: str) -> dict:
        return {
            "stream": topic,
            "payload": data,
            "source_timestamp": at,
            "received_at": at,
        }

    async def rows():
        key = live.target_session_key
        at = "2026-09-05T13:59:58Z" if key == "100" else "2026-09-05T14:00:01Z"
        yield raw(
            "SessionInfo",
            {
                "Key": int(key),
                "Name": "Practice 3" if key == "100" else "Qualifying",
                "Type": "Practice" if key == "100" else "Qualifying",
            },
            at,
        )
        yield raw("SessionStatus", {"Status": "Started"}, at)
        yield raw(
            "TimingData",
            {"Lines": {"44": {"NumberOfLaps": 12 if key == "100" else 1}}},
            at,
        )
        while True:
            await asyncio.sleep(1)
            yield raw("Heartbeat", {}, at)

    live = PublicLiveSession(row_source=rows, now=lambda: clock[0])
    app = create_app(
        tmp_path,
        now=lambda: clock[0],
        public_live=True,
        live_session=live,
        prepare_weekend_context=lambda **kw: {},
    )
    startup = app.router.on_startup[0]
    monitor = inspect.getclosurevars(startup).nonlocals["monitor_live_source"]
    reconcile = inspect.getclosurevars(monitor).nonlocals["reconcile_live_source"]

    with TestClient(app) as client:
        for _ in range(100):
            if live.state.drivers.get("44"):
                break
            time.sleep(0.005)
        assert live.state.drivers["44"].lap == 12

        with (
            client.websocket_connect(
                "/api/v1/stream?session_key=100&mode=live"
            ) as socket,
            client.websocket_connect(
                "/api/v1/stream?session_key=100&mode=live&delay_seconds=137"
            ) as delayed,
        ):
            before = socket.receive_json()
            assert before["data"]["drivers"]["44"]["lap"] == 12
            delayed_before = delayed.receive_json()
            assert "44" not in delayed_before["data"]["drivers"]

            clock[0] = datetime(2026, 9, 5, 14, 0, 1, tzinfo=UTC)
            client.portal.call(reconcile)

            for _ in range(100):
                if live.state.drivers.get("44") and live.target_session_key == "200":
                    break
                time.sleep(0.005)
            assert live.target_session_key == "200"

            socket.send_json({"type": "snapshot"})
            after = socket.receive_json()
            assert after["data"]["drivers"].get("44", {}).get("lap") == 12, (
                "Proven old timing was replaced by an empty placeholder"
            )
            assert after["live"]["phase"] == "STALE"
            assert after["live"]["nextSessionKey"] == "200"
            assert after["live"]["replayReady"] is False
            assert after.get("handoff") is None
            assert after["data"]["session"]["status"] == "RUNNING"
            assert after["metadata"]["complete"] is False
            assert after["capabilities"]["capabilities"]["intervals"] is True
            assert (tmp_path / "live-100.in-progress.jsonl").is_file()
            assert not (tmp_path / "live-100.json").exists()

            # A reconnect to the old session must retain the same cursor-safe
            # state. The newer collector is not permission to skip the delay.
            waiting = client.get(
                "/api/v1/state?session_key=100&mode=live&delay_seconds=137"
            ).json()
            assert "44" not in waiting["data"]["drivers"]
            assert "nextSessionKey" not in waiting["live"]
            clock[0] += timedelta(seconds=137)
            delayed.send_json({"type": "snapshot"})
            for _ in range(10):
                tail = delayed.receive_json()
                if tail["live"].get("nextSessionKey"):
                    break
            assert tail["data"]["drivers"]["44"]["lap"] == 12
            assert tail["live"]["nextSessionKey"] == "200"
            assert tail["live"]["delaySeconds"] == 137
            assert tail.get("handoff") is None
            assert tail["live"]["replayReady"] is False
            assert live.target_session_key == "200"
            assert live.state.drivers["44"].lap == 1
