"""Lightweight OpenF1 season metadata and circuit geometry cache."""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from http.client import HTTPException
from pathlib import Path
from typing import Any

from .adapters.openf1 import OpenF1Client
from .adapters.season_calendar import SeasonRound, fetch_season_rounds, utc_date
from .session import classify_session

logger = logging.getLogger(__name__)

CATALOG_FORMAT = "slipstream.openf1-catalog.v1"


def recent_seasons(count: int = 3, *, now: datetime | None = None) -> list[int]:
    """Return the current season and the preceding ``count - 1`` seasons."""
    if count < 1:
        raise ValueError("season count must be at least 1")
    current_year = (now or datetime.now(UTC)).year
    return list(range(current_year - count + 1, current_year + 1))


def sync_catalog(
    path: Path,
    years: list[int],
    *,
    client: OpenF1Client | None = None,
    max_age: timedelta = timedelta(hours=24),
    now: datetime | None = None,
    fetch_rounds: Callable[[int], list[SeasonRound]] = fetch_season_rounds,
) -> dict[str, Any]:
    """Cache session metadata and linked circuit paths for the requested seasons."""
    clock = now or datetime.now(UTC)
    existing = read_catalog(path)
    if _is_fresh(existing, years, max_age=max_age, now=clock):
        return existing

    source = client or OpenF1Client()
    meetings: dict[str, dict[str, Any]] = {}
    sessions: list[dict[str, Any]] = []
    for year in sorted(set(years)):
        year_meetings = source.get("meetings", year=year, allow_not_found=True)
        for meeting in year_meetings:
            meeting_key = str(meeting.get("meeting_key") or "")
            if not meeting_key:
                continue
            circuit_url = meeting.get("circuit_info_url")
            circuit_payload = None
            if isinstance(circuit_url, str) and circuit_url.startswith("https://"):
                circuit_payload = source.get_object_url(
                    circuit_url, allow_not_found=True
                )
            meetings[meeting_key] = {
                "meeting_key": meeting.get("meeting_key"),
                "meeting_name": meeting.get("meeting_name"),
                "meeting_official_name": meeting.get("meeting_official_name"),
                "location": meeting.get("location"),
                "country_name": meeting.get("country_name"),
                "circuit_key": meeting.get("circuit_key"),
                "circuit_short_name": meeting.get("circuit_short_name"),
                "date_start": meeting.get("date_start"),
                "date_end": meeting.get("date_end"),
                "year": meeting.get("year") or year,
                "is_cancelled": meeting.get("is_cancelled"),
                "circuit": _normalize_circuit(circuit_payload, circuit_url),
            }
        sessions.extend(
            _select_session_fields(session, year)
            for session in source.get("sessions", year=year, allow_not_found=True)
            if session.get("session_key") is not None
        )

        try:
            rounds = fetch_rounds(year)
        except (OSError, ValueError, KeyError, TypeError, HTTPException) as error:
            # Optional calendar metadata must never prevent catalog refresh.
            logger.warning(
                "Round calendar unavailable for %s: %s", year, type(error).__name__
            )
            rounds = []
        _attach_round_numbers(meetings, sessions, year, rounds)

    payload: dict[str, Any] = {
        "format": CATALOG_FORMAT,
        "schema_version": 1,
        "round_metadata_version": 1,
        "source": "openf1",
        "updated_at": clock.isoformat().replace("+00:00", "Z"),
        "years": sorted(set(years)),
        "meetings": meetings,
        "sessions": sorted(
            sessions, key=lambda item: str(item.get("date_start") or "")
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    return payload


def read_catalog(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("format") != CATALOG_FORMAT:
        return {}
    return payload


def _is_fresh(
    payload: dict[str, Any],
    years: list[int],
    *,
    max_age: timedelta,
    now: datetime,
) -> bool:
    if payload.get("round_metadata_version") != 1 or not set(years).issubset(
        set(payload.get("years", []))
    ):
        return False
    try:
        updated = datetime.fromisoformat(str(payload["updated_at"]))
    except (KeyError, TypeError, ValueError):
        return False
    return now - updated <= max_age


def _select_session_fields(session: dict[str, Any], year: int) -> dict[str, Any]:
    fields = (
        "session_key",
        "meeting_key",
        "session_name",
        "session_type",
        "circuit_short_name",
        "location",
        "country_name",
        "date_start",
        "date_end",
        "gmt_offset",
        "is_cancelled",
        "year",
    )
    selected = {key: session.get(key) for key in fields}
    selected["year"] = selected.get("year") or year
    return selected


def _normalize_circuit(
    payload: dict[str, Any] | None, source_url: object
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    x_values = payload.get("x")
    y_values = payload.get("y")
    if not (
        isinstance(x_values, list)
        and isinstance(y_values, list)
        and len(x_values) >= 3
        and len(x_values) == len(y_values)
        and all(isinstance(value, (int, float)) for value in (*x_values, *y_values))
    ):
        return None
    return {
        "key": str(payload.get("circuitKey") or "") or None,
        "name": payload.get("circuitName"),
        "year": payload.get("year"),
        "rotation": payload.get("rotation"),
        "path": [[float(x), float(y)] for x, y in zip(x_values, y_values, strict=True)],
        "source": source_url if isinstance(source_url, str) else None,
        "availability": {"path": "available"},
    }


def _attach_round_numbers(
    meetings: dict[str, dict[str, Any]],
    sessions: list[dict[str, Any]],
    year: int,
    rounds: list[SeasonRound],
) -> None:
    """Match unique Grand Prix dates, never meeting IDs, names or list positions."""
    races = []
    for session in sessions:
        if session.get("year") != year:
            continue
        meeting = meetings.get(str(session.get("meeting_key")), {})
        if session.get("is_cancelled") is True or meeting.get("is_cancelled") is True:
            continue
        if (
            classify_session(
                session.get("session_type"), session.get("session_name")
            ).kind.value
            != "race"
        ):
            continue
        race_date = utc_date(session.get("date_start"))
        if race_date:
            races.append((str(session.get("meeting_key")), race_date))
    dates = Counter(date for _, date in races)
    meeting_counts = Counter(key for key, _ in races)
    round_dates = Counter(item.race_date for item in rounds)
    round_numbers = Counter(item.number for item in rounds)
    by_date = {
        item.race_date: item.number
        for item in rounds
        if round_dates[item.race_date] == round_numbers[item.number] == 1
    }
    for key, race_date in races:
        if (
            key in meetings
            and dates[race_date] == meeting_counts[key] == 1
            and race_date in by_date
        ):
            meetings[key]["round_number"] = by_date[race_date]
            meetings[key]["round_source"] = (
                f"https://api.jolpi.ca/ergast/f1/{year}/races.json"
            )
