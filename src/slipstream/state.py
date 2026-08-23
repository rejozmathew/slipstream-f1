"""Canonical immutable normalized race state and reducer."""

from __future__ import annotations

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
    activity: str = "UNKNOWN"
    progress_observed_at_lap: int | None = None
    qualifying_eliminated: bool | None = None


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
                and self.session.status == "SUSPENDED"
            ):
                updates["control_status"] = "NORMAL"
            session = replace(self.session, **updates)
            if updates.keys() & {"status", "control_status", "marshal_status"}:
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
            item = replace(current, **updates)
            return replace(
                self,
                updated_at=event.occurred_at,
                session=_with_local_time(self.session, event.occurred_at),
                drivers={**self.drivers, number: item},
            )
        if event.kind == "timing":
            number = str(event.payload["number"])
            current = self.drivers.get(number, DriverState(number=number))
            updates = {k: v for k, v in event.payload.items() if k != "number"}
            # Completed-lap evidence is retained by SessionEvidence, not repeated in
            # every high-frequency RaceState snapshot.
            updates.pop("lap_observation", None)
            if "status" in updates:
                from .lifecycle import transition_driver_status

                updates["status"] = transition_driver_status(
                    current.status, updates["status"]
                )
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
                "RETIRED", "DNF", "DNS", "DISQUALIFIED", "DSQ", "WITHDRAWN"
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
            drivers = _with_progress_activity(
                {**self.drivers, number: item}, session
            )
            return replace(
                self,
                updated_at=event.occurred_at,
                session=_with_local_time(session, event.occurred_at),
                drivers=drivers,
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
            session = self.session
            updates = _session_updates_from_race_control(item)
            if (
                updates.get("control_status") == "NORMAL"
                and session.control_status == "RED_FLAG"
            ):
                updates.pop("control_status")
            if updates:
                session = _with_display_status(replace(session, **updates))
            return replace(
                self,
                updated_at=event.occurred_at,
                session=_with_local_time(session, event.occurred_at),
                race_control=(*self.race_control, item),
            )
        raise ValueError(f"Unsupported event kind: {event.kind}")


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


def _session_updates_from_race_control(
    message: RaceControlMessage,
) -> dict[str, str]:
    """Return observed session-control or marshal transitions only."""

    scope = message.scope.upper() if message.scope else None
    if scope not in (None, "TRACK") or message.driver_number is not None:
        return {}
    flag = message.flag.upper() if message.flag else None
    if scope == "TRACK" and flag == "GREEN":
        return {"marshal_status": "ALL_CLEAR", "control_status": "NORMAL"}
    if scope == "TRACK" and flag in {"YELLOW", "DOUBLE YELLOW"}:
        return {"marshal_status": "YELLOW"}
    if scope == "TRACK" and flag == "RED":
        return {"marshal_status": "RED"}
    if scope == "TRACK" and flag == "CHEQUERED":
        return {"control_status": "CHEQUERED"}
    if scope == "TRACK" and flag == "CLEAR":
        return {"marshal_status": "ALL_CLEAR", "control_status": "NORMAL"}
    category = message.category.upper()
    text = message.message.upper().strip()
    if category == "SAFETYCAR" and text == "VIRTUAL SAFETY CAR DEPLOYED":
        return {"control_status": "VSC"}
    if category == "SAFETYCAR" and "VIRTUAL SAFETY CAR ENDING" in text:
        return {"control_status": "VSC_ENDING"}
    if category == "SAFETYCAR" and text == "SAFETY CAR DEPLOYED":
        return {"control_status": "SAFETY_CAR"}
    if text.startswith("RED FLAG") and (flag == "RED" or "RACE SUSPENDED" in text):
        return {"control_status": "RED_FLAG"}
    return {}


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
    if session.status.upper() == "SUSPENDED" or control == "RED_FLAG":
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
        display, legacy = "ALL_CLEAR", "GREEN"
    else:
        display, legacy = "UNKNOWN", None
    return replace(session, display_status=display, track_status=legacy)


def _with_progress_activity(
    drivers: dict[str, DriverState], session: SessionState
) -> dict[str, DriverState]:
    """Mark conservative non-terminal circulation gaps from source lap progress."""
    if (
        session.layout_family != "race"
        or session.lap is None
        or str(session.status).upper() in {"FINISHED", "ENDED", "COMPLETE", "FINAL"}
    ):
        return drivers
    terminal = {"RETIRED", "DNF", "DNS", "DISQUALIFIED", "DSQ", "WITHDRAWN"}
    result = dict(drivers)
    for number, driver in drivers.items():
        if (
            str(driver.status).upper() in terminal
            or driver.activity == "IN_PIT"
            or driver.progress_observed_at_lap is None
        ):
            continue
        if session.lap - driver.progress_observed_at_lap >= 2:
            result[number] = replace(driver, activity="NO_RECENT_PROGRESS")
    return result
