"""Public Formula 1 live transport and canonical event normalization.

The adapter produces source-neutral canonical events and normalized recordings.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import aiohttp

from .events import NormalizedEvent, parse_timestamp
from .evidence import SessionEvidence
from .f1_timing import (
    finalize_f1_classifications,
    merge_f1_provider_value,
    normalize_f1_timing,
)
from .live_recording import NormalizedLiveRecorder
from .session import classify_session
from .state import RaceState

RECORD_SEPARATOR = "\x1e"
RECORDING_FORMAT = "slipstream.f1-signalr-recording.v1"
NEGOTIATE_URL = "https://livetiming.formula1.com/signalrcore/negotiate"
CONNECT_URL = "wss://livetiming.formula1.com/signalrcore"

# Streams observed to remain public in 2026. CarData.z, Position.z, team
# radio, and other enhanced feeds are intentionally absent because they now
# require authentication.
PUBLIC_TOPICS = (
    "DriverList",
    "ExtrapolatedClock",
    "Heartbeat",
    "LapCount",
    "RaceControlMessages",
    "SessionData",
    "SessionInfo",
    "SessionStatus",
    "TimingAppData",
    "TimingData",
    "TopThree",
    "TrackStatus",
    "WeatherData",
)

CAPABILITIES = {
    "historical_replay": False,
    "live_timing": True,
    "positions": False,
    "intervals": True,
    "sector_timing": True,
    "location_xy": False,
    "circuit_shape": False,
    "race_control": True,
    "weather": True,
    "local_time": True,
    "authenticated": False,
}


class LiveSourceError(RuntimeError):
    """Raised when the public live transport cannot produce a recording."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def canonical_utc(value: str) -> str:
    """Render a provider UTC timestamp in canonical offset-aware form."""
    return parse_timestamp(value).isoformat().replace("+00:00", "Z")


def recording_header(*, captured_at: str | None = None) -> dict[str, Any]:
    """Return the first JSONL record for a public live capture."""
    return {
        "format": RECORDING_FORMAT,
        "schema_version": 1,
        "source": "f1-signalr-public",
        "captured_at": captured_at or utc_now(),
        "source_capabilities": CAPABILITIES,
        "topics": list(PUBLIC_TOPICS),
    }


def decode_signalr_text(
    text: str, *, received_at: str
) -> tuple[list[dict[str, Any]], bool]:
    """Decode SignalR Core JSON records into stable raw recording rows.

    Returns ``(rows, ping_received)``. Invocation results are initial
    snapshots; ``feed`` invocations are incremental provider messages.
    """
    rows: list[dict[str, Any]] = []
    ping_received = False
    for segment in text.split(RECORD_SEPARATOR):
        if not segment.strip():
            continue
        try:
            message = json.loads(segment)
        except json.JSONDecodeError as error:
            raise LiveSourceError("SignalR returned invalid JSON") from error
        if not isinstance(message, dict):
            continue
        message_type = message.get("type")
        if message_type == 1 and str(message.get("target", "")).lower() == "feed":
            arguments = message.get("arguments")
            if not isinstance(arguments, list) or len(arguments) < 2:
                continue
            stream = arguments[0]
            if not isinstance(stream, str):
                continue
            rows.append(
                {
                    "received_at": received_at,
                    "stream": stream,
                    "source_timestamp": (
                        arguments[2]
                        if len(arguments) > 2 and isinstance(arguments[2], str)
                        else None
                    ),
                    "payload": arguments[1],
                    "initial": False,
                }
            )
        elif message_type == 3:
            result = message.get("result")
            if isinstance(result, dict):
                rows.extend(
                    {
                        "received_at": received_at,
                        "stream": stream,
                        "source_timestamp": None,
                        "payload": payload,
                        "initial": True,
                    }
                    for stream, payload in result.items()
                )
        elif message_type == 6:
            ping_received = True
        elif message_type == 7:
            detail = message.get("error") or "no reason supplied"
            raise LiveSourceError(f"SignalR closed the connection: {detail}")
    return rows, ping_received


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    """Write a complete live recording. Primarily useful for test fixtures."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as output:
        for row in rows:
            output.write(json.dumps(row, separators=(",", ":")) + "\n")


class PublicLiveRecorder:
    """Record the public F1 live feed through one upstream connection."""

    def __init__(
        self,
        *,
        negotiate_url: str = NEGOTIATE_URL,
        connect_url: str = CONNECT_URL,
        topics: tuple[str, ...] = PUBLIC_TOPICS,
    ) -> None:
        self.negotiate_url = negotiate_url
        self.connect_url = connect_url
        self.topics = topics
        self._running = False

    async def record(
        self,
        path: Path,
        *,
        idle_timeout: float = 90.0,
        duration: float | None = None,
    ) -> int:
        """Connect, write a versioned JSONL recording, and return row count."""
        if self._running:
            raise LiveSourceError("This recorder already owns an upstream connection")
        if idle_timeout <= 0:
            raise ValueError("idle_timeout must be greater than zero")
        if duration is not None and duration <= 0:
            raise ValueError("duration must be greater than zero")

        self._running = True
        websocket: aiohttp.ClientWebSocketResponse | None = None
        session: aiohttp.ClientSession | None = None
        count = 0
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"User-Agent": "slipstream-f1/0.1"},
            )
            token = await self._negotiate(session)
            connect_query = urlencode({"id": token})
            websocket = await session.ws_connect(
                f"{self.connect_url}?{connect_query}", heartbeat=20
            )
            await websocket.send_str(
                json.dumps({"protocol": "json", "version": 1}) + RECORD_SEPARATOR
            )
            handshake = await asyncio.wait_for(websocket.receive(), idle_timeout)
            self._validate_handshake(handshake)
            await websocket.send_str(
                json.dumps(
                    {
                        "type": 1,
                        "target": "Subscribe",
                        "arguments": [list(self.topics)],
                        "invocationId": "0",
                    }
                )
                + RECORD_SEPARATOR
            )
            started = asyncio.get_running_loop().time()

            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8", newline="\n") as output:
                output.write(
                    json.dumps(recording_header(), separators=(",", ":")) + "\n"
                )
                output.flush()
                while (
                    duration is None
                    or asyncio.get_running_loop().time() - started < duration
                ):
                    remaining = idle_timeout
                    if duration is not None:
                        remaining = min(
                            remaining,
                            max(
                                0.01,
                                duration
                                - (asyncio.get_running_loop().time() - started),
                            ),
                        )
                    try:
                        message = await asyncio.wait_for(websocket.receive(), remaining)
                    except TimeoutError as error:
                        if (
                            duration is not None
                            and asyncio.get_running_loop().time() - started >= duration
                        ):
                            break
                        raise LiveSourceError(
                            f"No live data received for {idle_timeout:g} seconds"
                        ) from error
                    if message.type == aiohttp.WSMsgType.TEXT:
                        rows, ping = decode_signalr_text(
                            message.data, received_at=utc_now()
                        )
                        if ping:
                            await websocket.send_str(
                                json.dumps({"type": 6}) + RECORD_SEPARATOR
                            )
                        for row in rows:
                            output.write(json.dumps(row, separators=(",", ":")) + "\n")
                            count += 1
                        if rows:
                            output.flush()
                    elif message.type in {
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    }:
                        raise LiveSourceError("The live connection closed unexpectedly")
            return count
        finally:
            if websocket is not None:
                await websocket.close()
            if session is not None:
                await session.close()
            self._running = False

    async def _negotiate(self, session: aiohttp.ClientSession) -> str:
        params = {"negotiateVersion": "1"}
        # The current public endpoint returns 405 to OPTIONS while accepting the
        # actual POST negotiation. Browsers may preflight; this server-owned
        # client does not need to invent a provider requirement for OPTIONS.
        async with session.post(self.negotiate_url, params=params) as response:
            if response.status >= 400:
                raise LiveSourceError(
                    f"Live negotiation failed with HTTP {response.status}"
                )
            payload = await response.json()
        token = payload.get("connectionToken") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise LiveSourceError("Live negotiation returned no connection token")
        return token

    @staticmethod
    def _validate_handshake(message: aiohttp.WSMessage) -> None:
        if message.type != aiohttp.WSMsgType.TEXT:
            raise LiveSourceError("SignalR closed before completing its handshake")
        for segment in message.data.split(RECORD_SEPARATOR):
            if not segment.strip():
                continue
            try:
                payload = json.loads(segment)
            except json.JSONDecodeError as error:
                raise LiveSourceError(
                    "SignalR returned an invalid handshake"
                ) from error
            if isinstance(payload, dict) and payload.get("error"):
                raise LiveSourceError(f"SignalR handshake failed: {payload['error']}")


LIVE_CONNECTION_STATES = ("OFFLINE", "CONNECTING", "LIVE", "STALE", "UNAVAILABLE")
LIVE_PRODUCT_PHASES = (
    "PRE_EVENT",
    "CONNECTING",
    "LIVE",
    "STALE",
    "RECONNECTING",
    "FINALIZING",
    "COMPLETE",
    "REPLAY_READY",
    "UNAVAILABLE",
)


class LiveSessionMismatch(LiveSourceError):
    """Raised when the public feed does not match the selected live session."""


def _merge_provider_value(current: Any, patch: Any) -> Any:
    """Merge SignalR sparse updates without leaking them outside the adapter."""

    return merge_f1_provider_value(current, patch)


def _number(value: Any, *, integer: bool = False) -> float | int | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return int(parsed) if integer else parsed


def _duration_seconds(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parts = [float(part) for part in str(value).split(":")]
    except ValueError:
        return None
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return parts[0] if len(parts) == 1 else None


def _value(value: Any) -> Any:
    return value.get("Value") if isinstance(value, dict) else value


def _truthy(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes"}


def _ordered_values(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [
            item
            for _, item in sorted(
                value.items(),
                key=lambda pair: int(pair[0]) if str(pair[0]).isdigit() else 999,
            )
        ]
    return []


def _session_status(payload: dict[str, Any]) -> str:
    status = str(payload.get("Status") or payload.get("SessionStatus") or "").upper()
    started = str(payload.get("Started") or "").upper()
    if status:
        if status in {"ENDS", "FINISHED", "FINALISED", "FINALIZED"}:
            return "FINISHED"
        if status in {"ABORTED", "SUSPENDED"}:
            return "SUSPENDED"
        if status in {"STARTED", "RUNNING", "RESUMED"}:
            return "RUNNING"
        if status in {"INACTIVE", "NOT STARTED"}:
            return "SCHEDULED"
        return "UNKNOWN"
    if started == "FINISHED":
        return "FINISHED"
    if started in {"STARTED", "RUNNING"}:
        return "RUNNING"
    return "UNKNOWN"


def _track_status_updates(payload: dict[str, Any]) -> dict[str, str]:
    message = str(payload.get("Message") or "").upper()
    if "DOUBLE YELLOW" in message:
        return {"marshal_status": "YELLOW"}
    if "CHEQUERED" in message:
        return {"control_status": "CHEQUERED"}
    return {
        "1": {"marshal_status": "ALL_CLEAR", "control_status": "NORMAL"},
        "2": {"marshal_status": "YELLOW"},
        "4": {"control_status": "SAFETY_CAR"},
        "5": {"marshal_status": "RED"},
        "6": {"control_status": "VSC"},
        "7": {"control_status": "VSC_ENDING"},
    }.get(str(payload.get("Status") or ""), {})


def _status_series_track_updates(value: object) -> dict[str, str]:
    normalized = str(value or "").upper().replace("_", "")
    if normalized in {"ALLCLEAR", "GREEN"}:
        return {"marshal_status": "ALL_CLEAR", "control_status": "NORMAL"}
    if normalized in {"YELLOW", "DOUBLEYELLOW"}:
        return {"marshal_status": "YELLOW"}
    if normalized == "RED":
        return {"marshal_status": "RED"}
    return {}


def _live_race_control_updates(item: dict[str, Any]) -> dict[str, str]:
    """Return persistent transitions the public source can explicitly exit."""
    if item.get("RacingNumber") is not None:
        return {}
    scope = str(item.get("Scope") or "").upper() or None
    if scope not in {None, "TRACK"}:
        return {}
    category = str(item.get("Category") or "").upper()
    text = " ".join(str(item.get("Message") or "").upper().split())
    flag = str(item.get("Flag") or "").upper()
    if text.startswith("RED FLAG") and (flag == "RED" or "RACE SUSPENDED" in text):
        return {"status": "SUSPENDED", "control_status": "RED_FLAG"}
    if category == "SAFETYCAR" and text == "VIRTUAL SAFETY CAR DEPLOYED":
        return {"control_status": "VSC"}
    if category == "SAFETYCAR" and "VIRTUAL SAFETY CAR ENDING" in text:
        return {"control_status": "VSC_ENDING"}
    if category == "SAFETYCAR" and text == "SAFETY CAR DEPLOYED":
        return {"control_status": "SAFETY_CAR"}
    if flag == "CHEQUERED" or "CHEQUERED FLAG" in text:
        return {"control_status": "CHEQUERED"}
    if scope == "TRACK" and flag in {"GREEN", "CLEAR"}:
        return {"marshal_status": "ALL_CLEAR"}
    if scope == "TRACK" and flag in {"YELLOW", "DOUBLE YELLOW"}:
        return {"marshal_status": "YELLOW"}
    if scope == "TRACK" and flag == "RED":
        return {"marshal_status": "RED"}
    return {}


class F1LiveAdapter:
    """Stateful boundary from observed public SignalR topics to NormalizedEvent."""

    _ORDER = (
        "SessionInfo",
        "SessionStatus",
        "SessionData",
        "ExtrapolatedClock",
        "DriverList",
        "TimingAppData",
        "TimingData",
        "LapCount",
        "TrackStatus",
        "RaceControlMessages",
        "WeatherData",
    )

    def __init__(
        self, target_session_key: str, *, source: str = "f1-signalr-public"
    ) -> None:
        self.target_session_key = str(target_session_key)
        self.source = source
        self.streams: dict[str, Any] = {}
        self.session_verified = False
        self._published_initial = False
        self._seen_race_control: set[str] = set()
        self._seen_status_series: set[str] = set()
        self._qualifying_phase = "UNKNOWN"

    def ingest(self, row: dict[str, Any]) -> tuple[NormalizedEvent, ...]:
        stream = str(row.get("stream") or "")
        if stream not in PUBLIC_TOPICS:
            return ()
        payload = row.get("payload")
        self.streams[stream] = _merge_provider_value(self.streams.get(stream), payload)
        if stream == "SessionInfo":
            key = str(
                self.streams[stream].get("Key")
                if isinstance(self.streams[stream], dict)
                else ""
            )
            if key and key != self.target_session_key:
                raise LiveSessionMismatch(
                    f"public feed session {key} does not match selected live session "
                    f"{self.target_session_key}"
                )
            self.session_verified = key == self.target_session_key
        if not self.session_verified:
            return ()

        received_at = str(row.get("received_at") or utc_now())
        occurred_at = str(row.get("source_timestamp") or received_at)
        if not self._published_initial:
            self._published_initial = True
            events = [
                event
                for name in self._ORDER
                for event in self._events_for(
                    name, self.streams.get(name), occurred_at, self.streams.get(name)
                )
            ]
            return tuple(events)
        return tuple(
            self._events_for(stream, self.streams[stream], occurred_at, payload)
        )

    def _events_for(
        self, stream: str, merged: Any, occurred_at: str, patch: Any
    ) -> list[NormalizedEvent]:
        if not isinstance(merged, dict):
            return []
        if stream == "SessionInfo":
            return self._session_info_events(merged, occurred_at)
        if stream == "SessionStatus":
            status = _session_status(merged)
            return [
                NormalizedEvent(
                    "session",
                    occurred_at,
                    self.source,
                    {"status": status},
                    received_at=occurred_at,
                )
            ]
        if stream == "SessionData":
            return self._session_data_events(merged, occurred_at)
        if stream == "ExtrapolatedClock":
            return self._clock_events(merged, occurred_at)
        if stream == "DriverList":
            return self._driver_events(merged, occurred_at)
        if stream == "TimingData":
            return self._timing_events(merged, patch, occurred_at)
        if stream == "TimingAppData":
            return self._stint_events(merged, occurred_at)
        if stream == "LapCount":
            updates: dict[str, Any] = {}
            current = _number(
                merged.get("CurrentLap") or merged.get("Current"), integer=True
            )
            total = _number(
                merged.get("TotalLaps") or merged.get("Total"), integer=True
            )
            if current is not None:
                updates["lap"] = current
            if total is not None:
                updates["total_laps"] = total
            return (
                [
                    NormalizedEvent(
                        "session",
                        occurred_at,
                        self.source,
                        updates,
                        received_at=occurred_at,
                    )
                ]
                if updates
                else []
            )
        if stream == "TrackStatus":
            updates = _track_status_updates(merged)
            return (
                [
                    NormalizedEvent(
                        "session",
                        occurred_at,
                        self.source,
                        updates,
                        received_at=occurred_at,
                    )
                ]
                if updates
                else []
            )
        if stream == "RaceControlMessages":
            return self._race_control_events(merged, occurred_at)
        if stream == "WeatherData":
            mapping = {
                "AirTemp": ("air_temperature", float),
                "TrackTemp": ("track_temperature", float),
                "Humidity": ("humidity", float),
                "Pressure": ("pressure", float),
                "Rainfall": ("rainfall", _truthy),
                "WindSpeed": ("wind_speed", float),
                "WindDirection": ("wind_direction", int),
            }
            updates: dict[str, Any] = {}
            for provider_key, (canonical_key, converter) in mapping.items():
                if provider_key not in merged:
                    continue
                try:
                    updates[canonical_key] = converter(merged[provider_key])
                except (TypeError, ValueError):
                    continue
            return (
                [
                    NormalizedEvent(
                        "weather",
                        occurred_at,
                        self.source,
                        updates,
                        received_at=occurred_at,
                    )
                ]
                if updates
                else []
            )
        return []

    def _clock_events(
        self, payload: dict[str, Any], occurred_at: str
    ) -> list[NormalizedEvent]:
        remaining = payload.get("Remaining")
        if not isinstance(remaining, str) or remaining.count(":") != 2:
            return []
        return [
            NormalizedEvent(
                "session",
                occurred_at,
                self.source,
                {
                    "session_clock": remaining,
                    "session_clock_running": _truthy(payload.get("Extrapolating")),
                },
                received_at=occurred_at,
            )
        ]

    def _session_data_events(
        self, payload: dict[str, Any], occurred_at: str
    ) -> list[NormalizedEvent]:
        events: list[NormalizedEvent] = []
        for item in _ordered_values(payload.get("StatusSeries")):
            if not isinstance(item, dict) or not item.get("Utc"):
                continue
            updates: dict[str, Any] = {}
            if item.get("SessionStatus") is not None:
                status = _session_status({"Status": item.get("SessionStatus")})
                if status != "UNKNOWN":
                    updates["status"] = status
            if item.get("TrackStatus") is not None:
                updates.update(_status_series_track_updates(item.get("TrackStatus")))
            if updates:
                event_key = json.dumps(
                    [canonical_utc(str(item["Utc"])), updates],
                    sort_keys=True,
                    separators=(",", ":"),
                )
                if event_key in self._seen_status_series:
                    continue
                self._seen_status_series.add(event_key)
                events.append(
                    NormalizedEvent(
                        "session",
                        canonical_utc(str(item["Utc"])),
                        self.source,
                        updates,
                        received_at=occurred_at,
                    )
                )
        candidates: list[dict[str, Any]] = []
        for key in ("Series", "StatusSeries"):
            candidates.extend(
                item
                for item in _ordered_values(payload.get(key))
                if isinstance(item, dict)
            )
        phase: str | None = None
        for item in candidates:
            raw_value = str(
                item.get("Value") or item.get("QualifyingPart") or ""
            ).upper()
            if raw_value in {"Q1", "Q2", "Q3", "SQ1", "SQ2", "SQ3"}:
                phase = raw_value
            elif raw_value in {"1", "2", "3"} and str(
                item.get("Type") or ""
            ).lower() in {"qualifyingpart", "qualifying_part"}:
                session_info = str(self.streams.get("SessionInfo", {})).upper()
                phase = f"{'SQ' if 'SPRINT' in session_info else 'Q'}{raw_value}"
        if phase is not None:
            self._qualifying_phase = phase
            events.append(
                NormalizedEvent(
                    "session",
                    occurred_at,
                    self.source,
                    {"qualifying_phase": phase},
                    received_at=occurred_at,
                )
            )
        return events

    def _session_info_events(
        self, payload: dict[str, Any], occurred_at: str
    ) -> list[NormalizedEvent]:
        meeting = (
            payload.get("Meeting") if isinstance(payload.get("Meeting"), dict) else {}
        )
        circuit = (
            meeting.get("Circuit") if isinstance(meeting.get("Circuit"), dict) else {}
        )
        session_name = payload.get("Name")
        session_type = payload.get("Type")
        classification = classify_session(
            str(session_type or ""), str(session_name or "")
        )
        updates: dict[str, Any] = {"key": self.target_session_key}
        optional = {
            "name": session_name,
            "meeting_name": meeting.get("Name"),
            "session_type": session_type,
            "circuit": circuit.get("ShortName"),
            "location": meeting.get("Location"),
            "started_at": payload.get("StartDate"),
            "ended_at": payload.get("EndDate"),
            "gmt_offset": payload.get("GmtOffset"),
        }
        updates.update(
            {key: value for key, value in optional.items() if value not in {None, ""}}
        )
        if session_name or session_type:
            updates.update(
                session_kind=classification.kind.value,
                layout_family=classification.layout_family.value,
            )
        status = _session_status(payload)
        if status != "UNKNOWN":
            updates["status"] = status
        return [
            NormalizedEvent(
                "session",
                occurred_at,
                self.source,
                updates,
                received_at=occurred_at,
            )
        ]

    def _driver_events(
        self, payload: dict[str, Any], occurred_at: str
    ) -> list[NormalizedEvent]:
        roster_size = sum(
            1
            for raw_number, item in payload.items()
            if raw_number != "_kf" and isinstance(item, dict)
        )
        events: list[NormalizedEvent] = (
            [
                NormalizedEvent(
                    "session",
                    occurred_at,
                    self.source,
                    {"eligible_field_size": roster_size},
                    received_at=occurred_at,
                )
            ]
            if roster_size
            else []
        )
        for raw_number, item in payload.items():
            if raw_number == "_kf" or not isinstance(item, dict):
                continue
            number = str(item.get("RacingNumber") or raw_number)
            events.append(
                NormalizedEvent(
                    "driver",
                    occurred_at,
                    self.source,
                    {
                        "number": number,
                        "code": item.get("Tla"),
                        "name": item.get("FullName"),
                        "team": item.get("TeamName"),
                        "team_colour": item.get("TeamColour"),
                        "status": "UNKNOWN",
                    },
                    received_at=occurred_at,
                )
            )
        return events

    def _timing_events(
        self, merged: dict[str, Any], patch: Any, occurred_at: str
    ) -> list[NormalizedEvent]:
        return normalize_f1_timing(
            merged,
            patch,
            occurred_at,
            source=self.source,
            timing_app_data=self.streams.get("TimingAppData"),
            qualifying_phase=self._qualifying_phase,
        )

    def _stint_events(
        self, payload: dict[str, Any], occurred_at: str
    ) -> list[NormalizedEvent]:
        lines = payload.get("Lines") if isinstance(payload.get("Lines"), dict) else {}
        events: list[NormalizedEvent] = []
        for raw_number, item in lines.items():
            if not isinstance(item, dict):
                continue
            stints = _ordered_values(item.get("Stints"))
            if not stints or not isinstance(stints[-1], dict):
                continue
            stint = stints[-1]
            total_laps = _number(stint.get("TotalLaps"), integer=True)
            new_value = stint.get("New")
            tyre_usage = (
                "NEW"
                if _truthy(new_value)
                else "USED"
                if new_value is not None
                else "UNKNOWN"
            )
            events.append(
                NormalizedEvent(
                    "timing",
                    occurred_at,
                    self.source,
                    {
                        "number": str(item.get("RacingNumber") or raw_number),
                        "compound": stint.get("Compound"),
                        "tyre_age": total_laps,
                        "stint_laps": total_laps,
                        "tyre_usage": tyre_usage,
                    },
                    received_at=occurred_at,
                )
            )
        return events

    def _race_control_events(
        self, payload: dict[str, Any], occurred_at: str
    ) -> list[NormalizedEvent]:
        messages = payload.get("Messages")
        if not isinstance(messages, (dict, list)):
            return []
        items = messages.items() if isinstance(messages, dict) else enumerate(messages)
        events: list[NormalizedEvent] = []
        for index, item in items:
            if not isinstance(item, dict):
                continue
            identity = str(item.get("Utc") or item.get("Timestamp") or index)
            if identity in self._seen_race_control:
                continue
            self._seen_race_control.add(identity)
            message = str(item.get("Message") or "")
            if not message:
                continue
            events.append(
                NormalizedEvent(
                    "race_control",
                    canonical_utc(str(item.get("Utc") or occurred_at)),
                    self.source,
                    {
                        "category": str(item.get("Category") or "Other"),
                        "message": message,
                        "flag": item.get("Flag"),
                        "scope": item.get("Scope"),
                        "driver_number": str(item.get("RacingNumber"))
                        if item.get("RacingNumber") is not None
                        else None,
                        "sector": _number(item.get("Sector"), integer=True),
                        "lap": _number(item.get("Lap"), integer=True),
                    },
                    received_at=occurred_at,
                )
            )
            updates = _live_race_control_updates(item)
            if updates:
                events.append(
                    NormalizedEvent(
                        "session",
                        canonical_utc(str(item.get("Utc") or occurred_at)),
                        self.source,
                        updates,
                        received_at=occurred_at,
                    )
                )
        return events


class PublicSignalRConnection:
    """Yield raw public rows from one SignalR Core connection."""

    def __init__(
        self,
        *,
        negotiate_url: str = NEGOTIATE_URL,
        connect_url: str = CONNECT_URL,
        topics: tuple[str, ...] = PUBLIC_TOPICS,
    ) -> None:
        self.negotiate_url = negotiate_url
        self.connect_url = connect_url
        self.topics = topics

    async def rows(self) -> AsyncIterator[dict[str, Any]]:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(
            timeout=timeout, headers={"User-Agent": "slipstream-f1/0.1"}
        ) as session:
            async with session.post(
                self.negotiate_url, params={"negotiateVersion": "1"}
            ) as response:
                if response.status >= 400:
                    raise LiveSourceError(
                        f"Live negotiation failed with HTTP {response.status}"
                    )
                negotiated = await response.json()
            token = (
                negotiated.get("connectionToken")
                if isinstance(negotiated, dict)
                else None
            )
            if not isinstance(token, str) or not token:
                raise LiveSourceError("Live negotiation returned no connection token")
            async with session.ws_connect(
                f"{self.connect_url}?{urlencode({'id': token})}", heartbeat=20
            ) as websocket:
                await websocket.send_str(
                    json.dumps({"protocol": "json", "version": 1}) + RECORD_SEPARATOR
                )
                handshake = await websocket.receive()
                PublicLiveRecorder._validate_handshake(handshake)
                await websocket.send_str(
                    json.dumps(
                        {
                            "type": 1,
                            "target": "Subscribe",
                            "arguments": [list(self.topics)],
                            "invocationId": "0",
                        }
                    )
                    + RECORD_SEPARATOR
                )
                async for message in websocket:
                    if message.type == aiohttp.WSMsgType.TEXT:
                        rows, ping = decode_signalr_text(
                            message.data, received_at=utc_now()
                        )
                        if ping:
                            await websocket.send_str(
                                json.dumps({"type": 6}) + RECORD_SEPARATOR
                            )
                        for row in rows:
                            yield row
                    elif message.type in {
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    }:
                        raise LiveSourceError(
                            "The public live connection closed unexpectedly"
                        )


@dataclass(frozen=True)
class LiveSourceView:
    target_session_key: str | None
    status: str
    connected: bool
    stale: bool
    sequence: int
    last_received_at: str | None
    error: str | None
    phase: str
    replay_ready: bool
    final_recording: str | None


class PublicLiveSession:
    """Own one public upstream, canonical state, and normalized session artifact."""

    def __init__(
        self,
        row_source: Callable[[], AsyncIterator[dict[str, Any]]] | None = None,
        *,
        now: Callable[[], datetime] | None = None,
        stale_after: float = 25.0,
        maximum_backoff: float = 30.0,
        normalized_recording_dir: Path | None = None,
        finalization_drain: float = 5.0,
        on_recording_finalized: Callable[[Path], bool] | None = None,
    ) -> None:
        self._row_source = row_source or PublicSignalRConnection().rows
        self._now = now or (lambda: datetime.now(UTC))
        self._stale_after = stale_after
        self._maximum_backoff = maximum_backoff
        self._normalized_recording_dir = normalized_recording_dir
        self._finalization_drain = max(0.0, finalization_drain)
        self._on_recording_finalized = on_recording_finalized
        self._target_session_key: str | None = None
        self._scheduled_start: str | None = None
        self._scheduled_end: str | None = None
        self._status = "OFFLINE"
        self._phase = "UNAVAILABLE"
        self._error: str | None = None
        self._last_received_at: str | None = None
        self._events: list[NormalizedEvent] = []
        self._state = RaceState()
        self._evidence = SessionEvidence()
        self._task: asyncio.Task[None] | None = None
        self._finalization_task: asyncio.Task[None] | None = None
        self._normalized_recorder: NormalizedLiveRecorder | None = None
        self._completion_observed = False
        self._ever_connected = False
        self._reconnecting = False
        self._replay_ready = False
        self._final_recording: Path | None = None
        self._phase_history: list[str] = []
        self._adapter: F1LiveAdapter | None = None

    @property
    def state(self) -> RaceState:
        return self._state

    @property
    def evidence(self) -> SessionEvidence:
        return self._evidence

    @property
    def events(self) -> tuple[NormalizedEvent, ...]:
        return tuple(self._events)

    @property
    def target_session_key(self) -> str | None:
        return self._target_session_key

    @property
    def phase_history(self) -> tuple[str, ...]:
        return tuple(self._phase_history)

    def configure_recording(
        self,
        directory: Path,
        on_finalized: Callable[[Path], bool] | None = None,
    ) -> None:
        self._normalized_recording_dir = directory
        self._on_recording_finalized = on_finalized

    def view(self, session_key: str | None = None) -> LiveSourceView:
        matches = session_key is None or str(session_key) == self._target_session_key
        status = self._status if matches else "OFFLINE"
        return LiveSourceView(
            self._target_session_key if matches else None,
            status,
            status == "LIVE",
            status == "STALE",
            len(self._events) if matches else 0,
            self._last_received_at if matches else None,
            self._error if matches else None,
            self._phase if matches else "UNAVAILABLE",
            self._replay_ready if matches else False,
            str(self._final_recording) if matches and self._final_recording else None,
        )

    async def start(
        self,
        session_key: str,
        *,
        scheduled_start: str | None = None,
        scheduled_end: str | None = None,
        seed_events: Iterable[NormalizedEvent] = (),
    ) -> None:
        key = str(session_key)
        seeded = tuple(seed_events)
        if key == self._target_session_key and (
            (self._task is not None and not self._task.done()) or self._events
        ):
            static_circuit = tuple(
                event
                for event in seeded
                if event.kind == "circuit"
                and isinstance(event.payload.get("path"), (list, tuple))
                and len(event.payload["path"]) >= 3
            )
            if not self._state.circuit.path and static_circuit:
                if self._normalized_recorder is not None:
                    self._normalized_recorder.append(static_circuit)
                self._events.extend(static_circuit)
                self._events.sort(key=lambda event: parse_timestamp(event.occurred_at))
                self._rebuild_projection()
            return
        await self.stop()
        self._target_session_key = key
        self._scheduled_start = scheduled_start
        self._scheduled_end = scheduled_end
        self._status = "CONNECTING"
        self._error = None
        self._last_received_at = None
        self._events = []
        self._state = RaceState()
        self._evidence = SessionEvidence()
        self._completion_observed = False
        self._ever_connected = False
        self._reconnecting = False
        self._replay_ready = False
        self._final_recording = None
        self._phase_history = []
        self._normalized_recorder = (
            NormalizedLiveRecorder(self._normalized_recording_dir, key)
            if self._normalized_recording_dir is not None
            else None
        )
        self._restore_recorded_events(seeded)
        if self._completion_observed:
            self._set_phase("FINALIZING")
            self._schedule_finalization()
        else:
            self._set_phase(self._phase_for_schedule("CONNECTING"))
        self._task = asyncio.create_task(self._run(key))

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        finalization_task = self._finalization_task
        self._finalization_task = None
        if finalization_task is not None and not finalization_task.done():
            finalization_task.cancel()
            try:
                await finalization_task
            except asyncio.CancelledError:
                pass
        self._status = "OFFLINE"
        self._target_session_key = None

    async def apply_rows(
        self, session_key: str, rows: Iterable[dict[str, Any]]
    ) -> None:
        """Apply a deterministic raw fixture without opening a connection."""
        self._target_session_key = str(session_key)
        self._status = "CONNECTING"
        self._set_phase("CONNECTING")
        if self._normalized_recording_dir is not None:
            self._normalized_recorder = NormalizedLiveRecorder(
                self._normalized_recording_dir, str(session_key)
            )
            self._restore_recorded_events(())
        adapter = F1LiveAdapter(str(session_key))
        self._adapter = adapter
        for row in rows:
            self._apply(adapter.ingest(row), str(row.get("received_at") or utc_now()))
        if self._events and not self._completion_observed:
            self._status = "LIVE"
            self._set_phase("LIVE")
            self._error = None
        if self._completion_observed:
            await self._finalize_after_drain()

    def _restore_recorded_events(
        self, seed_events: tuple[NormalizedEvent, ...]
    ) -> None:
        recovered = (
            self._normalized_recorder.events if self._normalized_recorder else ()
        )
        fresh_seed = (
            self._normalized_recorder.append(seed_events)
            if self._normalized_recorder
            else seed_events
        )
        self._events = sorted(
            (*recovered, *fresh_seed),
            key=lambda event: parse_timestamp(event.occurred_at),
        )
        self._rebuild_projection()
        self._completion_observed = False
        for event in self._events:
            if self._event_completes_session(event):
                self._completion_observed = True
        if recovered:
            self._ever_connected = True
            latest = max(
                recovered,
                key=lambda event: parse_timestamp(
                    event.received_at or event.occurred_at
                ),
            )
            self._last_received_at = latest.received_at or latest.occurred_at

    @staticmethod
    def _event_completes_session(event: NormalizedEvent) -> bool:
        status = str(event.payload.get("status") or "").upper()
        return event.kind == "session" and status in {
            "FINISHED",
            "ENDED",
            "COMPLETE",
            "FINAL",
            "FINALIZED",
            "FINALISED",
        }

    def _apply(self, events: Iterable[NormalizedEvent], received_at: str) -> bool:
        batch = tuple(events)
        if self._normalized_recorder is not None:
            batch = self._normalized_recorder.append(batch)
        if not batch:
            self._last_received_at = received_at
            return False

        previous_count = len(self._events)
        ordered = sorted(
            (*self._events, *batch),
            key=lambda event: parse_timestamp(event.occurred_at),
        )
        append_only = ordered[:previous_count] == self._events
        self._events = ordered
        if append_only:
            for sequence, event in enumerate(
                ordered[previous_count:],
                start=previous_count + 1,
            ):
                self._state = self._state.apply(event)
                self._evidence = self._evidence.append(
                    event,
                    sequence=sequence,
                    state=self._state,
                )
        else:
            self._rebuild_projection()

        for event in batch:
            if self._event_completes_session(event):
                self._completion_observed = True
                self._set_phase("FINALIZING")
        self._last_received_at = received_at
        self._status = "LIVE"
        self._ever_connected = True
        self._reconnecting = False
        if not self._completion_observed:
            self._set_phase("LIVE")
        self._error = None
        return True

    def _rebuild_projection(self) -> None:
        self._state = RaceState()
        self._evidence = SessionEvidence()
        for sequence, event in enumerate(self._events, start=1):
            self._state = self._state.apply(event)
            self._evidence = self._evidence.append(
                event,
                sequence=sequence,
                state=self._state,
            )

    def _phase_for_schedule(self, fallback: str) -> str:
        if self._scheduled_start:
            try:
                if self._now() < datetime.fromisoformat(self._scheduled_start):
                    return "PRE_EVENT"
            except ValueError:
                pass
        return fallback

    def _set_phase(self, phase: str) -> None:
        if phase not in LIVE_PRODUCT_PHASES:
            raise ValueError(f"unsupported live product phase: {phase}")
        self._phase = phase
        if not self._phase_history or self._phase_history[-1] != phase:
            self._phase_history.append(phase)

    def _schedule_finalization(self) -> None:
        # Every factual post-chequered packet extends the deterministic drain.
        # This preserves late classification/timing updates before atomic close.
        if self._finalization_task is not None and not self._finalization_task.done():
            self._finalization_task.cancel()
        self._finalization_task = asyncio.create_task(self._finalize_after_drain())

    async def _finalize_after_drain(self) -> None:
        if self._finalization_drain:
            await asyncio.sleep(self._finalization_drain)
        if not self._completion_observed:
            return
        if self._state.session.session_kind == "race" and self._adapter is not None:
            at = max(
                (event.occurred_at for event in self._events),
                key=parse_timestamp,
                default=self._state.updated_at or utc_now(),
            )
            self._apply(
                finalize_f1_classifications(
                    self._adapter.streams.get("TimingData", {}),
                    at,
                    source="f1-signalr-public",
                ),
                at,
            )
        self._set_phase("COMPLETE")
        if self._normalized_recorder is None:
            return
        self._status = "OFFLINE"
        self._reconnecting = False
        self._error = None
        await self._stop_completed_upstream()
        final_path = self._normalized_recorder.finalize()
        self._final_recording = final_path
        ready = True
        if self._on_recording_finalized is not None:
            ready = bool(self._on_recording_finalized(final_path))
        self._replay_ready = ready
        if ready:
            self._set_phase("REPLAY_READY")

    async def _stop_completed_upstream(self) -> None:
        task = self._task
        if task is None or task is asyncio.current_task() or task.done():
            return
        self._task = None
        task.cancel()
        await asyncio.sleep(0)

    async def _wait_for_scheduled_start(self, session_key: str) -> None:
        while self._target_session_key == session_key and self._scheduled_start:
            try:
                seconds = (
                    datetime.fromisoformat(self._scheduled_start) - self._now()
                ).total_seconds()
            except ValueError:
                return
            if seconds <= 0:
                return
            self._set_phase("PRE_EVENT")
            await asyncio.sleep(min(seconds, 15.0))

    async def _run(self, session_key: str) -> None:
        await self._wait_for_scheduled_start(session_key)
        backoff = 1.0
        while self._target_session_key == session_key and not self._replay_ready:
            adapter = F1LiveAdapter(session_key)
            self._adapter = adapter
            self._status = "CONNECTING" if not self._ever_connected else "STALE"
            self._reconnecting = self._ever_connected
            self._set_phase("RECONNECTING" if self._reconnecting else "CONNECTING")
            try:
                iterator = self._row_source().__aiter__()
                while (
                    self._target_session_key == session_key and not self._replay_ready
                ):
                    try:
                        row = await asyncio.wait_for(
                            anext(iterator), timeout=self._stale_after
                        )
                    except StopAsyncIteration as error:
                        raise LiveSourceError("The public live stream ended") from error
                    except TimeoutError as error:
                        self._status = "STALE"
                        self._set_phase("STALE")
                        self._error = f"No public live data received for {self._stale_after:g} seconds"
                        raise LiveSourceError(self._error) from error
                    emitted = self._apply(
                        adapter.ingest(row),
                        str(row.get("received_at") or utc_now()),
                    )
                    if emitted and self._completion_observed:
                        self._schedule_finalization()
                    backoff = 1.0
            except asyncio.CancelledError:
                raise
            except (LiveSourceError, aiohttp.ClientError, OSError) as error:
                if self._completion_observed:
                    if (
                        self._finalization_task is None
                        or self._finalization_task.done()
                    ):
                        self._schedule_finalization()
                    return
                self._status = "UNAVAILABLE" if not self._ever_connected else "STALE"
                self._error = str(error)
                self._reconnecting = self._ever_connected
                self._set_phase("RECONNECTING" if self._reconnecting else "UNAVAILABLE")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._maximum_backoff)
