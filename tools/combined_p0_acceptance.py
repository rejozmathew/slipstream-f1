"""Isolated acceptance harness. All transport rows in this harness are SYNTHETIC.

Production adapter, collector, persistence, API, reducer and viewer paths are used.
Never point --data at production storage. Setup requires a new destination.
Run setup, then serve on a private port, then probe. See the repair report.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path


def stamp(value):
    return value.isoformat().replace("+00:00", "Z")


def setup(args):
    args.data.mkdir(parents=True, exist_ok=False)
    for path in (args.repo / "recordings").glob("*.json"):
        shutil.copy2(path, args.data / path.name)
    fixture = (
        args.repo / ".codex-tmp/combined-p0-20260905-01/recordings/live-11357.json"
    )
    shutil.copy2(fixture, args.data / fixture.name)
    practice = (
        args.repo / ".codex-tmp/combined-p0-20260905-01/recordings/live-11356.json"
    )
    shutil.copy2(practice, args.data / practice.name)
    catalog_path = args.data / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    # Keep normal background cache refresh enabled; this isolated inventory is fresh.
    catalog["updated_at"] = stamp(datetime.now(UTC))
    catalog_path.write_text(json.dumps(catalog))
    operational = args.data / ".slipstream/acceptance-operational-fixture"
    operational.mkdir(parents=True)
    for index in range(1000):
        (operational / f"diagnostic-{index}.json").write_text('{"operational":true}')
    files = list(args.data.glob("*.json"))
    print(
        json.dumps(
            {
                "recordings": len(files) - 1,
                "bytes": sum(p.stat().st_size for p in files),
                "operationalJsonFiles": 1000,
                "originalQualifyingSha256": hashlib.sha256(
                    fixture.read_bytes()
                ).hexdigest(),
            }
        )
    )


def serve(args):
    import uvicorn

    from slipstream.api import create_app
    from slipstream.catalog import recent_seasons, sync_catalog
    from slipstream.live import PublicLiveSession, decode_signalr_text
    from slipstream.replay import load_events, replay

    origin = time.monotonic()
    base = datetime(2026, 9, 5, 14, 28, 54, tzinfo=UTC)
    state = {
        "active": False,
        "complete": False,
        "offset": 0,
        "rows": 0,
        "bursts": 0,
        "connections": 0,
    }
    numbers = list(replay(load_events(args.data / "live-11357.json")).drivers)

    def now():
        return base + timedelta(seconds=time.monotonic() - origin + state["offset"])

    def row(topic, payload, at=None):
        state["rows"] += 1
        message = {
            "type": 1,
            "target": "feed",
            "arguments": [topic, payload, at or stamp(now())],
        }
        decoded, _ = decode_signalr_text(
            json.dumps(message) + "\x1e", received_at=stamp(now())
        )
        return decoded[0]

    async def rows():
        state["connections"] += 1
        yield row(
            "SessionInfo",
            {
                "Key": 11357,
                "Name": "Qualifying",
                "Type": "Qualifying",
                "StartDate": "2026-09-05T16:00:00",
                "EndDate": "2026-09-05T17:00:00",
                "GmtOffset": "02:00:00",
            },
        )
        yield row(
            "SessionData",
            {
                "StatusSeries": {
                    "0": {
                        "Utc": "2026-09-05T14:18:00.071Z",
                        "SessionStatus": "Finished",
                    },
                    "1": {"Utc": "2026-09-05T14:25:00Z", "SessionStatus": "Started"},
                },
                "Series": {
                    "0": {"Utc": "2026-09-05T14:18:00Z", "QualifyingPart": 1},
                    "1": {"Utc": "2026-09-05T14:25:00Z", "QualifyingPart": 2},
                },
            },
        )
        yield row("SessionStatus", {"Status": "Started"})
        while not state["active"]:
            await asyncio.sleep(0.05)
        while not state["complete"]:
            await asyncio.sleep(0.1)
            state["bursts"] += 1
            yield row(
                "TimingData",
                {
                    "Lines": {
                        number: {
                            "NumberOfLaps": 13 + state["bursts"],
                            "BestLapTime": {"Value": "1:22.500"},
                        }
                        for number in numbers
                    }
                },
            )
            if state["connections"] == 1 and state["bursts"] == 12:
                raise OSError("SYNTHETIC Q2 transport disconnect")
        yield row(
            "SessionData", {"Series": {"2": {"Utc": stamp(now()), "QualifyingPart": 3}}}
        )
        yield row("SessionStatus", {"Status": "Finished"})
        yield row(
            "TimingData",
            {
                "Lines": {
                    number: {"NumberOfLaps": 999, "BestLapTime": {"Value": "1:21.999"}}
                    for number in numbers
                }
            },
        )
        yield row("SessionStatus", {"Status": "Finalised"})
        while True:
            await asyncio.sleep(5)
            yield row("Heartbeat", {})

    live = PublicLiveSession(
        row_source=rows, now=now, maximum_backoff=0.05, finalization_drain=0.05
    )

    def refresh_catalog():
        sync_catalog(
            args.data / "catalog.json", recent_seasons(3), max_age=timedelta(hours=6)
        )

    def synthetic_download(key):
        state["downloadCalls"] = state.get("downloadCalls", 0) + 1
        fail = state.get("downloadFail", False)
        time.sleep(5)
        if fail:
            raise OSError("SYNTHETIC historical download failure")
        return [
            {
                "kind": "session",
                "occurred_at": "2026-09-04T14:00:00Z",
                "source": "synthetic-acceptance",
                "payload": {
                    "key": str(key),
                    "name": "Practice 2",
                    "session_type": "Practice",
                    "session_kind": "practice_2",
                    "layout_family": "practice",
                    "started_at": "2026-09-04T14:00:00Z",
                    "ended_at": "2026-09-04T15:00:00Z",
                    "status": "RUNNING",
                },
            },
            {
                "kind": "timing",
                "occurred_at": "2026-09-04T14:01:00Z",
                "source": "synthetic-acceptance",
                "payload": {"number": "44", "lap": 1, "best_lap": "1:22.000"},
            },
            {
                "kind": "session",
                "occurred_at": "2026-09-04T15:00:00Z",
                "source": "synthetic-acceptance",
                "payload": {"status": "FINISHED", "session_complete": True},
            },
        ]

    options = {"now": now, "live_session": live, "web_dir": args.web}
    if args.synthetic_downloads:
        options["capture_session"] = synthetic_download
    if not args.baseline:
        options["refresh_catalog"] = refresh_catalog
    app = create_app(args.data, **options)

    @app.get("/__fixture/status")
    async def portable_status():
        try:
            import psutil

            rss = psutil.Process().memory_info().rss
        except ImportError:
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes

                class Counters(ctypes.Structure):
                    _fields_ = [
                        ("cb", wintypes.DWORD),
                        ("PageFaultCount", wintypes.DWORD),
                    ] + [
                        (name, ctypes.c_size_t)
                        for name in (
                            "PeakWorkingSetSize",
                            "WorkingSetSize",
                            "QuotaPeakPagedPoolUsage",
                            "QuotaPagedPoolUsage",
                            "QuotaPeakNonPagedPoolUsage",
                            "QuotaNonPagedPoolUsage",
                            "PagefileUsage",
                            "PeakPagefileUsage",
                        )
                    ]

                counters = Counters()
                counters.cb = ctypes.sizeof(counters)
                info = ctypes.windll.psapi.GetProcessMemoryInfo
                info.argtypes = [
                    wintypes.HANDLE,
                    ctypes.POINTER(Counters),
                    wintypes.DWORD,
                ]
                assert info(wintypes.HANDLE(-1), ctypes.byref(counters), counters.cb)
                rss = counters.WorkingSetSize
            else:
                rss = int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf(
                    "SC_PAGE_SIZE"
                )
        return {
            **state,
            "clock": stamp(now()),
            "rssBytes": rss,
            "python": platform.python_version(),
            "platform": platform.platform(),
        }

    @app.post("/__fixture/action")
    async def action(payload: dict):
        state["active"] = bool(payload.get("start", state["active"]))
        state["downloadFail"] = bool(
            payload.get("downloadFail", state.get("downloadFail", False))
        )
        state["complete"] = bool(payload.get("complete", state["complete"]))
        state["offset"] += float(payload.get("advanceSeconds", 0))
        return dict(state)

    # The SPA catch-all must come after the harness-only routes.
    catchalls = [
        route
        for route in app.router.routes
        if getattr(route, "path", "") == "/{path:path}"
    ]
    for route in catchalls:
        app.router.routes.remove(route)
        app.router.routes.append(route)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


async def probe(args):
    import aiohttp

    metrics = {
        "fixture": "SYNTHETIC continuous public-topic rows through production processing",
        "url": args.url,
    }
    samples = []
    running = True
    async with aiohttp.ClientSession() as client:

        async def get(path):
            async with client.get(args.url + path) as response:
                response.raise_for_status()
                return await response.json()

        async def snapshot(ws):
            packet = await asyncio.wait_for(ws.receive_json(), 30)
            assert packet.get("type") == "state.snapshot", packet
            return packet

        async def poll():
            while running:
                start = time.perf_counter()
                payload = await get("/api/v1/catalog")
                assert payload["sessions"]
                samples.append(time.perf_counter() - start)
                await asyncio.sleep(0.025)

        metrics["initial"] = await get("/__fixture/status")
        async with client.post(
            args.url + "/__fixture/action", json={"start": True}
        ) as response:
            response.raise_for_status()
        polling = asyncio.create_task(poll())
        live_ws = await client.ws_connect(
            args.url + "/api/v1/stream?session_key=11357&mode=live"
        )
        first_live = await snapshot(live_ws)
        assert len(first_live["data"]["drivers"]) == 22
        assert first_live["mode"] == "live"
        live_cursor = first_live["seq"]
        openings, seeks, refreshes = [], [], []
        for iteration in range(4):
            start = time.perf_counter()
            async with client.ws_connect(
                args.url + "/api/v1/stream?session_key=11353&mode=replay"
            ) as ws:
                opening = await snapshot(ws)
                openings.append(time.perf_counter() - start)
                assert (
                    opening["playbackReady"]
                    and opening["metadata"]
                    and opening["capabilities"]
                )
                assert opening["seq"] < opening["metadata"]["eventCount"]
                assert opening["data"]["drivers"], (
                    "A useful race opening must include drivers"
                )
                metrics.setdefault(
                    "openingDriverCount", len(opening["data"]["drivers"])
                )
                for fraction in (0.95, 0.2, 0.7, 0.05):
                    target = int(opening["metadata"]["eventCount"] * fraction)
                    start = time.perf_counter()
                    await ws.send_json({"type": "seek", "seq": target})
                    result = await snapshot(ws)
                    seeks.append(time.perf_counter() - start)
                    assert result["seq"] == target
                    assert result["data"]["drivers"]
                    if result.get("analytics"):
                        assert result["analytics"]["sequence"] == target
                # A separate viewer at its own cursor must not move this controller.
                start = time.perf_counter()
                async with client.ws_connect(
                    args.url + "/api/v1/stream?session_key=11353&mode=replay"
                ) as refresh:
                    refreshed = await snapshot(refresh)
                    assert refreshed["seq"] == opening["seq"]
                refreshes.append(time.perf_counter() - start)
                await ws.send_json({"type": "snapshot"})
                assert (await snapshot(ws))["seq"] == target
                if iteration == 0:
                    async with client.ws_connect(
                        args.url + "/api/v1/stream?session_key=11326&mode=replay"
                    ) as other:
                        other_open = await snapshot(other)
                        assert other_open["metadata"]["sessionKey"] == "11326"
                        # This archived file has no driver identities at its
                        # official start; the source-cursor reducer also yields
                        # zero. Verify real timing after seeking, never invent it.
                        metrics["secondaryOpeningDriverCount"] = len(
                            other_open["data"]["drivers"]
                        )
                        await other.send_json(
                            {
                                "type": "seek",
                                "seq": int(other_open["metadata"]["eventCount"] * 0.9),
                            }
                        )
                        other_state = await snapshot(other)
                        assert other_state["data"]["session"]["key"] == "11326"
                        assert other_state["data"]["drivers"]
                        await ws.send_json({"type": "snapshot"})
                        assert (await snapshot(ws))["seq"] == target
                        metrics["twoReplayMemory"] = await get("/__fixture/status")
        # Allow the deliberate reconnect even when warm rounds finish very quickly.
        await asyncio.sleep(2)
        await live_ws.send_json({"type": "snapshot"})
        live = await snapshot(live_ws)
        while live["seq"] <= live_cursor:
            live = await snapshot(live_ws)
        assert live["data"]["session"]["qualifying_phase"] == "Q2"
        assert live["live"]["phase"] not in {"FINALIZING", "COMPLETE", "REPLAY_READY"}
        metrics["beforeCompletion"] = await get("/api/v1/diagnostics")
        assert metrics["beforeCompletion"]["live"]["connections"] >= 2
        delayed = await client.ws_connect(
            args.url + "/api/v1/stream?session_key=11357&mode=live&delay_seconds=137"
        )
        delayed_first = await snapshot(delayed)
        assert delayed_first["seq"] < live["seq"]
        async with client.post(
            args.url + "/__fixture/action", json={"complete": True}
        ) as response:
            response.raise_for_status()
        await asyncio.sleep(0.4)
        await delayed.send_json({"type": "snapshot"})
        delayed_before = await snapshot(delayed)
        assert delayed_before.get("handoff") is None
        assert all(
            driver.get("lap") != 999
            for driver in delayed_before["data"]["drivers"].values()
        )
        async with client.post(
            args.url + "/__fixture/action", json={"advanceSeconds": 140}
        ) as response:
            response.raise_for_status()
        await delayed.send_json({"type": "snapshot"})
        for _ in range(20):
            final = await snapshot(delayed)
            if final.get("handoff"):
                break
        assert final["handoff"] == "REPLAY_READY"
        assert all(driver["lap"] == 999 for driver in final["data"]["drivers"].values())
        assert final["analytics"]["sequence"] == final["seq"]
        await delayed.close()
        await live_ws.close()
        running = False
        await polling
        metrics["final"] = await get("/__fixture/status")
        metrics["diagnostics"] = await get("/api/v1/diagnostics")
        timing = metrics["diagnostics"]["live"]["topics"]["TimingData"]
        assert timing["normalized"] == timing["persisted"] == 22 * timing["received"]
        assert timing["received"] == metrics["final"]["bursts"] + 1

    def percentile(values, fraction):
        return sorted(values)[min(len(values) - 1, int(len(values) * fraction))]

    metrics.update(
        coldOpenSeconds=openings[0],
        warmOpenSeconds=openings[1:],
        seekSeconds=seeks,
        refreshSeconds=refreshes,
        httpSamples=len(samples),
        httpP95Seconds=percentile(samples, 0.95),
        httpP99Seconds=percentile(samples, 0.99),
        httpMaxSeconds=max(samples),
    )
    args.output.write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))


async def measure(args):
    import aiohttp

    log_path = args.output.with_suffix(".server.log")
    command = [
        sys.executable,
        __file__,
        "serve",
        "--data",
        str(args.data),
        "--web",
        str(args.web),
        "--port",
        str(args.port),
    ]
    start = time.perf_counter()
    with log_path.open("w") as log:
        child = await asyncio.to_thread(
            subprocess.Popen,
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=1)
            ) as client:
                for _ in range(600):
                    if child.poll() is not None:
                        raise RuntimeError(
                            f"server exited {child.returncode}; see {log_path}"
                        )
                    try:
                        async with client.get(
                            args.url + "/__fixture/status"
                        ) as response:
                            if response.status == 200:
                                break
                    except (aiohttp.ClientError, TimeoutError):
                        pass
                    await asyncio.sleep(0.05)
                else:
                    raise TimeoutError("server did not listen in 30 seconds")
            listening = time.perf_counter() - start
            await probe(args)
            result = json.loads(args.output.read_text())
            result["startupSeconds"] = listening
            args.output.write_text(json.dumps(result, indent=2))
            print(f"STARTUP_SECONDS={listening:.6f}")
        finally:
            child.terminate()
            await asyncio.to_thread(child.wait, 15)


async def baseline_probe(args):
    """Measure the old opening contract without pretending it passes new gates."""
    import aiohttp

    samples, openings, seeks, refreshes = [], [], [], []
    running = True
    result = {
        "contract": "d72ddd6 REST-final then metadata/capabilities and WS",
        "url": args.url,
    }
    async with aiohttp.ClientSession() as client:

        async def get(path):
            async with client.get(args.url + path) as response:
                response.raise_for_status()
                return await response.json()

        async def poll():
            while running:
                start = time.perf_counter()
                await get("/api/v1/catalog")
                samples.append(time.perf_counter() - start)
                await asyncio.sleep(0.025)

        result["initial"] = await get("/__fixture/status")
        async with client.post(
            args.url + "/__fixture/action", json={"start": True}
        ) as response:
            response.raise_for_status()
        polling = asyncio.create_task(poll())
        for _ in range(3):
            start = time.perf_counter()
            state = await get("/api/v1/state?session_key=11353&mode=replay")
            metadata, _ = await asyncio.gather(
                get("/api/v1/replay?session_key=11353"),
                get("/api/v1/capabilities?session_key=11353"),
            )
            async with client.ws_connect(
                args.url + "/api/v1/stream?session_key=11353&mode=replay"
            ) as ws:
                frame = await asyncio.wait_for(ws.receive_json(), 60)
                openings.append(time.perf_counter() - start)
                result["restOpeningSequence"] = state["seq"]
                result["wsOpeningSequence"] = frame["seq"]
                assert metadata["eventCount"] > 100000
                for fraction in (0.95, 0.2):
                    target = int(metadata["eventCount"] * fraction)
                    start = time.perf_counter()
                    await ws.send_json({"type": "seek", "seq": target})
                    frame = await asyncio.wait_for(ws.receive_json(), 60)
                    seeks.append(time.perf_counter() - start)
                    assert frame["seq"] == target
                start = time.perf_counter()
                async with client.ws_connect(
                    args.url + "/api/v1/stream?session_key=11353&mode=replay"
                ) as other:
                    await asyncio.wait_for(other.receive_json(), 60)
                refreshes.append(time.perf_counter() - start)
        running = False
        await polling
        result["final"] = await get("/__fixture/status")
    result.update(
        coldOpenSeconds=openings[0],
        warmOpenSeconds=openings[1:],
        seekSeconds=seeks,
        refreshSeconds=refreshes,
        httpSamples=len(samples),
        httpP95Seconds=sorted(samples)[int(len(samples) * 0.95)],
        httpP99Seconds=sorted(samples)[min(len(samples) - 1, int(len(samples) * 0.99))],
        httpMaxSeconds=max(samples),
    )
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=["setup", "serve", "probe", "measure", "baseline-probe"]
    )
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--synthetic-downloads", action="store_true")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--data", type=Path)
    parser.add_argument("--web", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18344)
    parser.add_argument("--url", default="http://127.0.0.1:18344")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode == "setup":
        setup(args)
    elif args.mode == "serve":
        serve(args)
    elif args.mode == "measure":
        asyncio.run(measure(args))
    elif args.mode == "baseline-probe":
        asyncio.run(baseline_probe(args))
    else:
        asyncio.run(probe(args))


if __name__ == "__main__":
    main()
