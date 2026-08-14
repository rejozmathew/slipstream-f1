"""OpenF1 historical recording acquisition and normalization.

Provider payloads stop at this module. Everything emitted from here is a
source-neutral :class:`NormalizedEvent` consumed by the canonical reducer.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from slipstream.events import NormalizedEvent

RECORDING_FORMAT = "slipstream.openf1-recording.v1"
CAPABILITIES = {
    "historical_replay": True,
    "live_timing": False,
    "positions": True,
    "intervals": True,
    "location_xy": False,
    "circuit_shape": True,
    "race_control": True,
    "weather": True,
    "local_time": True,
    "authenticated": False,
}


class OpenF1Error(RuntimeError):
    """Raised when OpenF1 cannot provide a usable response."""


class OpenF1Client:
    """Small public API client with rate-limit-aware sequential requests."""

    def __init__(
        self,
        base_url: str = "https://api.openf1.org/v1",
        *,
        opener: Callable[..., Any] = urlopen,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        minimum_interval: float = 0.4,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._opener = opener
        self._sleep = sleep
        self._monotonic = monotonic
        self._minimum_interval = minimum_interval
        self._last_request_at: float | None = None

    def get(
        self, endpoint: str, *, allow_not_found: bool = False, **params: object
    ) -> list[dict[str, Any]]:
        query = urlencode(
            {key: value for key, value in params.items() if value is not None}
        )
        url = f"{self.base_url}/{endpoint}?{query}"
        payload = self._request_json(url, allow_not_found=allow_not_found)
        if payload is None:
            return []
        if not isinstance(payload, list):
            raise OpenF1Error(f"OpenF1 {endpoint} returned a non-list response")
        return payload

    def get_object_url(
        self, url: str, *, allow_not_found: bool = False
    ) -> dict[str, Any] | None:
        """Fetch a linked JSON object while preserving the same polite request policy."""
        payload = self._request_json(url, allow_not_found=allow_not_found)
        if payload is None or (allow_not_found and payload == []):
            return None
        if not isinstance(payload, dict):
            raise OpenF1Error(f"Linked circuit data at {url} returned a non-object")
        return payload

    def _request_json(self, url: str, *, allow_not_found: bool) -> Any | None:
        for attempt in range(4):
            self._wait_for_rate_limit()
            request = Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "slipstream-f1/0.1",
                },
            )
            try:
                with self._opener(request, timeout=30) as response:
                    self._last_request_at = self._monotonic()
                    payload = json.loads(response.read().decode("utf-8"))
                return payload
            except HTTPError as error:
                self._last_request_at = self._monotonic()
                if error.code == 404 and allow_not_found:
                    return []
                if error.code != 429 or attempt == 3:
                    raise OpenF1Error(
                        f"JSON request failed with HTTP {error.code}: {url}"
                    ) from error
                retry_after = float(error.headers.get("Retry-After", "1"))
                self._sleep(max(retry_after, 1.0))
        raise AssertionError("unreachable")

    def _wait_for_rate_limit(self) -> None:
        if self._last_request_at is None:
            return
        remaining = self._minimum_interval - (self._monotonic() - self._last_request_at)
        if remaining > 0:
            self._sleep(remaining)

    def capture_session(
        self, session_key: int, *, include_location: bool = False
    ) -> dict[str, Any]:
        sessions = self.get("sessions", session_key=session_key)
        if len(sessions) != 1:
            raise OpenF1Error(
                f"Expected one session for key {session_key}, received {len(sessions)}"
            )
        meeting_key = sessions[0].get("meeting_key")
        endpoints = {
            "sessions": sessions,
            "meetings": self.get("meetings", meeting_key=meeting_key),
        }
        meeting = endpoints["meetings"][0] if endpoints["meetings"] else {}
        circuit_info_url = meeting.get("circuit_info_url")
        circuit_info = None
        if isinstance(circuit_info_url, str) and circuit_info_url.startswith(
            "https://"
        ):
            circuit_info = self.get_object_url(circuit_info_url, allow_not_found=True)
        for endpoint in (
            "drivers",
            "laps",
            "position",
            "intervals",
            "race_control",
            "session_result",
            "stints",
            "pit",
            "weather",
        ):
            endpoints[endpoint] = self.get(
                endpoint, session_key=session_key, allow_not_found=True
            )
        endpoints["location"] = []
        if include_location:
            for driver in endpoints["drivers"]:
                endpoints["location"].extend(
                    self.get(
                        "location",
                        session_key=session_key,
                        driver_number=driver.get("driver_number"),
                        allow_not_found=True,
                    )
                )
        session_capabilities = {
            **CAPABILITIES,
            "intervals": bool(endpoints["intervals"]),
            "race_control": bool(endpoints["race_control"]),
            "weather": bool(endpoints["weather"]),
            "local_time": bool(sessions[0].get("gmt_offset")),
            "circuit_shape": _has_circuit_path(circuit_info),
            "location_xy": bool(endpoints["location"]),
        }
        return {
            "format": RECORDING_FORMAT,
            "schema_version": 1,
            "source": "openf1",
            "source_capabilities": session_capabilities,
            "captured_at": datetime.now(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "session_key": session_key,
            "circuit_info": {
                "source_url": circuit_info_url,
                "payload": circuit_info,
            }
            if circuit_info
            else None,
            "endpoints": endpoints,
        }


def write_recording(path: Path, recording: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(recording, indent=2) + "\n", encoding="utf-8")


def is_openf1_recording(raw: object) -> bool:
    return isinstance(raw, dict) and raw.get("format") == RECORDING_FORMAT


def recording_to_events(recording: dict[str, Any]) -> list[NormalizedEvent]:
    if not is_openf1_recording(recording):
        raise ValueError("Not a supported OpenF1 recording")
    endpoints = recording.get("endpoints")
    if not isinstance(endpoints, dict):
        raise TypeError("OpenF1 recording endpoints must be a mapping")
    session = _first(endpoints, "sessions")
    meeting = _first(endpoints, "meetings", required=False) or {}
    started_at = session["date_start"]
    ended_at = session["date_end"]
    source = "openf1"
    results = endpoints.get("session_result", [])
    completed_laps = [
        result.get("number_of_laps")
        for result in results
        if isinstance(result.get("number_of_laps"), int)
    ]
    race_total_laps = (
        max(completed_laps)
        if session.get("session_type") == "Race" and completed_laps
        else None
    )
    events = [
        NormalizedEvent(
            kind="session",
            occurred_at=started_at,
            source=source,
            payload={
                "key": str(session["session_key"]),
                "name": session.get("session_name"),
                "meeting_name": meeting.get("meeting_name") or session.get("location"),
                "session_type": session.get("session_type"),
                "circuit": session.get("circuit_short_name"),
                "location": session.get("location"),
                "started_at": started_at,
                "ended_at": ended_at,
                "gmt_offset": session.get("gmt_offset"),
                "total_laps": race_total_laps,
                "status": "STARTED",
            },
        )
    ]
    circuit_info = recording.get("circuit_info")
    circuit_payload = (
        circuit_info.get("payload") if isinstance(circuit_info, dict) else None
    )
    if _has_circuit_path(circuit_payload):
        x_values = circuit_payload["x"]
        y_values = circuit_payload["y"]
        events.append(
            NormalizedEvent(
                kind="circuit",
                occurred_at=started_at,
                source=source,
                payload={
                    "key": str(
                        circuit_payload.get("circuitKey")
                        or meeting.get("circuit_key")
                        or ""
                    )
                    or None,
                    "name": circuit_payload.get("circuitName")
                    or session.get("circuit_short_name"),
                    "year": circuit_payload.get("year"),
                    "rotation": circuit_payload.get("rotation"),
                    "path": tuple(
                        (float(x_value), float(y_value))
                        for x_value, y_value in zip(x_values, y_values, strict=True)
                    ),
                    "source": circuit_info.get("source_url"),
                    "availability": {"path": "available"},
                },
            )
        )
    else:
        events.append(
            NormalizedEvent(
                kind="circuit",
                occurred_at=started_at,
                source=source,
                payload={"availability": {"path": "unavailable"}},
            )
        )
    stints_by_driver: dict[str, list[dict[str, Any]]] = {}
    for stint in endpoints.get("stints", []):
        stints_by_driver.setdefault(str(stint["driver_number"]), []).append(stint)
    lap_windows: dict[str, list[tuple[datetime, int, float | None]]] = {}
    for lap in endpoints.get("laps", []):
        if lap.get("date_start") and lap.get("lap_number") is not None:
            duration = lap.get("lap_duration")
            lap_windows.setdefault(str(lap["driver_number"]), []).append(
                (
                    _as_datetime(lap["date_start"]),
                    int(lap["lap_number"]),
                    float(duration) if isinstance(duration, (int, float)) else None,
                )
            )
    for windows in lap_windows.values():
        windows.sort(key=lambda item: item[0])
    location_numbers = {
        str(item["driver_number"])
        for item in endpoints.get("location", [])
        if item.get("driver_number") is not None
    }
    for driver in endpoints.get("drivers", []):
        number = str(driver["driver_number"])
        has_intervals = bool(endpoints.get("intervals"))
        driver_stints = stints_by_driver.get(number, [])
        has_stints = bool(driver_stints)
        initial_stint = (
            min(driver_stints, key=lambda item: int(item.get("lap_start") or 1))
            if driver_stints
            else None
        )
        events.append(
            NormalizedEvent(
                kind="driver",
                occurred_at=started_at,
                source=source,
                payload={
                    "number": number,
                    "code": driver.get("name_acronym"),
                    "name": driver.get("full_name"),
                    "team": driver.get("team_name"),
                    "team_colour": driver.get("team_colour"),
                    "compound": initial_stint.get("compound")
                    if initial_stint
                    else None,
                    "tyre_age": int(initial_stint.get("tyre_age_at_start") or 0)
                    if initial_stint
                    else None,
                    "stint_laps": 0 if initial_stint else None,
                    "status": "RUNNING",
                    "availability": {
                        "interval_to_ahead": "available"
                        if has_intervals
                        else "unsupported",
                        "track_position": (
                            "available"
                            if has_intervals
                            and lap_windows.get(number)
                            else "unsupported"
                        ),
                        "compound": "available" if has_stints else "unavailable",
                        "tyre_age": "available" if has_stints else "unavailable",
                        "stint_laps": "available" if has_stints else "unavailable",
                        "pit_count": "available"
                        if "pit" in endpoints
                        else "unavailable",
                        "speed": "unsupported",
                        "gear": "unsupported",
                        "location_xy": "available"
                        if number in location_numbers
                        else "unsupported",
                    },
                },
            )
        )
    best_laps: dict[str, float] = {}
    pit_data_available = "pit" in endpoints
    pit_laps = {
        (str(item["driver_number"]), int(item["lap_number"]))
        for item in endpoints.get("pit", [])
        if item.get("driver_number") is not None
        and isinstance(item.get("lap_number"), int)
    }
    neutralized_laps = {
        int(item["lap_number"])
        for item in endpoints.get("race_control", [])
        if isinstance(item.get("lap_number"), int)
        and _is_neutralized_message(item)
    }
    for lap in endpoints.get("laps", []):
        if not lap.get("date_start"):
            continue
        number = str(lap["driver_number"])
        lap_number = lap.get("lap_number")
        duration = lap.get("lap_duration")
        best_lap = None
        if isinstance(duration, (int, float)) and duration > 0:
            previous_best = best_laps.get(number)
            if previous_best is None or duration < previous_best:
                best_laps[number] = float(duration)
                best_lap = _format_duration(duration)
        stint = _stint_for_lap(stints_by_driver.get(number, []), lap_number)
        stint_laps = None
        tyre_age = None
        compound = None
        if stint is not None and isinstance(lap_number, int):
            stint_laps = lap_number - int(stint["lap_start"]) + 1
            tyre_age = int(stint.get("tyre_age_at_start") or 0) + stint_laps
            compound = stint.get("compound")
        pit_in = None
        pit_out = None
        if pit_data_available and isinstance(lap_number, int):
            pit_in = (number, lap_number) in pit_laps
            pit_out = bool(lap.get("is_pit_out_lap")) or (
                (number, lap_number - 1) in pit_laps
            )
        contamination_reasons = []
        if pit_in:
            contamination_reasons.append("pit_in")
        if pit_out:
            contamination_reasons.append("pit_out")
        if isinstance(lap_number, int) and lap_number in neutralized_laps:
            contamination_reasons.append("neutralized_track")
        duration_value = (
            float(duration) if isinstance(duration, (int, float)) and duration > 0 else None
        )
        if duration_value is None:
            contamination_reasons.append("missing_duration")
        quality = (
            "unknown"
            if duration_value is None
            else "contaminated"
            if contamination_reasons
            else "representative"
        )
        observation = None
        if isinstance(lap_number, int):
            observation = {
                "lap": lap_number,
                "started_at": lap["date_start"],
                "duration": duration_value,
                "sector_1": lap.get("duration_sector_1"),
                "sector_2": lap.get("duration_sector_2"),
                "sector_3": lap.get("duration_sector_3"),
                "compound": compound,
                "stint_number": (
                    int(stint["stint_number"])
                    if stint is not None
                    and isinstance(stint.get("stint_number"), int)
                    else None
                ),
                "tyre_age": tyre_age,
                "pit_in": pit_in,
                "pit_out": pit_out,
                "quality": quality,
                "contamination_reasons": contamination_reasons,
            }
        events.append(
            _timing_event(
                lap["date_start"],
                number,
                lap=lap_number,
                last_lap=_format_duration(duration),
                best_lap=best_lap,
                compound=compound,
                tyre_age=tyre_age,
                stint_laps=stint_laps,
                sector_1=lap.get("duration_sector_1"),
                sector_2=lap.get("duration_sector_2"),
                sector_3=lap.get("duration_sector_3"),
                lap_observation=observation,
            )
        )
    for position in endpoints.get("position", []):
        if position.get("date"):
            events.append(
                _timing_event(
                    position["date"],
                    position["driver_number"],
                    position=position.get("position"),
                )
            )
    for interval in endpoints.get("intervals", []):
        if interval.get("date"):
            events.append(
                _timing_event(
                    interval["date"],
                    interval["driver_number"],
                    gap_to_leader=_format_gap(interval.get("gap_to_leader")),
                    interval_to_ahead=_format_gap(interval.get("interval")),
                    track_position=_estimate_track_position(
                        lap_windows.get(str(interval["driver_number"]), []),
                        interval["date"],
                    ),
                )
            )
    for location in endpoints.get("location", []):
        if location.get("date") and location.get("x") is not None and location.get("y") is not None:
            events.append(
                _timing_event(
                    location["date"],
                    location["driver_number"],
                    x=float(location["x"]),
                    y=float(location["y"]),
                    z=float(location["z"]) if location.get("z") is not None else None,
                )
            )
    pit_counts: dict[str, int] = {}
    for pit in sorted(endpoints.get("pit", []), key=lambda item: item.get("date", "")):
        if not pit.get("date"):
            continue
        number = str(pit["driver_number"])
        pit_counts[number] = pit_counts.get(number, 0) + 1
        events.append(_timing_event(pit["date"], number, pit_count=pit_counts[number]))
    for message in endpoints.get("race_control", []):
        if message.get("date") and message.get("message"):
            events.append(
                NormalizedEvent(
                    kind="race_control",
                    occurred_at=message["date"],
                    source=source,
                    payload={
                        "category": message.get("category") or "Unknown",
                        "message": message["message"],
                        "flag": message.get("flag"),
                        "scope": message.get("scope"),
                        "driver_number": (
                            str(message["driver_number"])
                            if message.get("driver_number") is not None
                            else None
                        ),
                        "sector": message.get("sector"),
                        "lap": message.get("lap_number"),
                    },
                )
            )
    weather_fields = (
        "air_temperature",
        "track_temperature",
        "humidity",
        "pressure",
        "rainfall",
        "wind_speed",
        "wind_direction",
    )
    events.append(
        NormalizedEvent(
            kind="weather",
            occurred_at=started_at,
            source=source,
            payload={"availability": {key: "unavailable" for key in weather_fields}},
        )
    )
    weather_rows = endpoints.get("weather", [])
    for weather in weather_rows:
        if not weather.get("date"):
            continue
        values = {
            key: (
                _as_rainfall(weather.get(key))
                if key == "rainfall"
                else weather.get(key)
            )
            for key in weather_fields
        }
        events.append(
            NormalizedEvent(
                kind="weather",
                occurred_at=weather["date"],
                source=source,
                payload={
                    **values,
                    "availability": {
                        key: "available" if value is not None else "unavailable"
                        for key, value in values.items()
                    },
                },
            )
        )
    result_numbers: set[str] = set()
    for result in results:
        result_numbers.add(str(result["driver_number"]))
        best_lap = None
        if session.get("session_type") != "Race":
            best_lap = _format_duration(_last_available(result.get("duration")))
        events.append(
            _timing_event(
                ended_at,
                result["driver_number"],
                position=result.get("position"),
                lap=result.get("number_of_laps"),
                gap_to_leader=_result_gap(result),
                best_lap=best_lap,
                status=_result_status(result),
            )
        )
    final_status = "CANCELLED" if session.get("is_cancelled") else "FINISHED"
    for driver in endpoints.get("drivers", []):
        number = str(driver["driver_number"])
        if number not in result_numbers:
            events.append(_timing_event(ended_at, number, status=final_status))
    events.append(
        NormalizedEvent(
            kind="session",
            occurred_at=ended_at,
            source=source,
            payload={
                "status": final_status,
                "lap": max(completed_laps) if completed_laps else None,
                "total_laps": race_total_laps,
                "track_status": "CANCELLED"
                if final_status == "CANCELLED"
                else "CHEQUERED",
            },
        )
    )
    from slipstream.events import parse_timestamp

    return sorted(events, key=lambda event: parse_timestamp(event.occurred_at))


def _first(
    endpoints: dict[str, Any], name: str, *, required: bool = True
) -> dict[str, Any] | None:
    items = endpoints.get(name, [])
    if items:
        return items[0]
    if required:
        raise ValueError(f"OpenF1 recording has no {name} data")
    return None


def _has_circuit_path(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    x_values = payload.get("x")
    y_values = payload.get("y")
    return (
        isinstance(x_values, list)
        and isinstance(y_values, list)
        and len(x_values) >= 3
        and len(x_values) == len(y_values)
        and all(isinstance(value, (int, float)) for value in (*x_values, *y_values))
    )


def _timing_event(
    occurred_at: str, driver_number: object, **updates: object
) -> NormalizedEvent:
    return NormalizedEvent(
        kind="timing",
        occurred_at=occurred_at,
        source="openf1",
        payload={
            "number": str(driver_number),
            **{key: value for key, value in updates.items() if value is not None},
        },
    )


def _format_duration(seconds: object) -> str | None:
    if not isinstance(seconds, (int, float)):
        return None
    minutes, remainder = divmod(float(seconds), 60)
    return f"{int(minutes)}:{remainder:06.3f}"


def _is_neutralized_message(message: dict[str, Any]) -> bool:
    flag = str(message.get("flag") or "").upper()
    text = str(message.get("message") or "").upper()
    return flag in {"YELLOW", "DOUBLE YELLOW", "RED"} or any(
        token in text for token in ("SAFETY CAR", "VIRTUAL SAFETY CAR", "RED FLAG")
    )

def _format_gap(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return _format_gap(_last_available(value))
    if isinstance(value, (int, float)):
        return f"+{float(value):.3f}"
    return str(value)


def _last_available(value: object) -> object:
    if isinstance(value, list):
        return next((item for item in reversed(value) if item is not None), None)
    return value


def _stint_for_lap(
    stints: list[dict[str, Any]], lap_number: object
) -> dict[str, Any] | None:
    if not isinstance(lap_number, int):
        return None
    for stint in stints:
        lap_start = stint.get("lap_start")
        lap_end = stint.get("lap_end")
        if not isinstance(lap_start, (int, float)):
            continue
        end = int(lap_end) if isinstance(lap_end, (int, float)) else lap_number
        if int(lap_start) <= lap_number <= end:
            return stint
    return None


def _as_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _estimate_track_position(
    windows: list[tuple[datetime, int, float | None]], timestamp: str
) -> float | None:
    if not windows:
        return None
    current_time = _as_datetime(timestamp)
    selected_index = next(
        (index - 1 for index, item in enumerate(windows) if item[0] > current_time),
        len(windows) - 1,
    )
    if selected_index < 0:
        return None
    started_at, _, duration = windows[selected_index]
    if selected_index + 1 < len(windows):
        lap_seconds = (windows[selected_index + 1][0] - started_at).total_seconds()
    else:
        lap_seconds = duration
    if not lap_seconds or lap_seconds <= 0:
        return None
    elapsed = (current_time - started_at).total_seconds()
    return round(max(0.0, min(0.999, elapsed / lap_seconds)), 3)


def _result_gap(result: dict[str, Any]) -> str | None:
    if result.get("position") == 1:
        return "LEADER"
    return _format_gap(result.get("gap_to_leader"))


def _result_status(result: dict[str, Any]) -> str:
    if result.get("dsq"):
        return "DISQUALIFIED"
    if result.get("dns"):
        return "DNS"
    if result.get("dnf"):
        return "DNF"
    return "FINISHED"


def _as_rainfall(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes"}
