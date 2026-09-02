"""Private lightweight meeting metadata for historical Pirelli catch-up."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..adapters.openf1 import OpenF1Client
from ..session import classify_session

PIRELLI_METADATA_FORMAT = "slipstream.pirelli.metadata.v1"


@dataclass(frozen=True)
class PirelliSessionDescriptor:
    key: str
    meeting_key: str
    meeting_name: str
    session_name: str
    session_type: str
    date_start: str
    date_end: str
    year: int
    location: str | None = None
    circuit: str | None = None

    @property
    def session_kind(self) -> str:
        return classify_session(self.session_type, self.session_name).kind.value


def metadata_path(data_root: Path) -> Path:
    return data_root / ".slipstream" / "pirelli-metadata.json"


def sync_pirelli_metadata(
    path: Path,
    years: tuple[int, ...] | list[int],
    *,
    client: OpenF1Client | Any | None = None,
    max_age: timedelta = timedelta(days=7),
    now: datetime | None = None,
) -> dict[str, Any]:
    """Cache meeting/session identity only; no timing data or circuit geometry."""

    selected_years = sorted({int(year) for year in years})
    if not selected_years:
        raise ValueError("at least one Pirelli metadata season is required")
    clock = now or datetime.now(UTC)
    existing = read_pirelli_metadata(path)
    if _is_fresh(existing, selected_years, max_age=max_age, now=clock):
        return existing

    source = client or OpenF1Client()
    meetings: dict[str, dict[str, Any]] = {}
    sessions: list[dict[str, Any]] = []
    for year in selected_years:
        for meeting in source.get("meetings", year=year, allow_not_found=True):
            meeting_key = str(meeting.get("meeting_key") or "")
            if not meeting_key:
                continue
            meetings[meeting_key] = {
                "meetingKey": meeting_key,
                "meetingName": meeting.get("meeting_name"),
                "location": meeting.get("location"),
                "circuit": meeting.get("circuit_short_name"),
                "dateStart": meeting.get("date_start"),
                "dateEnd": meeting.get("date_end"),
                "year": int(meeting.get("year") or year),
            }
        for session in source.get("sessions", year=year, allow_not_found=True):
            session_key = str(session.get("session_key") or "")
            meeting_key = str(session.get("meeting_key") or "")
            if not session_key or not meeting_key:
                continue
            sessions.append(
                {
                    "sessionKey": session_key,
                    "meetingKey": meeting_key,
                    "sessionName": session.get("session_name"),
                    "sessionType": session.get("session_type"),
                    "dateStart": session.get("date_start"),
                    "dateEnd": session.get("date_end"),
                    "year": int(session.get("year") or year),
                    "isCancelled": bool(session.get("is_cancelled", False)),
                }
            )

    payload: dict[str, Any] = {
        "format": PIRELLI_METADATA_FORMAT,
        "updatedAt": clock.astimezone(UTC).isoformat(),
        "years": selected_years,
        "meetings": meetings,
        "sessions": sorted(
            sessions, key=lambda item: (str(item.get("dateStart") or ""), item["sessionKey"])
        ),
    }
    _atomic_json(path, payload)
    return payload


def read_pirelli_metadata(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("format") != PIRELLI_METADATA_FORMAT:
        return {}
    return payload


def metadata_descriptors(payload: dict[str, Any]) -> tuple[PirelliSessionDescriptor, ...]:
    meetings = payload.get("meetings")
    meeting_rows = meetings if isinstance(meetings, dict) else {}
    descriptors: list[PirelliSessionDescriptor] = []
    for raw in payload.get("sessions", []):
        if not isinstance(raw, dict) or raw.get("isCancelled"):
            continue
        meeting_key = str(raw.get("meetingKey") or "")
        meeting = meeting_rows.get(meeting_key, {})
        if not isinstance(meeting, dict):
            meeting = {}
        start = str(raw.get("dateStart") or "")
        end = str(raw.get("dateEnd") or start)
        key = str(raw.get("sessionKey") or "")
        if not meeting_key or not key or not start:
            continue
        descriptors.append(
            PirelliSessionDescriptor(
                key=key,
                meeting_key=meeting_key,
                meeting_name=str(
                    meeting.get("meetingName")
                    or meeting.get("location")
                    or "Grand Prix"
                ),
                session_name=str(raw.get("sessionName") or "Session"),
                session_type=str(raw.get("sessionType") or "Session"),
                date_start=start,
                date_end=end,
                year=int(raw.get("year") or meeting.get("year") or start[:4]),
                location=(
                    str(meeting["location"])
                    if meeting.get("location") is not None
                    else None
                ),
                circuit=(
                    str(meeting["circuit"])
                    if meeting.get("circuit") is not None
                    else None
                ),
            )
        )
    return tuple(sorted(descriptors, key=lambda item: (item.date_start, item.key)))


def _is_fresh(
    payload: dict[str, Any],
    years: list[int],
    *,
    max_age: timedelta,
    now: datetime,
) -> bool:
    if not payload or not set(years).issubset(set(payload.get("years", []))):
        return False
    try:
        updated = datetime.fromisoformat(str(payload["updatedAt"]))
    except (KeyError, TypeError, ValueError):
        return False
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    return now.astimezone(UTC) - updated.astimezone(UTC) <= max_age


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)
