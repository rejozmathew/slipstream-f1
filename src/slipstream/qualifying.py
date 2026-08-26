"""Cursor-safe, server-authored Qualifying session intelligence."""

from __future__ import annotations

from datetime import datetime
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
    2024: {20: {"Q1": 15, "Q2": 10, "SQ1": 15, "SQ2": 10}},
    2025: {20: {"Q1": 15, "Q2": 10, "SQ1": 15, "SQ2": 10}},
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

    sprint = resource.descriptor.session_kind == "sprint_qualifying"
    phase_boundaries = _phase_boundaries(resource, sequence, sprint=sprint)
    normalized_phase = str(state.session.qualifying_phase or "UNKNOWN").upper()
    phase_from_state = normalized_phase in QUALIFYING_PHASES
    phase = normalized_phase if phase_from_state else (
        _phase_at_sequence(phase_boundaries, sequence) or "UNKNOWN"
    )
    ordered = sorted(state.drivers.values(), key=lambda item: item.position or 999)
    attempts_by_driver = {
        driver.number: _attempts(resource, driver.number, sequence, sprint=sprint)
        for driver in ordered
    }
    scoped_best = {
        driver.number: _scope_best(driver, attempts_by_driver[driver.number], phase)
        for driver in ordered
    }
    benchmark = _benchmark(ordered, scoped_best)
    advancing_count = _advancing_count(
        resource.descriptor.year, state.session.eligible_field_size, phase
    )
    driver_payload: dict[str, dict[str, Any]] = {}
    for driver in ordered:
        best = scoped_best[driver.number]
        best_seconds = best[0] if best is not None else None
        cut_state = _cut_state(driver, advancing_count)
        segment_results = _segment_results(
            driver,
            attempts_by_driver[driver.number],
            sprint=sprint,
        )
        driver_payload[driver.number] = {
            "driverNumber": driver.number,
            "activity": _activity(driver),
            "scopeBest": best[1] if best is not None else None,
            "benchmarkDelta": (
                round(best_seconds - benchmark["seconds"], 3)
                if benchmark is not None and best_seconds is not None
                else None
            ),
            "cutState": cut_state,
            "qStatus": _q_status(driver),
            "segmentResults": segment_results,
            "attempts": attempts_by_driver[driver.number],
            "latestLap": _latest_lap(attempts_by_driver[driver.number]),
            "tyreUsage": driver.tyre_usage,
            "teammate": None,
        }

    for driver in ordered:
        teammate = next(
            (
                candidate
                for candidate in ordered
                if candidate.number != driver.number
                and candidate.team
                and candidate.team == driver.team
            ),
            None,
        )
        own_best = scoped_best.get(driver.number)
        teammate_best = scoped_best.get(teammate.number) if teammate else None
        if teammate is not None:
            comparison = "UNKNOWN"
            gap = None
            if own_best is not None and teammate_best is not None:
                gap = round(abs(own_best[0] - teammate_best[0]), 3)
                comparison = (
                    "FASTER"
                    if own_best[0] < teammate_best[0]
                    else "SLOWER"
                    if own_best[0] > teammate_best[0]
                    else "LEVEL"
                )
            driver_payload[driver.number]["teammate"] = {
                "driverNumber": teammate.number,
                "code": teammate.code,
                "comparison": comparison,
                "gapSeconds": gap,
            }

    cutoff = _driver_at(ordered, advancing_count)
    first_out = _driver_at(ordered, advancing_count + 1 if advancing_count else None)
    return {
        "status": "AVAILABLE",
        "phase": phase,
        "phaseEvidence": (
            "normalized public SessionData"
            if phase_from_state
            else "cursor-safe observed SessionStatus segment starts"
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
                "scope": "SEGMENT" if phase != "UNKNOWN" else "SESSION",
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
    resource: ReplayResource,
    driver_number: str,
    sequence: int,
    *,
    sprint: bool,
) -> list[dict[str, Any]]:
    items = [
        item
        for item in resource.evidence.lap_observations
        if item.driver_number == str(driver_number) and item.sequence <= sequence
    ]
    phase_boundaries = _phase_boundaries(resource, sequence, sprint=sprint)
    return [
        {
            "attempt": index,
            "phase": (
                item.observation.qualifying_phase
                if item.observation.qualifying_phase in QUALIFYING_PHASES
                else _phase_at_sequence(phase_boundaries, item.sequence) or "UNKNOWN"
            ),
            "lap": item.observation.lap,
            "lapTime": item.observation.duration,
            "sector1": item.observation.sector_1,
            "sector2": item.observation.sector_2,
            "sector3": item.observation.sector_3,
            "compound": item.observation.compound,
            "tyreAge": item.observation.tyre_age,
            "tyreUsage": item.observation.tyre_usage,
            "validity": item.observation.lap_validity,
            "classification": _attempt_classification(item.observation),
            "occurredAt": item.occurred_at,
        }
        for index, item in enumerate(items, start=1)
    ]


def _attempt_classification(observation: Any) -> str:
    if observation.pit_in is True and observation.pit_out is True:
        return "PIT"
    if observation.pit_in is True:
        return "IN"
    if observation.pit_out is True:
        return "OUT"
    if observation.duration is None:
        return "UNKNOWN"
    if observation.quality == "representative":
        return "TIMED"
    return "NON_REP"


def _latest_lap(attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    item = next(
        (
            candidate
            for candidate in reversed(attempts)
            if isinstance(candidate.get("lapTime"), (int, float))
        ),
        None,
    )
    if item is None:
        return None
    return {
        "lap": item["lap"],
        "lapTime": item["lapTime"],
        "sector1": item["sector1"],
        "sector2": item["sector2"],
        "sector3": item["sector3"],
        "classification": item["classification"],
    }


def _phase_boundaries(
    resource: ReplayResource,
    sequence: int,
    *,
    sprint: bool,
) -> list[tuple[int, str]]:
    phases = ("SQ1", "SQ2", "SQ3") if sprint else ("Q1", "Q2", "Q3")
    starts: list[tuple[int, str]] = []
    last_started_at: str | None = None
    for event_sequence, event in enumerate(resource.events, start=1):
        if event_sequence > sequence:
            break
        is_initial_start = (
            event.kind == "session"
            and event.payload.get("status") == "RUNNING"
            and event.payload.get("layout_family") == "qualifying"
        )
        is_segment_start = (
            event.kind == "race_control"
            and event.payload.get("category") == "SessionStatus"
            and event.payload.get("message") == "SESSION STARTED"
        )
        if not (is_initial_start or is_segment_start):
            continue
        if last_started_at is not None:
            current = _timestamp_seconds(event.occurred_at)
            previous = _timestamp_seconds(last_started_at)
            if current is not None and previous is not None and current - previous < 60:
                continue
        if len(starts) >= len(phases):
            break
        starts.append((event_sequence, phases[len(starts)]))
        last_started_at = event.occurred_at
    return starts


def _phase_at_sequence(
    boundaries: list[tuple[int, str]], sequence: int
) -> str | None:
    phase = None
    for boundary_sequence, candidate in boundaries:
        if boundary_sequence > sequence:
            break
        phase = candidate
    return phase


def _timestamp_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def _scope_best(
    driver: DriverState, attempts: list[dict[str, Any]], phase: str
) -> tuple[float, str] | None:
    candidates = [
        float(item["lapTime"])
        for item in attempts
        if isinstance(item.get("lapTime"), (int, float))
        and (phase == "UNKNOWN" or item.get("phase") == phase)
    ]
    results = driver.qualifying_results
    if results is not None:
        index = {"Q1": 0, "SQ1": 0, "Q2": 1, "SQ2": 1, "Q3": 2, "SQ3": 2}.get(phase)
        values = results if index is None else (results[index],)
        candidates.extend(float(value) for value in values if value is not None)
    if not candidates:
        return None
    seconds = min(candidates)
    return seconds, _format_duration(seconds)


def _benchmark(
    drivers: list[DriverState], scoped_best: dict[str, tuple[float, str] | None]
) -> dict[str, Any] | None:
    candidates = []
    for driver in drivers:
        best = scoped_best.get(driver.number)
        if best is not None:
            candidates.append((best[0], driver, best[1]))
    if not candidates:
        return None
    seconds, driver, lap_time = min(candidates, key=lambda item: item[0])
    return {"seconds": seconds, "driver": driver, "lapTime": lap_time}


def _advancing_count(year: int, field_size: int | None, phase: str) -> int | None:
    if field_size is None:
        return None
    return _ADVANCING_COUNTS.get(year, {}).get(field_size, {}).get(phase)


def _cut_state(driver: DriverState, advancing_count: int | None) -> str:
    if driver.qualifying_eliminated is True:
        return "ELIMINATED"
    if advancing_count is None or driver.position is None:
        return "UNKNOWN"
    return "ADVANCING" if driver.position <= advancing_count else "BELOW_CUT"


def _activity(driver: DriverState) -> str:
    if driver.activity in {"ON_TRACK", "IN_PIT"}:
        return driver.activity
    return "UNKNOWN"


def _segment_results(
    driver: DriverState,
    attempts: list[dict[str, Any]],
    *,
    sprint: bool,
) -> list[float | None]:
    if driver.qualifying_results is not None:
        return list(driver.qualifying_results)
    phases = ("SQ1", "SQ2", "SQ3") if sprint else ("Q1", "Q2", "Q3")
    results: list[float | None] = []
    for phase in phases:
        candidates = [
            float(item["lapTime"])
            for item in attempts
            if item.get("phase") == phase
            and item.get("validity") != "INVALID"
            and isinstance(item.get("lapTime"), (int, float))
        ]
        results.append(min(candidates) if candidates else None)
    return results


def _q_status(driver: DriverState) -> str | None:
    status = str(driver.status or "").upper()
    if status in {"DNS", "NOT_STARTING", "SCRATCHED", "WITHDRAWN"}:
        return "DNS"
    if status in {"DSQ", "DISQUALIFIED"}:
        return "DSQ"
    if driver.qualifying_eliminated is True:
        return f"OUT {driver.qualifying_phase_reached}" if driver.qualifying_phase_reached else None
    if driver.qualifying_results is not None and driver.qualifying_phase_reached:
        return driver.qualifying_phase_reached
    return None


def _driver_at(drivers: list[DriverState], position: int | None) -> DriverState | None:
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


def _format_duration(seconds: float) -> str:
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}:{remainder:06.3f}" if minutes else f"{remainder:.3f}"


def _unknown_cut_line() -> dict[str, Any]:
    return {
        "advancePosition": None,
        "cutoff": None,
        "firstOut": None,
        "status": "UNKNOWN",
    }
