"""Versioned HTTP/WebSocket transport over a local replay library."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .adapters.openf1 import OpenF1Client, write_recording
from .events import parse_timestamp
from .library import ReplayLibrary, ReplayResource
from .playback import ReplayController
from .serialization import state_envelope


def create_app(
    recording_path: Path,
    *,
    now: Callable[[], datetime] | None = None,
    capture_session: Callable[[int], dict[str, Any]] | None = None,
    web_dir: Path | None = None,
) -> FastAPI:
    clock = now or (lambda: datetime.now(UTC))
    library_ref = [ReplayLibrary(recording_path, now=clock)]
    downloader = capture_session or OpenF1Client().capture_session
    download_lock = asyncio.Lock()
    downloads_enabled = recording_path.is_dir() and os.access(recording_path, os.W_OK)
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

    @app.get("/api/v1/catalog")
    def get_catalog() -> dict[str, Any]:
        return {
            **library_ref[0].catalog(),
            "downloadsEnabled": downloads_enabled,
        }

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
            "catalog": {
                **library_ref[0].catalog(),
                "downloadsEnabled": True,
            },
        }

    @app.get("/api/v1/state")
    def get_state(session_key: str | None = None) -> dict[str, Any]:
        selected = resource(session_key)
        return state_envelope(
            selected.final_state,
            sequence=len(selected.events),
            session_time=selected.events[-1].occurred_at if selected.events else None,
        )

    @app.get("/api/v1/capabilities")
    def get_capabilities(session_key: str | None = None) -> dict[str, Any]:
        selected = resource(session_key)
        return {
            "v": 1,
            "source": selected.descriptor.source,
            "capabilities": selected.descriptor.capabilities,
            "replayAvailable": selected.replay_available,
            "isLive": selected.is_live,
            "positionMode": selected.descriptor.position_mode,
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
        return {
            "v": 1,
            "sessionKey": selected.descriptor.key,
            "eventCount": len(selected.events) if selected.replay_available else 0,
            "startTime": start_time,
            "endTime": end_time,
            "durationSeconds": duration,
            "available": selected.replay_available,
            "isLive": selected.is_live,
            "positionMode": selected.descriptor.position_mode,
        }

    @app.websocket("/api/v1/stream")
    async def stream(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            selected = library_ref[0].get(websocket.query_params.get("session_key"))
        except KeyError as error:
            await websocket.send_json({"v": 1, "type": "error", "error": str(error)})
            await websocket.close(code=1008)
            return
        controller = ReplayController(
            selected.events,
            start_time=selected.descriptor.date_start,
            end_time=_effective_end_time(selected, clock()),
        )
        controller.start()
        send_lock = asyncio.Lock()
        playback_task: asyncio.Task[None] | None = None
        await _send_snapshot(websocket, controller, send_lock)
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
                        _play(websocket, controller, speed, send_lock)
                    )
                    continue
                if message_type != "snapshot":
                    playback_task = await _stop_playback(playback_task, controller)
                await _handle_message(websocket, controller, message, send_lock)
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
) -> None:
    naturally_finished = False
    try:
        while controller.is_playing and not controller.finished:
            await asyncio.sleep(0.25)
            controller.advance(0.25 * speed)
            await _send_snapshot(websocket, controller, send_lock)
        naturally_finished = controller.finished
    except (WebSocketDisconnect, RuntimeError):
        return
    finally:
        controller.pause()
        if naturally_finished:
            await _send_snapshot(websocket, controller, send_lock)


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
    await _send_snapshot(websocket, controller, send_lock)


async def _send_snapshot(
    websocket: WebSocket,
    controller: ReplayController,
    send_lock: asyncio.Lock,
) -> None:
    payload = state_envelope(
        controller.state,
        sequence=controller.cursor,
        session_time=controller.playhead,
        playing=controller.is_playing,
    )
    async with send_lock:
        await websocket.send_json(payload)
