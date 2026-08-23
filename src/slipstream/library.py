"""Discovery and lazy loading for the historical session library."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .adapters.openf1 import is_openf1_recording
from .catalog import CATALOG_FORMAT, read_catalog
from .events import NormalizedEvent, parse_timestamp
from .evidence import SessionEvidence
from .replay import load_events, replay
from .session import classify_session
from .state import RaceState


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

    @property
    def session_kind(self) -> str:
        return classify_session(self.session_type, self.session_name).kind.value

    @property
    def layout_family(self) -> str:
        return classify_session(self.session_type, self.session_name).layout_family.value

    @property
    def available(self) -> bool:
        return self.path is not None

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


@dataclass(frozen=True)
class ReplayResource:
    descriptor: SessionDescriptor
    events: tuple[NormalizedEvent, ...]
    final_state: RaceState
    evidence: SessionEvidence
    replay_available: bool
    is_live: bool


class ReplayLibrary:
    """Merge a preloaded season catalog with recordings loaded on demand."""

    def __init__(
        self,
        source_path: Path,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._now = now or (lambda: datetime.now(UTC))
        candidates = (
            [source_path]
            if source_path.is_file()
            else sorted(source_path.rglob("*.json"))
        )
        descriptors: dict[str, SessionDescriptor] = {}
        if source_path.is_dir():
            for path in candidates:
                catalog = read_catalog(path)
                if catalog:
                    descriptors.update(_catalog_descriptors(catalog))
        for path in candidates:
            local = _read_descriptor(path)
            if local is None:
                continue
            preloaded = descriptors.get(local.key)
            if preloaded is not None:
                local = _attach_local_recording(preloaded, local)
            descriptors[local.key] = local
        if not descriptors:
            raise ValueError(f"No supported sessions found at {source_path}")
        self.descriptors = descriptors
        self._cache: dict[str, ReplayResource] = {}

    @property
    def default_key(self) -> str:
        now = self._now()
        live = [item for item in self.descriptors.values() if item.is_live(now)]
        if live:
            return max(live, key=lambda item: item.date_start).key
        available = [item for item in self.descriptors.values() if item.available]
        candidates = available or list(self.descriptors.values())
        return max(candidates, key=lambda item: item.date_start).key

    def get(self, key: str | None = None) -> ReplayResource:
        selected_key = key or self.default_key
        descriptor = self.descriptors.get(selected_key)
        if descriptor is None:
            raise KeyError(f"Unknown replay session: {selected_key}")
        cached = self._cache.get(selected_key)
        live = descriptor.is_live(self._now())
        if cached is not None and cached.is_live == live:
            return cached
        if descriptor.path is not None:
            events = _with_preloaded_circuit(
                tuple(load_events(descriptor.path)), descriptor
            )
        else:
            events = _preview_events(descriptor, live=live, now=self._now())
        resource = ReplayResource(
            descriptor=descriptor,
            events=events,
            final_state=replay(list(events)),
            evidence=SessionEvidence.from_events(events),
            replay_available=descriptor.available,
            is_live=live,
        )
        self._cache = {selected_key: resource}
        return resource

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
    )


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
        )
    return descriptors


def _preview_events(
    descriptor: SessionDescriptor, *, live: bool, now: datetime
) -> tuple[NormalizedEvent, ...]:
    try:
        future = parse_timestamp(descriptor.date_start) > now
    except ValueError:
        future = False
    status = "LIVE" if live else "SCHEDULED" if future else "NOT_DOWNLOADED"
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
        events.append(
            NormalizedEvent(
                kind="session",
                occurred_at=now.isoformat().replace("+00:00", "Z"),
                source=descriptor.source,
                payload={"status": "LIVE"},
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


def _read_descriptor(path: Path) -> SessionDescriptor | None:
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
            capabilities=dict(raw.get("source_capabilities") or {}),
        )
    if isinstance(raw, list):
        try:
            events = [NormalizedEvent.from_mapping(item) for item in raw]
            state = replay(events)
        except (KeyError, TypeError, ValueError):
            return None
        if not events:
            return None
        date_start = state.session.started_at or events[0].occurred_at
        date_end = state.session.ended_at or events[-1].occurred_at
        key = state.session.key or path.stem
        return SessionDescriptor(
            key=key,
            year=int(date_start[:4]),
            meeting_key=key,
            meeting_name=state.session.meeting_name or "Replay",
            session_name=state.session.name or "Session",
            session_type=state.session.session_type or state.session.name or "Session",
            circuit=state.session.circuit,
            location=state.session.location,
            date_start=date_start,
            date_end=date_end,
            gmt_offset=state.session.gmt_offset,
            path=path,
            source=events[0].source,
            capabilities=_normalized_recording_capabilities(events, state),
        )
    return None


def _normalized_recording_capabilities(
    events: list[NormalizedEvent], state: RaceState
) -> dict[str, bool]:
    timing = [event.payload for event in events if event.kind == "timing"]
    return {
        "historical_replay": True,
        "live_timing": events[0].source == "f1-signalr-public",
        "positions": any(item.get("track_position") is not None for item in timing),
        "intervals": any(
            item.get("interval") is not None or item.get("gap_to_leader") is not None
            for item in timing
        ),
        "location_xy": any(
            item.get("x") is not None and item.get("y") is not None for item in timing
        ),
        "circuit_shape": bool(state.circuit.path),
        "race_control": any(event.kind == "race_control" for event in events),
        "weather": any(event.kind == "weather" for event in events),
        "local_time": bool(state.session.gmt_offset),
        "authenticated": False,
    }
