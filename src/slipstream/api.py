"""Versioned HTTP/WebSocket transport over a local replay library."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from math import isfinite
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .adapters.openf1 import OpenF1Client, write_recording
from .analytics import AnalyticsService
from .async_work import finish_owned
from .events import NormalizedEvent, parse_timestamp
from .historical_download import HistoricalSessionDownloader
from .library import ReplayBusyError, ReplayLibrary, ReplayResource
from .live import PublicLiveSession, RecordingBusyError
from .live_recording import NormalizedLiveRecorder
from .pirelli.backfill import PirelliHistoricalCoordinator
from .pirelli.contracts import SessionScope
from .pirelli.coordinator import PirelliRuntimeCoordinator
from .pirelli.ingest import PirelliIngestionService
from .pirelli.seed import import_bundled_pirelli_seed, import_pirelli_seed
from .pirelli.store import PirelliAvailability, PirelliEvidenceStore
from .playback import ReplayController
from .replay import events_from_recording
from .serialization import state_envelope
from .session_completion import session_completion
from .state import RaceState
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
    pirelli_historical_coordinator: PirelliHistoricalCoordinator | None = None,
    pirelli_backfill_initial_delay: float = 60.0,
    refresh_catalog: Callable[[], Any] | None = None,
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
    compute_lock = asyncio.Semaphore(2)
    preparation_lock = asyncio.Semaphore(1)
    preparation_registry_lock = asyncio.Lock()
    preparations: dict[int, asyncio.Task] = {}
    preparation_cleanup: set[asyncio.Task] = set()
    background_tasks: set[asyncio.Task] = set()
    initialization = {
        "status": "refreshing" if refresh_catalog is not None else "ready",
        "error": None,
    }
    seed_task: list[asyncio.Task | None] = [None]

    async def compute(function, *args, **kwargs):
        async with compute_lock:
            worker = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
            return await finish_owned(worker)

    async def release_resource(selected):
        # Cleanup itself must survive a second cancellation, including while
        # waiting for a compute slot or another thread's library lock.
        await finish_owned(
            asyncio.create_task(compute(library_ref[0].release, selected))
        )

    @asynccontextmanager
    async def resource_lease(key=None, *, http=False):
        owned = []

        def acquire():
            selected = library_ref[0].acquire(key)
            owned.append(selected)
            return selected

        try:
            try:
                selected = await compute(acquire)
            except KeyError as error:
                if http:
                    raise HTTPException(status_code=404, detail=str(error)) from error
                raise
            except ReplayBusyError as error:
                if http:
                    raise HTTPException(status_code=503, detail=str(error)) from error
                raise
            yield selected
        finally:
            if owned:
                await release_resource(owned.pop())

    async def ensure_preparation(selected):
        async with preparation_registry_lock:
            if selected.prepared:
                return None
            identity = id(selected)
            if identity in preparations:
                return preparations[identity]
            owned = []

            def retain():
                library_ref[0].retain(selected)
                owned.append(selected)

            try:
                await compute(retain)
            except BaseException:
                if owned:
                    await release_resource(owned.pop())
                raise

            async def prepare_owned():
                async with preparation_lock:
                    await compute(selected.prepare)

            async def cleanup_preparation():
                try:
                    await release_resource(selected)
                finally:
                    preparations.pop(identity, None)

            def finished(_done):
                # This callback also runs if cancellation precedes the job's
                # first instruction, when a coroutine finally cannot run.
                cleanup = asyncio.create_task(cleanup_preparation())
                preparation_cleanup.add(cleanup)
                cleanup.add_done_callback(preparation_cleanup.discard)

            task = background(prepare_owned())
            preparations[identity] = task
            task.add_done_callback(finished)
            return task

    async def prepare_replay(selected):
        task = await ensure_preparation(selected)
        if task is not None:
            await asyncio.shield(task)

    def background(coroutine):
        task = asyncio.create_task(coroutine)
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

        def report_failure(done):
            if not done.cancelled() and done.exception() is not None:
                logger.warning(
                    "Background work failed: %s", type(done.exception()).__name__
                )

        task.add_done_callback(report_failure)
        return task

    downloads_enabled = recording_path.is_dir() and os.access(recording_path, os.W_OK)
    completed_live: dict[str, tuple[ReplayResource, Any, datetime]] = {}
    live_reconcile_lock = asyncio.Lock()
    recovery_key: str | None = None
    recovery_checked = False

    def retain_drained_session(key: str, source=None) -> None:
        completed_live[key] = (
            ReplayResource(
                replace(library_ref[0].descriptors[key], complete=False)
                if source is not None
                else library_ref[0].descriptors[key],
                live.events,
                live.state,
                live.evidence,
                replay_available=False,
            ),
            source or live.view(key),
            clock(),
        )
        while len(completed_live) > 3:
            completed_live.pop(next(iter(completed_live)))
        if source is None:
            asyncio.get_running_loop().call_soon(
                lambda: asyncio.create_task(reconcile_live_source())
            )

    async def expose_live_recording(_path: Path) -> bool:
        # Publication may finish after the one collector has moved to another key.
        key = _path.name.removeprefix("live-").removesuffix(".json")
        await compute(library_ref[0].refresh_session, key, _path)
        ready = bool(
            key
            and library_ref[0].descriptors.get(key)
            and library_ref[0].descriptors[key].available
        )
        if key and ready:
            archived = completed_live.get(key)
            if archived is None:
                return ready
            selected = ReplayResource(
                library_ref[0].descriptors[key],
                archived[0].events,
                archived[0].final_state,
                archived[0].evidence,
                replay_available=True,
            )
            completed_live[key] = (
                selected,
                replace(
                    live.view(key), phase="REPLAY_READY", replay_ready=True, error=None
                ),
                archived[2],
            )
            while len(completed_live) > 3:
                completed_live.pop(next(iter(completed_live)))
        asyncio.get_running_loop().call_soon(
            lambda: asyncio.create_task(reconcile_live_source())
        )
        return ready

    if downloads_enabled:
        live.configure_recording(
            recording_path, expose_live_recording, retain_drained_session
        )
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

    def import_seed():
        if pirelli_store is None or not seed_enabled:
            return
        try:
            configured_seed = os.getenv("SLIPSTREAM_PIRELLI_SEED_PATH")
            if configured_seed:
                import_pirelli_seed(Path(configured_seed), recording_path)
            else:
                import_bundled_pirelli_seed(recording_path)
        except Exception:
            logger.exception(
                "Bundled Pirelli seed import failed; startup will continue"
            )

    pirelli_backfill_enabled = os.getenv(
        "SLIPSTREAM_PIRELLI_BACKFILL", "1"
    ).strip().lower() not in {"0", "false", "no", "off"}
    pirelli_historical = (
        pirelli_historical_coordinator
        if downloads_enabled and pirelli_historical_coordinator is not None
        else PirelliHistoricalCoordinator(
            recording_path,
            pirelli_ingestion,
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
    app = FastAPI(title="Slipstream", version="0.1.0")
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
        except ReplayBusyError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

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
        if pirelli_historical is not None:
            if availability.status != "PRESENT":
                pirelli_historical.prioritize(selected.descriptor.meeting_key)
            refresh_status = pirelli_historical.availability_status(
                selected.descriptor.meeting_key, now=clock()
            )
            if refresh_status == "FETCHING" or (
                availability.status != "PRESENT" and refresh_status is not None
            ):
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
        now_value = clock()
        current = [
            descriptor
            for descriptor in library_ref[0].descriptors.values()
            if descriptor.is_live(now_value)
            and descriptor.complete is not True
            and not (
                descriptor.key == live.target_session_key
                and live.view(descriptor.key).replay_ready
            )
        ]
        if current:
            return max(current, key=lambda item: item.date_start)
        target = live.target_session_key
        existing = library_ref[0].descriptors.get(target)
        if (
            existing is not None
            and not live.view(target).replay_ready
            and (
                live.view(target).phase in {"FINALIZING", "COMPLETE"}
                or live.state.session.status in {"RUNNING", "SUSPENDED"}
            )
        ):
            return existing
        recovered = library_ref[0].descriptors.get(recovery_key)
        if recovered is not None and recovered.complete is not True:
            return recovered
        upcoming = [
            descriptor
            for descriptor in library_ref[0].descriptors.values()
            if descriptor.complete is not True
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
            "initialization": dict(initialization),
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
        async with live_reconcile_lock:
            await _reconcile_live_source()

    async def _reconcile_live_source() -> None:
        nonlocal recovery_key, recovery_checked
        if live_enabled and not recovery_checked and live.target_session_key is None:
            recovery_key = await compute(library_ref[0].recoverable_live_key)
            recovery_checked = True
        selected = current_live_descriptor()
        if selected is None:
            if live.target_session_key is not None:
                await live.stop(preserve_publications=True)
            return
        if (
            selected.path is not None
            and selected.complete is None
            and selected.key != live.target_session_key
        ):
            await compute(library_ref[0].refresh_session, selected.key, selected.path)
            if library_ref[0].descriptors[selected.key].complete:
                return await _reconcile_live_source()
        if (
            live.target_session_key is not None
            and live.target_session_key != selected.key
        ):
            previous_key = live.target_session_key
            await live.finish_pending()
            if previous_key not in completed_live and live.events:
                previous_source = live.view(previous_key)
                # No terminal packet arrived. Stop the old writer before taking
                # its last proven state, but leave its journal unfinished.
                await live.stop(preserve_publications=True)
                retain_drained_session(
                    previous_key,
                    replace(
                        previous_source,
                        status="OFFLINE",
                        connected=False,
                        stale=True,
                        phase="STALE",
                        sequence=len(live.events),
                        replay_ready=False,
                    ),
                )
        await live.start(
            selected.key,
            scheduled_start=selected.date_start,
            scheduled_end=selected.date_end,
            seed_events=library_ref[0].seed_events(selected.key),
        )
        recovery_key = None

    async def monitor_live_source() -> None:
        while True:
            try:
                await reconcile_live_source()
            except Exception:
                logger.exception("Live monitor failed; retrying")
            await asyncio.sleep(15)

    def completed_journal(descriptor):
        path = recording_path / f"live-{descriptor.key}.in-progress.jsonl"
        if not path.is_file() or parse_timestamp(descriptor.date_start) > clock():
            return None
        before = path.stat()
        recorder = NormalizedLiveRecorder(recording_path, descriptor.key)
        events = recorder.events
        identity = {}
        for event in events:
            if parse_timestamp(event.occurred_at) > clock() or (
                event.received_at and parse_timestamp(event.received_at) > clock()
            ):
                return None
            if event.kind == "session":
                identity.update(event.payload)
        if (
            str(identity.get("key")) != descriptor.key
            or not session_completion(
                events, session_kind=descriptor.session_kind
            ).complete
        ):
            return None
        after = path.stat()
        signature = (before.st_mtime_ns, before.st_size)
        if signature != (after.st_mtime_ns, after.st_size):
            return None
        return recorder, signature

    async def recover_completed_journals():
        cursor = 0
        while True:
            candidates = sorted(
                (d for d in library_ref[0].descriptors.values() if d.key.isdigit()),
                key=lambda d: d.date_start,
                reverse=True,
            )
            for offset in range(min(3, len(candidates))):
                descriptor = candidates[(cursor + offset) % len(candidates)]
                if descriptor.key == live.target_session_key:
                    continue
                try:
                    recovered = await compute(completed_journal, descriptor)
                    if recovered is not None:
                        await live.recover_completed_recording(*recovered)
                except (OSError, RuntimeError, ValueError, KeyError, TypeError):
                    logger.warning(
                        "Cannot recover completed journal for session %s",
                        descriptor.key,
                    )
            cursor = (cursor + 3) % max(1, len(candidates))
            await asyncio.sleep(15)

    async def initialize_optional_data():
        nonlocal recovery_checked
        if refresh_catalog is None:
            return
        while True:
            initialization.update(status="refreshing", error=None)
            try:
                await asyncio.to_thread(refresh_catalog)
                await compute(library_ref[0].refresh_catalog)
                recovery_checked = False
                initialization.update(status="ready", error=None)
                await reconcile_live_source()
                return
            except Exception as error:  # noqa: BLE001 - bounded background failure is visible and retryable
                initialization.update(status="retrying", error=type(error).__name__)
                logger.warning(
                    "Catalog refresh failed (%s); retrying", type(error).__name__
                )
                await asyncio.sleep(60)

    @app.on_event("startup")
    async def start_live_source() -> None:
        seed_task[0] = background(asyncio.to_thread(import_seed))
        background(initialize_optional_data())
        if downloads_enabled:
            background(recover_completed_journals())
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
        for pending in tuple(background_tasks):
            pending.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)
        while preparation_cleanup:
            await asyncio.gather(*preparation_cleanup, return_exceptions=True)
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
    async def get_catalog() -> JSONResponse:
        # The payload already consists of wire primitives. Avoid FastAPI's
        # second recursive Python traversal of the complete season inventory.
        return JSONResponse(catalog_payload())

    @app.get("/api/v1/diagnostics")
    async def get_diagnostics() -> dict[str, Any]:
        return {
            "v": 1,
            "live": live.diagnostics,
            "replay": library_ref[0].diagnostics,
            "initialization": dict(initialization),
        }

    download_jobs: dict[str, dict[str, Any]] = {}

    @app.get("/api/v1/jobs")
    async def get_jobs() -> dict[str, Any]:
        return {"v": 1, "jobs": list(download_jobs.values())}

    async def run_download(session_key: str):
        job = download_jobs[session_key]
        try:
            async with download_lock:
                job.update(status="DOWNLOADING", error=None)
                current = library_ref[0].descriptors[session_key]
                if current.available and current.complete is None:
                    # Fast discovery deliberately leaves completeness unknown.
                    # Inspect only this requested artifact before skipping work.
                    await compute(
                        library_ref[0].refresh_session,
                        session_key,
                        current.path,
                        inspect_completion=True,
                    )
                    current = library_ref[0].descriptors[session_key]
                if current.available and current.complete is True:
                    job["status"] = "AVAILABLE"
                    return
                if downloader is not None:
                    recording = await asyncio.to_thread(downloader, int(session_key))
                    events = await compute(events_from_recording, recording)
                    if not any(
                        event.kind == "session"
                        and str(event.payload.get("key")) == session_key
                        for event in events
                    ):
                        raise ValueError(
                            "download does not contain the requested session"
                        )
                    job["status"] = "FINALIZING"
                    path = recording_path / f"openf1-{session_key}.json"
                    await asyncio.to_thread(write_recording, path, recording)
                else:
                    path = await asyncio.to_thread(
                        historical_downloader.download, current, recording_path
                    )
                    job["status"] = "FINALIZING"
                await compute(
                    library_ref[0].refresh_session,
                    session_key,
                    path,
                    inspect_completion=True,
                )
                restored = library_ref[0].descriptors.get(session_key)
                if restored is None or not restored.available:
                    raise RuntimeError("download did not publish a usable replay")
                analytics_service.clear()
                job["status"] = "AVAILABLE"
        except asyncio.CancelledError:
            job.update(status="FAILED", error="Server stopped during download; retry")
            raise
        except Exception as error:  # noqa: BLE001 - bounded background failure is visible and retryable
            job.update(
                status="FAILED",
                error=f"Historical replay download failed: {type(error).__name__}: {str(error)[:200]}",
            )
            logger.warning(
                "Replay download failed session=%s error=%s",
                session_key,
                type(error).__name__,
            )

    @app.post("/api/v1/download", status_code=202)
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
        job = download_jobs.get(session_key)
        if job and job["status"] in {"QUEUED", "DOWNLOADING", "FINALIZING"}:
            return {"v": 1, **job}
        if len(download_jobs) >= 32:
            old = next(
                (
                    key
                    for key, value in download_jobs.items()
                    if value["status"] in {"AVAILABLE", "FAILED"}
                ),
                None,
            )
            if old is None:
                raise HTTPException(status_code=409, detail="Download queue is full")
            download_jobs.pop(old)
        job = {"sessionKey": session_key, "status": "QUEUED", "error": None}
        download_jobs[session_key] = job
        if descriptor.available and descriptor.complete is True:
            job["status"] = "AVAILABLE"
        else:
            background(run_download(session_key))
        return {"v": 1, **job}

    @app.delete("/api/v1/replay")
    async def delete_replay(session_key: str) -> dict[str, Any]:
        if download_jobs.get(session_key, {}).get("status") in {
            "QUEUED",
            "DOWNLOADING",
            "FINALIZING",
        }:
            raise HTTPException(
                status_code=409,
                detail="Wait for this session's download before deleting",
            )
        if not downloads_enabled:
            raise HTTPException(
                status_code=409,
                detail="Replay deletion requires writable recording storage",
            )
        descriptor = library_ref[0].descriptors.get(session_key)
        if descriptor is None:
            raise HTTPException(status_code=404, detail="Unknown catalog session")
        try:
            async with (
                download_lock,
                live_reconcile_lock,
                live.deleting_recording(session_key),
            ):
                deletion = await compute(
                    delete_replay_artifacts, recording_path, session_key
                )
                if context_coordinator is not None:
                    context_coordinator.forget(descriptor)
                await compute(library_ref[0].refresh_session, session_key)
                analytics_service.clear()
                completed_live.pop(session_key, None)
        except RecordingBusyError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
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

    def live_position_mode(state: RaceState) -> str:
        return (
            "timing_estimate"
            if any(
                driver.track_position is not None for driver in state.drivers.values()
            )
            else "unavailable"
        )

    def live_state_envelope(
        selected: ReplayResource, *, delay_seconds: float = 0, archived=None
    ) -> dict[str, Any]:
        source = live.view(selected.descriptor.key)
        if archived and source.target_session_key != selected.descriptor.key:
            source = archived[1]
        has_live_state = (
            source.target_session_key == selected.descriptor.key and source.sequence > 0
        )
        events = (
            archived[0].events
            if archived
            else live.events
            if has_live_state
            else selected.events
        )
        if has_live_state and delay_seconds == 0:
            state = archived[0].final_state if archived else live.state
            evidence = archived[0].evidence if archived else live.evidence
            sequence = len(events)
            playhead = events[-1].occurred_at if events else state.updated_at
        else:
            controller = ReplayController(
                events,
                start_time=selected.descriptor.date_start,
                end_time=None,
            )
            if events and delay_seconds > 0:
                if archived:
                    end = parse_timestamp(events[-1].occurred_at)
                    target = min(
                        end,
                        end
                        + (clock() - archived[2])
                        - timedelta(seconds=delay_seconds),
                    )
                    controller.seek(target.isoformat())
                else:
                    controller.seek_delay(delay_seconds)
            elif events:
                controller.seek_cursor(len(events))
            state = controller.state if events else selected.final_state
            evidence = (
                archived[0].evidence
                if archived
                else live.evidence
                if has_live_state
                else selected.evidence
            )
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
            events=events,
            sequence=sequence,
            session_time=playhead,
            analytics=analytics,
        )
        envelope["mode"] = "live"
        envelope["live"] = live_payload(
            selected.descriptor.key, delay_seconds=delay_seconds
        )
        envelope["live"]["positionMode"] = (
            live_position_mode(state) if has_live_state else "unavailable"
        )
        if archived:
            envelope["live"].update(
                phase=source.phase,
                replayReady=source.replay_ready,
                error=source.error,
                connected=False,
                status="OFFLINE",
                stale=source.stale,
                sequence=source.sequence,
                lastReceivedAt=source.last_received_at,
                finalRecording=source.final_recording,
            )
            next_session = current_live_descriptor()
            if (
                source.phase == "STALE"
                and sequence >= len(events)
                and next_session is not None
                and next_session.key != selected.descriptor.key
            ):
                # This means only that the retained delayed tail is consumed.
                # It neither declares sporting completion nor a replay ready.
                envelope["live"]["nextSessionKey"] = next_session.key
        return envelope

    def replay_handoff_envelope(selected: ReplayResource) -> dict[str, Any]:
        envelope = state_envelope(
            selected.final_state,
            events=selected.events,
            sequence=len(selected.events),
            session_time=(selected.events[-1].occurred_at if selected.events else None),
        )
        envelope["mode"] = "replay"
        envelope["handoff"] = "REPLAY_READY"
        return envelope

    @app.get("/api/v1/state")
    async def get_state(
        session_key: str | None = None,
        mode: str = "auto",
        at: str | None = None,
        seq: int | None = None,
        delay_seconds: float = 0,
        recording_version: str | None = None,
    ) -> dict[str, Any]:
        async with resource_lease(session_key, http=True) as selected:
            return await state_for_resource(
                selected, mode, at, seq, delay_seconds, recording_version
            )

    async def state_for_resource(
        selected, mode, at, seq, delay_seconds, recording_version
    ):
        if mode not in {"auto", "live", "replay"}:
            raise HTTPException(
                status_code=422, detail="mode must be auto, live, or replay"
            )
        wants_live = mode == "live" or (
            mode == "auto" and live_mode_available(selected)
        )
        if wants_live:
            if (
                not live_mode_available(selected)
                and selected.descriptor.key not in completed_live
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Selected session is not available in Live mode",
                )
            if not isfinite(delay_seconds) or not 0 <= delay_seconds <= 300:
                raise HTTPException(
                    status_code=422,
                    detail="live delay must be between 0 and 300 seconds",
                )
            archived = completed_live.get(selected.descriptor.key)
            envelope = live_state_envelope(
                selected, delay_seconds=delay_seconds, archived=archived
            )
            envelope.update(
                metadata=metadata_payload(
                    archived[0] if archived else selected, archived
                ),
                capabilities=capability_payload(
                    archived[0] if archived else selected, archived
                ),
                playbackReady=True,
            )
            if (
                archived
                and envelope["live"]["replayReady"]
                and envelope["seq"] >= len(archived[0].events)
            ):
                envelope.update(mode="replay", handoff="REPLAY_READY")
            return envelope
        if at is not None and seq is not None:
            raise HTTPException(status_code=422, detail="use either at or seq")
        controller = selected.controller(
            end_time=_effective_end_time(selected, clock())
        )
        try:
            if (
                seq is not None
                and recording_version is not None
                and recording_version != selected.recording_version
            ):
                await compute(controller.start)
            elif seq is not None:
                await compute(controller.seek_cursor, seq)
            elif at == "start":
                await compute(controller.start)
            elif at is not None:
                await compute(controller.seek, at)
            else:
                await prepare_replay(selected)
                await compute(controller.seek_cursor, len(selected.events))
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        envelope = state_envelope(
            controller.state,
            events=selected.events,
            sequence=controller.cursor,
            session_time=controller.playhead,
        )
        envelope.update(
            mode="replay",
            metadata=metadata_payload(selected),
            capabilities=capability_payload(selected),
            playbackReady=True,
        )
        return envelope

    @app.get("/api/v1/capabilities")
    async def get_capabilities(session_key: str | None = None) -> dict[str, Any]:
        async with resource_lease(session_key, http=True) as selected:
            return capability_payload(selected)

    def capability_payload(selected, archived=None):
        source = archived[1] if archived else live.view(selected.descriptor.key)
        live_available = bool(archived) or live_mode_available(selected)
        retained_state = archived[0].final_state if archived else live.state
        live_mode = (
            live_position_mode(retained_state)
            if source.target_session_key == selected.descriptor.key
            else "unavailable"
        )
        capabilities = dict(selected.descriptor.capabilities)
        if live_available:
            capabilities.update(
                {
                    "live_timing": True,
                    "positions": live_mode == "timing_estimate",
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
                (
                    live_position_mode(retained_state)
                    if source.target_session_key == selected.descriptor.key
                    else "unavailable"
                )
                if live_available
                else selected.descriptor.position_mode
            ),
        }

    @app.get("/api/v1/replay")
    async def get_replay_metadata(session_key: str | None = None) -> dict[str, Any]:
        async with resource_lease(session_key, http=True) as selected:
            return metadata_payload(selected)

    def metadata_payload(selected, archived=None):
        start_time = selected.descriptor.date_start
        end_time = _effective_end_time(selected, clock())
        duration = (
            (parse_timestamp(end_time) - parse_timestamp(start_time)).total_seconds()
            if start_time and end_time
            else 0
        )
        source = archived[1] if archived else live.view(selected.descriptor.key)
        live_available = bool(archived) or live_mode_available(selected)
        return {
            "v": 1,
            "sessionKey": selected.descriptor.key,
            "eventCount": len(selected.events) if selected.replay_available else 0,
            "startTime": start_time,
            "endTime": end_time,
            "durationSeconds": duration,
            "available": selected.replay_available,
            "complete": selected.descriptor.complete,
            "recordingVersion": selected.recording_version,
            "replayAvailable": selected.replay_available,
            "liveAvailable": live_available,
            "liveConnected": source.connected,
            "liveStale": source.stale,
            "liveStatus": source.status if live_available else "OFFLINE",
            "livePhase": source.phase if live_available else "UNAVAILABLE",
            "replayReady": selected.replay_available or source.replay_ready,
            "isLive": selected.is_live,
            "positionMode": (
                (
                    live_position_mode(
                        archived[0].final_state if archived else live.state
                    )
                    if source.target_session_key == selected.descriptor.key
                    else "unavailable"
                )
                if live_available
                else selected.descriptor.position_mode
            ),
        }

    @app.get("/api/v1/driver-history")
    async def get_driver_history(
        driver_number: str,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        """Return normalized evidence on demand, never inside RaceState snapshots."""

        async with resource_lease(session_key, http=True) as selected:
            await prepare_replay(selected)
            return await compute(driver_history_payload, selected, driver_number)

    def driver_history_payload(selected, driver_number):
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
        recording_version: str | None = None,
    ) -> dict[str, Any]:
        if seed_task[0] is not None:
            await asyncio.shield(seed_task[0])
        async with resource_lease(session_key, http=True) as selected:
            if (
                recording_version is not None
                and recording_version != selected.recording_version
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Recording changed; refresh state before requesting analytics",
                )
            return await analytics_for_resource(selected, at, seq)

    async def analytics_for_resource(selected, at, seq):
        await prepare_replay(selected)
        controller = selected.controller(
            end_time=_effective_end_time(selected, clock()),
        )
        if at is not None and seq is not None:
            raise HTTPException(status_code=422, detail="use either at or seq")
        try:
            if seq is not None:
                await compute(controller.seek_cursor, seq)
            elif at is not None:
                await compute(controller.seek, at)
            else:
                await compute(controller.seek_cursor, len(selected.events))
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        context = meeting_context(selected, prepare=True)
        result = analytics_service.snapshot(
            selected,
            controller.state,
            sequence=controller.cursor,
            as_of=controller.playhead,
            context=context,
            pirelli=pirelli_context(selected),
        )
        result["recordingVersion"] = selected.recording_version
        return result

    @app.websocket("/api/v1/stream")
    async def stream(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            async with resource_lease(
                websocket.query_params.get("session_key")
            ) as selected:
                await stream_selected(websocket, selected)
        except (KeyError, ReplayBusyError, OSError, ValueError) as error:
            await websocket.send_json({"v": 1, "type": "error", "error": str(error)})
            await websocket.close(code=1008)
            return

    async def stream_selected(websocket: WebSocket, selected: ReplayResource) -> None:
        requested_mode = websocket.query_params.get("mode", "auto")
        wants_live = requested_mode == "live" or (
            requested_mode == "auto" and live_mode_available(selected)
        )
        if wants_live:
            if (
                not live_mode_available(selected)
                and selected.descriptor.key not in completed_live
            ):
                await websocket.send_json(
                    {
                        "v": 1,
                        "type": "error",
                        "error": "Selected session is not available in Live mode",
                    }
                )
                await websocket.close(code=1008)
                return
            try:
                delay_seconds = float(websocket.query_params.get("delay_seconds", 0))
                if not isfinite(delay_seconds) or not 0 <= delay_seconds <= 300:
                    raise ValueError("live delay must be between 0 and 300 seconds")
            except ValueError as error:
                await websocket.send_json(
                    {"v": 1, "type": "error", "error": str(error)}
                )
                await websocket.close(code=1008)
                return
            archived = None
            try:
                while True:
                    archived = completed_live.get(selected.descriptor.key) or archived
                    if not live_mode_available(selected) and archived is None:
                        refreshed = await compute(resource, selected.descriptor.key)
                        if refreshed.replay_available:
                            await compute(refreshed.prepare)
                            archived = (
                                refreshed,
                                live.view(selected.descriptor.key),
                                clock(),
                            )
                    envelope = live_state_envelope(
                        selected, delay_seconds=delay_seconds, archived=archived
                    )
                    envelope.update(
                        metadata=metadata_payload(
                            archived[0] if archived else selected, archived
                        ),
                        capabilities=capability_payload(
                            archived[0] if archived else selected, archived
                        ),
                        playbackReady=True,
                    )
                    if (
                        archived
                        and envelope["live"]["replayReady"]
                        and envelope["seq"] >= len(archived[0].events)
                    ):
                        envelope.update(mode="replay", handoff="REPLAY_READY")
                    await websocket.send_json(envelope)
                    if envelope.get("handoff"):
                        await websocket.close(code=1000)
                        return
                    try:
                        message = await asyncio.wait_for(
                            websocket.receive_json(), timeout=0.5
                        )
                    except TimeoutError:
                        continue
                    message_type = message.get("type")
                    if message_type == "delay":
                        try:
                            requested_delay = float(message.get("seconds", 0))
                        except (ValueError, TypeError):
                            requested_delay = float("nan")
                        if (
                            not isfinite(requested_delay)
                            or not 0 <= requested_delay <= 300
                        ):
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

        controller = selected.controller(
            end_time=_effective_end_time(selected, clock()),
        )
        try:
            resume = websocket.query_params.get("seq")
            resume_version = websocket.query_params.get("recording_version")
            if (
                resume_version is not None
                and resume_version != selected.recording_version
            ):
                resume = None
            if resume is not None:
                await compute(controller.seek_cursor, int(resume))
            else:
                await compute(controller.start)
        except ValueError as error:
            await websocket.send_json({"v": 1, "type": "error", "error": str(error)})
            return

        def current_analytics() -> dict[str, Any] | None:
            if not selected.prepared:
                return None
            return analytics_service.snapshot(
                selected,
                controller.state,
                sequence=controller.cursor,
                as_of=controller.playhead,
                context=meeting_context(selected, prepare=False),
                pirelli=pirelli_context(selected),
            )

        controller_lock = asyncio.Lock()

        async def replay_compute(function, *args, **kwargs):
            if (
                getattr(function, "__self__", None) is controller
                and function.__name__.startswith("seek")
                and not selected.prepared
            ):
                # A seek immediately after opening must join preparation, not
                # race a second full reduction against the same history.
                await prepare_replay(selected)
            async with controller_lock:
                return await compute(function, *args, **kwargs)

        send_lock = asyncio.Lock()
        playback_task: asyncio.Task[None] | None = None
        await _send_snapshot(
            websocket,
            controller,
            send_lock,
            opening={
                "metadata": metadata_payload(selected),
                "capabilities": capability_payload(selected),
                "playbackReady": True,
            },
        )
        await ensure_preparation(selected)
        meeting_context(selected, prepare=True)
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
                        await compute(controller.start)
                    controller.is_playing = True
                    playback_task = asyncio.create_task(
                        _play(
                            websocket,
                            controller,
                            speed,
                            send_lock,
                            current_analytics,
                            replay_compute,
                            controller_lock,
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
                    replay_compute,
                    controller_lock,
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
    if selected.replay_available:
        terminal = _settled_terminal_time(selected)
        end = terminal or (
            selected.events[-1].occurred_at
            if selected.events
            else selected.descriptor.date_end
        )
        return max((selected.descriptor.date_start, end), key=parse_timestamp)
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
        if (
            event.kind == "session"
            and str(event.payload.get("qualifying_phase") or "").upper() == final_phase
        ):
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

    completion = session_completion(
        selected.events, session_kind=selected.descriptor.session_kind
    )
    first_terminal = completion.at
    if first_terminal is None:
        return first_terminal
    if selected.descriptor.session_kind in {"qualifying", "sprint_qualifying"}:
        # Qualifying emits a FINISHED boundary for each phase and may repeat
        # terminal packets after Q3. The replay ends at the first terminal
        # boundary after the final phase actually starts.
        return first_terminal
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
    compute,
    state_lock: asyncio.Lock | None = None,
) -> None:
    naturally_finished = False
    try:
        while controller.is_playing and not controller.finished:
            await asyncio.sleep(0.25)
            await compute(controller.advance, 0.25 * speed)
            await _send_snapshot(
                websocket,
                controller,
                send_lock,
                analytics_supplier=analytics_supplier,
                state_lock=state_lock,
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
                analytics_supplier=analytics_supplier,
                state_lock=state_lock,
            )


async def _stop_playback(
    task: asyncio.Task[None] | None, controller: ReplayController
) -> None:
    if task is not None and not task.done():
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    controller.pause()


async def _handle_message(
    websocket: WebSocket,
    controller: ReplayController,
    message: dict[str, Any],
    send_lock: asyncio.Lock,
    analytics_supplier: Callable[[], dict[str, Any]],
    compute,
    state_lock: asyncio.Lock | None = None,
) -> None:
    message_type = message.get("type")
    try:
        if message_type == "seek":
            if "seq" in message:
                await compute(controller.seek_cursor, int(message["seq"]))
            else:
                await compute(controller.seek, str(message["at"]))
        elif message_type == "seek_relative":
            await compute(controller.seek_relative, float(message["seconds"]))
        elif message_type == "step":
            await compute(controller.step)
        elif message_type == "delay":
            await compute(controller.seek_delay, float(message["seconds"]))
        elif message_type == "reset":
            await compute(controller.start)
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
        analytics_supplier=analytics_supplier,
        state_lock=state_lock,
    )


async def _send_snapshot(
    websocket: WebSocket,
    controller: ReplayController,
    send_lock: asyncio.Lock,
    analytics: dict[str, Any] | None = None,
    opening: dict[str, Any] | None = None,
    *,
    analytics_supplier: Callable[[], dict[str, Any] | None] | None = None,
    state_lock: asyncio.Lock | None = None,
) -> None:
    def capture():
        payload = state_envelope(
            controller.state,
            events=controller.events,
            sequence=controller.cursor,
            session_time=controller.playhead,
            playing=controller.is_playing,
            analytics=analytics_supplier() if analytics_supplier else analytics,
        )
        if opening:
            payload.update(opening)
        return payload

    async with state_lock or asyncio.Lock():
        payload = capture()
    async with send_lock:
        await websocket.send_json(payload)
