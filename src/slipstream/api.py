"""Versioned HTTP/WebSocket transport over a local replay library."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .adapters.openf1 import OpenF1Client, write_recording
from .analytics import AnalyticsService
from .events import NormalizedEvent, parse_timestamp
from .evidence import SessionEvidence
from .historical_download import HistoricalSessionDownloader
from .library import ReplayLibrary, ReplayResource
from .live import PublicLiveSession
from .pirelli.backfill import PirelliHistoricalCoordinator
from .pirelli.config import DEFAULT_PIRELLI_HISTORY_YEARS, validate_history_years
from .pirelli.contracts import SessionScope
from .pirelli.coordinator import PirelliRuntimeCoordinator
from .pirelli.ingest import PirelliIngestionService
from .pirelli.seed import import_bundled_pirelli_seed, import_pirelli_seed
from .pirelli.store import PirelliAvailability, PirelliEvidenceStore
from .playback import ReplayController
from .serialization import state_envelope
from .storage import delete_replay_artifacts
from .weekend import (
    ContextAvailability,
    WeekendContextCoordinator,
    WeekendContextStore,
)

logger = logging.getLogger(__name__)


def create_app(
    recording_path: Path,
    *,
    now: Callable[[], datetime] | None = None,
    capture_session: Callable[[int], dict[str, Any]] | None = None,
    prepare_weekend_context: Callable[..., dict[str, Any]] | None = None,
    web_dir: Path | None = None,
    public_live: bool | None = None,
    live_session: PublicLiveSession | None = None,
    pirelli_history_years: int = DEFAULT_PIRELLI_HISTORY_YEARS,
    pirelli_historical_coordinator: PirelliHistoricalCoordinator | None = None,
    pirelli_backfill_initial_delay: float = 60.0,
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
    downloader = capture_session
    historical_downloader = HistoricalSessionDownloader()
    analytics_service = AnalyticsService()
    download_lock = asyncio.Lock()
    downloads_enabled = recording_path.is_dir() and os.access(recording_path, os.W_OK)

    def expose_live_recording(_path: Path) -> bool:
        library_ref[0] = ReplayLibrary(recording_path, now=clock)
        key = live.target_session_key
        ready = bool(
            key
            and library_ref[0].descriptors.get(key)
            and library_ref[0].descriptors[key].available
        )
        asyncio.get_running_loop().call_soon(
            lambda: asyncio.create_task(reconcile_live_source())
        )
        return ready

    if downloads_enabled:
        live.configure_recording(recording_path, expose_live_recording)
    pirelli_store = PirelliEvidenceStore(recording_path) if downloads_enabled else None
    pirelli_refresh_enabled = os.getenv(
        "SLIPSTREAM_PIRELLI_REFRESH", "1"
    ).strip().lower() not in {"0", "false", "no", "off"}
    pirelli_ingestion = (
        PirelliIngestionService(pirelli_store.archive)
        if pirelli_store is not None
        else None
    )
    pirelli_coordinator = (
        PirelliRuntimeCoordinator(pirelli_ingestion)
        if pirelli_ingestion is not None and pirelli_refresh_enabled
        else None
    )
    seed_enabled = os.getenv("SLIPSTREAM_PIRELLI_SEED", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    if pirelli_store is not None and seed_enabled:
        try:
            configured_seed = os.getenv("SLIPSTREAM_PIRELLI_SEED_PATH")
            if configured_seed:
                import_pirelli_seed(Path(configured_seed), recording_path)
            else:
                import_bundled_pirelli_seed(recording_path)
        except Exception:
            logger.exception("Bundled Pirelli seed import failed; startup will continue")
    pirelli_backfill_enabled = os.getenv(
        "SLIPSTREAM_PIRELLI_BACKFILL", "1"
    ).strip().lower() not in {"0", "false", "no", "off"}
    pirelli_historical = (
        pirelli_historical_coordinator
        if downloads_enabled and pirelli_historical_coordinator is not None
        else PirelliHistoricalCoordinator(
            recording_path,
            pirelli_ingestion,
            history_years=validate_history_years(pirelli_history_years),
        )
        if pirelli_ingestion is not None and pirelli_backfill_enabled
        else None
    )
    pirelli_refresh_task: list[asyncio.Task[None] | None] = [None]
    pirelli_backfill_task: list[asyncio.Task[None] | None] = [None]
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
        allow_methods=["GET", "POST", "DELETE"],
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
            return PirelliAvailability(
                "ABSENT", error="operational Pirelli storage is not writable"
            )
        scope = (
            SessionScope.SPRINT
            if selected.descriptor.session_kind == "sprint"
            else SessionScope.RACE
            if selected.descriptor.session_kind == "race"
            else None
        )
        if scope is None:
            return PirelliAvailability(
                "ABSENT", error="Pirelli strategy applies only to Race or Sprint"
            )
        availability = pirelli_store.load(
            meeting_key=selected.descriptor.meeting_key,
            target_session_key=selected.descriptor.key,
            evidence_cutoff=selected.descriptor.date_start,
            session_scope=scope,
        )
        if availability.status != "PRESENT" and pirelli_historical is not None:
            pirelli_historical.prioritize(selected.descriptor.meeting_key)
            refresh_status = pirelli_historical.availability_status(
                selected.descriptor.meeting_key, now=clock()
            )
            if refresh_status is not None:
                availability = replace(
                    availability,
                    status=refresh_status,
                    error=(
                        "official_pirelli_context_retry_scheduled"
                        if refresh_status == "RETRYING"
                        else "official_pirelli_context_queued"
                    ),
                )
        return availability

    def current_live_descriptor():
        if not live_enabled:
            return None
        target = live.target_session_key
        if target is not None:
            existing = library_ref[0].descriptors.get(target)
            phase = live.view(target).phase
            if existing is not None and phase in {"FINALIZING", "COMPLETE"}:
                return existing
        now_value = clock()
        current = [
            descriptor
            for descriptor in library_ref[0].descriptors.values()
            if descriptor.is_live(now_value) and not descriptor.available
        ]
        if current:
            return max(current, key=lambda item: item.date_start)
        upcoming = [
            descriptor
            for descriptor in library_ref[0].descriptors.values()
            if not descriptor.available
            and parse_timestamp(descriptor.date_start) > now_value
            and parse_timestamp(descriptor.date_start) - now_value <= timedelta(hours=6)
        ]
        return min(upcoming, key=lambda item: item.date_start) if upcoming else None

    def live_payload(
        session_key: str | None, *, delay_seconds: float = 0
    ) -> dict[str, Any]:
        view = live.view(session_key)
        return {
            "status": view.status,
            "phase": view.phase,
            "connected": view.connected,
            "stale": view.stale,
            "sequence": view.sequence,
            "lastReceivedAt": view.last_received_at,
            "error": view.error,
            "replayReady": view.replay_ready,
            "finalRecording": view.final_recording,
            "delaySeconds": delay_seconds,
        }

    def catalog_payload() -> dict[str, Any]:
        payload = library_ref[0].catalog()
        live_descriptor = current_live_descriptor()
        for session in payload["sessions"]:
            selected_live = bool(
                live_descriptor and session["sessionKey"] == live_descriptor.key
            )
            source = live.view(session["sessionKey"])
            session.update(
                {
                    "liveAvailable": bool(live_enabled and selected_live),
                    "liveConnected": selected_live and source.connected,
                    "liveStale": selected_live and source.stale,
                    "liveStatus": source.status if selected_live else "OFFLINE",
                    "livePhase": source.phase if selected_live else "UNAVAILABLE",
                    "replayReady": source.replay_ready
                    if selected_live
                    else session["available"],
                }
            )
        return {
            **payload,
            "defaultSessionKey": (
                live_descriptor.key
                if live_descriptor is not None
                else payload["defaultSessionKey"]
            ),
            "downloadsEnabled": downloads_enabled,
            "liveSessionKey": live_descriptor.key if live_descriptor else None,
            "liveStatus": (
                live.view(live_descriptor.key).status
                if live_descriptor is not None
                else "OFFLINE"
            ),
            "livePhase": (
                live.view(live_descriptor.key).phase
                if live_descriptor is not None
                else "UNAVAILABLE"
            ),
        }

    async def reconcile_live_source() -> None:
        selected = current_live_descriptor()
        if selected is None:
            if live.target_session_key is not None:
                await live.stop()
            return
        resource_for_seed = library_ref[0].get(selected.key)
        await live.start(
            selected.key,
            scheduled_start=selected.date_start,
            scheduled_end=selected.date_end,
            seed_events=resource_for_seed.events,
        )

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
        if pirelli_historical is not None:
            pirelli_backfill_task[0] = asyncio.create_task(
                pirelli_historical.run_forever(
                    clock, initial_delay=pirelli_backfill_initial_delay
                )
            )

    @app.on_event("shutdown")
    async def stop_live_source() -> None:
        historical_task = pirelli_backfill_task[0]
        pirelli_backfill_task[0] = None
        if historical_task is not None:
            historical_task.cancel()
            with suppress(asyncio.CancelledError):
                await historical_task
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
                    if downloader is not None:
                        recording = await asyncio.to_thread(
                            downloader, int(session_key)
                        )
                        await asyncio.to_thread(
                            write_recording,
                            recording_path / f"openf1-{session_key}.json",
                            recording,
                        )
                    else:
                        await asyncio.to_thread(
                            historical_downloader.download,
                            current,
                            recording_path,
                        )
                    library_ref[0] = ReplayLibrary(recording_path, now=clock)
                    restored = library_ref[0].descriptors.get(session_key)
                    if restored is None or not restored.available:
                        raise RuntimeError(
                            "download did not publish a usable replay for the selected session"
                        )
                    analytics_service.clear()
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

    @app.delete("/api/v1/replay")
    async def delete_replay(session_key: str) -> dict[str, Any]:
        if not downloads_enabled:
            raise HTTPException(
                status_code=409,
                detail="Replay deletion requires writable recording storage",
            )
        descriptor = library_ref[0].descriptors.get(session_key)
        if descriptor is None:
            raise HTTPException(status_code=404, detail="Unknown catalog session")
        live_view = live.view(session_key)
        if (
            live.target_session_key == session_key
            and live_view.phase != "REPLAY_READY"
        ):
            raise HTTPException(
                status_code=409,
                detail="Cannot delete a replay while its live recording is active",
            )
        async with download_lock:
            deletion = await asyncio.to_thread(
                delete_replay_artifacts, recording_path, session_key
            )
            if context_coordinator is not None:
                context_coordinator.forget(descriptor)
            library_ref[0] = ReplayLibrary(recording_path, now=clock)
            analytics_service.clear()
        return {
            "v": 1,
            "sessionKey": session_key,
            "status": "unavailable",
            "removed": list(deletion.removed),
            "catalog": catalog_payload(),
        }

    def live_mode_available(selected: ReplayResource) -> bool:
        descriptor = current_live_descriptor()
        return bool(
            live_enabled
            and descriptor is not None
            and descriptor.key == selected.descriptor.key
        )

    def live_state_envelope(
        selected: ReplayResource, *, delay_seconds: float = 0
    ) -> dict[str, Any]:
        source = live.view(selected.descriptor.key)
        has_live_state = (
            source.target_session_key == selected.descriptor.key and source.sequence > 0
        )
        events = live.events if has_live_state else selected.events
        if has_live_state and delay_seconds == 0:
            state = live.state
            evidence = live.evidence
            sequence = len(events)
            playhead = events[-1].occurred_at if events else state.updated_at
        else:
            controller = ReplayController(
                events,
                start_time=selected.descriptor.date_start,
                end_time=None,
            )
            if events and delay_seconds > 0:
                controller.seek_delay(delay_seconds)
            elif events:
                controller.seek_cursor(len(events))
            state = controller.state if events else selected.final_state
            evidence = SessionEvidence.from_events(tuple(events))
            sequence = controller.cursor
            playhead = controller.playhead or state.updated_at
        analytics = None
        if has_live_state and source.phase not in {
            "PRE_EVENT",
            "CONNECTING",
            "UNAVAILABLE",
        }:
            live_resource = ReplayResource(
                descriptor=selected.descriptor,
                events=tuple(events),
                final_state=state,
                evidence=evidence,
                replay_available=False,
                is_live=True,
            )
            analytics = analytics_service.snapshot(
                live_resource,
                state,
                sequence=sequence,
                as_of=playhead,
                context=meeting_context(selected, prepare=True),
                pirelli=pirelli_context(selected),
            )
        envelope = state_envelope(
            state,
            sequence=sequence,
            session_time=playhead,
            analytics=analytics,
        )
        envelope["mode"] = "live"
        envelope["live"] = live_payload(
            selected.descriptor.key, delay_seconds=delay_seconds
        )
        return envelope

    def replay_handoff_envelope(selected: ReplayResource) -> dict[str, Any]:
        envelope = state_envelope(
            selected.final_state,
            sequence=len(selected.events),
            session_time=(selected.events[-1].occurred_at if selected.events else None),
        )
        envelope["mode"] = "replay"
        envelope["handoff"] = "REPLAY_READY"
        return envelope

    @app.get("/api/v1/state")
    async def get_state(
        session_key: str | None = None, mode: str = "auto"
    ) -> dict[str, Any]:
        selected = resource(session_key)
        if mode not in {"auto", "live", "replay"}:
            raise HTTPException(
                status_code=422, detail="mode must be auto, live, or replay"
            )
        wants_live = mode == "live" or (
            mode == "auto" and live_mode_available(selected)
        )
        if wants_live:
            if not live_mode_available(selected):
                raise HTTPException(
                    status_code=409,
                    detail="Selected session is not available in Live mode",
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
        live_available = live_mode_available(selected)
        capabilities = dict(selected.descriptor.capabilities)
        if live_available:
            capabilities.update(
                {
                    "live_timing": True,
                    "positions": False,
                    "intervals": True,
                    "sector_timing": True,
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
            "livePhase": source.phase if live_available else "UNAVAILABLE",
            "replayReady": selected.replay_available or source.replay_ready,
            "isLive": selected.is_live,
            "positionMode": (
                "unavailable" if live_available else selected.descriptor.position_mode
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
        live_available = live_mode_available(selected)
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
            "livePhase": source.phase if live_available else "UNAVAILABLE",
            "replayReady": selected.replay_available or source.replay_ready,
            "isLive": selected.is_live,
            "positionMode": (
                "unavailable" if live_available else selected.descriptor.position_mode
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
                    "ordinal": item.ordinal,
                }
                for item in selected.evidence.pit_events_for_driver(str(driver_number))
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
            requested_mode == "auto" and live_mode_available(selected)
        )
        if wants_live:
            if not live_mode_available(selected):
                await websocket.send_json(
                    {
                        "v": 1,
                        "type": "error",
                        "error": "Selected session is not available in Live mode",
                    }
                )
                await websocket.close(code=1008)
                return
            delay_seconds = 0.0
            try:
                while True:
                    if not live_mode_available(selected):
                        refreshed = library_ref[0].get(selected.descriptor.key)
                        if refreshed.replay_available:
                            await websocket.send_json(
                                replay_handoff_envelope(refreshed)
                            )
                            await websocket.close(code=1000)
                            return
                    await websocket.send_json(
                        live_state_envelope(selected, delay_seconds=delay_seconds)
                    )
                    try:
                        message = await asyncio.wait_for(
                            websocket.receive_json(), timeout=0.5
                        )
                    except TimeoutError:
                        continue
                    message_type = message.get("type")
                    if message_type == "delay":
                        requested_delay = float(message.get("seconds", 0))
                        if requested_delay < 0 or requested_delay > 300:
                            await websocket.send_json(
                                {
                                    "v": 1,
                                    "type": "error",
                                    "error": "live delay must be between 0 and 300 seconds",
                                }
                            )
                            continue
                        delay_seconds = requested_delay
                    elif message_type in {"reset", "live"}:
                        delay_seconds = 0.0
                    elif message_type != "snapshot":
                        await websocket.send_json(
                            {
                                "v": 1,
                                "type": "error",
                                "error": "Live mode supports only delay, reset/live, and snapshot",
                            }
                        )
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
        terminal = _settled_terminal_time(selected)
        return terminal or selected.descriptor.date_end
    scheduled_end = parse_timestamp(selected.descriptor.date_end)
    effective = min(now, scheduled_end)
    return effective.isoformat().replace("+00:00", "Z")


def _first_terminal_time(events: tuple[NormalizedEvent, ...]) -> str | None:
    """Return the first normalized, user-domain session terminal boundary."""

    for event in events:
        if _is_terminal_session_event(event):
            return event.occurred_at
    return None


def _is_terminal_session_event(event: NormalizedEvent) -> bool:
    if event.kind != "session":
        return False
    terminal_statuses = {"FINISHED", "CANCELLED"}
    terminal_controls = {"CHEQUERED", "CANCELLED"}
    status = str(event.payload.get("status") or "").upper()
    track = str(event.payload.get("track_status") or "").upper()
    control = str(event.payload.get("control_status") or "").upper()
    display = str(event.payload.get("display_status") or "").upper()
    return status in terminal_statuses or bool(
        terminal_controls.intersection({track, control, display})
    )


def _qualifying_terminal_time(
    events: tuple[NormalizedEvent, ...], *, sprint: bool
) -> str | None:
    final_phase = "SQ3" if sprint else "Q3"
    final_phase_started = False
    first_terminal_boundary: str | None = None
    for event in events:
        if event.kind == "session" and str(
            event.payload.get("qualifying_phase") or ""
        ).upper() == final_phase:
            final_phase_started = True
        if not final_phase_started or not _is_terminal_session_event(event):
            continue
        first_terminal_boundary = first_terminal_boundary or event.occurred_at
        if str(event.payload.get("status") or "").upper() in {
            "FINISHED",
            "CANCELLED",
        }:
            return event.occurred_at
    return first_terminal_boundary


def _settled_terminal_time(selected: ReplayResource) -> str | None:
    """Return the factual end after all phases or race classification settle."""

    first_terminal = _first_terminal_time(selected.events)
    if first_terminal is None:
        return first_terminal
    if selected.descriptor.session_kind in {"qualifying", "sprint_qualifying"}:
        # Qualifying emits a FINISHED boundary for each phase and may repeat
        # terminal packets after Q3. The replay ends at the first terminal
        # boundary after the final phase actually starts.
        return _qualifying_terminal_time(
            selected.events,
            sprint=selected.descriptor.session_kind == "sprint_qualifying",
        ) or first_terminal
    if selected.descriptor.session_kind != "race":
        return first_terminal

    participants: set[str] = set()
    classified: set[str] = set()
    eligible_field_size = 0
    terminal_seen = False
    for event in selected.events:
        if event.kind == "session":
            field_size = event.payload.get("eligible_field_size")
            if isinstance(field_size, int):
                eligible_field_size = max(eligible_field_size, field_size)
            if event.occurred_at == first_terminal:
                terminal_seen = True
        elif event.kind in {"driver", "timing"}:
            number = event.payload.get("number")
            if number is not None:
                participants.add(str(number))
                if event.payload.get("classification") not in {None, ""}:
                    classified.add(str(number))
        expected = max(eligible_field_size, len(participants))
        if terminal_seen and expected > 0 and len(classified) >= expected:
            return event.occurred_at

    # Legacy recordings without final classification retain their factual
    # terminal boundary instead of exposing unrelated post-session packets.
    return first_terminal


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
