"""Replay readiness and performance baseline benchmark harness.

Measures all Phase 1 baseline metrics and scenarios using locally available recordings.
Run with: uv run python tools/benchmark_baseline.py
"""

from __future__ import annotations

import asyncio
import ctypes
from ctypes import wintypes
import gc
import json
import os
import pathlib
import sys
import time
from typing import Any

from starlette.testclient import TestClient

from slipstream.adapters.openf1 import is_openf1_recording, recording_to_events
from slipstream.analytics import AnalyticsService
from slipstream.api import create_app
from slipstream.events import NormalizedEvent
from slipstream.evidence import SessionEvidence
from slipstream.library import ReplayLibrary, ReplayResource, SessionDescriptor
from slipstream.pirelli.store import PirelliAvailability
from slipstream.playback import ReplayController
from slipstream.replay import replay
from slipstream.state import RaceState
from slipstream.weekend import ContextAvailability

# Windows RSS measurement via GetProcessMemoryInfo
class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]

_GetProcessMemoryInfo = ctypes.windll.psapi.GetProcessMemoryInfo
_GetProcessMemoryInfo.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
    wintypes.DWORD,
]
_GetProcessMemoryInfo.restype = wintypes.BOOL

def get_process_rss_mb() -> float:
    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    _GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
    return counters.WorkingSetSize / (1024 * 1024)

RECORDINGS_DIR = pathlib.Path("recordings")

SESSIONS_TO_BENCHMARK = [
    {
        "name": "British GP 2024 Race (Canonical F1)",
        "path": RECORDINGS_DIR / "f1-static-11353.json",
        "session_key": "11353",
        "kind": "race",
        "source_tier": "canonical_f1",
    },
    {
        "name": "British GP 2024 Qualifying (Canonical F1)",
        "path": RECORDINGS_DIR / "f1-static-11349.json",
        "session_key": "11349",
        "kind": "qualifying",
        "source_tier": "canonical_f1",
    },
    {
        "name": "Spanish GP 2024 Race (OpenF1)",
        "path": RECORDINGS_DIR / "openf1-11299.json",
        "session_key": "11299",
        "kind": "race",
        "source_tier": "openf1",
    },
    {
        "name": "British GP 2024 Qualifying (OpenF1)",
        "path": RECORDINGS_DIR / "openf1-11349.json",
        "session_key": "11349",
        "kind": "qualifying",
        "source_tier": "openf1",
    },
]

def benchmark_single_session(cfg: dict[str, Any]) -> dict[str, Any]:
    path: pathlib.Path = cfg["path"]
    if not path.is_file():
        return {"error": f"File {path} not found"}

    file_size_mb = path.stat().st_size / (1024 * 1024)
    gc.collect()
    rss_before = get_process_rss_mb()

    # 1. Parse JSON
    t0 = time.perf_counter()
    raw = json.loads(path.read_text(encoding="utf-8"))
    t_parse = time.perf_counter() - t0

    # 2. Normalization
    t0 = time.perf_counter()
    if isinstance(raw, list):
        events = [NormalizedEvent.from_mapping(item) for item in raw]
    elif is_openf1_recording(raw):
        events = recording_to_events(raw)
    else:
        raise ValueError(f"Unknown format for {path}")
    t_norm = time.perf_counter() - t0
    event_count = len(events)

    # 3. Final state reduction
    t0 = time.perf_counter()
    final_state = replay(list(events))
    t_reduce = time.perf_counter() - t0

    # 4. SessionEvidence build
    t0 = time.perf_counter()
    evidence = SessionEvidence.from_events(events)
    t_evidence = time.perf_counter() - t0

    rss_after = get_process_rss_mb()

    # 5. Analytics calculation at final state
    t0 = time.perf_counter()
    analytics_svc = AnalyticsService()
    dummy_desc = SessionDescriptor(
        key=cfg["session_key"],
        year=2024,
        meeting_key=cfg["session_key"],
        meeting_name="Grand Prix",
        session_name="Race" if cfg["kind"] == "race" else "Qualifying",
        session_type="Race" if cfg["kind"] == "race" else "Qualifying",
        circuit="Silverstone",
        location="Silverstone",
        date_start=events[0].occurred_at if events else "",
        date_end=events[-1].occurred_at if events else "",
        gmt_offset="+01:00",
        path=path,
        source=cfg["source_tier"],
        capabilities={"historical_replay": True},
    )
    res = ReplayResource(
        descriptor=dummy_desc,
        events=tuple(events),
        final_state=final_state,
        evidence=evidence,
        replay_available=True,
        is_live=False,
    )
    analytics_snapshot = analytics_svc.snapshot(
        res,
        final_state,
        sequence=event_count,
        as_of=events[-1].occurred_at if events else None,
        context=ContextAvailability("unavailable"),
        pirelli=PirelliAvailability("ABSENT"),
    )
    t_analytics = time.perf_counter() - t0

    # 6. Seek operations
    controller = ReplayController(events)
    t0 = time.perf_counter()
    controller.seek_cursor(event_count // 2)
    t_seek_mid = time.perf_counter() - t0

    t0 = time.perf_counter()
    controller.seek_cursor(int(event_count * 0.95))
    t_seek_end = time.perf_counter() - t0

    return {
        "name": cfg["name"],
        "session_key": cfg["session_key"],
        "kind": cfg["kind"],
        "source_type": cfg["source_tier"],
        "file_size_mb": round(file_size_mb, 2),
        "event_count": event_count,
        "rss_before_mb": round(rss_before, 1),
        "rss_after_mb": round(rss_after, 1),
        "rss_delta_mb": round(rss_after - rss_before, 1),
        "parse_time_s": round(t_parse, 3),
        "normalization_time_s": round(t_norm, 3),
        "reduction_time_s": round(t_reduce, 3),
        "evidence_build_time_s": round(t_evidence, 3),
        "analytics_time_s": round(t_analytics, 3),
        "seek_50_s": round(t_seek_mid, 3),
        "seek_95_s": round(t_seek_end, 3),
        "total_compute_s": round(t_parse + t_norm + t_reduce + t_evidence + t_analytics, 3),
    }

def benchmark_end_to_end_scenarios() -> dict[str, Any]:
    results = {}
    print("\nRunning End-to-End Scenarios...")

    import tempfile
    import shutil
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = pathlib.Path(tmp_dir)
        shutil.copy(RECORDINGS_DIR / "catalog.json", tmp_path / "catalog.json")
        shutil.copy(RECORDINGS_DIR / "f1-static-11353.json", tmp_path / "f1-static-11353.json")
        shutil.copy(RECORDINGS_DIR / "f1-static-11349.json", tmp_path / "f1-static-11349.json")

        # 1. Cold server / process startup time
        t0 = time.perf_counter()
        app = create_app(tmp_path, public_live=False)
        client = TestClient(app)
        t_cold_startup = time.perf_counter() - t0

        # 2. First open of Session 11353 (Race)
        t0 = time.perf_counter()
        r_state = client.get("/api/v1/state?session_key=11353&mode=replay")
        t_first_rest_state = time.perf_counter() - t0

        t0 = time.perf_counter()
        r_replay = client.get("/api/v1/replay?session_key=11353")
        r_caps = client.get("/api/v1/capabilities?session_key=11353")
        t_first_metadata = time.perf_counter() - t0

        t0 = time.perf_counter()
        with client.websocket_connect("/api/v1/stream?session_key=11353&mode=replay") as ws:
            first_snapshot = ws.receive_json()
            t_first_ws_snapshot = time.perf_counter() - t0

        t_first_controls_usable = t_first_rest_state + t_first_metadata + t_first_ws_snapshot

        # 3. Same-session repeat open (11353)
        t0 = time.perf_counter()
        r_state2 = client.get("/api/v1/state?session_key=11353&mode=replay")
        t_repeat_rest_state = time.perf_counter() - t0

        t0 = time.perf_counter()
        with client.websocket_connect("/api/v1/stream?session_key=11353&mode=replay") as ws:
            ws_snap = ws.receive_json()
            t_repeat_ws = time.perf_counter() - t0

        t_repeat_controls_usable = t_repeat_rest_state + t_repeat_ws

        # 4. A -> B -> A selection:
        t0 = time.perf_counter()
        client.get("/api/v1/state?session_key=11349&mode=replay")
        with client.websocket_connect("/api/v1/stream?session_key=11349&mode=replay") as ws:
            ws.receive_json()
        t_open_b = time.perf_counter() - t0

        # Now select 11353 (A again)
        t0 = time.perf_counter()
        r_state_a2 = client.get("/api/v1/state?session_key=11353&mode=replay")
        t_a_again_rest = time.perf_counter() - t0

        t0 = time.perf_counter()
        with client.websocket_connect("/api/v1/stream?session_key=11353&mode=replay") as ws:
            ws.receive_json()
            t_a_again_ws = time.perf_counter() - t0

        t_a_again_controls_usable = t_a_again_rest + t_a_again_ws

        # 5. Restart followed by open:
        t0 = time.perf_counter()
        app_restarted = create_app(tmp_path, public_live=False)
        client_restarted = TestClient(app_restarted)
        t_restart = time.perf_counter() - t0

        t0 = time.perf_counter()
        client_restarted.get("/api/v1/state?session_key=11353&mode=replay")
        with client_restarted.websocket_connect("/api/v1/stream?session_key=11353&mode=replay") as ws:
            ws.receive_json()
        t_restart_open = time.perf_counter() - t0

        # 6. Post-download open simulation
        t0 = time.perf_counter()
        lib_refresh = ReplayLibrary(tmp_path)
        t_post_download_refresh = time.perf_counter() - t0

        # 7. Two simultaneous viewers (both seeking in 11353)
        with client.websocket_connect("/api/v1/stream?session_key=11353&mode=replay") as ws1:
            snap1 = ws1.receive_json()
            with client.websocket_connect("/api/v1/stream?session_key=11353&mode=replay") as ws2:
                snap2 = ws2.receive_json()
                t0 = time.perf_counter()
                ws1.send_json({"type": "seek", "seq": 20000})
                snap1_seek = ws1.receive_json()
                t_viewer1_seek = time.perf_counter() - t0

                t0 = time.perf_counter()
                ws2.send_json({"type": "seek", "seq": 80000})
                snap2_seek = ws2.receive_json()
                t_viewer2_seek = time.perf_counter() - t0

        # 8. Live client with delay simulation:
        raw_11353 = json.loads((tmp_path / "f1-static-11353.json").read_text(encoding="utf-8"))
        events_11353 = [NormalizedEvent.from_mapping(e) for e in raw_11353]
        ctrl_live = ReplayController(events_11353)
        t0 = time.perf_counter()
        ctrl_live.seek_delay(45.0)
        t_live_delay_45s = time.perf_counter() - t0

        t0 = time.perf_counter()
        ctrl_live.seek_delay(137.0)
        t_live_delay_137s = time.perf_counter() - t0

        results = {
            "cold_startup_s": round(t_cold_startup, 3),
            "first_open": {
                "rest_state_s": round(t_first_rest_state, 3),
                "metadata_caps_s": round(t_first_metadata, 3),
                "ws_snapshot_s": round(t_first_ws_snapshot, 3),
                "controls_usable_s": round(t_first_controls_usable, 3),
            },
            "repeat_open": {
                "rest_state_s": round(t_repeat_rest_state, 3),
                "ws_snapshot_s": round(t_repeat_ws, 3),
                "controls_usable_s": round(t_repeat_controls_usable, 3),
            },
            "a_b_a_selection": {
                "b_open_s": round(t_open_b, 3),
                "a_again_rest_s": round(t_a_again_rest, 3),
                "a_again_ws_s": round(t_a_again_ws, 3),
                "a_again_controls_usable_s": round(t_a_again_controls_usable, 3),
            },
            "restart_followed_by_open": {
                "restart_s": round(t_restart, 3),
                "open_after_restart_s": round(t_restart_open, 3),
                "total_s": round(t_restart + t_restart_open, 3),
            },
            "post_download": {
                "library_rescan_s": round(t_post_download_refresh, 3),
            },
            "simultaneous_viewers": {
                "viewer1_seek_20k_s": round(t_viewer1_seek, 3),
                "viewer2_seek_80k_s": round(t_viewer2_seek, 3),
            },
            "live_delay_simulation": {
                "delay_45s_seek_s": round(t_live_delay_45s, 3),
                "delay_137s_seek_s": round(t_live_delay_137s, 3),
            },
        }

    return results

def main():
    print("============================================================")
    print("SLIPSTREAM REPLAY READINESS PERFORMANCE BASELINE BENCHMARK")
    print("============================================================")

    session_benchmarks = []
    for cfg in SESSIONS_TO_BENCHMARK:
        print(f"\nBenchmarking session: {cfg['name']} ({cfg['path'].name})...")
        res = benchmark_single_session(cfg)
        session_benchmarks.append(res)
        print(f"  File size: {res.get('file_size_mb')} MB, Events: {res.get('event_count')}")
        print(f"  Parse: {res.get('parse_time_s')}s, Norm: {res.get('normalization_time_s')}s")
        print(f"  Reduction (final state): {res.get('reduction_time_s')}s")
        print(f"  Evidence build: {res.get('evidence_build_time_s')}s")
        print(f"  Analytics: {res.get('analytics_time_s')}s")
        print(f"  Seek 50%: {res.get('seek_50_s')}s, Seek 95%: {res.get('seek_95_s')}s")
        print(f"  Total compute: {res.get('total_compute_s')}s")
        print(f"  RSS Before: {res.get('rss_before_mb')} MB, After: {res.get('rss_after_mb')} MB (Delta: +{res.get('rss_delta_mb')} MB)")

    scenarios = benchmark_end_to_end_scenarios()

    combined_output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sessions": session_benchmarks,
        "scenarios": scenarios,
    }

    out_file = pathlib.Path("docs/baseline-benchmark-results.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(combined_output, indent=2), encoding="utf-8")
    print(f"\nAggregated baseline benchmark results written to: {out_file}")

if __name__ == "__main__":
    main()
