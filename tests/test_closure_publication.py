"""Controlled regressions for closure, publication, deletion, and cursor recovery.

Maintained behavioral checks:
1. Old pending publication after collector transitions prevents DELETE with 409,
   retry then becomes available, then delete succeeds with no resurrection.
2. Deletion while a held finalize disk worker is running prevents ack (409).
3. Completed Q3 journal restarts/publishes offline (no upstream), idempotent restart.
4. Invalid journals (missing key, wrong key, future timestamps, Q1-only) are not published.
5. WS and REST seq+recording_version old value after atomic replacement resets to
   official start in the SAME response with new frozen metadata.
6. Known version on the same recording preserves the cursor.
7. Analytics endpoint returns 409 for foreign recording versions.
8. Selective runtime cancellation preserves disk worker writer ownership.

Synthetic fixtures only; Pirelli features disabled; no actual upstream or network.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import threading
import time
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from slipstream.api import create_app
from slipstream.catalog import CATALOG_FORMAT
from slipstream.events import NormalizedEvent
from slipstream.library import ReplayLibrary
from slipstream.live import PublicLiveSession
from slipstream.live_recording import NormalizedLiveRecorder


def quiet(monkeypatch) -> None:
    """Disable Pirelli background features and remove network credentials."""
    for feature in ("SEED", "REFRESH", "BACKFILL"):
        monkeypatch.setenv(f"SLIPSTREAM_PIRELLI_{feature}", "0")
    monkeypatch.delenv("OPENF1_TOKEN", raising=False)
    monkeypatch.delenv("SLIPSTREAM_CREDENTIALS", raising=False)


def event(at: str, kind: str = "session", **payload: Any) -> NormalizedEvent:
    return NormalizedEvent(kind, at, "SYNTHETIC-CLOSURE", payload)


def catalog(root: Path) -> None:
    (root / "catalog.json").write_text(
        json.dumps(
            {
                "format": CATALOG_FORMAT,
                "source": "openf1",
                "meetings": {},
                "sessions": [
                    {
                        "session_key": "100",
                        "meeting_key": "1293",
                        "year": 2026,
                        "session_name": "Qualifying",
                        "session_type": "Qualifying",
                        "date_start": "2026-09-05T14:00:00Z",
                        "date_end": "2026-09-05T15:00:00Z",
                    },
                    {
                        "session_key": "200",
                        "meeting_key": "1293",
                        "year": 2026,
                        "session_name": "Qualifying",
                        "session_type": "Qualifying",
                        "date_start": "2026-09-05T14:00:00Z",
                        "date_end": "2026-09-05T15:00:00Z",
                    },
                    {
                        "session_key": "11357",
                        "meeting_key": "1293",
                        "year": 2026,
                        "session_name": "Qualifying",
                        "session_type": "Qualifying",
                        "date_start": "2026-09-05T14:00:00Z",
                        "date_end": "2026-09-05T15:00:00Z",
                    },
                    {
                        "session_key": "101",
                        "meeting_key": "1293",
                        "year": 2026,
                        "session_name": "Qualifying",
                        "session_type": "Qualifying",
                        "date_start": "2026-09-05T14:00:00Z",
                        "date_end": "2026-09-05T15:00:00Z",
                    },
                    {
                        "session_key": "102",
                        "meeting_key": "1293",
                        "year": 2026,
                        "session_name": "Qualifying",
                        "session_type": "Qualifying",
                        "date_start": "2026-09-05T14:00:00Z",
                        "date_end": "2026-09-05T15:00:00Z",
                    },
                    {
                        "session_key": "103",
                        "meeting_key": "1293",
                        "year": 2026,
                        "session_name": "Qualifying",
                        "session_type": "Qualifying",
                        "date_start": "2026-09-05T14:00:00Z",
                        "date_end": "2026-09-05T15:00:00Z",
                    },
                    {
                        "session_key": "104",
                        "meeting_key": "1293",
                        "year": 2026,
                        "session_name": "Qualifying",
                        "session_type": "Qualifying",
                        "date_start": "2026-09-05T14:00:00Z",
                        "date_end": "2026-09-05T15:00:00Z",
                    },
                ],
            }
        )
    )


def make_recording(root: Path, key: str = "100") -> tuple[Path, list[NormalizedEvent]]:
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
        event("2026-09-05T14:05:00Z", "timing", number="44", lap=1),
        event("2026-09-05T14:10:00Z", "timing", number="44", lap=2),
    ]
    path = root / f"live-{key}.json"
    path.write_text(json.dumps([asdict(e) for e in rows]))
    return path, rows


def make_app(root: Path, **kwargs: Any):
    return create_app(root, prepare_weekend_context=lambda **kw: {}, **kwargs)


def endpoint(app, path: str):
    return next(r.endpoint for r in app.routes if r.path == path)


def library_of(app) -> ReplayLibrary:
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


def rollout_catalog(root):
    """Two distinct sessions matching the manually driven lifecycle below."""
    catalog(root)
    path = root / "catalog.json"
    payload = json.loads(path.read_text())
    payload["sessions"] = [
        s for s in payload["sessions"] if s["session_key"] in {"100", "200"}
    ]
    old = payload["sessions"][0]
    old.update(
        session_name="Practice 3",
        session_type="Practice",
        date_start="2026-09-05T10:00:00Z",
        date_end="2026-09-05T11:00:00Z",
    )
    path.write_text(json.dumps(payload))


def establish_under_monitor_ownership(client, app, live, establish):
    """Manual test setup must not race the app's automatic startup monitor."""
    delete_endpoint = next(
        r.endpoint
        for r in app.routes
        if r.path == "/api/v1/replay" and "DELETE" in getattr(r, "methods", set())
    )
    lock = inspect.getclosurevars(delete_endpoint).nonlocals["live_reconcile_lock"]

    async def owned():
        async with lock:
            await live.stop(preserve_publications=True)
            await establish()

    client.portal.call(owned)


# ==============================================================================
# 1. Old pending publication after collector transition prevents DELETE with 409
# ==============================================================================


def test_old_pending_publication_after_collector_transition_prevents_delete_with_409(
    tmp_path, monkeypatch
):
    """Old pending publication in retry prevents DELETE with 409, then succeeds without resurrection."""
    quiet(monkeypatch)
    rollout_catalog(tmp_path)
    now = datetime(2026, 9, 5, 14, 2, tzinfo=UTC)

    async def idle_rows():
        while True:
            await asyncio.sleep(10)
            yield {}

    live = PublicLiveSession(
        row_source=idle_rows,
        now=lambda: now,
        finalization_drain=0,
        maximum_backoff=0.02,
    )
    app = make_app(tmp_path, public_live=True, live_session=live, now=lambda: now)

    fail = threading.Event()
    fail.set()
    attempted = threading.Event()
    original_finalize = NormalizedLiveRecorder.finalize

    def finalize(recorder):
        if recorder.session_key == "100" and fail.is_set():
            attempted.set()
            raise OSError("controlled publication outage")
        return original_finalize(recorder)

    monkeypatch.setattr(NormalizedLiveRecorder, "finalize", finalize)

    async def establish():
        await live.start(
            "100",
            seed_events=(
                event(
                    "2026-09-05T11:00:00Z",
                    key="100",
                    name="Practice 3",
                    session_type="Practice",
                    session_kind="practice",
                    status="FINISHED",
                    session_complete=True,
                ),
            ),
        )
        await live.finish_pending()
        assert await asyncio.to_thread(attempted.wait, 2)
        await live.start(
            "200",
            seed_events=(
                event(
                    "2026-09-05T14:00:00Z",
                    key="200",
                    name="Qualifying",
                    session_type="Qualifying",
                    session_kind="qualifying",
                    status="RUNNING",
                ),
            ),
        )

    with TestClient(app) as client:
        establish_under_monitor_ownership(client, app, live, establish)
        # Session 100 has a pending retry in background, collector has transitioned to 200.
        # DELETE must be rejected with 409.
        busy_result = client.delete("/api/v1/replay?session_key=100")
        assert busy_result.status_code == 409, (
            f"Expected 409 for pending publication deletion, got {busy_result.status_code}"
        )

        # Allow publication to succeed
        fail.clear()
        for _ in range(100):
            cat = client.get("/api/v1/catalog").json()
            s100 = next(
                (
                    s
                    for s in cat["sessions"]
                    if (s.get("sessionKey") or s.get("session_key")) == "100"
                ),
                None,
            )
            if s100 and s100.get("available") and s100.get("replayReady"):
                break
            time.sleep(0.02)

        # Once available, delete must succeed
        delete_result = client.delete("/api/v1/replay?session_key=100")
        assert delete_result.status_code == 200, (
            f"Expected 200 for available replay deletion, got {delete_result.status_code}"
        )
        assert delete_result.json().get("status") == "unavailable"

        # Verify no resurrection occurs after acknowledged deletion
        time.sleep(0.05)
        assert not (tmp_path / "live-100.json").exists(), (
            "Acknowledged deletion was resurrected"
        )
        assert not (tmp_path / "live-100.in-progress.jsonl").exists(), (
            "Journal retained after successful deletion"
        )


# ==============================================================================
# 2. Deletion while a held finalize disk worker is running prevents ack
# ==============================================================================


def test_deletion_during_held_finalize_disk_worker_prevents_ack(tmp_path, monkeypatch):
    """Calling DELETE while the finalize disk worker is actively executing returns 409."""
    quiet(monkeypatch)
    rollout_catalog(tmp_path)
    now = datetime(2026, 9, 5, 11, 2, tzinfo=UTC)

    async def idle_rows():
        while True:
            await asyncio.sleep(10)
            yield {}

    live = PublicLiveSession(
        row_source=idle_rows,
        now=lambda: now,
        finalization_drain=0,
        maximum_backoff=0.02,
    )
    app = make_app(tmp_path, public_live=True, live_session=live, now=lambda: now)

    entered = threading.Event()
    release = threading.Event()
    original_finalize = NormalizedLiveRecorder.finalize

    def finalize(recorder):
        if recorder.session_key == "100":
            entered.set()
            if not release.wait(5):
                raise TimeoutError("held finalize worker watchdog timed out")
        return original_finalize(recorder)

    monkeypatch.setattr(NormalizedLiveRecorder, "finalize", finalize)

    async def establish():
        await live.start(
            "100",
            seed_events=(
                event(
                    "2026-09-05T11:00:00Z",
                    key="100",
                    name="Practice 3",
                    session_type="Practice",
                    session_kind="practice",
                    status="FINISHED",
                    session_complete=True,
                ),
            ),
        )
        await live.finish_pending()

    try:
        with TestClient(app) as client:
            establish_under_monitor_ownership(client, app, live, establish)
            assert entered.wait(2), "Finalize worker was not entered"

            # While disk worker is running, delete attempt must return 409
            result = client.delete("/api/v1/replay?session_key=100")
            assert result.status_code == 409, (
                f"Expected 409 busy response while finalize disk worker is held, got {result.status_code}"
            )

            # Release the worker so it finishes properly
            release.set()
            for _ in range(50):
                if (tmp_path / "live-100.json").exists():
                    break
                time.sleep(0.02)

            assert (tmp_path / "live-100.json").exists(), (
                "Final recording was not created after worker released"
            )
    finally:
        release.set()


# ==============================================================================
# 3. Completed Q3 journal restarts/publishes offline (no upstream), idempotent
# ==============================================================================


def test_completed_q3_journal_restarts_and_publishes_offline_idempotent(
    tmp_path, monkeypatch
):
    """Completed Q3 journal publishes offline on startup without upstream calls; restarting is idempotent."""
    quiet(monkeypatch)
    catalog(tmp_path)

    session_start = "2026-09-05T14:00:00Z"
    session_end = "2026-09-05T15:00:00Z"
    restart_time = datetime(2026, 9, 5, 15, 2, tzinfo=UTC)

    recorder = NormalizedLiveRecorder(tmp_path, "11357")
    recorder.append(
        (
            event(
                session_start,
                key="11357",
                name="Qualifying",
                session_type="Qualifying",
                session_kind="qualifying",
                started_at=session_start,
                ended_at=session_end,
                status="RUNNING",
            ),
            event("2026-09-05T14:55:00Z", qualifying_phase="Q3"),
            event("2026-09-05T15:01:00Z", status="FINISHED"),
        )
    )

    upstream_calls: list[str] = []

    async def rows():
        upstream_calls.append("opened")
        while True:
            await asyncio.sleep(3600)
            yield {}

    live1 = PublicLiveSession(row_source=rows, now=lambda: restart_time)
    app1 = make_app(
        tmp_path,
        now=lambda: restart_time,
        public_live=True,
        live_session=live1,
    )

    with TestClient(app1) as client:
        # Wait for completed journal recovery to publish
        published = False
        for _ in range(50):
            cat = client.get("/api/v1/catalog").json()
            session = next(
                (
                    s
                    for s in cat["sessions"]
                    if (s.get("sessionKey") or s.get("session_key")) == "11357"
                ),
                None,
            )
            if session and session.get("available"):
                published = True
                break
            time.sleep(0.04)

        assert published, "Completed Q3 journal was not published offline on restart"
        assert not upstream_calls, (
            "Upstream collection was resumed for an already completed journal"
        )
        assert (tmp_path / "live-11357.json").exists()

    # Idempotent restart: start another instance on the same directory
    restart_time2 = datetime(2026, 9, 5, 15, 5, tzinfo=UTC)
    live2 = PublicLiveSession(row_source=rows, now=lambda: restart_time2)
    app2 = make_app(
        tmp_path,
        now=lambda: restart_time2,
        public_live=True,
        live_session=live2,
    )

    with TestClient(app2) as client2:
        cat2 = client2.get("/api/v1/catalog").json()
        session2 = next(
            (
                s
                for s in cat2["sessions"]
                if (s.get("sessionKey") or s.get("session_key")) == "11357"
            ),
            None,
        )
        assert session2 and session2.get("available"), (
            "Session not available on second restart"
        )
        assert not upstream_calls, "Upstream connection attempted on idempotent restart"


# ==============================================================================
# 4. Invalid missing/wrong key/future/Q1-only journals not published
# ==============================================================================


@pytest.mark.parametrize("invalid_key", ["101", "102", "103", "104"])
def test_invalid_journals_not_published(tmp_path, monkeypatch, invalid_key):
    """Journals that are invalid (missing key, wrong key, future timestamps, or Q1-only) are rejected."""
    quiet(monkeypatch)
    catalog(tmp_path)
    now = datetime(2026, 9, 5, 15, 2, tzinfo=UTC)

    # 1. Missing key
    rec_101 = NormalizedLiveRecorder(tmp_path, "101")
    rec_101.append(
        (
            event(
                "2026-09-05T14:00:00Z",
                name="Qualifying",
                session_type="Qualifying",
                status="RUNNING",
            ),
            event("2026-09-05T14:55:00Z", qualifying_phase="Q3"),
            event("2026-09-05T15:01:00Z", status="FINISHED"),
        )
    )

    # 2. Wrong key (declares key 999 inside payload)
    rec_102 = NormalizedLiveRecorder(tmp_path, "102")
    rec_102.append(
        (
            event(
                "2026-09-05T14:00:00Z",
                key="999",
                name="Qualifying",
                session_type="Qualifying",
                status="RUNNING",
            ),
            event("2026-09-05T14:55:00Z", qualifying_phase="Q3"),
            event("2026-09-05T15:01:00Z", status="FINISHED"),
        )
    )

    # 3. Future timestamps (event occurred_at in the future relative to now)
    rec_103 = NormalizedLiveRecorder(tmp_path, "103")
    rec_103.append(
        (
            event(
                "2026-09-05T16:00:00Z",
                key="103",
                name="Qualifying",
                session_type="Qualifying",
                status="RUNNING",
            ),
            event("2026-09-05T16:55:00Z", qualifying_phase="Q3"),
            event("2026-09-05T17:01:00Z", status="FINISHED"),
        )
    )

    # 4. Q1-only journal for Qualifying session (not complete)
    rec_104 = NormalizedLiveRecorder(tmp_path, "104")
    rec_104.append(
        (
            event(
                "2026-09-05T14:00:00Z",
                key="104",
                name="Qualifying",
                session_type="Qualifying",
                status="RUNNING",
            ),
            event("2026-09-05T14:15:00Z", qualifying_phase="Q1"),
            event("2026-09-05T14:20:00Z", status="FINISHED"),
        )
    )

    async def idle_rows():
        while True:
            await asyncio.sleep(10)
            yield {}

    # Put the selected invalid fixture inside the first bounded scan batch.
    # Every case must actually be inspected before asserting non-publication.
    payload = json.loads((tmp_path / "catalog.json").read_text())
    payload["sessions"] = [
        row for row in payload["sessions"] if row["session_key"] == invalid_key
    ]
    (tmp_path / "catalog.json").write_text(json.dumps(payload))
    inspected = threading.Event()
    original_recover = NormalizedLiveRecorder._recover

    def observed_recover(recorder):
        try:
            return original_recover(recorder)
        finally:
            if recorder.session_key == invalid_key:
                inspected.set()

    monkeypatch.setattr(NormalizedLiveRecorder, "_recover", observed_recover)
    live = PublicLiveSession(row_source=idle_rows, now=lambda: now)
    app = make_app(tmp_path, public_live=False, live_session=live, now=lambda: now)

    with TestClient(app) as client:
        assert inspected.wait(2), "The invalid journal must be inspected in this test"
        time.sleep(0.1)

        cat = client.get("/api/v1/catalog").json()
        sessions = {
            (s.get("sessionKey") or s.get("session_key")): s for s in cat["sessions"]
        }

        assert not (tmp_path / f"live-{invalid_key}.json").exists(), (
            f"Invalid journal {invalid_key} was erroneously finalized to JSON"
        )
        assert not sessions[invalid_key].get("available"), (
            f"Invalid journal {invalid_key} became available in catalog"
        )


# ==============================================================================
# 5 & 6. WS/REST version mismatch resets cursor; known version preserves cursor
# ==============================================================================


def test_ws_and_rest_recording_version_mismatch_and_preservation(tmp_path, monkeypatch):
    """WS & REST seq+recording_version mismatch resets to start with new frozen metadata; matching preserves."""
    quiet(monkeypatch)
    catalog(tmp_path)
    p, _rows_v1 = make_recording(tmp_path, "100")

    app = make_app(
        tmp_path,
        public_live=False,
        now=lambda: datetime(2026, 9, 5, 16, tzinfo=UTC),
    )

    with TestClient(app) as client:
        # 1. Obtain V1 initial state & recordingVersion
        v1_state = client.get("/api/v1/state?session_key=100&mode=replay&seq=2").json()
        v1_version = v1_state["metadata"]["recordingVersion"]
        assert v1_state["seq"] == 2
        assert v1_version is not None

        # 2. Known version matching preserves cursor in REST
        rest_matching = client.get(
            f"/api/v1/state?session_key=100&mode=replay&seq=2&recording_version={v1_version}"
        ).json()
        assert rest_matching["seq"] == 2
        assert rest_matching["metadata"]["recordingVersion"] == v1_version

        # 3. Known version matching preserves cursor in WS
        with client.websocket_connect(
            f"/api/v1/stream?session_key=100&mode=replay&seq=2&recording_version={v1_version}"
        ) as ws:
            ws_matching = ws.receive_json()
            assert ws_matching["seq"] == 2
            assert ws_matching["metadata"]["recordingVersion"] == v1_version

        # 4. Perform atomic replacement with new recording (V2)
        rows_v2 = [
            event(
                "2026-09-05T14:00:00Z",
                key="100",
                name="Qualifying",
                session_type="Qualifying",
                started_at="2026-09-05T14:00:00Z",
                ended_at="2026-09-05T15:00:00Z",
                status="RUNNING",
            ),
            event("2026-09-05T14:02:00Z", "driver", number="44", name="Driver"),
            event("2026-09-05T14:05:00Z", "timing", number="44", lap=1),
            event("2026-09-05T14:10:00Z", "timing", number="44", lap=2),
        ]
        temp = tmp_path / "replacement.tmp"
        temp.write_text(json.dumps([asdict(e) for e in rows_v2]))
        temp.replace(p)

        # 5. REST seq + old recording_version resets to official start in SAME response
        rest_mismatched = client.get(
            f"/api/v1/state?session_key=100&mode=replay&seq=2&recording_version={v1_version}"
        ).json()
        assert rest_mismatched["seq"] == 1, (
            f"Expected reset to seq 1 on version mismatch, got {rest_mismatched['seq']}"
        )
        v2_version = rest_mismatched["metadata"]["recordingVersion"]
        assert v2_version != v1_version, "Expected updated recordingVersion in metadata"

        # 6. WS seq + old recording_version resets to official start in SAME response
        with client.websocket_connect(
            f"/api/v1/stream?session_key=100&mode=replay&seq=2&recording_version={v1_version}"
        ) as ws:
            ws_mismatched = ws.receive_json()
            assert ws_mismatched["seq"] == 1, (
                f"Expected reset to seq 1 on WS version mismatch, got {ws_mismatched['seq']}"
            )
            assert ws_mismatched["metadata"]["recordingVersion"] == v2_version

        # 7. Known version matching on the NEW recording preserves cursor in REST & WS
        rest_v2_match = client.get(
            f"/api/v1/state?session_key=100&mode=replay&seq=3&recording_version={v2_version}"
        ).json()
        assert rest_v2_match["seq"] == 3
        assert rest_v2_match["metadata"]["recordingVersion"] == v2_version

        with client.websocket_connect(
            f"/api/v1/stream?session_key=100&mode=replay&seq=3&recording_version={v2_version}"
        ) as ws:
            ws_v2_match = ws.receive_json()
            assert ws_v2_match["seq"] == 3
            assert ws_v2_match["metadata"]["recordingVersion"] == v2_version


# ==============================================================================
# 7. Analytics foreign version 409
# ==============================================================================


def test_analytics_foreign_version_returns_409(tmp_path, monkeypatch):
    """Analytics request with mismatched foreign recording_version returns 409."""
    quiet(monkeypatch)
    catalog(tmp_path)
    make_recording(tmp_path, "100")

    app = make_app(
        tmp_path,
        public_live=False,
        now=lambda: datetime(2026, 9, 5, 16, tzinfo=UTC),
    )

    with TestClient(app) as client:
        state = client.get("/api/v1/state?session_key=100&mode=replay").json()
        valid_version = state["metadata"]["recordingVersion"]

        # Foreign version must return 409
        foreign_resp = client.get(
            "/api/v1/analytics?session_key=100&recording_version=foreign_v9999"
        )
        assert foreign_resp.status_code == 409, (
            f"Expected 409 for foreign analytics version, got {foreign_resp.status_code}"
        )
        assert (
            foreign_resp.json().get("detail")
            == "Recording changed; refresh state before requesting analytics"
        )

        # Correct version returns 200
        valid_resp = client.get(
            f"/api/v1/analytics?session_key=100&recording_version={valid_version}"
        )
        assert valid_resp.status_code == 200, (
            f"Expected 200 for matching analytics version, got {valid_resp.status_code}"
        )


# ==============================================================================
# 8. Selective runtime cancellation preserves disk worker writer ownership
# ==============================================================================


def test_runtime_cancellation_preserves_writer_ownership(tmp_path, monkeypatch):
    """Cancellation of a publication task preserves writer ownership through completion."""
    quiet(monkeypatch)
    recorder = NormalizedLiveRecorder(tmp_path, "100")
    recorder.append(
        [
            event(
                "2026-09-05T14:00:00Z",
                key="100",
                name="Practice",
                session_type="Practice",
                session_kind="practice",
                started_at="2026-09-05T14:00:00Z",
                ended_at="2026-09-05T15:00:00Z",
                status="FINISHED",
                session_complete=True,
            )
        ]
    )

    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    original_finalize = NormalizedLiveRecorder.finalize

    def finalize(rec):
        if rec.session_key == "100":
            entered.set()
            if not release.wait(5):
                raise TimeoutError("finalize release watchdog timed out")
        path = original_finalize(rec)
        finished.set()
        return path

    monkeypatch.setattr(NormalizedLiveRecorder, "finalize", finalize)

    async def run():
        published = []
        live = PublicLiveSession(
            normalized_recording_dir=tmp_path,
            finalization_drain=0,
        )
        live.configure_recording(tmp_path, lambda path: published.append(path) or True)
        await live.start("100")
        try:
            await live.finish_pending()
            assert await asyncio.to_thread(entered.wait, 2)
            task = live._publications["100"].task
            task.cancel()
            await asyncio.sleep(0.02)
            assert not task.done(), "Cancellation must retain the in-flight writer"
            release.set()
            with suppress(asyncio.CancelledError):
                await task
            assert finished.is_set(), "Writer ownership was interrupted by cancellation"
            assert recorder.final_path.exists(), (
                "Final recording was not completed on disk"
            )
            assert published == [recorder.final_path], (
                "Completed rename must still update catalog visibility"
            )
            assert live.view("100").replay_ready
        finally:
            release.set()
            await live.stop()

    asyncio.run(run())


def test_analytics_cache_is_scoped_to_recording_version(tmp_path, monkeypatch):
    quiet(monkeypatch)
    catalog(tmp_path)
    path, rows = make_recording(tmp_path)
    rows.append(event("2026-09-05T14:11:00Z", qualifying_phase="Q2"))
    path.write_text(json.dumps([asdict(row) for row in rows]))
    app = make_app(tmp_path, public_live=False)
    with TestClient(app) as client:
        first = client.get("/api/v1/analytics?session_key=100&seq=4").json()
        assert first["qualifying"]["phase"] == "Q2"
        rows[-1] = event("2026-09-05T14:11:00Z", qualifying_phase="Q3")
        replacement = tmp_path / "replacement.tmp"
        replacement.write_text(json.dumps([asdict(row) for row in rows]))
        replacement.replace(path)
        second = client.get("/api/v1/analytics?session_key=100&seq=4").json()
        assert second["recordingVersion"] != first["recordingVersion"]
        assert second["qualifying"]["phase"] == "Q3"


def test_offline_inspection_before_delete_cannot_register_after_ack(
    tmp_path, monkeypatch
):
    quiet(monkeypatch)
    catalog(tmp_path)
    recorder = NormalizedLiveRecorder(tmp_path, "100")
    recorder.append(
        (
            event(
                "2026-09-05T14:00:00Z",
                key="100",
                name="Qualifying",
                session_type="Qualifying",
                session_kind="qualifying",
                status="FINISHED",
                session_complete=True,
            ),
        )
    )
    live = PublicLiveSession()
    app = make_app(
        tmp_path,
        public_live=False,
        live_session=live,
        now=lambda: datetime(2026, 9, 5, 16, tzinfo=UTC),
    )
    inspected, resume = threading.Event(), asyncio.Event()
    original = live.recover_completed_recording
    results = []

    async def held_registration(selected, signature):
        inspected.set()
        await resume.wait()
        result = await original(selected, signature)
        results.append(result)
        return result

    monkeypatch.setattr(live, "recover_completed_recording", held_registration)
    with TestClient(app) as client:
        try:
            assert inspected.wait(2)
            response = client.delete("/api/v1/replay?session_key=100")
            assert response.status_code == 200
            client.portal.call(resume.set)
            for _ in range(100):
                if results:
                    break
                time.sleep(0.01)
            assert results == [False]
            assert not recorder.final_path.exists()
            assert not recorder.temporary_path.exists()
            assert "100" not in live.diagnostics["publications"]
        finally:
            client.portal.call(resume.set)
