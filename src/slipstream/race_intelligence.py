"""Deterministic race-intelligence helpers over canonical state and evidence."""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median
from typing import Any

from .evidence import LapObservation, PitEvent
from .lifecycle import (
    is_circulating,
    is_session_participant,
    is_stopped,
    is_terminal,
)
from .state import DriverState, RaceState

RACE_PHASE_BANDS = (
    ("OPENING", 0.0, 0.25),
    ("EARLY", 0.25, 0.50),
    ("MIDDLE", 0.50, 0.75),
    ("LATE", 0.75, 1.01),
)
PHASE_WEIGHTS = {0: 1.0, 1: 0.5, 2: 0.2, 3: 0.1}
MIN_FINISH_STINT_SAMPLES = 3
MIN_FINISH_EFFECTIVE_WEIGHT = 2.0
MAX_FINISH_PACE_FADE = 0.25
MEANINGFUL_BATTLE_GAP_SECONDS = 12.0
BATTLE_HOLD_SECONDS = 20.0
BATTLE_HISTORY_MAX_SAMPLES = 40
WHOLE_TRACK_RESET_STATES = frozenset({"SAFETY CAR", "VSC", "VSC ENDING", "RED", "RED FLAG"})


def race_phase(lap: int | None, total_laps: int | None) -> str | None:
    if not lap or not total_laps or total_laps <= 0:
        return None
    progress = max(0.0, min(1.0, lap / total_laps))
    return next(name for name, lower, upper in RACE_PHASE_BANDS if lower <= progress < upper)


def phase_weight(sample_lap: int, current_lap: int, total_laps: int) -> float:
    names = [item[0] for item in RACE_PHASE_BANDS]
    sample = race_phase(sample_lap, total_laps)
    current = race_phase(current_lap, total_laps)
    if sample is None or current is None:
        return 0.0
    return PHASE_WEIGHTS[abs(names.index(sample) - names.index(current))]


def finish_assessment(
    driver: DriverState,
    state: RaceState,
    evidence_by_driver: dict[str, tuple[LapObservation, ...]],
    pace_trend: dict[str, Any],
    dry_rule_state: str,
) -> dict[str, Any]:
    """Assess live reach-to-flag feasibility without turning absence into a plan."""

    current_lap = state.session.lap
    total_laps = state.session.total_laps
    if is_terminal(driver) or _session_final(state):
        return _unknown_finish("terminal drivers/races have no live TO_FINISH outlook")
    if state.session.session_kind not in {"race", "sprint"}:
        return _unknown_finish("TO_FINISH is only defined for Race and Sprint")
    if str(state.session.track_status or "").upper() in WHOLE_TRACK_RESET_STATES:
        return _unknown_finish("whole-track neutralization invalidates finish projection")
    if dry_rule_state not in {"SATISFIED", "NOT_APPLICABLE"}:
        return _unknown_finish("dry-tyre rule state does not prove a legal run to the flag")
    if not current_lap or not total_laps or driver.tyre_age is None or not driver.compound:
        return _unknown_finish("race lap, total laps, current compound, and tyre age are required")
    trend = pace_trend.get("value")
    if not isinstance(trend, (int, float)):
        return _unknown_finish("current-driver clean current-stint Pace Trend is required")
    if trend > MAX_FINISH_PACE_FADE:
        return _unknown_finish(
            f"current Pace Fade {trend:.3f}s/lap exceeds the {MAX_FINISH_PACE_FADE:.2f}s/lap finish gate"
        )

    samples: list[tuple[int, float]] = []
    compound = driver.compound.upper()
    for observations in evidence_by_driver.values():
        for item in observations:
            previous = (item.previous_compound or item.compound or "").upper()
            if item.pit_in is not True or previous != compound or item.tyre_age is None:
                continue
            weight = phase_weight(item.lap, current_lap, total_laps)
            if weight > 0:
                samples.append((item.tyre_age, weight))
    effective = sum(weight for _, weight in samples)
    if len(samples) < MIN_FINISH_STINT_SAMPLES or effective < MIN_FINISH_EFFECTIVE_WEIGHT:
        return _unknown_finish(
            f"need {MIN_FINISH_STINT_SAMPLES} same-race {compound} stint-life samples with effective phase weight {MIN_FINISH_EFFECTIVE_WEIGHT:g}"
        )

    capacity = _weighted_percentile(samples, 0.75)
    required_age = driver.tyre_age + max(0, total_laps - current_lap)
    evidence = [
        f"{len(samples)} completed same-race {compound} stints; phase-weighted support {effective:.1f}",
        f"phase-weighted 75th-percentile observed life {capacity:.1f} laps versus {required_age} required",
        f"current clean-stint Pace Trend {trend:.3f}s/lap",
        f"dry-rule state {dry_rule_state}; track regime {state.session.track_status or 'UNKNOWN'}",
    ]
    if required_age <= capacity:
        return {
            "status": "SUPPORTED",
            "canFinish": True,
            "requiredTyreAge": required_age,
            "supportedTyreAge": round(capacity, 1),
            "racePhase": race_phase(current_lap, total_laps),
            "evidenceBasis": evidence,
        }
    return {
        "status": "INSUFFICIENT",
        "canFinish": None,
        "requiredTyreAge": required_age,
        "supportedTyreAge": round(capacity, 1),
        "racePhase": race_phase(current_lap, total_laps),
        "evidenceBasis": [*evidence, "observed stint life does not support a no-stop finish"],
    }


def field_distributions(
    state: RaceState,
    evidence_by_driver: dict[str, tuple[LapObservation, ...]],
) -> dict[str, Any]:
    population = _race_population(state)
    current_field = [*population["running"], *population["inPit"]]
    starting: Counter[str] = Counter()
    starting_known = 0
    sequences: Counter[str] = Counter()
    for observations in evidence_by_driver.values():
        compounds = [item.compound.upper() for item in observations if item.compound]
        if not compounds:
            continue
        first = next(
            (
                item.compound.upper()
                for item in observations
                if item.compound and (item.stint_number in {None, 1} or item.lap <= 2)
            ),
            None,
        )
        if first:
            starting[first] += 1
            starting_known += 1
        ordered: list[str] = []
        for compound in compounds:
            if not ordered or ordered[-1] != compound:
                ordered.append(compound)
        if ordered:
            sequences[" → ".join(ordered)] += 1

    current = Counter(
        state.drivers[number].compound.upper()
        for number in current_field
        if state.drivers[number].compound
    )
    stops = Counter(state.drivers[number].pit_count for number in current_field)
    return {
        "runningDriverCount": len(current_field),
        "startingTyreDistribution": dict(sorted(starting.items())),
        "startingTyrePopulation": {
            "known": starting_known,
            "participants": sum(
                1 for driver in state.drivers.values() if is_session_participant(driver)
            ),
        },
        "currentTyreDistribution": dict(sorted(current.items())),
        "currentTyrePopulation": {"known": sum(current.values()), "running": len(current_field)},
        "stopDistribution": {str(key): value for key, value in sorted(stops.items())},
        "observedSequences": [
            {"sequence": sequence, "drivers": count}
            for sequence, count in sequences.most_common()
        ],
        "evidenceBasis": [
            "starting tyres use first-stint/race-start evidence, including later terminal starters",
            f"current tyres and completed stops use {len(current_field)} factually running or in-pit drivers at this cursor",
        ],
    }


def race_read(
    state: RaceState,
    driver_models: dict[str, dict[str, Any]],
    evidence_by_driver: dict[str, tuple[LapObservation, ...]],
    pit_events: tuple[PitEvent, ...],
    dry_states: dict[str, str],
    lifecycle: str,
    distributions: dict[str, Any],
) -> dict[str, Any]:
    population = _race_population(state)
    current_field = [*population["running"], *population["inPit"]]

    trend_counts = Counter({"highFade": 0, "moderateFade": 0, "lowOrStable": 0, "unknown": 0})
    comparable = 0
    for number in current_field:
        pace = driver_models.get(number, {}).get("pace", {})
        trend = pace.get("paceTrend") or pace.get("degradation") or {}
        value = trend.get("value")
        if not isinstance(value, (int, float)):
            trend_counts["unknown"] += 1
            continue
        comparable += 1
        if value >= 0.15:
            trend_counts["highFade"] += 1
        elif value >= 0.06:
            trend_counts["moderateFade"] += 1
        else:
            trend_counts["lowOrStable"] += 1

    dry_counts = Counter(dry_states.get(number, "UNKNOWN") for number in current_field)
    current_lap = state.session.lap or 0
    recent = [
        {
            "driverNumber": event.driver_number,
            "lap": event.lap,
            "previousCompound": event.previous_compound,
            "newCompound": event.new_compound,
        }
        for event in pit_events
        if not current_lap or event.lap >= max(1, current_lap - 3)
    ]

    stint_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    total_laps = state.session.total_laps
    for observations in evidence_by_driver.values():
        for item in observations:
            compound = (item.previous_compound or item.compound or "").upper()
            if item.pit_in is not True or not compound or item.tyre_age is None:
                continue
            stint_groups[compound].append(
                {
                    "life": item.tyre_age,
                    "phase": race_phase(item.lap, total_laps),
                }
            )
    stint_context = {
        compound: {
            "completedStints": len(items),
            "medianLife": round(median(item["life"] for item in items), 1),
            "phaseCounts": dict(Counter(item["phase"] or "UNKNOWN" for item in items)),
        }
        for compound, items in sorted(stint_groups.items())
        if items
    }

    observed_sequences = distributions["observedSequences"]
    archetype = {"status": "UNKNOWN", "value": None, "evidenceBasis": ["no supported observed compound/stint sequence majority"]}
    if observed_sequences:
        leader = observed_sequences[0]
        observed_total = sum(item["drivers"] for item in observed_sequences)
        if leader["drivers"] >= 2 and leader["drivers"] / observed_total >= 0.4:
            archetype = {
                "status": "OBSERVED",
                "value": leader["sequence"],
                "drivers": leader["drivers"],
                "denominator": observed_total,
                "evidenceBasis": ["dominant observed compound sequence; not a forecast of remaining stops"],
            }

    summary: list[str] = []
    stop_distribution = distributions["stopDistribution"]
    if stop_distribution:
        dominant_stops, count = max(stop_distribution.items(), key=lambda item: item[1])
        noun = "stop" if dominant_stops == "1" else "stops"
        summary.append(
            f"{count} of {len(current_field)} running or in-pit drivers have exactly "
            f"{dominant_stops} completed {noun}."
        )
    if comparable:
        elevated = trend_counts["highFade"] + trend_counts["moderateFade"]
        summary.append(f"{elevated} of {comparable} comparable running drivers show moderate or high Pace Fade.")
    unsatisfied = dry_counts["UNSATISFIED"]
    if unsatisfied:
        summary.append(f"{unsatisfied} of {len(current_field)} running or in-pit drivers still need another dry compound.")
    if recent:
        summary.append(f"{len(recent)} pit events were observed in the last three race laps.")

    return {
        "raceLifecycle": lifecycle,
        "population": {
            "participants": sum(len(numbers) for numbers in population.values()),
            "running": len(population["running"]),
            "inPit": len(population["inPit"]),
            "stopped": len(population["stopped"]),
            "unconfirmed": len(population["unconfirmed"]),
            "terminal": len(population["terminal"]),
        },
        "completedStopDistribution": stop_distribution,
        "startingTyreDistribution": distributions["startingTyreDistribution"],
        "currentTyreDistribution": distributions["currentTyreDistribution"],
        "paceTrendDistribution": {
            "comparableDrivers": comparable,
            **dict(trend_counts),
            "denominator": len(current_field),
            "basis": "current-race clean current-stint Pace Trend only; Weekend fallback excluded",
        },
        "stintContextByCompound": stint_context,
        "dryRequirementLandscape": {
            "satisfied": dry_counts["SATISFIED"],
            "unsatisfied": unsatisfied,
            "notApplicable": dry_counts["NOT_APPLICABLE"],
            "unknown": dry_counts["UNKNOWN"],
            "denominator": len(current_field),
        },
        "strategyArchetype": archetype,
        "recentPitActivity": recent,
        "summaryFacts": summary,
    }


def _race_population(state: RaceState) -> dict[str, list[str]]:
    """Partition session participants into mutually exclusive factual groups."""

    population: dict[str, list[str]] = {
        "running": [],
        "inPit": [],
        "stopped": [],
        "unconfirmed": [],
        "terminal": [],
    }
    for number, driver in state.drivers.items():
        if not is_session_participant(driver):
            continue
        if is_terminal(driver):
            population["terminal"].append(number)
        elif is_stopped(driver):
            population["stopped"].append(number)
        elif is_circulating(driver) and str(driver.activity or "").upper() == "IN_PIT":
            population["inPit"].append(number)
        elif is_circulating(driver):
            population["running"].append(number)
        else:
            population["unconfirmed"].append(number)
    return population


def hard_projection_violations(strategy: dict[str, Any], driver: DriverState | None, state: RaceState) -> list[str]:
    violations: list[str] = []
    future_fields = ("primaryStrategy", "alternateStrategy", "likelyNextCompound", "pitWindow")
    has_future = any(strategy.get(field, {}).get("value") is not None for field in future_fields)
    if (driver is not None and is_terminal(driver) or _session_final(state)) and has_future:
        violations.append("terminal driver/race has a future projection")
    window = strategy.get("pitWindow", {}).get("value")
    if isinstance(window, list) and len(window) == 2:
        current = state.session.lap or 0
        total = state.session.total_laps
        if int(window[0]) < current or int(window[1]) < int(window[0]):
            violations.append("pit window is behind the race cursor or reversed")
        if total and int(window[1]) > total:
            violations.append("pit window extends beyond race end")
    if strategy.get("disposition") == "TO_FINISH":
        if window is not None:
            violations.append("TO_FINISH retains a future pit window")
        if strategy.get("likelyNextCompound", {}).get("value") is not None:
            violations.append("TO_FINISH retains a next compound")
    if driver is not None:
        remaining = strategy.get("likelyStopCount", {}).get("value")
        if isinstance(remaining, (int, float)) and remaining < driver.pit_count:
            violations.append("likely total stop count is below completed stops")
    return violations


def _weighted_percentile(samples: list[tuple[int, float]], percentile: float) -> float:
    ordered = sorted(samples)
    target = sum(weight for _, weight in ordered) * percentile
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= target:
            return float(value)
    return float(ordered[-1][0])


def _session_final(state: RaceState) -> bool:
    return str(state.session.status or "").upper() in {"FINISHED", "ENDED", "COMPLETE", "FINAL"} or str(state.session.track_status or "").upper() == "CHEQUERED"


def _unknown_finish(reason: str) -> dict[str, Any]:
    return {"status": "UNKNOWN", "canFinish": None, "requiredTyreAge": None, "supportedTyreAge": None, "racePhase": None, "evidenceBasis": [reason]}


