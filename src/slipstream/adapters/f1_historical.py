"""Official Formula 1 static timing archive reconstruction."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ..events import NormalizedEvent, parse_timestamp
from ..live import F1LiveAdapter, canonical_utc

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
        found = _find_session(index, str(session_key))
        if found is None:
            raise F1HistoricalError(
                f"official F1 archive has no indexed session {session_key} in {year}"
            )
        path = str(found.get("Path") or found.get("path") or "").strip("/")
        if not path:
            raise F1HistoricalError(
                f"official F1 session {session_key} has no archive path"
            )
        return F1ArchiveSession(str(session_key), path, int(year))

    def capture_events(
        self, session_key: str | int, *, year: int
    ) -> tuple[NormalizedEvent, ...]:
        session = self.resolve_session(year, session_key)
        topic_rows: list[tuple[timedelta, int, str, Any]] = []
        session_info: dict[str, Any] | None = None
        for order, topic in enumerate(LOW_VOLUME_TOPICS):
            base = f"{STATIC_ROOT}/{session.path}/{topic}"
            full = self._get_optional_json(f"{base}.json")
            stream = self._get_optional_text(f"{base}.jsonStream")
            if stream is not None:
                for offset, patch in parse_json_stream(stream):
                    topic_rows.append((offset, order, topic, patch))
            elif isinstance(full, dict):
                initial = dict(full)
                if topic == "SessionInfo":
                    for key in ("Status", "SessionStatus", "Started"):
                        initial.pop(key, None)
                topic_rows.append((timedelta(0), order, topic, initial))
            if topic == "SessionInfo" and isinstance(full, dict):
                session_info = full
        if session_info is None:
            raise F1HistoricalError("official F1 reconstruction requires SessionInfo")
        if not any(topic == "TimingData" for _, _, topic, _ in topic_rows):
            raise F1HistoricalError("official F1 reconstruction requires TimingData")

        start = _session_start(session_info)
        adapter = F1LiveAdapter(str(session_key), source="f1-static-public")
        events: list[NormalizedEvent] = []
        for offset, _order, topic, payload in sorted(
            topic_rows, key=lambda item: (item[0], item[1])
        ):
            occurred_at = _at_offset(start, offset)
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

        final_at = _final_cursor(events)
        if final_at is not None:
            lines = adapter.streams.get("TimingData", {}).get("Lines", {})
            if isinstance(lines, dict):
                for raw_number, line in lines.items():
                    if not isinstance(line, dict):
                        continue
                    classification = _final_classification(line)
                    if classification is None:
                        continue
                    events.append(
                        NormalizedEvent(
                            "timing",
                            final_at,
                            "f1-static-public",
                            {
                                "number": str(line.get("RacingNumber") or raw_number),
                                "classification": classification,
                            },
                            received_at=final_at,
                        )
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


def _find_session(value: Any, key: str) -> dict[str, Any] | None:
    if isinstance(value, dict):
        own_key = value.get("Key", value.get("SessionKey", value.get("session_key")))
        if str(own_key) == key and (value.get("Path") or value.get("path")):
            return value
        for child in value.values():
            found = _find_session(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_session(child, key)
            if found is not None:
                return found
    return None


def _session_start(info: dict[str, Any]) -> datetime:
    raw = info.get("StartDate")
    if not isinstance(raw, str):
        raise F1HistoricalError("SessionInfo has no StartDate")
    return parse_timestamp(canonical_utc(raw))


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


def _final_classification(line: dict[str, Any]) -> str | None:
    raw = str(
        line.get("Classification")
        or line.get("ResultStatus")
        or line.get("Status")
        or ""
    ).upper()
    if raw in {"DNF", "DNS", "DSQ", "DISQUALIFIED", "FINISHED"}:
        return "DSQ" if raw == "DISQUALIFIED" else raw
    if bool(line.get("Retired")) or bool(line.get("Stopped")):
        return "DNF"
    if line.get("Position") is not None:
        return "FINISHED"
    return None
