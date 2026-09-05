"""Event-loop responsiveness benchmark for Section C.

Measures whether parsing, reduction, evidence construction, or analytics
blocks the async server/event loop.
Compares:
1. Current main-thread synchronous execution (as implemented today in api.py)
2. Threadpool execution (asyncio.to_thread)
3. Multiple concurrent workers/threads

Outputs exact latency measurements for:
- GET /api/v1/catalog
- Existing viewer WebSocket snapshot
- Job / status polling
"""

from __future__ import annotations

import asyncio
import gc
import json
import os
import pathlib
import sys
import tempfile
import time
from typing import Any

import aiohttp
import uvicorn
from fastapi import FastAPI

from slipstream.api import create_app
from slipstream.events import NormalizedEvent
from slipstream.evidence import SessionEvidence
from slipstream.library import ReplayLibrary, ReplayResource
from slipstream.playback import ReplayController
from slipstream.replay import replay

RECORDINGS_DIR = pathlib.Path("recordings")
PORT = 8991
HOST = "127.0.0.1"

async def run_event_loop_benchmarks():
    print("============================================================")
    print("SLIPSTREAM EVENT-LOOP RESPONSIVENESS BENCHMARK (SECTION C)")
    print("============================================================")

    # Prepare minimal test directory with catalog and race 11353
    import shutil
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = pathlib.Path(tmp_dir)
        shutil.copy(RECORDINGS_DIR / "catalog.json", tmp_path / "catalog.json")
        shutil.copy(RECORDINGS_DIR / "f1-static-11353.json", tmp_path / "f1-static-11353.json")
        shutil.copy(RECORDINGS_DIR / "f1-static-11349.json", tmp_path / "f1-static-11349.json")

        app = create_app(tmp_path, public_live=False)

        # Start uvicorn server in an asyncio background task
        config = uvicorn.Config(app=app, host=HOST, port=PORT, log_level="error")
        server = uvicorn.Server(config=config)
        server_task = asyncio.create_task(server.serve())

        # Wait for server to start
        await asyncio.sleep(1.0)
        base_url = f"http://{HOST}:{PORT}"
        ws_url = f"ws://{HOST}:{PORT}"

        results: dict[str, Any] = {}

        try:
            async with aiohttp.ClientSession() as session:
                # 1. Baseline measurements when idle
                print("\n1. Measuring idle baseline latencies...")
                catalog_latencies = []
                for _ in range(5):
                    t0 = time.perf_counter()
                    async with session.get(f"{base_url}/api/v1/catalog") as resp:
                        assert resp.status == 200
                        await resp.json()
                    catalog_latencies.append((time.perf_counter() - t0) * 1000)

                idle_catalog_avg_ms = sum(catalog_latencies) / len(catalog_latencies)
                idle_catalog_max_ms = max(catalog_latencies)
                print(f"  Idle GET /api/v1/catalog: avg={idle_catalog_avg_ms:.2f}ms, max={idle_catalog_max_ms:.2f}ms")

                # Connect an existing WebSocket viewer on 11349 (warm cache)
                # First warm up 11349
                async with session.get(f"{base_url}/api/v1/state?session_key=11349") as resp:
                    await resp.json()

                ws_latencies = []
                async with session.ws_connect(f"{ws_url}/api/v1/stream?session_key=11349&mode=replay") as ws:
                    init_snap = await ws.receive_json()
                    for _ in range(5):
                        t0 = time.perf_counter()
                        await ws.send_json({"type": "snapshot"})
                        reply = await ws.receive_json()
                        ws_latencies.append((time.perf_counter() - t0) * 1000)

                idle_ws_avg_ms = sum(ws_latencies) / len(ws_latencies)
                idle_ws_max_ms = max(ws_latencies)
                print(f"  Idle WS snapshot round-trip: avg={idle_ws_avg_ms:.2f}ms, max={idle_ws_max_ms:.2f}ms")

                results["idle"] = {
                    "catalog_avg_ms": round(idle_catalog_avg_ms, 2),
                    "catalog_max_ms": round(idle_catalog_max_ms, 2),
                    "ws_snapshot_avg_ms": round(idle_ws_avg_ms, 2),
                    "ws_snapshot_max_ms": round(idle_ws_max_ms, 2),
                }

                # 2. Measure during synchronous load of large replay (Current Implementation)
                # Client A calls GET /api/v1/state?session_key=11353 (evicts cache and does 8s synchronous CPU)
                # While that is in flight, Client B polls catalog and Client C sends WS snapshot
                print("\n2. Measuring event-loop blocking under current synchronous implementation...")

                async def client_a_open_heavy():
                    t0 = time.perf_counter()
                    async with session.get(f"{base_url}/api/v1/state?session_key=11353") as resp:
                        res = await resp.json()
                    return time.perf_counter() - t0

                async def client_b_probe_catalog():
                    # Sleep 100ms so Client A has started its heavy work
                    await asyncio.sleep(0.1)
                    probe_results = []
                    t0 = time.perf_counter()
                    async with session.get(f"{base_url}/api/v1/catalog") as resp:
                        await resp.json()
                    elapsed = (time.perf_counter() - t0) * 1000
                    return elapsed

                async def client_c_probe_ws():
                    await asyncio.sleep(0.2)
                    async with session.ws_connect(f"{ws_url}/api/v1/stream?session_key=11349&mode=replay") as ws:
                        # Even connecting WS while event loop is blocked will stall!
                        t0 = time.perf_counter()
                        init_msg = await ws.receive_json()
                        elapsed = (time.perf_counter() - t0) * 1000
                        return elapsed

                # Evict cache first by hitting 11349
                await session.get(f"{base_url}/api/v1/state?session_key=11349")

                # Launch concurrent tasks
                task_a = asyncio.create_task(client_a_open_heavy())
                task_b = asyncio.create_task(client_b_probe_catalog())
                task_c = asyncio.create_task(client_c_probe_ws())

                t_a, t_b, t_c = await asyncio.gather(task_a, task_b, task_c)
                print(f"  Heavy replay load duration: {t_a:.2f}s")
                print(f"  BLOCKED GET /api/v1/catalog latency: {t_b:.2f}ms ({t_b/1000:.2f}s!)")
                print(f"  BLOCKED WS connection/snapshot latency: {t_c:.2f}ms ({t_c/1000:.2f}s!)")

                results["synchronous_blocked"] = {
                    "heavy_load_duration_s": round(t_a, 3),
                    "catalog_blocked_latency_ms": round(t_b, 2),
                    "ws_blocked_latency_ms": round(t_c, 2),
                    "degradation_factor": round(t_b / idle_catalog_avg_ms, 1),
                }

                # 3. Threading experiment (asyncio.to_thread):
                # Measure what happens if heavy CPU reduction runs in asyncio.to_thread
                print("\n3. Measuring GIL impact with asyncio.to_thread...")
                raw_11353 = json.loads((tmp_path / "f1-static-11353.json").read_text(encoding="utf-8"))
                events_11353 = [NormalizedEvent.from_mapping(e) for e in raw_11353]

                def cpu_heavy_reduction():
                    return replay(list(events_11353))

                async def thread_worker():
                    t0 = time.perf_counter()
                    res = await asyncio.to_thread(cpu_heavy_reduction)
                    return time.perf_counter() - t0

                async def probe_catalog_during_thread():
                    await asyncio.sleep(0.1)
                    probe_times = []
                    for _ in range(5):
                        t0 = time.perf_counter()
                        async with session.get(f"{base_url}/api/v1/catalog") as resp:
                            await resp.json()
                        probe_times.append((time.perf_counter() - t0) * 1000)
                        await asyncio.sleep(0.05)
                    return probe_times

                task_th = asyncio.create_task(thread_worker())
                task_probe = asyncio.create_task(probe_catalog_during_thread())
                th_dur, probe_times = await asyncio.gather(task_th, task_probe)

                th_avg_ms = sum(probe_times) / len(probe_times)
                th_max_ms = max(probe_times)
                print(f"  Thread reduction duration: {th_dur:.2f}s")
                print(f"  GET /catalog latency during thread reduction: avg={th_avg_ms:.2f}ms, max={th_max_ms:.2f}ms")

                results["threading_to_thread"] = {
                    "reduction_duration_s": round(th_dur, 3),
                    "catalog_during_thread_avg_ms": round(th_avg_ms, 2),
                    "catalog_during_thread_max_ms": round(th_max_ms, 2),
                    "event_loop_unblocked": bool(th_max_ms < 100),
                }

                # 4. Multi-thread GIL contention test (2 concurrent reductions in threads)
                print("\n4. Measuring multi-thread GIL contention (2 concurrent thread reductions)...")
                t0 = time.perf_counter()
                task1 = asyncio.to_thread(cpu_heavy_reduction)
                task2 = asyncio.to_thread(cpu_heavy_reduction)
                task_probe2 = asyncio.create_task(probe_catalog_during_thread())
                _, _, probe2_times = await asyncio.gather(task1, task2, task_probe2)
                t_multi = time.perf_counter() - t0

                m_avg_ms = sum(probe2_times) / len(probe2_times)
                m_max_ms = max(probe2_times)
                print(f"  2x Thread reduction total duration: {t_multi:.2f}s (vs single thread {th_dur:.2f}s)")
                print(f"  GET /catalog latency during 2x thread reduction: avg={m_avg_ms:.2f}ms, max={m_max_ms:.2f}ms")

                results["multi_thread_contention"] = {
                    "dual_thread_duration_s": round(t_multi, 3),
                    "single_thread_duration_s": round(th_dur, 3),
                    "gil_slowdown_ratio": round(t_multi / th_dur, 2),
                    "catalog_avg_ms": round(m_avg_ms, 2),
                    "catalog_max_ms": round(m_max_ms, 2),
                }

        finally:
            server.should_exit = True
            await server_task

        out_file = pathlib.Path("docs/event-loop-benchmark-results.json")
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nEvent-loop benchmark results saved to: {out_file}")

if __name__ == "__main__":
    asyncio.run(run_event_loop_benchmarks())
