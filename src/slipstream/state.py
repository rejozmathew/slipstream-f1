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


@dataclass(frozen=True)
class SessionState:
    key: str | None = None
    name: str | None = None
    meeting_name: str | None = None
    session_type: str | None = None
    circuit: str | None = None
    location: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    gmt_offset: str | None = None
    local_time: str | None = None
    lap: int | None = None
    total_laps: int | None = None
    track_status: str | None = None
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
            session = replace(self.session, **event.payload)
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
            item = replace(
                current, **{k: v for k, v in event.payload.items() if k != "number"}
            )
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
            explicit_availability = updates.pop("availability", {})
            availability = {
                **current.availability,
                **{key: "available" for key in updates},
                **explicit_availability,
            }
            item = replace(current, **updates)
            item = replace(item, availability=availability)
            session = self.session
            event_lap = updates.get("lap")
            if isinstance(event_lap, int) and (
                session.lap is None or event_lap > session.lap
            ):
                session = replace(session, lap=event_lap)
            return replace(
                self,
                updated_at=event.occurred_at,
                session=_with_local_time(session, event.occurred_at),
                drivers={**self.drivers, number: item},
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
            track_status = _track_status_from(item)
            if track_status:
                session = replace(session, track_status=track_status)
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


def _track_status_from(message: RaceControlMessage) -> str | None:
    """Return only observed whole-track transitions."""

    scope = message.scope.upper() if message.scope else None
    if scope not in (None, "TRACK") or message.driver_number is not None:
        return None
    flag = message.flag.upper() if message.flag else None
    if scope == "TRACK" and flag in {
        "GREEN",
        "YELLOW",
        "DOUBLE YELLOW",
        "RED",
        "CHEQUERED",
    }:
        return flag
    if scope == "TRACK" and flag == "CLEAR":
        return "GREEN"
    category = message.category.upper()
    text = message.message.upper().strip()
    if category == "SAFETYCAR" and text == "VIRTUAL SAFETY CAR DEPLOYED":
        return "VSC"
    if category == "SAFETYCAR" and text == "SAFETY CAR DEPLOYED":
        return "SAFETY CAR"
    if text.startswith("RED FLAG") and (flag == "RED" or "RACE SUSPENDED" in text):
        return "RED"
    return None
