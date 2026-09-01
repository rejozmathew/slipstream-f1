"""Canonical immutable normalized race state and reducer."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import timedelta, timezone

from .events import NormalizedEvent, parse_timestamp


@dataclass(frozen=True)
class DriverState:
    number: str
    code: str | None = None
    name: str | None = None
    team: str | None = None
    team_colour: str | None = None
    position: int | None = None
    lap: int | None = None
    gap_to_leader: str | None = None
    interval_to_ahead: str | None = None
    last_lap: str | None = None
    best_lap: str | None = None
    compound: str | None = None
    tyre_age: int | None = None
    stint_laps: int | None = None
    tyre_usage: str = "UNKNOWN"
    pit_count: int = 0
    track_position: float | None = None
    x: float | None = None
    y: float | None = None
    z: float | None = None
    sector_1: float | None = None
    sector_2: float | None = None
    sector_3: float | None = None
    availability: dict[str, str] = field(default_factory=dict)
    status: str = "UNKNOWN"
    classification: str | None = None
    source_condition: str = "UNKNOWN"
    source_retired: bool | None = None
    source_stopped: bool | None = None
    activity: str = "UNKNOWN"
    progress_observed_at_lap: int | None = None
    qualifying_eliminated: bool | None = None
    qualifying_results: tuple[float | None, float | None, float | None] | None = None
    qualifying_phase_reached: str | None = None


@dataclass(frozen=True)
class SessionState:
    key: str | None = None
    name: str | None = None
    meeting_name: str | None = None
    session_type: str | None = None
    session_kind: str = "unknown"
    layout_family: str = "unsupported"
    circuit: str | None = None
    location: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    gmt_offset: str | None = None
    local_time: str | None = None
    lap: int | None = None
    total_laps: int | None = None
    track_status: str | None = None
    control_status: str = "UNKNOWN"
    marshal_status: str = "UNKNOWN"
    display_status: str = "UNKNOWN"
    qualifying_phase: str = "UNKNOWN"
    eligible_field_size: int | None = None
    session_clock: str | None = None
    session_clock_running: bool | None = None
    status: str = "UNKNOWN"


@dataclass(frozen=True)
class WeatherState:
    updated_at: str | None = None
    air_temperature: float | None = None
    track_temperature: float | None = None
    humidity: float | None = None
    pressure: float | None = None
    rainfall: bool | None = None
    wind_speed: float | None = None
    wind_direction: int | None = None
    availability: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CircuitState:
    key: str | None = None
    name: str | None = None
    year: int | None = None
    rotation: float | None = None
    path: tuple[tuple[float, float], ...] = ()
    source: str | None = None
    availability: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RaceControlMessage:
    occurred_at: str
    category: str
    message: str
    flag: str | None = None
    scope: str | None = None
    driver_number: str | None = None
    sector: int | None = None
    lap: int | None = None


@dataclass(frozen=True)
class RaceState:
    schema_version: int = 1
    updated_at: str | None = None
    session: SessionState = field(default_factory=SessionState)
    circuit: CircuitState = field(default_factory=CircuitState)
    weather: WeatherState = field(default_factory=WeatherState)
    drivers: dict[str, DriverState] = field(default_factory=dict)
    race_control: tuple[RaceControlMessage, ...] = ()

    def apply(self, event: NormalizedEvent) -> RaceState:
        if event.kind == "session":
            updates = dict(event.payload)
            explicit_display_status = "display_status" in updates
            legacy_track_status = updates.pop("track_status", None)
            if legacy_track_status is not None:
                for key, value in _legacy_track_updates(legacy_track_status).items():
                    updates.setdefault(key, value)
            if (
                updates.get("control_status") == "NORMAL"
                and self.session.control_status == "RED_FLAG"
            ):
                explicit_resumption = (
                    self.session.status == "SUSPENDED"
                    and updates.get("status") == "RUNNING"
                )
                if not explicit_resumption:
                    updates.pop("control_status")
            if (
                updates.get("status") == "RUNNING"
                and self.session.status in {"SUSPENDED", "FINISHED", "SCHEDULED"}
            ):
                # An explicit session restart/resumption is authoritative. It
                # may close a terminal segment or suspended interval; a
                # marshal-only TRACK CLEAR event still cannot do so.
                updates["control_status"] = "NORMAL"
            session = replace(self.session, **updates)
            if (
                updates.keys() & {"status", "control_status", "marshal_status"}
                and not explicit_display_status
            ):
                session = _with_display_status(session)
            elif legacy_track_status is not None:
                session = replace(session, track_status=str(legacy_track_status))
            return replace(
                self,
                updated_at=event.occurred_at,
                session=_with_local_time(session, event.occurred_at),
            )
        if event.kind == "circuit":
            updates = dict(event.payload)
            path = updates.get("path")
            if isinstance(path, (list, tuple)):
                updates["path"] = tuple(
                    (float(point[0]), float(point[1]))
                    for point in path
                    if isinstance(point, (list, tuple)) and len(point) >= 2
                )
            explicit_availability = updates.pop("availability", {})
            availability = {
                **self.circuit.availability,
                **explicit_availability,
            }
            return replace(
                self,
                updated_at=event.occurred_at,
                session=_with_local_time(self.session, event.occurred_at),
                circuit=replace(self.circuit, **updates, availability=availability),
            )
        if event.kind == "driver":
            number = str(event.payload["number"])
            current = self.drivers.get(number, DriverState(number=number))
            updates = {k: v for k, v in event.payload.items() if k != "number"}
            if "status" in updates:
                from .lifecycle import transition_driver_status

                updates["status"] = transition_driver_status(
                    current.status, updates["status"]
                )
            updates = _with_driver_lifecycle_projection(current, updates)
            item = replace(current, **updates)
            return replace(
                self,
                updated_at=event.occurred_at,
                session=_with_local_time(self.session, event.occurred_at),
                drivers=_with_monotonic_gaps({**self.drivers, number: item}),
            )
        if event.kind == "timing":
            number = str(event.payload["number"])
            current = self.drivers.get(number, DriverState(number=number))
            updates = {k: v for k, v in event.payload.items() if k != "number"}
            # Completed-lap evidence is retained by SessionEvidence, not repeated in
            # every high-frequency RaceState snapshot.
            updates.pop("lap_observation", None)
            updates.pop("pit_observation", None)
            if "status" in updates:
                from .lifecycle import transition_driver_status

                updates["status"] = transition_driver_status(
                    current.status, updates["status"]
                )
            updates = _with_driver_lifecycle_projection(current, updates)
            session = self.session
            event_lap = updates.get("lap")
            progressed = isinstance(event_lap, int) and (
                current.lap is None or event_lap > current.lap
            )
            if isinstance(event_lap, int) and (
                session.lap is None or event_lap > session.lap
            ):
                session = replace(session, lap=event_lap)
            if progressed:
                updates.setdefault("activity", "ON_TRACK")
                # Store the driver's own last proven lap for the deterministic gap rule.
                updates["progress_observed_at_lap"] = event_lap
            if str(updates.get("status") or "").upper() in {
                "RETIRED",
                "DNF",
                "DNS",
                "DISQUALIFIED",
                "DSQ",
                "WITHDRAWN",
            }:
                updates["activity"] = "UNKNOWN"
            explicit_availability = updates.pop("availability", {})
            availability = {
                **current.availability,
                **{
                    key: "available"
                    for key in updates
                    if key not in {"activity", "progress_observed_at_lap"}
                },
                **explicit_availability,
            }
            item = replace(current, **updates, availability=availability)
            return replace(
                self,
                updated_at=event.occurred_at,
                session=_with_local_time(session, event.occurred_at),
                drivers=_with_monotonic_gaps({**self.drivers, number: item}),
            )
        if event.kind == "weather":
            updates = dict(event.payload)
            explicit_availability = updates.pop("availability", {})
            availability = {
                **self.weather.availability,
                **{key: "available" for key in updates if key != "updated_at"},
                **explicit_availability,
            }
            weather = replace(
                self.weather,
                **updates,
                updated_at=event.occurred_at,
                availability=availability,
            )
            return replace(
                self,
                updated_at=event.occurred_at,
                session=_with_local_time(self.session, event.occurred_at),
                weather=weather,
            )
        if event.kind == "race_control":
            item = RaceControlMessage(occurred_at=event.occurred_at, **event.payload)
            return replace(
                self,
                updated_at=event.occurred_at,
                session=_with_local_time(self.session, event.occurred_at),
                race_control=(*self.race_control, item),
            )
        raise ValueError(f"Unsupported event kind: {event.kind}")


def _with_monotonic_gaps(drivers: dict[str, DriverState]) -> dict[str, DriverState]:
    """Mask cross-packet gaps that cannot form a valid classified tower.

    OpenF1 position and interval packets are independently timestamped. When
    a stale numeric gap moves behind a newer position it must become
    unavailable, not be presented as a same-snapshot ordering fact.
    """

    result = dict(drivers)
    largest = 0.0
    for driver in sorted(
        (item for item in result.values() if item.position is not None),
        key=lambda item: item.position or 999,
    ):
        if driver.position == 1:
            largest = 0.0
            continue
        value = _numeric_gap_seconds(driver.gap_to_leader)
        if value is None:
            continue
        if value + 1e-9 < largest:
            availability = {**driver.availability, "gap_to_leader": "unavailable"}
            result[driver.number] = replace(
                driver,
                gap_to_leader=None,
                availability=availability,
            )
            continue
        largest = value
    return result


def _numeric_gap_seconds(value: str | None) -> float | None:
    if not value or "LAP" in value.upper():
        return None
    match = re.search(r"-?\d+(?:[.,]\d+)?", value)
    if match is None:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def _with_local_time(session: SessionState, occurred_at: str) -> SessionState:
    if not session.gmt_offset:
        return session
    try:
        raw = session.gmt_offset
        sign = -1 if raw.startswith("-") else 1
        hours, minutes, seconds = (int(part) for part in raw.lstrip("+-").split(":"))
        offset = timezone(
            sign * timedelta(hours=hours, minutes=minutes, seconds=seconds)
        )
        local_time = parse_timestamp(occurred_at).astimezone(offset).isoformat()
    except (TypeError, ValueError):
        return session
    return replace(session, local_time=local_time)


def _legacy_track_updates(value: object) -> dict[str, str]:
    normalized = str(value or "").upper().replace("_", " ")
    if normalized in {"GREEN", "ALL CLEAR"}:
        return {"marshal_status": "ALL_CLEAR", "control_status": "NORMAL"}
    if normalized in {"YELLOW", "DOUBLE YELLOW"}:
        return {"marshal_status": "YELLOW"}
    if normalized == "RED":
        return {"marshal_status": "RED"}
    controls = {
        "RED FLAG": "RED_FLAG",
        "SAFETY CAR": "SAFETY_CAR",
        "VSC": "VSC",
        "VSC ENDING": "VSC_ENDING",
        "CHEQUERED": "CHEQUERED",
    }
    control = controls.get(normalized)
    return {"control_status": control} if control else {}


def _with_display_status(session: SessionState) -> SessionState:
    control = session.control_status.upper()
    marshal = session.marshal_status.upper()
    if session.status.upper() == "CANCELLED":
        display, legacy = "CANCELLED", "CANCELLED"
    elif session.status.upper() == "SUSPENDED" or control == "RED_FLAG":
        display, legacy = "RED_FLAG", "RED FLAG"
    elif control == "SAFETY_CAR":
        display, legacy = "SAFETY_CAR", "SAFETY CAR"
    elif control == "VSC":
        display, legacy = "VSC", "VSC"
    elif control == "VSC_ENDING":
        display, legacy = "VSC_ENDING", "VSC ENDING"
    elif control == "CHEQUERED":
        display, legacy = "CHEQUERED", "CHEQUERED"
    elif marshal == "RED":
        display, legacy = "RED", "RED"
    elif marshal == "YELLOW":
        display, legacy = "YELLOW", "YELLOW"
    elif marshal == "ALL_CLEAR":
        display, legacy = "GREEN", "GREEN"
    else:
        display, legacy = "UNKNOWN", None
    return replace(session, display_status=display, track_status=legacy)


def _with_driver_lifecycle_projection(
    current: DriverState, updates: dict[str, object]
) -> dict[str, object]:
    """Project separate source-condition/final facts onto the legacy status field."""

    result = dict(updates)
    classification = result.get("classification", current.classification)
    if classification is not None:
        value = str(classification).upper()
        result["classification"] = value
        result["status"] = value
        return result
    condition = result.get("source_condition")
    if condition is None:
        return result
    projected = {
        "RETIRED_INDICATED": "RETIRED",
        "STOPPED": "STOPPED",
        "IN_PIT": "RUNNING",
        "RUNNING": "RUNNING",
        "UNKNOWN": "UNKNOWN",
    }.get(str(condition).upper(), "UNKNOWN")
    # Provider conditions are explicitly retractable and bypass the terminal
    # transition guard.  Only classification is irreversible.
    result["status"] = projected
    return result
