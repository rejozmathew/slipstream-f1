"""Controlled boundary and lifetime tests for replay closures.

Maintains:
- C2: snapshot-mid-advance coherency and non-blocking playback continuity
- C3: cancelled-acquire pin leak & cancellation boundaries (before/during/after, error cleanup, concurrent survivors)
- C4: viewer release non-blocking event loop under concurrent load
- C5: queued preparation resource accounting, failure handling, and duplicate coalescing

Synthetic data only; Pirelli disabled; no network/credentials used.
"""

from __future__ import annotations

import asyncio
import gc
import inspect
import itertools
import json
import threading
import time
import weakref
from contextlib import suppress
from dataclasses import asdict

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from slipstream.api import create_app
from slipstream.catalog import CATALOG_FORMAT
from slipstream.events import NormalizedEvent
from slipstream.library import ReplayResource
from slipstream.playback import ReplayController


def quiet(monkeypatch):
    for feature in ("SEED", "REFRESH", "BACKFILL"):
        monkeypatch.setenv("SLIPSTREAM_PIRELLI_" + feature, "0")
    monkeypatch.setenv("SLIPSTREAM_LIVE_DISABLED", "1")
    monkeypatch.delenv("OPENF1_TOKEN", raising=False)
    monkeypatch.delenv("SLIPSTREAM_CREDENTIALS", raising=False)


def event(at, kind="session", **payload):
    return NormalizedEvent(kind, at, "SYNTHETIC-CLOSURE", payload)


def recording(root, key="100"):
    rows = [
        event(
            "2026-09-05T14:00:00Z",
            key=key,
            name="Qualifying",
            session_type="Qualifying",
            session_kind="qualifying",
            started_at="2026-09-05T14:00:00Z",
            ended_at="2026-09-05T15:00:00Z",
            status="RUNNING",
        ),
        event("2026-09-05T14:00:00.100Z", "timing", number="44", lap=1),
        event("2026-09-05T14:00:01Z", "timing", number="44", lap=2),
    ]
    path = root / f"live-{key}.json"
    path.write_text(json.dumps([asdict(e) for e in rows]))
    return rows


def catalog(root):
    (root / "catalog.json").write_text(
        json.dumps(
            {
                "format": CATALOG_FORMAT,
                "source": "openf1",
                "meetings": {},
                "sessions": [
                    {
                        "session_key": key,
                        "meeting_key": "1293",
                        "year": 2026,
                        "session_name": name,
                        "session_type": stype,
                        "date_start": start,
                        "date_end": end,
                    }
                    for key, name, stype, start, end in [
                        (
                            "100",
                            "Practice 3",
                            "Practice",
                            "2026-09-05T10:00:00Z",
                            "2026-09-05T11:00:00Z",
                        ),
                        (
                            "200",
                            "Qualifying",
                            "Qualifying",
                            "2026-09-05T14:00:00Z",
                            "2026-09-05T15:00:00Z",
                        ),
                    ]
                ],
            }
        )
    )


def endpoint(app, path):
    return next(r.endpoint for r in app.routes if r.path == path)


def library_of(app):
    stream_ep = endpoint(app, "/api/v1/stream")
    closure_vars = inspect.getclosurevars(stream_ep).nonlocals
    if "library_ref" in closure_vars:
        ref = closure_vars["library_ref"]
        return ref[0] if isinstance(ref, (list, tuple)) else ref
    if "library" in closure_vars:
        return closure_vars["library"]
    for route in app.routes:
        cv = inspect.getclosurevars(route.endpoint).nonlocals
        if "library_ref" in cv:
            ref = cv["library_ref"]
            return ref[0] if isinstance(ref, (list, tuple)) else ref
        if "library" in cv:
            return cv["library"]
    raise LookupError("Could not locate ReplayLibrary on app endpoints")


def make_app(root, **kwargs):
    return create_app(root, prepare_weekend_context=lambda **kw: {}, **kwargs)


# ==============================================================================
# C2: Snapshot mid-advance coherency and playback continuity
# ==============================================================================


def test_snapshot_is_coherent_during_background_advance(tmp_path, monkeypatch):
    """C2: Verify snapshot coherency during advance and ensure playback is not paused.

    The held worker is independently released via threading.Timer before awaiting
    snapshot completion, preventing deadlocks when safe serialization is active.
    """
    quiet(monkeypatch)
    recording(tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = ReplayController.__setattr__
    held = []

    def assigning(self, name, value):
        original(self, name, value)
        if (
            name == "state"
            and value.drivers.get("44") is not None
            and value.drivers["44"].lap == 1
            and not held
        ):
            held.append(self)
            entered.set()
            if not release.wait(3):
                raise TimeoutError("controlled assignment watchdog")

    monkeypatch.setattr(ReplayController, "__setattr__", assigning)
    app = make_app(tmp_path, public_live=False)
    observed = None
    timer = None
    with TestClient(app) as client:
        try:
            with client.websocket_connect(
                "/api/v1/stream?session_key=100&mode=replay"
            ) as ws:
                initial = ws.receive_json()
                assert initial["seq"] == 1
                ws.send_json({"type": "play"})
                assert entered.wait(2), "advance did not enter the controlled window"
                ws.send_json({"type": "snapshot"})

                # Independently release held worker before awaiting snapshot response
                # so safe serialization does not deadlock the test.
                timer = threading.Timer(0.15, release.set)
                timer.start()

                observed = ws.receive_json()
                release.set()

                # Verify playback not unintentionally paused
                assert observed.get("playback", {}).get("playing") is True, (
                    "snapshot request should not pause active playback"
                )

                # Playback continues advancing
                subsequent = ws.receive_json()
                assert subsequent.get("playback", {}).get("playing") is True, (
                    "playback should continue after snapshot"
                )
        finally:
            if timer is not None:
                timer.cancel()
            release.set()

    # Verify snapshot coherency:
    # Snapshot must not publish next-event facts with the preceding event cursor/time
    assert not (observed["seq"] == 1 and observed["data"]["drivers"]), (
        "snapshot publishes next-event facts with the preceding event cursor/time"
    )
    if observed["data"]["drivers"]:
        assert observed["seq"] >= 2, (
            f"snapshot with updated drivers must reflect advanced sequence cursor, got {observed['seq']}"
        )
    if observed.get("analytics"):
        assert observed["analytics"]["sequence"] == observed["seq"]
        assert observed["analytics"]["asOf"] == observed["sessionTime"]


# ==============================================================================
# C3: Cancelled acquire pin leak and cancellation boundaries
# ==============================================================================


def test_cancelled_open_releases_acquired_resource(tmp_path, monkeypatch):
    """C3: Cancellation during acquire does not leave a leaked lease/pin."""
    quiet(monkeypatch)
    recording(tmp_path)
    app = make_app(tmp_path, public_live=False)
    library = library_of(app)
    entered, release = threading.Event(), threading.Event()
    original = library.acquire

    def acquire(key):
        result = original(key)
        entered.set()
        if not release.wait(3):
            raise TimeoutError("controlled acquire watchdog")
        return result

    monkeypatch.setattr(library, "acquire", acquire)

    class MockSocket:
        def __init__(self):
            self.query_params = {"session_key": "100", "mode": "replay"}

        async def accept(self):
            pass

        async def send_json(self, payload):
            pass

        async def close(self, **kw):
            pass

        async def receive_json(self):
            await asyncio.sleep(10)

    async def run():
        task = asyncio.create_task(endpoint(app, "/api/v1/stream")(MockSocket()))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            await asyncio.sleep(0.02)
            release.set()
            with suppress(asyncio.CancelledError):
                await task
            assert not library._leased, (
                "cancelled opening abandons a pinned resource before release finally is entered"
            )
            assert not library._pins, "pins leaked after cancelled acquire"
        finally:
            release.set()
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    asyncio.run(run())


def test_cancellation_before_acquire_leaves_no_pins(tmp_path, monkeypatch):
    """C3 boundary: Cancellation before acquire starts leaves zero pins."""
    quiet(monkeypatch)
    recording(tmp_path)
    app = make_app(tmp_path, public_live=False)
    library = library_of(app)

    class MockSocket:
        def __init__(self):
            self.query_params = {"session_key": "100", "mode": "replay"}

        async def accept(self):
            raise asyncio.CancelledError()

        async def send_json(self, payload):
            pass

        async def close(self, **kw):
            pass

        async def receive_json(self):
            await asyncio.sleep(10)

    async def run():
        task = asyncio.create_task(endpoint(app, "/api/v1/stream")(MockSocket()))
        with suppress(asyncio.CancelledError):
            await task
        assert not library._leased, "cancellation before acquire leaked lease"
        assert not library._pins, "cancellation before acquire leaked pins"

    asyncio.run(run())


def test_cancellation_after_acquire_releases_resource(tmp_path, monkeypatch):
    """C3 boundary: Cancellation after acquire while active releases resource."""
    quiet(monkeypatch)
    recording(tmp_path)
    app = make_app(tmp_path, public_live=False)
    library = library_of(app)
    opened = asyncio.Event()

    class MockSocket:
        def __init__(self):
            self.query_params = {"session_key": "100", "mode": "replay"}

        async def accept(self):
            pass

        async def send_json(self, payload):
            if payload.get("playbackReady"):
                opened.set()

        async def close(self, **kw):
            pass

        async def receive_json(self):
            await asyncio.sleep(10)

    async def run():
        task = asyncio.create_task(endpoint(app, "/api/v1/stream")(MockSocket()))
        try:
            await asyncio.wait_for(opened.wait(), timeout=2.0)
            assert len(library._leased) > 0, "resource should be leased while streaming"
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            assert not library._leased, (
                "cancellation after acquire must release leased resource"
            )
            assert not library._pins, (
                "cancellation after acquire must clean up all pins"
            )
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            await app.router.on_shutdown[0]()

    asyncio.run(run())


def test_acquire_error_cleanup_does_not_leak_pins(tmp_path, monkeypatch):
    """C3 boundary: Erroneous acquire cleanly unwinds without leaking pins."""
    quiet(monkeypatch)
    recording(tmp_path)
    app = make_app(tmp_path, public_live=False)
    library = library_of(app)

    class MockSocket:
        def __init__(self):
            self.query_params = {"session_key": "999-invalid", "mode": "replay"}
            self.closed = False

        async def accept(self):
            pass

        async def send_json(self, payload):
            pass

        async def close(self, **kw):
            self.closed = True

        async def receive_json(self):
            await asyncio.sleep(10)

    async def run():
        socket = MockSocket()
        task = asyncio.create_task(endpoint(app, "/api/v1/stream")(socket))
        await task
        assert not library._leased, "invalid session error must not leak leases"
        assert not library._pins, "invalid session error must not leak pins"

    asyncio.run(run())


def test_concurrent_viewers_survive_one_cancellation(tmp_path, monkeypatch):
    """C3 boundary: When one viewer is cancelled, concurrent viewers survive uncorrupted."""
    quiet(monkeypatch)
    recording(tmp_path)
    app = make_app(tmp_path, public_live=False)
    library = library_of(app)

    ready_1, ready_2 = asyncio.Event(), asyncio.Event()
    disconnect_2 = asyncio.Event()

    class Socket1:
        def __init__(self):
            self.query_params = {"session_key": "100", "mode": "replay"}

        async def accept(self):
            pass

        async def send_json(self, payload):
            if payload.get("playbackReady"):
                ready_1.set()

        async def close(self, **kw):
            pass

        async def receive_json(self):
            await asyncio.sleep(10)

    class Socket2:
        def __init__(self):
            self.query_params = {"session_key": "100", "mode": "replay"}

        async def accept(self):
            pass

        async def send_json(self, payload):
            if payload.get("playbackReady"):
                ready_2.set()

        async def close(self, **kw):
            pass

        async def receive_json(self):
            await disconnect_2.wait()
            raise WebSocketDisconnect()

    async def run():
        task1 = asyncio.create_task(endpoint(app, "/api/v1/stream")(Socket1()))
        task2 = asyncio.create_task(endpoint(app, "/api/v1/stream")(Socket2()))
        try:
            await asyncio.wait_for(ready_1.wait(), timeout=2.0)
            await asyncio.wait_for(ready_2.wait(), timeout=2.0)

            resource = library.get("100")
            # Preparation has its own lease; wait for its cleanup before
            # asserting the two viewer leases in this tiny synthetic fixture.
            for _ in range(100):
                if resource.prepared and library._pins.get(id(resource)) == 2:
                    break
                await asyncio.sleep(0.01)
            assert library._pins.get(id(resource)) == 2

            # Cancel viewer 1
            task1.cancel()
            with suppress(asyncio.CancelledError):
                await task1

            # Viewer 2 remains active, pin decrements by 1
            assert not task2.done(), "Viewer 2 should survive cancellation of Viewer 1"
            assert library._pins.get(id(resource)) == 1

            # Disconnect viewer 2 cleanly
            disconnect_2.set()
            await task2

            assert not library._leased, (
                "All leases should be cleared after both viewers exit"
            )
            assert not library._pins, (
                "All pins should be cleared after both viewers exit"
            )
        finally:
            for t in (task1, task2):
                if not t.done():
                    t.cancel()
                    with suppress(asyncio.CancelledError):
                        await t
            await app.router.on_shutdown[0]()

    asyncio.run(run())


# ==============================================================================
# C4: Release non-blocking event loop behind slow load
# ==============================================================================


def test_viewer_close_does_not_block_event_loop_behind_other_load(
    tmp_path, monkeypatch
):
    """C4: Viewer close does not block the asyncio event loop behind another slow load."""
    quiet(monkeypatch)
    recording(tmp_path, "100")
    recording(tmp_path, "200")
    app = make_app(tmp_path, public_live=False)
    library = library_of(app)
    selected_ready, disconnect = asyncio.Event(), asyncio.Event()
    entered, release = threading.Event(), threading.Event()
    original = library.refresh_session

    def refresh(key, *args, **kwargs):
        if key == "200":
            entered.set()
            if not release.wait(3):
                raise TimeoutError("controlled load watchdog")
        return original(key, *args, **kwargs)

    monkeypatch.setattr(library, "refresh_session", refresh)

    class MockSocket:
        def __init__(self):
            self.query_params = {"session_key": "100", "mode": "replay"}

        async def accept(self):
            pass

        async def send_json(self, payload):
            selected_ready.set()

        async def close(self, **kw):
            pass

        async def receive_json(self):
            await disconnect.wait()
            raise WebSocketDisconnect()

    async def run():
        ticks = []

        async def ticker():
            while True:
                ticks.append(time.perf_counter())
                await asyncio.sleep(0.005)

        ticktask = asyncio.create_task(ticker())
        task = asyncio.create_task(endpoint(app, "/api/v1/stream")(MockSocket()))
        load = None
        timer = None
        try:
            await asyncio.wait_for(selected_ready.wait(), 2)
            load = asyncio.create_task(asyncio.to_thread(library.get, "200"))
            assert await asyncio.to_thread(entered.wait, 2)

            # Load holds library lock; watchdog releases it so blocked loop doesn't hang
            timer = threading.Timer(0.35, release.set)
            timer.start()
            disconnect.set()
            await task
            await load
            await asyncio.sleep(0.02)
            maximum = max(b - a for a, b in itertools.pairwise(ticks))
            print("event-loop heartbeat gap on viewer close", maximum)
            assert maximum < 0.15, (
                "library.release synchronously blocks event loop behind another replay load"
            )
        finally:
            release.set()
            if timer:
                timer.cancel()
            if load:
                await load
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            ticktask.cancel()
            with suppress(asyncio.CancelledError):
                await ticktask
            await app.router.on_shutdown[0]()

    asyncio.run(run())


# ==============================================================================
# C5: Queued preparation lifetimes, failure cleanup, and duplicate coalescing
# ==============================================================================


def test_queued_preparation_resources_are_in_retained_budget(tmp_path, monkeypatch):
    """C5: Queued preparation must not retain evicted resources outside the cache budget."""
    quiet(monkeypatch)
    for i in range(6):
        recording(tmp_path, str(100 + i))
    app = make_app(tmp_path, public_live=False)
    library = library_of(app)
    stream_selected = inspect.getclosurevars(endpoint(app, "/api/v1/stream")).nonlocals[
        "stream_selected"
    ]
    ensure_preparation = inspect.getclosurevars(stream_selected).nonlocals[
        "ensure_preparation"
    ]
    preparations = inspect.getclosurevars(ensure_preparation).nonlocals["preparations"]

    async def wait_for_preparation_registration(key):
        # The first frame intentionally precedes preparation registration. Keep
        # this viewer until the queued-job premise of this test is established.
        for _ in range(200):
            selected = library._cache.get(key)
            if selected is not None and id(selected) in preparations:
                return
            await asyncio.sleep(0.005)
        raise AssertionError("preparation was not registered before viewer close")

    entered, release = threading.Event(), threading.Event()
    original = ReplayResource.prepare
    resources = []
    acquire = library.acquire

    def track(key):
        resource = acquire(key)
        resources.append(weakref.ref(resource))
        return resource

    monkeypatch.setattr(library, "acquire", track)

    def prepare(resource):
        entered.set()
        if not release.wait(5):
            raise TimeoutError("preparation watchdog")
        return original(resource)

    monkeypatch.setattr(ReplayResource, "prepare", prepare)
    try:
        with TestClient(app) as client:
            try:
                admitted, busy = [], []
                for i in range(6):
                    with client.websocket_connect(
                        f"/api/v1/stream?session_key={100 + i}&mode=replay"
                    ) as ws:
                        opening = ws.receive_json()
                        if opening.get("playbackReady"):
                            admitted.append(i)
                            client.portal.call(
                                wait_for_preparation_registration, str(100 + i)
                            )
                        else:
                            assert opening["type"] == "error"
                            assert "memory budget is in use" in opening["error"]
                            busy.append(i)
                assert entered.wait(1)
                gc.collect()
                alive = {id(r()): r() for r in resources if r() is not None}
                reserved = set(library._sizes)
                unreserved = set(alive) - reserved
                print(
                    "pending-preparation accounting",
                    {
                        "aliveResources": len(alive),
                        "cacheEntries": library.diagnostics["entries"],
                        "reservedResources": len(reserved),
                        "unreservedRetainedResources": len(unreserved),
                    },
                )
                assert not unreserved, (
                    "queued preparation retains evicted resources outside the cache budget"
                )
                assert 1 <= len(admitted) <= 3
                assert len(alive) <= 3 and len(reserved) <= 3
                assert len(admitted) + len(busy) == 6
            finally:
                release.set()
            for _ in range(100):
                if not library._pins:
                    break
                time.sleep(0.01)
            assert not library._pins
            for i in busy:
                with client.websocket_connect(
                    f"/api/v1/stream?session_key={100 + i}&mode=replay"
                ) as ws:
                    assert ws.receive_json()["playbackReady"]
    finally:
        release.set()


def test_preparation_failure_does_not_leave_pins_or_tasks(tmp_path, monkeypatch):
    """C5 boundary: Preparation failure cleans up without leaking pins or background tasks."""
    quiet(monkeypatch)
    recording(tmp_path, "100")
    app = make_app(tmp_path, public_live=False)
    library = library_of(app)
    failed_event = threading.Event()

    def failing_prepare(self):
        failed_event.set()
        raise RuntimeError("simulated preparation failure")

    monkeypatch.setattr(ReplayResource, "prepare", failing_prepare)

    with (
        TestClient(app) as client,
        client.websocket_connect("/api/v1/stream?session_key=100&mode=replay") as ws,
    ):
        initial = ws.receive_json()
        assert initial.get("playbackReady") is True
        assert failed_event.wait(2.0), "preparation was not attempted"
        time.sleep(0.05)

    assert not library._leased, "preparation failure must not leave leased resources"
    assert not library._pins, "preparation failure must not leave pinned resources"


def test_duplicate_preparation_does_not_leave_pins_or_duplicate_tasks(
    tmp_path, monkeypatch
):
    """C5 boundary: Duplicate preparation requests coalesce without pin or task leakage."""
    quiet(monkeypatch)
    recording(tmp_path, "100")
    app = make_app(tmp_path, public_live=False)
    library = library_of(app)
    prepare_started = threading.Event()
    prepare_release = threading.Event()
    original_prepare = ReplayResource.prepare
    calls = []

    def tracked_prepare(self):
        calls.append(id(self))
        prepare_started.set()
        if not prepare_release.wait(3.0):
            raise TimeoutError("preparation release watchdog")
        return original_prepare(self)

    monkeypatch.setattr(ReplayResource, "prepare", tracked_prepare)

    try:
        with (
            TestClient(app) as client,
            client.websocket_connect(
                "/api/v1/stream?session_key=100&mode=replay"
            ) as ws1,
        ):
            assert ws1.receive_json().get("playbackReady") is True
            assert prepare_started.wait(2.0), "first preparation did not start"
            with client.websocket_connect(
                "/api/v1/stream?session_key=100&mode=replay"
            ) as ws2:
                assert ws2.receive_json().get("playbackReady") is True
                prepare_release.set()
                time.sleep(0.05)
    finally:
        prepare_release.set()

    assert not library._leased, "duplicate preparation must not leak leases"
    assert not library._pins, "duplicate preparation must not leak pins"
    assert len(calls) == 1, "viewers must share one preparation job"
