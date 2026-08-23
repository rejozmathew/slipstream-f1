"""Cursor-safe, server-authored Qualifying session intelligence."""

from __future__ import annotations

from typing import Any

from .library import ReplayResource
from .state import DriverState, RaceState

QUALIFYING_PHASES = ("Q1", "Q2", "Q3", "SQ1", "SQ2", "SQ3")
QUALIFYING_MODEL_VERSION = "qualifying-intelligence-v1"

# Verified rule profiles for the primary historical/live corpus. A field size
# outside these explicit profiles remains UNKNOWN rather than inheriting a
# timeless top-15 assumption.
_ADVANCING_COUNTS: dict[int, dict[int, dict[str, int]]] = {
    2023: {20: {"Q1": 15, "Q2": 10, "SQ1": 15, "SQ2": 10}},
    2026: {22: {"Q1": 16, "Q2": 10, "SQ1": 16, "SQ2": 10}},
}


def build_qualifying_snapshot(
    resource: ReplayResource,
    state: RaceState,
    *,
    sequence: int,
) -> dict[str, Any]:
    if resource.descriptor.layout_family != "qualifying":
        return {
            "status": "NOT_APPLICABLE",
            "phase": "UNKNOWN",
            "sessionClock": None,
            "benchmark": None,
            "cutLine": _unknown_cut_line(),
            "drivers": {},
            "modelVersion": QUALIFYING_MODEL_VERSION,
        }

    phase = str(state.session.qualifying_phase or "UNKNOWN").upper()
    if phase not in QUALIFYING_PHASES:
        phase = "UNKNOWN"
    ordered = sorted(state.drivers.values(), key=lambda item: item.position or 999)
    attempts_by_driver = {
        driver.number: _attempts(resource, driver.number, sequence)
        for driver in ordered
    }
    benchmark = _benchmark(ordered, phase)
    advancing_count = _advancing_count(
        resource.descriptor.year, len(ordered), phase
    )
    driver_payload: dict[str, dict[str, Any]] = {}
    for driver in ordered:
        best_seconds = _duration_seconds(driver.best_lap or driver.last_lap)
        driver_payload[driver.number] = {
            "driverNumber": driver.number,
            "activity": _activity(driver),
            "benchmarkDelta": (
                round(best_seconds - benchmark["seconds"], 3)
                if benchmark is not None and best_seconds is not None
                else None
            ),
            "cutState": _cut_state(driver, advancing_count),
            "attempts": attempts_by_driver[driver.number],
            "tyreUsage": driver.tyre_usage,
        }

    cutoff = _driver_at(ordered, advancing_count)
    first_out = _driver_at(ordered, advancing_count + 1 if advancing_count else None)
    return {
        "status": "AVAILABLE",
        "phase": phase,
        "phaseEvidence": (
            "normalized public SessionData"
            if phase != "UNKNOWN"
            else "phase is not established by normalized source evidence"
        ),
        "sessionClock": state.session.session_clock,
        "sessionClockRunning": state.session.session_clock_running,
        "benchmark": (
            {
                "driverNumber": benchmark["driver"].number,
                "code": benchmark["driver"].code,
                "lapTime": benchmark["lapTime"],
            }
            if benchmark is not None
            else None
        ),
        "cutLine": {
            "advancePosition": advancing_count,
            "cutoff": _driver_summary(cutoff),
            "firstOut": _driver_summary(first_out),
            "status": "AVAILABLE" if advancing_count is not None else "UNKNOWN",
        },
        "drivers": driver_payload,
        "modelVersion": QUALIFYING_MODEL_VERSION,
    }


def _attempts(
    resource: ReplayResource, driver_number: str, sequence: int
) -> list[dict[str, Any]]:
    items = [
        item
        for item in resource.evidence.lap_observations
        if item.driver_number == str(driver_number) and item.sequence <= sequence
    ]
    return [
        {
            "attempt": index,
            "phase": item.observation.qualifying_phase,
            "lap": item.observation.lap,
            "lapTime": item.observation.duration,
            "sector1": item.observation.sector_1,
            "sector2": item.observation.sector_2,
            "sector3": item.observation.sector_3,
            "compound": item.observation.compound,
            "tyreAge": item.observation.tyre_age,
            "tyreUsage": item.observation.tyre_usage,
            "validity": item.observation.lap_validity,
            "occurredAt": item.occurred_at,
        }
        for index, item in enumerate(items, start=1)
    ]


def _benchmark(
    drivers: list[DriverState], phase: str
) -> dict[str, Any] | None:
    if phase == "UNKNOWN":
        return None
    candidates = []
    for driver in drivers:
        lap_time = driver.best_lap or driver.last_lap
        seconds = _duration_seconds(lap_time)
        if seconds is not None:
            candidates.append((seconds, driver, lap_time))
    if not candidates:
        return None
    seconds, driver, lap_time = min(candidates, key=lambda item: item[0])
    return {"seconds": seconds, "driver": driver, "lapTime": lap_time}


def _advancing_count(year: int, field_size: int, phase: str) -> int | None:
    return _ADVANCING_COUNTS.get(year, {}).get(field_size, {}).get(phase)


def _cut_state(driver: DriverState, advancing_count: int | None) -> str:
    if driver.qualifying_eliminated is True:
        return "ELIMINATED"
    if advancing_count is None or driver.position is None:
        return "UNKNOWN"
    return "ADVANCING" if driver.position <= advancing_count else "BELOW_CUT"


def _activity(driver: DriverState) -> str:
    if driver.activity in {"ON_TRACK", "IN_PIT", "NO_RECENT_PROGRESS"}:
        return driver.activity
    return "UNKNOWN"


def _driver_at(
    drivers: list[DriverState], position: int | None
) -> DriverState | None:
    if position is None:
        return None
    return next((driver for driver in drivers if driver.position == position), None)


def _driver_summary(driver: DriverState | None) -> dict[str, Any] | None:
    if driver is None:
        return None
    return {
        "driverNumber": driver.number,
        "code": driver.code,
        "position": driver.position,
        "bestLap": driver.best_lap or driver.last_lap,
    }


def _duration_seconds(value: str | None) -> float | None:
    if not value:
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


def _unknown_cut_line() -> dict[str, Any]:
    return {
        "advancePosition": None,
        "cutoff": None,
        "firstOut": None,
        "status": "UNKNOWN",
    }
