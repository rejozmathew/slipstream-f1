"""Discovery and lazy loading for the historical session library."""

from __future__ import annotations

import json
import logging
import re
import sys
import threading
import time
from collections import Counter, OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .adapters.openf1 import is_openf1_recording
from .catalog import CATALOG_FORMAT, read_catalog
from .events import NormalizedEvent, parse_timestamp
from .evidence import SessionEvidence
from .replay import events_from_recording
from .session import classify_session
from .session_completion import session_completion
from .state import RaceState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionDescriptor:
    key: str
    year: int
    meeting_key: str
    meeting_name: str
    session_name: str
    session_type: str
    circuit: str | None
    location: str | None
    date_start: str
    date_end: str
    gmt_offset: str | None
    path: Path | None
    source: str
    capabilities: dict[str, bool]
    circuit_data: dict[str, Any] | None = None
    country: str | None = None
    complete: bool | None = None

    @property
    def session_kind(self) -> str:
        return classify_session(self.session_type, self.session_name).kind.value

    @property
    def layout_family(self) -> str:
        return classify_session(
            self.session_type, self.session_name
        ).layout_family.value

    @property
    def available(self) -> bool:
        return self.path is not None

    @property
    def recording_version(self) -> str | None:
        if self.path is None:
            return None
        try:
            info = self.path.stat()
        except OSError:
            return None
        return f"{self.path.name}:{info.st_mtime_ns}:{info.st_size}"

    @property
    def circuit_shape_available(self) -> bool:
        return bool(
            self.capabilities.get("circuit_shape")
            or (self.circuit_data and self.circuit_data.get("path"))
        )

    @property
    def position_mode(self) -> str:
        if self.capabilities.get("location_xy"):
            return "precise_xy"
        if self.capabilities.get("positions"):
            return "timing_estimate"
        return "unavailable"

    def is_live(self, now: datetime) -> bool:
        try:
            return (
                parse_timestamp(self.date_start) <= now < parse_timestamp(self.date_end)
            )
        except (TypeError, ValueError):
            return False

    def is_downloadable(self, now: datetime) -> bool:
        try:
            return parse_timestamp(self.date_end) <= now
        except (TypeError, ValueError):
            return False

    def serialize(self, now: datetime) -> dict[str, Any]:
        return {
            "sessionKey": self.key,
            "year": self.year,
            "meetingKey": self.meeting_key,
            "meetingName": self.meeting_name,
            "sessionName": self.session_name,
            "sessionType": self.session_type,
            "sessionKind": self.session_kind,
            "layoutFamily": self.layout_family,
            "circuit": self.circuit,
            "location": self.location,
            "dateStart": self.date_start,
            "dateEnd": self.date_end,
            "gmtOffset": self.gmt_offset,
            "available": self.available,
            "recordingVersion": self.recording_version,
            "isLive": self.is_live(now),
            "downloadable": self.is_downloadable(now),
            "circuitShapeAvailable": self.circuit_shape_available,
            "positionMode": self.position_mode,
        }

    def serialize_now_independent(self) -> dict[str, Any]:
        """Stable meeting inventory fields for a persisted context pack."""

        return {
            "session_key": self.key,
            "meeting_key": self.meeting_key,
            "session_name": self.session_name,
            "session_type": self.session_type,
            "session_kind": self.session_kind,
            "layout_family": self.layout_family,
            "date_start": self.date_start,
            "date_end": self.date_end,
        }

    def meeting_inventory(
        self, descriptors: dict[str, SessionDescriptor]
    ) -> tuple[SessionDescriptor, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in descriptors.values()
                    if item.meeting_key == self.meeting_key
                ),
                key=lambda item: item.date_start,
            )
        )


@dataclass(frozen=True, init=False)
class ReplayResource:
    """Reusable canonical data; preparation is coalesced, cursors stay private."""

    descriptor: SessionDescriptor
    events: tuple[NormalizedEvent, ...]
    replay_available: bool

    def __init__(
        self,
        descriptor,
        events,
        final_state=None,
        evidence=None,
        replay_available=False,
        is_live=False,
        *,
        clock=None,
        recording_version=None,
    ):
        for name, value in {
            "descriptor": descriptor,
            "events": tuple(events),
            "replay_available": replay_available,
            "recording_version": recording_version or descriptor.recording_version,
            "_is_live": is_live,
            "_clock": clock,
            "_prepare_lock": threading.Lock(),
            "_prepared": (final_state, evidence)
            if final_state is not None and evidence is not None
            else None,
            "_checkpoints": ((0, RaceState()),),
            "timestamps": tuple(parse_timestamp(e.occurred_at) for e in events),
        }.items():
            object.__setattr__(self, name, value)

    @property
    def is_live(self) -> bool:
        return self.descriptor.is_live(self._clock()) if self._clock else self._is_live

    @property
    def prepared(self) -> bool:
        return self._prepared is not None

    @property
    def checkpoints(self):
        return self._checkpoints

    def prepare(self) -> None:
        with self._prepare_lock:
            if self._prepared is not None:
                return
            checkpoints = [(0, RaceState())]

            def retain(sequence, state):
                if sequence % 512 == 0:
                    checkpoints.append((sequence, state))

            prepared = SessionEvidence.reduce_events(self.events, on_state=retain)
            if not checkpoints or checkpoints[-1][0] != len(self.events):
                checkpoints.append((len(self.events), prepared[0]))
            object.__setattr__(self, "_checkpoints", tuple(checkpoints))
            object.__setattr__(self, "_prepared", prepared)

    @property
    def final_state(self) -> RaceState:
        self.prepare()
        return self._prepared[0]

    @property
    def evidence(self) -> SessionEvidence:
        self.prepare()
        return self._prepared[1]

    def controller(self, *, start_time=None, end_time=None):
        from .playback import ReplayController

        return ReplayController(
            self.events,
            start_time=start_time or self.descriptor.date_start,
            end_time=end_time,
            timestamps=self.timestamps,
            checkpoints=lambda: self.checkpoints,
        )


class ReplayBusyError(RuntimeError):
    """The bounded reusable-resource budget is occupied by active viewers."""


class ReplayLibrary:
    """Merge a preloaded season catalog with recordings loaded on demand."""

    def __init__(
        self,
        source_path: Path,
        *,
        now: Callable[[], datetime] | None = None,
        cache_entries: int = 3,
        cache_bytes: int = 512 * 1024 * 1024,
    ) -> None:
        self._now = now or (lambda: datetime.now(UTC))
        self.source_path = source_path
        self._lock = threading.RLock()
        self._cache_entries = max(1, cache_entries)
        self._cache_bytes = max(1, cache_bytes)
        self._cache: OrderedDict[str, ReplayResource] = OrderedDict()
        self._signatures: dict[str, tuple] = {}
        self._sizes: dict[int, int] = {}
        self._pins: Counter[int] = Counter()
        self._leased: dict[int, ReplayResource] = {}
        self.loads = 0
        self.cache_hits = 0
        candidates = (
            [source_path]
            if source_path.is_file()
            else sorted(source_path.glob("*.json"))
        )
        catalog = (
            read_catalog(source_path / "catalog.json")
            if source_path.is_dir()
            else read_catalog(source_path)
        )
        self._catalog_descriptors = _catalog_descriptors(catalog)
        descriptors = dict(self._catalog_descriptors)
        self._recordings: dict[str, dict[Path, SessionDescriptor]] = {}
        for path in candidates:
            if path.name == "catalog.json":
                continue
            match = re.fullmatch(r"(live|f1-static|openf1)-(\d+)\.json", path.name)
            base = descriptors.get(match[2]) if match else None
            if base is not None:
                # Existing catalog + canonical filename supplies discovery
                # metadata. Parse timing only when somebody opens this session.
                source = {
                    "live": "f1-signalr-public",
                    "f1-static": "f1-static-public",
                    "openf1": "openf1",
                }[match[1]]
                local = replace(
                    base,
                    path=path,
                    source=source,
                    capabilities={**base.capabilities, "historical_replay": True},
                )
            else:
                local = _read_descriptor(path)
            if local is None:
                continue
            self._recordings.setdefault(local.key, {})[path] = local
            preloaded = descriptors.get(local.key)
            if preloaded is not None:
                local = _attach_local_recording(preloaded, local)
            current = descriptors.get(local.key)
            if current is None or _recording_priority(local) > _recording_priority(
                current
            ):
                descriptors[local.key] = local
        if not descriptors and source_path.is_file():
            raise ValueError(f"No supported sessions found at {source_path}")
        self.descriptors = descriptors

    def recoverable_live_key(self) -> str | None:
        """Find a recent unfinished local capture after a process restart.

        This bounded startup inspection never makes old journals live merely
        because their final persisted status happened to be RUNNING. The live
        adapter still verifies the upstream session identity on reconnect.
        """
        from .live_recording import IN_PROGRESS_SUFFIX, NormalizedLiveRecorder

        if not self.source_path.is_dir():
            return None
        now = self._now()
        candidates = []
        for descriptor in tuple(self.descriptors.values()):
            if descriptor.complete is True or not descriptor.key.isdecimal():
                continue
            try:
                end = parse_timestamp(descriptor.date_end)
                start = parse_timestamp(descriptor.date_start)
            except (TypeError, ValueError):
                continue
            if not (start <= end <= now and now - end <= timedelta(hours=6)):
                continue
            journal = self.source_path / f"live-{descriptor.key}{IN_PROGRESS_SUFFIX}"
            final = self.source_path / f"live-{descriptor.key}.json"
            if journal.is_file() or final.is_file():
                candidates.append(descriptor)
        for descriptor in sorted(
            candidates, key=lambda item: item.date_start, reverse=True
        )[:3]:
            try:
                events = NormalizedLiveRecorder(self.source_path, descriptor.key).events
                if not events:
                    continue
                ordered = sorted(
                    events, key=lambda event: parse_timestamp(event.occurred_at)
                )
                last = parse_timestamp(ordered[-1].occurred_at)
                if not timedelta(0) <= now - last <= timedelta(hours=2):
                    continue
                identity = {}
                for event in ordered:
                    if event.kind == "session":
                        identity.update(event.payload)
                if (
                    str(identity.get("key")) != descriptor.key
                    or identity.get("status")
                    not in {"RUNNING", "SUSPENDED", "FINISHED"}
                    or session_completion(
                        ordered, session_kind=descriptor.session_kind
                    ).complete
                ):
                    continue
                return descriptor.key
            except (OSError, RuntimeError, TypeError, ValueError, KeyError):
                logger.warning(
                    "Skipping invalid live recovery candidate session=%s",
                    descriptor.key,
                )
        return None

    @property
    def default_key(self) -> str | None:
        now = self._now()
        live = [item for item in self.descriptors.values() if item.is_live(now)]
        if live:
            return max(live, key=lambda item: item.date_start).key
        available = [item for item in self.descriptors.values() if item.available]
        candidates = available or list(self.descriptors.values())
        return (
            max(candidates, key=lambda item: parse_timestamp(item.date_start)).key
            if candidates
            else None
        )

    def get(self, key: str | None = None) -> ReplayResource:
        with self._lock:
            return self._get(key)

    def _get(self, key: str | None = None) -> ReplayResource:
        selected_key = key or self.default_key
        descriptor = self.descriptors.get(selected_key)
        if descriptor is None:
            raise KeyError(f"Unknown replay session: {selected_key}")
        cached = self._cache.get(selected_key)
        signature = _file_signature(descriptor.path)
        if cached is not None and self._signatures.get(selected_key) == signature:
            self.cache_hits += 1
            self._cache.move_to_end(selected_key)
            return cached
        started = time.perf_counter()
        if descriptor.path is not None:
            # Refresh capability and completeness truth for the one opened file.
            raw, signature = self.refresh_session(
                selected_key, descriptor.path, with_signature=True
            )
            descriptor = self.descriptors[selected_key]
            events = _with_preloaded_circuit(
                tuple(events_from_recording(raw)), descriptor
            )
            if descriptor.complete is None:
                descriptor = replace(
                    descriptor,
                    complete=session_completion(
                        events, session_kind=descriptor.session_kind
                    ).complete,
                )
                self.descriptors[selected_key] = descriptor
        else:
            events = _preview_events(
                descriptor, live=descriptor.is_live(self._now()), now=self._now()
            )
        resource = ReplayResource(
            descriptor=descriptor,
            events=events,
            replay_available=descriptor.available,
            clock=self._now,
            recording_version=(
                f"{descriptor.path.name}:{signature[2]}:{signature[1]}"
                if descriptor.path is not None
                else None
            ),
        )
        # Reserve room for the lazy evidence, timeline and in-memory checkpoints
        # as well as the measured Python event graph. No per-viewer event copies.
        size = _event_memory_size(events) + 24 * 1024 * 1024
        if size > min(self._cache_bytes, 300 * 1024 * 1024):
            raise ReplayBusyError(
                "Selected replay exceeds the per-session memory budget"
            )
        self._cache.pop(selected_key, None)

        def retained():
            return {
                id(item): item
                for item in (*self._cache.values(), *self._leased.values())
            }

        while (
            len(retained()) >= self._cache_entries
            or sum(self._sizes.get(identity, 0) for identity in retained()) + size
            > self._cache_bytes
        ):
            victim = next(
                (k for k, item in self._cache.items() if not self._pins[id(item)]), None
            )
            if victim is None:
                raise ReplayBusyError(
                    "Replay memory budget is in use; close an unused replay and retry"
                )
            evicted = self._cache.pop(victim)
            self._sizes.pop(id(evicted), None)
            self._signatures.pop(victim, None)
        self._sizes[id(resource)] = size
        self._cache[selected_key] = resource
        self._signatures[selected_key] = signature
        self.loads += 1
        logger.info(
            "Replay loaded session=%s events=%d seconds=%.3f reserved_bytes=%d",
            selected_key,
            len(events),
            time.perf_counter() - started,
            size,
        )
        return resource

    def acquire(self, key: str | None = None) -> ReplayResource:
        with self._lock:
            resource = self._get(key)
            identity = id(resource)
            self._pins[identity] += 1
            self._leased[identity] = resource
            return resource

    def release(self, resource: ReplayResource) -> None:
        with self._lock:
            identity = id(resource)
            self._pins[identity] -= 1
            if self._pins[identity] <= 0:
                self._pins.pop(identity, None)
                self._leased.pop(identity, None)
                if all(item is not resource for item in self._cache.values()):
                    self._sizes.pop(identity, None)

    def seed_events(self, key: str) -> tuple[NormalizedEvent, ...]:
        """Metadata-only live seed; the monitor never loads/evicts a replay."""
        descriptor = self.descriptors[key]
        return _preview_events(
            descriptor, live=descriptor.is_live(self._now()), now=self._now()
        )

    def refresh_session(
        self,
        key: str,
        path: Path | None = None,
        *,
        with_signature: bool = False,
        inspect_completion: bool = False,
    ):
        with self._lock:
            paths = set(self._recordings.get(key, {}))
            if path is not None:
                paths.add(path)
            candidates = {}
            contents = {}
            for candidate in paths:
                try:
                    # Publication can replace a file while it is being read.
                    # Bind the loaded events to the version actually read, so a
                    # later replacement cannot masquerade as the cached data.
                    for _attempt in range(2):
                        signature = _file_signature(candidate)
                        content = candidate.read_text(encoding="utf-8")
                        if signature == _file_signature(candidate):
                            break
                    else:
                        raise ReplayBusyError(
                            "Selected replay is being published; retry"
                        )
                    raw = json.loads(content)
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    continue
                local = _read_descriptor(candidate, raw)
                if local is not None and local.key == key:
                    base = self._catalog_descriptors.get(key)
                    candidates[candidate] = (
                        _attach_local_recording(base, local) if base else local
                    )
                    contents[candidate] = (raw, signature)
            self._recordings[key] = candidates
            if candidates:
                self.descriptors[key] = max(
                    candidates.values(), key=_recording_priority
                )
            elif key in self._catalog_descriptors:
                self.descriptors[key] = self._catalog_descriptors[key]
            else:
                self.descriptors.pop(key, None)
            old = self._cache.pop(key, None)
            self._signatures.pop(key, None)
            if old is not None and not self._pins[id(old)]:
                self._sizes.pop(id(old), None)
            selected = self.descriptors.get(key)
            loaded = contents.get(selected.path) if selected else None
            if inspect_completion and loaded and selected.complete is None:
                self.descriptors[key] = replace(
                    selected,
                    complete=session_completion(
                        events_from_recording(loaded[0]),
                        session_kind=selected.session_kind,
                    ).complete,
                )
            if with_signature:
                return loaded or (None, (None,))
            return loaded[0] if loaded else None

    def refresh_catalog(self) -> None:
        """Publish only the changed inventory, retaining unchanged resources."""
        catalog = _catalog_descriptors(read_catalog(self.source_path / "catalog.json"))
        with self._lock:
            self._catalog_descriptors = catalog
            for key, base in catalog.items():
                current = self.descriptors.get(key)
                self.descriptors[key] = (
                    _attach_local_recording(base, current)
                    if current and current.available
                    else base
                )

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "loads": self.loads,
            "hits": self.cache_hits,
            "entries": len(self._cache),
            "reservedBytes": sum(self._sizes.values()),
            "budgetBytes": self._cache_bytes,
        }

    def catalog(self) -> dict[str, Any]:
        now = self._now()
        sessions = sorted(
            self.descriptors.values(), key=lambda item: (item.year, item.date_start)
        )
        return {
            "v": 1,
            "defaultSessionKey": self.default_key,
            "sessions": [session.serialize(now) for session in sessions],
        }


def _attach_local_recording(
    catalog: SessionDescriptor, local: SessionDescriptor
) -> SessionDescriptor:
    capability_names = set(catalog.capabilities) | set(local.capabilities)
    capabilities = {
        name: bool(catalog.capabilities.get(name) or local.capabilities.get(name))
        for name in capability_names
    }
    capabilities["historical_replay"] = True
    return replace(
        catalog,
        path=local.path,
        source=local.source,
        capabilities=capabilities,
        circuit_data=local.circuit_data or catalog.circuit_data,
        complete=local.complete,
    )


def _recording_priority(descriptor: SessionDescriptor) -> int:
    """Choose one whole-session timing source explicitly, never by filename order."""

    if not descriptor.available:
        return 0
    if descriptor.complete is False:
        return {"f1-signalr-public": 3, "f1-static-public": 2, "openf1": 1}.get(
            descriptor.source, 1
        )
    return {
        "f1-signalr-public": 30,
        "f1-static-public": 20,
        "openf1": 10,
    }.get(descriptor.source, 1)


def _catalog_descriptors(raw: dict[str, Any]) -> dict[str, SessionDescriptor]:
    if raw.get("format") != CATALOG_FORMAT:
        return {}
    meetings = raw.get("meetings") if isinstance(raw.get("meetings"), dict) else {}
    descriptors: dict[str, SessionDescriptor] = {}
    for session in raw.get("sessions", []):
        if not isinstance(session, dict) or session.get("session_key") is None:
            continue
        meeting_key = str(session.get("meeting_key") or session["session_key"])
        meeting = meetings.get(meeting_key, {})
        date_start = str(session.get("date_start") or "")
        date_end = str(session.get("date_end") or date_start)
        circuit_data = meeting.get("circuit") if isinstance(meeting, dict) else None
        key = str(session["session_key"])
        descriptors[key] = SessionDescriptor(
            key=key,
            year=int(session.get("year") or date_start[:4]),
            meeting_key=meeting_key,
            meeting_name=str(
                meeting.get("meeting_name")
                or session.get("location")
                or "Unknown weekend"
            ),
            session_name=str(session.get("session_name") or "Session"),
            session_type=str(session.get("session_type") or "Session"),
            circuit=session.get("circuit_short_name")
            or meeting.get("circuit_short_name"),
            location=session.get("location") or meeting.get("location"),
            date_start=date_start,
            date_end=date_end,
            gmt_offset=session.get("gmt_offset"),
            path=None,
            source=str(raw.get("source") or "openf1"),
            capabilities={
                "historical_replay": False,
                "live_timing": False,
                "positions": False,
                "intervals": False,
                "location_xy": False,
                "circuit_shape": bool(circuit_data and circuit_data.get("path")),
                "race_control": False,
                "weather": False,
                "local_time": bool(session.get("gmt_offset")),
                "authenticated": False,
            },
            circuit_data=circuit_data if isinstance(circuit_data, dict) else None,
            country=session.get("country_name") or meeting.get("country_name"),
        )
    return descriptors


def _preview_events(
    descriptor: SessionDescriptor, *, live: bool, now: datetime
) -> tuple[NormalizedEvent, ...]:
    try:
        future = parse_timestamp(descriptor.date_start) > now
    except ValueError:
        future = False
    # Scheduled-window activity belongs to the catalog/live lifecycle. It is
    # not evidence that the sporting session has actually started.
    status = "SCHEDULED" if future else "UNKNOWN"
    events = [
        NormalizedEvent(
            kind="session",
            occurred_at=descriptor.date_start,
            source=descriptor.source,
            payload={
                "key": descriptor.key,
                "name": descriptor.session_name,
                "meeting_name": descriptor.meeting_name,
                "session_type": descriptor.session_type,
                "session_kind": descriptor.session_kind,
                "layout_family": descriptor.layout_family,
                "circuit": descriptor.circuit,
                "location": descriptor.location,
                "started_at": descriptor.date_start,
                "ended_at": descriptor.date_end,
                "gmt_offset": descriptor.gmt_offset,
                "status": status,
            },
        )
    ]
    if descriptor.circuit_data:
        events.append(
            NormalizedEvent(
                kind="circuit",
                occurred_at=descriptor.date_start,
                source=descriptor.source,
                payload=descriptor.circuit_data,
            )
        )
    else:
        events.append(
            NormalizedEvent(
                kind="circuit",
                occurred_at=descriptor.date_start,
                source=descriptor.source,
                payload={"availability": {"path": "unavailable"}},
            )
        )
    if live:
        # Advance presentation-local time without claiming the sporting session
        # has started. Schedule activity remains descriptor truth only.
        events.append(
            NormalizedEvent(
                kind="session",
                occurred_at=now.isoformat().replace("+00:00", "Z"),
                source=descriptor.source,
                payload={},
            )
        )
    return tuple(events)


def _with_preloaded_circuit(
    events: tuple[NormalizedEvent, ...], descriptor: SessionDescriptor
) -> tuple[NormalizedEvent, ...]:
    """Supply cached static geometry when an older recording did not embed it."""
    has_path = any(
        event.kind == "circuit"
        and isinstance(event.payload.get("path"), (list, tuple))
        and len(event.payload["path"]) >= 3
        for event in events
    )
    if has_path or not descriptor.circuit_data:
        return events
    replacement = NormalizedEvent(
        kind="circuit",
        occurred_at=descriptor.date_start,
        source=descriptor.source,
        payload=descriptor.circuit_data,
    )
    without_empty_circuit = tuple(event for event in events if event.kind != "circuit")
    return tuple(
        sorted(
            (*without_empty_circuit, replacement),
            key=lambda event: parse_timestamp(event.occurred_at),
        )
    )


def _read_descriptor(path: Path, raw=None) -> SessionDescriptor | None:
    if raw is None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
    if isinstance(raw, dict) and raw.get("format") == CATALOG_FORMAT:
        return None
    if is_openf1_recording(raw):
        endpoints = raw.get("endpoints", {})
        sessions = endpoints.get("sessions", [])
        if not sessions:
            return None
        session = sessions[0]
        meetings = endpoints.get("meetings", [])
        meeting = meetings[0] if meetings else {}
        date_start = str(session.get("date_start") or raw.get("captured_at") or "")
        date_end = str(session.get("date_end") or date_start)
        key = str(session.get("session_key") or raw.get("session_key") or path.stem)
        capabilities = dict(raw.get("source_capabilities") or {})
        capabilities.setdefault(
            "sector_timing",
            any(
                lap.get("duration_sector_1") is not None
                or lap.get("duration_sector_2") is not None
                or lap.get("duration_sector_3") is not None
                for lap in endpoints.get("laps", [])
            ),
        )
        return SessionDescriptor(
            key=key,
            year=int(session.get("year") or date_start[:4]),
            meeting_key=str(
                session.get("meeting_key") or meeting.get("meeting_key") or key
            ),
            meeting_name=str(
                meeting.get("meeting_name")
                or session.get("location")
                or "Unknown weekend"
            ),
            session_name=str(session.get("session_name") or "Session"),
            session_type=str(session.get("session_type") or "Session"),
            circuit=session.get("circuit_short_name"),
            location=session.get("location"),
            date_start=date_start,
            date_end=date_end,
            gmt_offset=session.get("gmt_offset"),
            path=path,
            source=str(raw.get("source") or "openf1"),
            capabilities=capabilities,
            country=session.get("country_name") or meeting.get("country_name"),
        )
    if isinstance(raw, list):
        try:
            # Discovery reads identity and coverage, never reconstructs timing.
            events = sorted(
                (
                    NormalizedEvent.from_mapping(item)
                    for item in raw
                    if item.get("kind") in {"session", "circuit"}
                ),
                key=lambda event: parse_timestamp(event.occurred_at),
            )
            identity = {}
            circuit_data = None
            for event in events:
                if event.kind == "session":
                    identity.update(event.payload)
                elif event.kind == "circuit" and event.payload.get("path"):
                    circuit_data = event.payload
        except (KeyError, TypeError, ValueError):
            return None
        if not raw or not events:
            return None
        date_start = identity.get("started_at") or min(
            (item["occurred_at"] for item in raw), key=parse_timestamp
        )
        date_end = identity.get("ended_at") or max(
            (item["occurred_at"] for item in raw), key=parse_timestamp
        )
        key = identity.get("key") or path.stem
        capabilities = _normalized_recording_capabilities(raw, identity, circuit_data)
        kind = classify_session(
            identity.get("session_type"), identity.get("name")
        ).kind.value
        return SessionDescriptor(
            key=key,
            year=int(date_start[:4]),
            meeting_key=key,
            meeting_name=identity.get("meeting_name") or "Replay",
            session_name=identity.get("name") or "Session",
            session_type=identity.get("session_type")
            or identity.get("name")
            or "Session",
            circuit=identity.get("circuit"),
            location=identity.get("location"),
            date_start=date_start,
            date_end=date_end,
            gmt_offset=identity.get("gmt_offset"),
            path=path,
            source=events[0].source,
            capabilities=capabilities,
            circuit_data=circuit_data,
            complete=session_completion(events, session_kind=kind).complete,
        )
    return None


def _normalized_recording_capabilities(
    events: list[dict], identity: dict, circuit_data: dict | None
) -> dict[str, bool]:
    timing = [event["payload"] for event in events if event["kind"] == "timing"]
    return {
        "historical_replay": True,
        "live_timing": events[0]["source"] == "f1-signalr-public",
        "positions": any(item.get("track_position") is not None for item in timing),
        "intervals": any(
            item.get("interval") is not None or item.get("gap_to_leader") is not None
            for item in timing
        ),
        "sector_timing": events[0]["source"] == "f1-signalr-public"
        or any(
            item.get("sector_1") is not None
            or item.get("sector_2") is not None
            or item.get("sector_3") is not None
            for item in timing
        ),
        "location_xy": any(
            item.get("x") is not None and item.get("y") is not None for item in timing
        ),
        "circuit_shape": bool(circuit_data and circuit_data.get("path")),
        "race_control": any(event["kind"] == "race_control" for event in events),
        "weather": any(event["kind"] == "weather" for event in events),
        "local_time": bool(identity.get("gmt_offset")),
        "authenticated": False,
    }


def _file_signature(path: Path | None) -> tuple:
    if path is None:
        return (None,)
    stat = path.stat()
    return (str(path), stat.st_size, stat.st_mtime_ns)


def _event_memory_size(events) -> int:
    """Conservatively reserve the acyclic canonical event graph.

    Shared values are intentionally over-counted; only the small vocabulary of
    dictionary keys is deduplicated. Retaining millions of scalar object IDs
    previously dominated cold opening. JSON payloads cannot cycle.
    """
    keys = set()

    def key_size(key):
        identity = id(key)
        if identity in keys:
            return 0
        # A malformed/extreme vocabulary still has bounded accounting overhead.
        if len(keys) < 8192:
            keys.add(identity)
        return sys.getsizeof(key)

    def size(value):
        total = sys.getsizeof(value)
        if isinstance(value, dict):
            total += sum(key_size(k) + size(v) for k, v in value.items())
        elif isinstance(value, (tuple, list)):
            total += sum(size(item) for item in value)
        elif isinstance(value, NormalizedEvent):
            # The fixed event record has no nested structure beyond its payload.
            total += sys.getsizeof(vars(value))
            total += sum(key_size(k) for k in vars(value))
            total += sys.getsizeof(value.kind) + sys.getsizeof(value.source)
            total += sys.getsizeof(value.occurred_at) + sys.getsizeof(value.received_at)
            total += size(value.payload)
        return total

    return size(events)
