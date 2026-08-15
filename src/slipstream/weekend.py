"""Versioned, low-frequency meeting context prepared outside replay assets."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .library import SessionDescriptor

WEEKEND_CONTEXT_FORMAT = "slipstream.weekend-context.v1"
WEEKEND_CONTEXT_SCHEMA_VERSION = 1
WEEKEND_CONTEXT_MODEL_VERSION = "weekend-context-v1"

ContextBuilder = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class ContextAvailability:
    status: str
    context: dict[str, Any] | None = None
    error: str | None = None


class WeekendContextStore:
    """Persist compact per-target-session context beneath the operational data root."""

    def __init__(self, data_root: Path) -> None:
        self.root = data_root / ".slipstream" / "weekend-context"

    def path_for(self, descriptor: SessionDescriptor) -> Path:
        return self.root / descriptor.meeting_key / f"{descriptor.key}.json"

    def load(self, descriptor: SessionDescriptor) -> dict[str, Any] | None:
        path = self.path_for(descriptor)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("format") != WEEKEND_CONTEXT_FORMAT:
            return None
        if payload.get("schema_version") != WEEKEND_CONTEXT_SCHEMA_VERSION:
            return None
        if payload.get("model_version") != WEEKEND_CONTEXT_MODEL_VERSION:
            return None
        if payload.get("evidence_cutoff") != descriptor.date_start:
            return None
        if str(payload.get("meeting_key")) != descriptor.meeting_key:
            return None
        if str(payload.get("target_session_key")) != descriptor.key:
            return None
        sessions = payload.get("sessions")
        if not isinstance(sessions, list) or any(
            not isinstance(session, dict)
            or str(session.get("meeting_key")) != descriptor.meeting_key
            for session in sessions
        ):
            return None
        return payload

    def save(self, descriptor: SessionDescriptor, payload: dict[str, Any]) -> None:
        path = self.path_for(descriptor)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        temporary.replace(path)


class WeekendContextCoordinator:
    """Serialize background context preparation without blocking replay startup."""

    def __init__(self, store: WeekendContextStore, builder: ContextBuilder) -> None:
        self.store = store
        self.builder = builder
        self._results: dict[str, ContextAvailability] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def current(self, descriptor: SessionDescriptor) -> ContextAvailability:
        result = self._results.get(descriptor.key)
        if result is not None:
            return result
        cached = self.store.load(descriptor)
        if cached is not None:
            result = ContextAvailability("ready", cached)
            self._results[descriptor.key] = result
            return result
        return ContextAvailability("missing")

    def ensure(
        self,
        descriptor: SessionDescriptor,
        inventory: tuple[SessionDescriptor, ...],
    ) -> ContextAvailability:
        current = self.current(descriptor)
        if current.status != "missing":
            return current
        self._results[descriptor.key] = ContextAvailability("preparing")
        task = asyncio.create_task(self._prepare(descriptor, inventory))
        self._tasks[descriptor.key] = task
        return self._results[descriptor.key]

    async def _prepare(
        self,
        descriptor: SessionDescriptor,
        inventory: tuple[SessionDescriptor, ...],
    ) -> None:
        try:
            payload = await asyncio.to_thread(
                self.builder,
                meeting_key=descriptor.meeting_key,
                target_session_key=descriptor.key,
                evidence_cutoff=descriptor.date_start,
                meeting_name=descriptor.meeting_name,
                inventory=[item.serialize_now_independent() for item in inventory],
            )
            self.store.save(descriptor, payload)
            self._results[descriptor.key] = ContextAvailability("ready", payload)
        except Exception as error:  # noqa: BLE001 - provider failures must not stop replay
            self._results[descriptor.key] = ContextAvailability(
                "unavailable", error=f"{type(error).__name__}: {error}"
            )
        finally:
            self._tasks.pop(descriptor.key, None)
