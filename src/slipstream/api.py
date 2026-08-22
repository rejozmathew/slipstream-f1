"""Versioned HTTP/WebSocket transport over a local replay library."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .adapters.openf1 import OpenF1Client, write_recording
from .analytics import AnalyticsService
from .events import parse_timestamp
from .library import ReplayLibrary, ReplayResource
from .live import PublicLiveSession
from .pirelli.coordinator import PirelliRuntimeCoordinator
from .pirelli.contracts import SessionScope
from .pirelli.ingest import PirelliIngestionService
from .pirelli.store import PirelliAvailability, PirelliEvidenceStore
from .playback import ReplayController
from .serialization import state_envelope
from .weekend import (
    ContextAvailability,
    WeekendContextCoordinator,
    WeekendContextStore,
)


def create_app(
    recording_path: Path,
    *,
    now: Callable[[], datetime] | None = None,
    capture_session: Callable[[int], dict[str, Any]] | None = None,
    prepare_weekend_context: Callable[..., dict[str, Any]] | None = None,
    web_dir: Path | None = None,
    public_live: bool | None = None,
    live_session: PublicLiveSession | None = None,
) -> FastAPI:
    clock = now or (lambda: datetime.now(UTC))
    live_enabled = (
        public_live
        if public_live is not None
        else os.getenv("SLIPSTREAM_PUBLIC_LIVE", "1").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    library_ref = [ReplayLibrary(recording_path, now=clock)]
    live = live_session or PublicLiveSession(now=clock)
    live_monitor_task: list[asyncio.Task[None] | None] = [None]
    downloader = capture_session or OpenF1Client().capture_session
    analytics_service = AnalyticsService()
    download_lock = asyncio.Lock()
    downloads_enabled = recording_path.is_dir() and os.access(recording_path, os.W_OK)
    pirelli_store = PirelliEvidenceStore(recording_path) if downloads_enabled else None
    pirelli_refresh_enabled = os.getenv("SLIPSTREAM_PIRELLI_REFRESH", "1").strip().lower() not in {"0", "false", "no", "off"}
    pirelli_coordinator = (
        PirelliRuntimeCoordinator(PirelliIngestionService(pirelli_store.archive))
        if pirelli_store is not None and pirelli_refresh_enabled
        else None
    )
    pirelli_refresh_task: list[asyncio.Task[None] | None] = [None]
    context_coordinator = (
        WeekendContextCoordinator(
            WeekendContextStore(recording_path),
            prepare_weekend_context or OpenF1Client().capture_weekend_context,
        )
        if downloads_enabled
        else None
    )
    app = FastAPI(title="Slipstream F1", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    def resource(session_key: str | None) -> ReplayResource:
        try:
            return library_ref[0].get(session_key)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    def meeting_context(
        selected: ReplayResource, *, prepare: bool
    ) -> ContextAvailability:
        if context_coordinator is None:
            return ContextAvailability(
                "unavailable", error="operational context storage is not writable"
            )
        if prepare:
            inventory = selected.descriptor.meeting_inventory(
                library_ref[0].descriptors
            )
            return context_coordinator.ensure(selected.descriptor, inventory)
        return context_coordinator.current(selected.descriptor)

    def pirelli_context(selected: ReplayResource) -> PirelliAvailability:
        if pirelli_store is None:
            return PirelliAvailability("ABSENT", error="operational Pirelli storage is not writable")
        scope = (
            SessionScope.SPRINT
            if selected.descriptor.session_kind == "sprint"
            else SessionScope.RACE
            if selected.descriptor.session_kind == "race"
            else None
        )
        if scope is None:
            return PirelliAvailability("ABSENT", error="Pirelli strategy applies only to Race or Sprint")
        return pirelli_store.load(
            meeting_key=selected.descriptor.meeting_key,
            target_session_key=selected.descriptor.key,
            evidence_cutoff=selected.descriptor.date_start,
            session_scope=scope,
        )

    def current_live_descriptor():
        if not live_enabled:
            return None
        current = [
            descriptor
            for descriptor in library_ref[0].descriptors.values()
            if descriptor.is_live(clock())
        ]
        return max(current, key=lambda item: item.date_start) if current else None

    def live_payload(session_key: str | None) -> dict[str, Any]:
        view = live.view(session_key)
        return {
            "status": view.status,
            "connected": view.connected,
            "stale": view.stale,
            "sequence": view.sequence,
            "lastReceivedAt": view.last_received_at,
            "error": view.error,
        }

    def catalog_payload() -> dict[str, Any]:
        payload = library_ref[0].catalog()
        live_descriptor = current_live_descriptor()
        for session in payload["sessions"]:
            scheduled_live = bool(session["isLive"])
            source = live.view(session["sessionKey"])
            session.update(
                {
                    "liveAvailable": bool(live_enabled and scheduled_live),
                    "liveConnected": scheduled_live and source.connected,
                    "liveStale": scheduled_live and source.stale,
                    "liveStatus": source.status if scheduled_live else "OFFLINE",
                }
            )
        return {
            **payload,
            "downloadsEnabled": downloads_enabled,
            "liveSessionKey": live_descriptor.key if live_descriptor else None,
            "liveStatus": (
                live.view(live_descriptor.key).status
                if live_descriptor is not None
                else "OFFLINE"
            ),
        }

    async def reconcile_live_source() -> None:
        selected = current_live_descriptor()
        if selected is None:
            if live.target_session_key is not None:
                await live.stop()
            return
        await live.start(selected.key)

    async def monitor_live_source() -> None:
        while True:
            await reconcile_live_source()
            await asyncio.sleep(15)

    @app.on_event("startup")
    async def start_live_source() -> None:
        await reconcile_live_source()
        live_monitor_task[0] = asyncio.create_task(monitor_live_source())
        if pirelli_coordinator is not None:
            pirelli_refresh_task[0] = asyncio.create_task(
                pirelli_coordinator.run_forever(
                    lambda: dict(library_ref[0].descriptors),
                    lambda: library_ref[0].default_key,
                    library_ref[0].get,
                    clock,
                )
            )

    @app.on_event("shutdown")
    async def stop_live_source() -> None:
        pirelli_task = pirelli_refresh_task[0]
        pirelli_refresh_task[0] = None
        if pirelli_task is not None:
            pirelli_task.cancel()
            with suppress(asyncio.CancelledError):
                await pirelli_task
        task = live_monitor_task[0]
        live_monitor_task[0] = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await live.stop()

    @app.get("/api/v1/catalog")
    def get_catalog() -> dict[str, Any]:
        return catalog_payload()

    @app.post("/api/v1/download")
    async def download_session(session_key: str) -> dict[str, Any]:
        if not downloads_enabled:
            raise HTTPException(
                status_code=409,
                detail="Downloads require the server to use a recording directory",
            )
        descriptor = library_ref[0].descriptors.get(session_key)
        if descriptor is None:
            raise HTTPException(status_code=404, detail="Unknown catalog session")
        if parse_timestamp(descriptor.date_end) > clock():
            raise HTTPException(
                status_code=409,
                detail="This session is not yet available as a historical replay",
            )
        async with download_lock:
            current = library_ref[0].descriptors.get(session_key)
            if current is not None and not current.available:
                try:
                    recording = await asyncio.to_thread(downloader, int(session_key))
                    await asyncio.to_thread(
                        write_recording,
                        recording_path / f"openf1-{session_key}.json",
                        recording,
                    )
                    library_ref[0] = ReplayLibrary(recording_path, now=clock)
                except Exception as error:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Historical replay download failed: {error}",
                    ) from error
        return {
            "v": 1,
            "sessionKey": session_key,
            "status": "available",
            "catalog": catalog_payload(),
        }

    def live_state_envelope(selected: ReplayResource) -> dict[str, Any]:
        source = live.view(selected.descriptor.key)
        has_live_state = (
            source.target_session_key == selected.descriptor.key
            and source.sequence > 0
        )
        state = live.state if has_live_state else selected.final_state
        envelope = state_envelope(
            state,
            sequence=source.sequence if has_live_state else len(selected.events),
            session_time=state.updated_at,
        )
        envelope["mode"] = "live"
        envelope["live"] = live_payload(selected.descriptor.key)
        return envelope

    @app.get("/api/v1/state")
    def get_state(
        session_key: str | None = None, mode: str = "auto"
    ) -> dict[str, Any]:
        selected = resource(session_key)
        if mode not in {"auto", "live", "replay"}:
            raise HTTPException(status_code=422, detail="mode must be auto, live, or replay")
        wants_live = mode == "live" or (mode == "auto" and selected.is_live)
        if wants_live:
            if not selected.is_live:
                raise HTTPException(
                    status_code=409, detail="Selected session is not currently live"
                )
            return live_state_envelope(selected)
        envelope = state_envelope(
            selected.final_state,
            sequence=len(selected.events),
            session_time=selected.events[-1].occurred_at if selected.events else None,
        )
        envelope["mode"] = "replay"
        return envelope

    @app.get("/api/v1/capabilities")
    def get_capabilities(session_key: str | None = None) -> dict[str, Any]:
        selected = resource(session_key)
        source = live.view(selected.descriptor.key)
        live_available = bool(live_enabled and selected.is_live)
        capabilities = dict(selected.descriptor.capabilities)
        if live_available:
            capabilities.update(
                {
                    "live_timing": True,
                    "positions": False,
                    "intervals": True,
                    "location_xy": False,
                    "race_control": True,
                    "weather": True,
                    "authenticated": False,
                }
            )
        return {
            "v": 1,
            "source": (
                "f1-signalr-public" if live_available else selected.descriptor.source
            ),
            "capabilities": capabilities,
            "replayAvailable": selected.replay_available,
            "liveAvailable": live_available,
            "liveConnected": source.connected,
            "liveStale": source.stale,
            "liveStatus": source.status if live_available else "OFFLINE",
            "isLive": selected.is_live,
            "positionMode": (
                "unavailable"
                if live_available
                else selected.descriptor.position_mode
            ),
        }

    @app.get("/api/v1/replay")
    def get_replay_metadata(session_key: str | None = None) -> dict[str, Any]:
        selected = resource(session_key)
        start_time = selected.descriptor.date_start
        end_time = _effective_end_time(selected, clock())
        duration = (
            (parse_timestamp(end_time) - parse_timestamp(start_time)).total_seconds()
            if start_time and end_time
            else 0
        )
        source = live.view(selected.descriptor.key)
        live_available = bool(live_enabled and selected.is_live)
        return {
            "v": 1,
            "sessionKey": selected.descriptor.key,
            "eventCount": len(selected.events) if selected.replay_available else 0,
            "startTime": start_time,
            "endTime": end_time,
            "durationSeconds": duration,
            "available": selected.replay_available,
            "replayAvailable": selected.replay_available,
            "liveAvailable": live_available,
            "liveConnected": source.connected,
            "liveStale": source.stale,
            "liveStatus": source.status if live_available else "OFFLINE",
            "isLive": selected.is_live,
            "positionMode": (
                "unavailable"
                if live_available
                else selected.descriptor.position_mode
            ),
        }

    @app.get("/api/v1/driver-history")
    def get_driver_history(
        driver_number: str,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        """Return normalized evidence on demand, never inside RaceState snapshots."""

        selected = resource(session_key)
        observations = [
            {
                "sequence": item.sequence,
                "occurredAt": item.occurred_at,
                **asdict(item.observation),
            }
            for item in selected.evidence.lap_observations
            if item.driver_number == str(driver_number)
        ]
        return {
            "v": 1,
            "sessionKey": selected.descriptor.key,
            "driverNumber": str(driver_number),
            "available": selected.replay_available,
            "observations": observations,
            "pitEvents": [
                {
                    "sequence": item.sequence,
                    "occurredAt": item.occurred_at,
                    "driverNumber": item.driver_number,
                    "lap": item.lap,
                    "previousCompound": item.previous_compound,
                    "newCompound": item.new_compound,
                    "stopDuration": item.stop_duration,
                    "pitLaneDuration": item.pit_lane_duration,
                }
                for item in selected.evidence.pit_events_for_driver(
                    str(driver_number)
                )
            ],
        }

    @app.get("/api/v1/analytics")
    async def get_analytics(
        session_key: str | None = None,
        at: str | None = None,
        seq: int | None = None,
    ) -> dict[str, Any]:
        selected = resource(session_key)
        controller = ReplayController(
            selected.events,
            start_time=selected.descriptor.date_start,
            end_time=_effective_end_time(selected, clock()),
        )
        if at is not None and seq is not None:
            raise HTTPException(status_code=422, detail="use either at or seq")
        try:
            if seq is not None:
                controller.seek_cursor(seq)
            elif at is not None:
                controller.seek(at)
            else:
                controller.seek_cursor(len(selected.events))
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        context = meeting_context(selected, prepare=True)
        return analytics_service.snapshot(
            selected,
            controller.state,
            sequence=controller.cursor,
            as_of=controller.playhead,
            context=context,
            pirelli=pirelli_context(selected),
        )

    @app.websocket("/api/v1/stream")
    async def stream(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            selected = library_ref[0].get(websocket.query_params.get("session_key"))
        except KeyError as error:
            await websocket.send_json({"v": 1, "type": "error", "error": str(error)})
            await websocket.close(code=1008)
            return
        requested_mode = websocket.query_params.get("mode", "auto")
        wants_live = requested_mode == "live" or (
            requested_mode == "auto" and selected.is_live
        )
        if wants_live:
            if not selected.is_live:
                await websocket.send_json(
                    {
                        "v": 1,
                        "type": "error",
                        "error": "Selected session is not currently live",
                    }
                )
                await websocket.close(code=1008)
                return
            try:
                while True:
                    await websocket.send_json(live_state_envelope(selected))
                    await asyncio.sleep(0.5)
            except (WebSocketDisconnect, RuntimeError):
                pass
            return

        controller = ReplayController(
            selected.events,
            start_time=selected.descriptor.date_start,
            end_time=_effective_end_time(selected, clock()),
        )
        controller.start()
        meeting_context(selected, prepare=True)

        def current_analytics() -> dict[str, Any]:
            return analytics_service.snapshot(
                selected,
                controller.state,
                sequence=controller.cursor,
                as_of=controller.playhead,
                context=meeting_context(selected, prepare=False),
                pirelli=pirelli_context(selected),
            )
        send_lock = asyncio.Lock()
        playback_task: asyncio.Task[None] | None = None
        await _send_snapshot(
            websocket, controller, send_lock, analytics=current_analytics()
        )
        try:
            while True:
                message = await websocket.receive_json()
                message_type = message.get("type")
                if message_type == "play":
                    playback_task = await _stop_playback(playback_task, controller)
                    speed = float(message.get("speed", 1))
                    if speed <= 0 or speed > 120:
                        await websocket.send_json(
                            {
                                "v": 1,
                                "type": "error",
                                "error": "speed must be greater than 0 and at most 120",
                            }
                        )
                        continue
                    if controller.finished:
                        controller.start()
                    controller.is_playing = True
                    playback_task = asyncio.create_task(
                        _play(
                            websocket,
                            controller,
                            speed,
                            send_lock,
                            current_analytics,
                        )
                    )
                    continue
                if message_type != "snapshot":
                    playback_task = await _stop_playback(playback_task, controller)
                await _handle_message(
                    websocket,
                    controller,
                    message,
                    send_lock,
                    current_analytics,
                )
        except WebSocketDisconnect:
            pass
        finally:
            await _stop_playback(playback_task, controller)

    if web_dir is not None:
        index_path = web_dir / "index.html"
        if not index_path.is_file():
            raise FileNotFoundError(f"Web build not found at {index_path}")
        assets_path = web_dir / "assets"
        if assets_path.is_dir():
            app.mount(
                "/assets",
                StaticFiles(directory=assets_path),
                name="web-assets",
            )

        @app.get("/", include_in_schema=False)
        def web_index() -> FileResponse:
            return FileResponse(index_path)

        @app.get("/{path:path}", include_in_schema=False)
        def web_fallback(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not Found")
            return FileResponse(index_path)

    return app


def _effective_end_time(selected: ReplayResource, now: datetime) -> str:
    if not selected.is_live:
        return selected.descriptor.date_end
    scheduled_end = parse_timestamp(selected.descriptor.date_end)
    effective = min(now, scheduled_end)
    return effective.isoformat().replace("+00:00", "Z")


async def _play(
    websocket: WebSocket,
    controller: ReplayController,
    speed: float,
    send_lock: asyncio.Lock,
    analytics_supplier: Callable[[], dict[str, Any]],
) -> None:
    naturally_finished = False
    try:
        while controller.is_playing and not controller.finished:
            await asyncio.sleep(0.25)
            controller.advance(0.25 * speed)
            await _send_snapshot(
                websocket,
                controller,
                send_lock,
                analytics=analytics_supplier(),
            )
        naturally_finished = controller.finished
    except (WebSocketDisconnect, RuntimeError):
        return
    finally:
        controller.pause()
        if naturally_finished:
            await _send_snapshot(
                websocket,
                controller,
                send_lock,
                analytics=analytics_supplier(),
            )


async def _stop_playback(
    task: asyncio.Task[None] | None, controller: ReplayController
) -> None:
    controller.pause()
    if task is not None and not task.done():
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def _handle_message(
    websocket: WebSocket,
    controller: ReplayController,
    message: dict[str, Any],
    send_lock: asyncio.Lock,
    analytics_supplier: Callable[[], dict[str, Any]],
) -> None:
    message_type = message.get("type")
    try:
        if message_type == "seek":
            if "seq" in message:
                controller.seek_cursor(int(message["seq"]))
            else:
                controller.seek(str(message["at"]))
        elif message_type == "seek_relative":
            controller.seek_relative(float(message["seconds"]))
        elif message_type == "step":
            controller.step()
        elif message_type == "delay":
            controller.seek_delay(float(message["seconds"]))
        elif message_type == "reset":
            controller.start()
        elif message_type == "pause":
            pass
        elif message_type != "snapshot":
            await websocket.send_json(
                {"v": 1, "type": "error", "error": "unsupported_message"}
            )
            return
    except (KeyError, ValueError) as error:
        await websocket.send_json({"v": 1, "type": "error", "error": str(error)})
        return
    await _send_snapshot(
        websocket,
        controller,
        send_lock,
        analytics=analytics_supplier(),
    )


async def _send_snapshot(
    websocket: WebSocket,
    controller: ReplayController,
    send_lock: asyncio.Lock,
    analytics: dict[str, Any] | None = None,
) -> None:
    payload = state_envelope(
        controller.state,
        sequence=controller.cursor,
        session_time=controller.playhead,
        playing=controller.is_playing,
        analytics=analytics,
    )
    async with send_lock:
        await websocket.send_json(payload)
