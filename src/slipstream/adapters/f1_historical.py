"""Official Formula 1 static timing archive reconstruction."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta, timezone
from math import ceil
from pathlib import Path
from statistics import median
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ..events import NormalizedEvent, parse_timestamp
from ..f1_timing import finalize_f1_classifications
from ..live import F1LiveAdapter, canonical_utc
from ..session import classify_session

STATIC_ROOT = "https://livetiming.formula1.com/static"
LOW_VOLUME_TOPICS = (
    "SessionInfo",
    "DriverList",
    "TimingData",
    "TimingAppData",
    "LapCount",
    "SessionStatus",
    "SessionData",
    "TrackStatus",
    "RaceControlMessages",
    "ExtrapolatedClock",
    "WeatherData",
)


class F1HistoricalError(RuntimeError):
    """Raised when one complete official historical reconstruction is unavailable."""


@dataclass(frozen=True)
class F1ArchiveSession:
    session_key: str
    path: str
    year: int


def parse_json_stream(text: str) -> tuple[tuple[timedelta, Any], ...]:
    """Parse timestamp-prefixed sparse jsonStream records deterministically."""

    records: list[tuple[timedelta, Any]] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip().lstrip("\ufeff")
        if not line:
            continue
        match = re.match(r"^(\d{1,2}):(\d{2}):(\d{2})\.(\d{3})(.*)$", line)
        if match is None:
            raise F1HistoricalError(f"invalid jsonStream prefix on line {line_number}")
        hours, minutes, seconds, millis, body = match.groups()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as error:
            raise F1HistoricalError(
                f"invalid jsonStream JSON on line {line_number}: {error}"
            ) from error
        records.append(
            (
                timedelta(
                    hours=int(hours),
                    minutes=int(minutes),
                    seconds=int(seconds),
                    milliseconds=int(millis),
                ),
                payload,
            )
        )
    return tuple(records)


class F1HistoricalClient:
    """Bounded client for official public low-volume static timing topics."""

    def __init__(self, *, opener: Any = urlopen) -> None:
        self._opener = opener
        self.headers = {
            "User-Agent": "BestHTTP",
            "Accept-Encoding": "identity",
            "Connection": "close",
        }

    def resolve_session(self, year: int, session_key: str | int) -> F1ArchiveSession:
        index = self._get_json(f"{STATIC_ROOT}/{int(year)}/Index.json")
        path = _find_session_path(index, str(session_key))
        if path is None:
            root_index = self._get_json(f"{STATIC_ROOT}/Index.json")
            path = _find_session_path(root_index, str(session_key))
        if path is None:
            raise F1HistoricalError(
                f"official F1 archive has no indexed session {session_key} in {year}"
            )
        if not path.startswith(f"{int(year)}/"):
            path = f"{int(year)}/{path}"
        return F1ArchiveSession(str(session_key), path, int(year))

    def capture_events(
        self,
        session_key: str | int,
        *,
        year: int,
        session_identity: Mapping[str, Any] | None = None,
    ) -> tuple[NormalizedEvent, ...]:
        session = self.resolve_session(year, session_key)
        topic_rows: list[tuple[timedelta, int, str, Any]] = []
        dynamic_snapshots: list[tuple[int, str, Any]] = []
        session_info: dict[str, Any] | None = None
        for order, topic in enumerate(LOW_VOLUME_TOPICS):
            base = f"{STATIC_ROOT}/{session.path}/{topic}"
            full = self._get_optional_json(f"{base}.json")
            stream = self._get_optional_text(f"{base}.jsonStream")
            if topic in {"SessionInfo", "DriverList"} and isinstance(full, dict):
                initial = dict(full)
                if topic == "SessionInfo":
                    initial = _normalize_session_info_times(initial, full)
                    for key in ("Status", "SessionStatus", "Started"):
                        initial.pop(key, None)
                topic_rows.append((timedelta(0), order, topic, initial))
            if stream is not None:
                for offset, patch in parse_json_stream(stream):
                    if topic == "SessionInfo" and isinstance(patch, dict):
                        patch = _normalize_session_info_times(patch, full)
                    topic_rows.append((offset, order, topic, patch))
            if isinstance(full, dict) and topic not in {"SessionInfo", "DriverList"}:
                dynamic_snapshots.append((order, topic, full))
            if topic == "SessionInfo" and isinstance(full, dict):
                session_info = full
        if session_info is None:
            raise F1HistoricalError("official F1 reconstruction requires SessionInfo")
        stream_zero = _stream_zero(topic_rows)
        final_offset = _final_offset(topic_rows, session_info, stream_zero)
        if final_offset is not None:
            topic_rows.extend(
                (final_offset, order, topic, payload)
                for order, topic, payload in dynamic_snapshots
            )
        if not any(topic == "TimingData" for _, _, topic, _ in topic_rows):
            raise F1HistoricalError("official F1 reconstruction requires TimingData")
        adapter = F1LiveAdapter(str(session_key), source="f1-static-public")
        events: list[NormalizedEvent] = []
        for offset, _order, topic, payload in sorted(
            topic_rows, key=lambda item: (item[0], item[1])
        ):
            occurred_at = _at_offset(stream_zero, offset)
            events.extend(
                adapter.ingest(
                    {
                        "stream": topic,
                        "payload": payload,
                        "source_timestamp": occurred_at,
                        "received_at": occurred_at,
                    }
                )
            )

        identity_payload = _session_identity_payload(
            str(session_key), session_info, session_identity
        )
        if identity_payload:
            identity_at = min(
                (event.occurred_at for event in events),
                key=parse_timestamp,
                default=_at_offset(stream_zero, timedelta(0)),
            )
            events.insert(
                0,
                NormalizedEvent(
                    "session",
                    identity_at,
                    "f1-static-public",
                    identity_payload,
                    received_at=identity_at,
                ),
            )

        final_at = _final_cursor(events)
        session_kind = str(identity_payload.get("session_kind") or "unknown")
        if final_at is not None and session_kind == "race":
            events.extend(
                finalize_f1_classifications(
                    adapter.streams.get("TimingData", {}),
                    final_at,
                    source="f1-static-public",
                )
            )

        if not any(
            event.kind == "session"
            and str(event.payload.get("key")) == str(session_key)
            for event in events
        ) or not any(event.kind == "timing" for event in events):
            raise F1HistoricalError(
                "official F1 reconstruction produced no usable canonical session"
            )
        return tuple(
            event
            for _, event in sorted(
                enumerate(events),
                key=lambda item: (parse_timestamp(item[1].occurred_at), item[0]),
            )
        )

    def _get_json(self, url: str) -> Any:
        return json.loads(self._get_text(url))

    def _get_optional_json(self, url: str) -> Any | None:
        text = self._get_optional_text(url)
        return json.loads(text) if text is not None else None

    def _get_optional_text(self, url: str) -> str | None:
        try:
            return self._get_text(url)
        except HTTPError as error:
            if error.code == 404:
                return None
            raise

    def _get_text(self, url: str) -> str:
        request = Request(url, headers=self.headers)
        try:
            with self._opener(request, timeout=30) as response:
                return response.read().decode("utf-8-sig")
        except Exception as error:
            if isinstance(error, HTTPError):
                raise
            raise F1HistoricalError(
                f"official F1 request failed: {url}: {error}"
            ) from error


def write_canonical_recording(path: Path, events: tuple[NormalizedEvent, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(".json.tmp")
    staging.write_text(
        json.dumps([asdict(event) for event in events], separators=(",", ":")),
        encoding="utf-8",
    )
    staging.replace(path)


def _find_session_path(value: Any, key: str, prefix: str = "") -> str | None:
    if isinstance(value, dict):
        own_key = value.get("Key", value.get("SessionKey", value.get("session_key")))
        own_path = str(value.get("Path") or value.get("path") or "").strip("/")
        if str(own_key) == key and own_path:
            return "/".join(part for part in (prefix, own_path) if part)
        child_prefix = "/".join(part for part in (prefix, own_path) if part)
        for child in value.values():
            found = _find_session_path(child, key, child_prefix)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_session_path(child, key, prefix)
            if found is not None:
                return found
    return None


def _stream_zero(rows: list[tuple[timedelta, int, str, Any]]) -> datetime:
    candidates: list[datetime] = []
    for offset, _order, topic, payload in rows:
        for raw_utc in _anchor_utc_values(topic, payload):
            candidates.append(parse_timestamp(canonical_utc(raw_utc)) - offset)
    if len(candidates) < 2:
        raise F1HistoricalError(
            "official F1 reconstruction has no reliable SessionTime-to-UTC anchor"
        )

    tolerance_seconds = 0.010
    best_cluster = max(
        (
            [
                candidate
                for candidate in candidates
                if abs((candidate - center).total_seconds()) <= tolerance_seconds
            ]
            for center in candidates
        ),
        key=len,
    )
    required_consensus = max(2, ceil(len(candidates) * 0.75))
    if len(best_cluster) < required_consensus:
        raise F1HistoricalError(
            "official F1 SessionTime-to-UTC anchors do not establish one stream zero"
        )
    return datetime.fromtimestamp(
        median(candidate.timestamp() for candidate in best_cluster), tz=UTC
    )


def _anchor_utc_values(topic: str, payload: Any) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        return ()
    if topic == "ExtrapolatedClock":
        raw = payload.get("Utc")
        return (str(raw),) if isinstance(raw, str) and raw else ()
    if topic != "SessionData":
        return ()

    values: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            raw = value.get("Utc")
            if isinstance(raw, str) and raw:
                values.append(raw)
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(payload.get("Series"))
    collect(payload.get("StatusSeries"))
    return tuple(values)


def _normalize_session_info_times(
    payload: dict[str, Any], full_info: Any
) -> dict[str, Any]:
    normalized = dict(payload)
    fallback = full_info if isinstance(full_info, dict) else {}
    gmt_offset = normalized.get("GmtOffset") or fallback.get("GmtOffset")
    for key in ("StartDate", "EndDate"):
        raw = normalized.get(key)
        if isinstance(raw, str) and raw:
            normalized[key] = _session_wall_time_utc(raw, gmt_offset)
    return normalized


def _session_wall_time_utc(raw: str, gmt_offset: Any) -> str:
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as error:
        raise F1HistoricalError(
            f"invalid SessionInfo wall-clock timestamp: {raw}"
        ) from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone(_gmt_offset(gmt_offset)))
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _gmt_offset(raw: Any) -> timedelta:
    match = re.fullmatch(r"([+-]?)(\d{1,2}):(\d{2}):(\d{2})", str(raw or ""))
    if match is None:
        raise F1HistoricalError(
            "naive SessionInfo wall-clock timestamp has no valid GmtOffset"
        )
    sign, hours, minutes, seconds = match.groups()
    offset = timedelta(
        hours=int(hours), minutes=int(minutes), seconds=int(seconds)
    )
    return -offset if sign == "-" else offset


def _session_identity_payload(
    session_key: str,
    session_info: dict[str, Any],
    session_identity: Mapping[str, Any] | None,
) -> dict[str, Any]:
    identity = session_identity or {}
    meeting = (
        session_info.get("Meeting")
        if isinstance(session_info.get("Meeting"), dict)
        else {}
    )
    circuit = (
        meeting.get("Circuit") if isinstance(meeting.get("Circuit"), dict) else {}
    )
    normalized_info = _normalize_session_info_times(session_info, session_info)
    name = identity.get("session_name") or session_info.get("Name")
    session_type = identity.get("session_type") or session_info.get("Type")
    classification = classify_session(str(session_type or ""), str(name or ""))
    values = {
        "key": session_key,
        "name": name,
        "meeting_name": identity.get("meeting_name") or meeting.get("Name"),
        "session_type": session_type,
        "session_kind": identity.get("session_kind") or classification.kind.value,
        "layout_family": identity.get("layout_family")
        or classification.layout_family.value,
        "circuit": identity.get("circuit") or circuit.get("ShortName"),
        "location": identity.get("location") or meeting.get("Location"),
        "started_at": identity.get("date_start") or normalized_info.get("StartDate"),
        "ended_at": identity.get("date_end") or normalized_info.get("EndDate"),
        "gmt_offset": identity.get("gmt_offset") or session_info.get("GmtOffset"),
    }
    return {key: value for key, value in values.items() if value not in {None, ""}}


def _at_offset(start: datetime, offset: timedelta) -> str:
    return (start + offset).astimezone(UTC).isoformat().replace("+00:00", "Z")


def _final_cursor(events: list[NormalizedEvent]) -> str | None:
    terminal = [
        event.occurred_at
        for event in events
        if event.kind == "session"
        and str(event.payload.get("status") or "").upper() == "FINISHED"
    ]
    return max(terminal, key=parse_timestamp) if terminal else None


def _final_offset(
    rows: list[tuple[timedelta, int, str, Any]],
    session_info: dict[str, Any],
    stream_zero: datetime,
) -> timedelta | None:
    finished = [
        offset
        for offset, _order, topic, payload in rows
        if topic == "SessionStatus"
        and isinstance(payload, dict)
        and str(payload.get("Status") or "").upper()
        in {"FINISHED", "ENDED", "COMPLETE"}
    ]
    if finished:
        return max(finished)
    raw_end = session_info.get("EndDate")
    if isinstance(raw_end, str):
        end = parse_timestamp(
            _session_wall_time_utc(raw_end, session_info.get("GmtOffset"))
        )
        return max(end - stream_zero, timedelta(0))
    return None
