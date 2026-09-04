"""Published Pirelli baseline contextualized by factual current-race evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .evidence import LapObservation, PitEvent
from .lifecycle import is_retired_indicated, terminal_state
from .pirelli.contracts import StrategyOption, StrategyOrder
from .pirelli.snapshot import PirelliEvidenceSnapshot
from .pirelli.store import PirelliAvailability
from .state import DriverState, RaceState

PUBLISHED_STRATEGY_MODEL_VERSION = "pirelli-published-strategy-v2"

_REFERENCE_PRIORITY = {
    "ALIGNED": 0,
    "SAME_COMPOUNDS_DIFFERENT_TIMING": 1,
    "SAME_COMPOUNDS_TIMING_UNKNOWN": 2,
    "EXTRA_SAME_COMPOUND_STOP": 3,
    "STILL_APPLICABLE": 4,
    "NOT_COMPARABLE": 5,
    "REFERENCE_ONLY": 6,
    "UNKNOWN": 7,
    "NO_MATCH": 8,
}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _option_payload(option: StrategyOption) -> dict[str, Any]:
    return {
        "id": option.id,
        "rank": option.rank.value,
        "order": option.order.value,
        "stopCount": option.stop_count,
        "compounds": [compound.value for compound in option.compounds],
        "pitWindows": [
            {"startLap": window.start_lap, "endLap": window.end_lap}
            if window is not None
            else None
            for window in option.pit_windows
        ],
        "publishedDeltaSeconds": option.published_delta_seconds,
        "publishedDeltaSecondsRange": list(option.published_delta_seconds_range)
        if option.published_delta_seconds_range is not None
        else None,
        "conditions": list(option.conditions),
        "caveats": list(option.caveats),
    }


def _tyre_bank(snapshot: PirelliEvidenceSnapshot) -> dict[str, Any]:
    bank = snapshot.latest_tyre_bank
    if bank is None:
        return {
            "status": "ABSENT",
            "coverage": "UNKNOWN",
            "asOf": None,
            "drivers": {},
        }
    drivers = {
        row.driver_number: {
            "driverNumber": row.driver_number,
            "driverCode": row.driver_code,
            "hard": {"new": row.hard.new, "used": row.hard.used},
            "medium": {"new": row.medium.new, "used": row.medium.used},
            "soft": {"new": row.soft.new, "used": row.soft.used},
        }
        for row in bank.drivers
        if row.driver_number is not None
    }
    return {
        "status": "PRESENT",
        "coverage": bank.coverage.value,
        "asOf": _iso(bank.as_of),
        "drivers": drivers,
    }


def _baseline(
    availability: PirelliAvailability | None,
    evidence_cutoff: str,
) -> tuple[
    dict[str, Any], tuple[StrategyOption, ...], tuple[StrategyOption, ...]
]:
    snapshot = availability.snapshot if availability is not None else None
    if availability is None or availability.status != "PRESENT" or snapshot is None:
        status = (
            availability.status
            if availability is not None
            and availability.status in {"FETCHING", "RETRYING"}
            else "ABSENT"
        )
        return (
            {
                "status": status,
                "source": None,
                "publishedAt": None,
                "retrievedAt": None,
                "sourceUrl": None,
                "evidenceCutoff": evidence_cutoff,
                "evidenceTier": "NONE",
                "modelAdmissible": False,
                "provenanceLabel": None,
                "options": [],
                "compoundSelection": None,
                "tyreBank": {
                    "status": "ABSENT",
                    "coverage": "UNKNOWN",
                    "asOf": None,
                    "drivers": {},
                },
                "contextFacts": [],
                "reason": availability.error if availability else "pirelli_context_unavailable",
            },
            (),
            (),
        )
    latest = snapshot.latest_strategy_release
    options = latest.strategies if latest is not None else ()
    model_options = options if availability.model_admissible else ()
    selection = snapshot.compound_selections[-1] if snapshot.compound_selections else None
    context_source_url = next(
        (
            evidence.source_url
            for fact in reversed(snapshot.context_facts)
            for evidence in fact.source_evidence
        ),
        None,
    )
    useful = bool(options or selection or snapshot.context_facts)
    if not useful:
        status = "ABSENT"
        reason = "no_useful_target_session_pirelli_fact"
    else:
        status = "PRESENT"
        reason = None
    return (
        {
            "status": status,
            "source": "PIRELLI" if useful else None,
            "publishedAt": _iso(latest.published_at) if latest else None,
            "retrievedAt": _iso(latest.retrieved_at) if latest else None,
            "sourceUrl": latest.source_url if latest else context_source_url,
            "evidenceCutoff": evidence_cutoff,
            "evidenceTier": availability.evidence_tier,
            "modelAdmissible": availability.model_admissible,
            "provenanceLabel": availability.provenance_label,
            "options": [_option_payload(option) for option in options],
            "compoundSelection": {
                "hard": selection.hard,
                "medium": selection.medium,
                "soft": selection.soft,
            }
            if selection is not None
            else None,
            "tyreBank": _tyre_bank(snapshot),
            "contextFacts": [
                {"category": fact.category, "statement": fact.statement}
                for fact in snapshot.context_facts
            ],
            "reason": reason,
        },
        model_options,
        options,
    )


def observed_compounds(
    driver: DriverState,
    observations: tuple[LapObservation, ...],
) -> list[str]:
    sequence: list[str] = []
    for value in [*(item.compound for item in observations), driver.compound]:
        compound = str(value or "").upper()
        if not compound:
            continue
        if not sequence or sequence[-1] != compound:
            sequence.append(compound)
    return sequence


def _compound(value: object) -> str | None:
    compound = str(value or "").upper()
    if compound in {"", "UNKNOWN", "UNAVAILABLE", "NONE", "NULL", "—", "-"}:
        return None
    return compound


def _actual_strategy(
    driver: DriverState,
    observations: tuple[LapObservation, ...],
    pit_events: tuple[PitEvent, ...],
) -> dict[str, Any]:
    events = tuple(sorted(pit_events, key=lambda item: item.sequence))
    first_event_lap = events[0].lap if events else None
    observed = next(
        (
            _compound(item.compound)
            for item in observations
            if _compound(item.compound)
            and (first_event_lap is None or item.lap < first_event_lap)
        ),
        None,
    )
    if events:
        initial = _compound(events[0].previous_compound) or observed
    else:
        initial = observed or _compound(driver.compound)
    compounds: list[str | None] = [initial] if initial is not None or events else []
    for event in events:
        compounds.append(_compound(event.new_compound))
    if events and compounds and compounds[-1] is None:
        compounds[-1] = _compound(driver.compound)
    completed_stops = max(int(driver.pit_count or 0), 0)
    evidence_complete = (
        len(events) == completed_stops
        and len(compounds) == len(events) + 1
        and all(compound is not None for compound in compounds)
    )
    return {
        "compounds": compounds,
        "stopLaps": [event.lap for event in events],
        "completedStops": completed_stops,
        "observedStops": len(events),
        "evidenceComplete": evidence_complete,
    }


def _stop_comparisons(
    option: StrategyOption,
    actual: dict[str, Any],
) -> list[dict[str, Any]]:
    stop_laps = actual["stopLaps"]
    actual_compounds = actual["compounds"]
    distinct_compounds: list[str | None] = []
    transition_laps: list[int | None] = []
    for index, compound in enumerate(actual_compounds):
        if not distinct_compounds:
            distinct_compounds.append(compound)
        elif compound != distinct_compounds[-1]:
            distinct_compounds.append(compound)
            transition_laps.append(stop_laps[index - 1] if index - 1 < len(stop_laps) else None)
    published_compounds = [compound.value for compound in option.compounds]
    comparisons: list[dict[str, Any]] = []
    for stop_index, window in enumerate(option.pit_windows):
        transition_matches = (
            len(distinct_compounds) > stop_index + 1
            and distinct_compounds[: stop_index + 2]
            == published_compounds[: stop_index + 2]
        )
        actual_lap = (
            transition_laps[stop_index]
            if transition_matches and stop_index < len(transition_laps)
            else None
        )
        if window is None:
            status = "NO_PUBLISHED_LAP"
        elif actual_lap is None:
            status = "NOT_OCCURRED"
        elif window.start_lap <= actual_lap <= window.end_lap:
            status = "INSIDE"
        else:
            status = "OUTSIDE"
        comparisons.append(
            {
                "stopIndex": stop_index,
                "actualLap": actual_lap,
                "publishedStartLap": window.start_lap if window is not None else None,
                "publishedEndLap": window.end_lap if window is not None else None,
                "status": status,
            }
        )
    return comparisons


def _reference_status(
    option: StrategyOption,
    actual: dict[str, Any],
    *,
    baseline_present: bool,
    current_lap: int | None,
    terminal: str | None,
    final: bool,
) -> tuple[str, list[dict[str, Any]]]:
    if not baseline_present:
        return "REFERENCE_ONLY", []
    comparisons = _stop_comparisons(option, actual)
    if option.order != StrategyOrder.ORDERED:
        return "NOT_COMPARABLE", comparisons
    compounds = actual["compounds"]
    if not actual["evidenceComplete"] or not compounds:
        return "UNKNOWN", comparisons
    published = [compound.value for compound in option.compounds]
    if compounds == published:
        timing = [item["status"] for item in comparisons]
        if "OUTSIDE" in timing:
            return "SAME_COMPOUNDS_DIFFERENT_TIMING", comparisons
        if timing and all(item == "INSIDE" for item in timing):
            return "ALIGNED", comparisons
        return "SAME_COMPOUNDS_TIMING_UNKNOWN", comparisons
    without_repeats = [
        compound
        for index, compound in enumerate(compounds)
        if index == 0 or compound != compounds[index - 1]
    ]
    if len(without_repeats) < len(compounds) and (
        without_repeats == published
        or without_repeats == published[: len(without_repeats)]
    ):
        return "EXTRA_SAME_COMPOUND_STOP", comparisons
    if compounds == published[: len(compounds)] and len(compounds) < len(published):
        completed_comparisons = comparisons[: max(len(compounds) - 1, 0)]
        if any(item["status"] == "OUTSIDE" for item in completed_comparisons):
            return "SAME_COMPOUNDS_DIFFERENT_TIMING", comparisons
        if terminal is not None or final:
            return "REFERENCE_ONLY", comparisons
        next_window = option.pit_windows[len(compounds) - 1]
        if (
            next_window is not None
            and current_lap is not None
            and current_lap > next_window.end_lap
        ):
            return "NO_MATCH", comparisons
        return "STILL_APPLICABLE", comparisons
    return "NO_MATCH", comparisons


def _assessment_summary(status: str) -> str:
    return {
        "STILL_APPLICABLE": "A published Pirelli tyre strategy is still applicable.",
        "ALIGNED": "Actual tyre strategy and stop timing align with a published Pirelli strategy.",
        "SAME_COMPOUNDS_DIFFERENT_TIMING": "Actual compounds match a published Pirelli strategy, but the stop timing differs.",
        "SAME_COMPOUNDS_TIMING_UNKNOWN": "Actual compounds match a published Pirelli strategy; stop timing cannot be compared.",
        "EXTRA_SAME_COMPOUND_STOP": "Actual tyre strategy includes an additional same-compound stop.",
        "NO_MATCH": "No published Pirelli tyre strategy matches the actual tyre strategy.",
        "NOT_COMPARABLE": "Published Pirelli compounds are available as pre-race reference.",
        "REFERENCE_ONLY": "Published Pirelli tyre strategies are available as pre-race reference.",
        "UNKNOWN": "Actual tyre strategy cannot yet be compared with the published Pirelli strategy.",
    }[status]


def _compact_sequence(compounds: list[str]) -> str:
    return " → ".join(compound[0] for compound in compounds)


def _window_state(current_lap: int | None, start: int, end: int) -> str:
    if current_lap is None:
        return "UNKNOWN"
    if current_lap < start:
        return "BEFORE"
    if current_lap <= end:
        return "ACTIVE"
    return "PASSED"


def _driver_published_strategy(
    driver: DriverState,
    observations: tuple[LapObservation, ...],
    options: tuple[StrategyOption, ...],
    published_options: tuple[StrategyOption, ...],
    pit_events: tuple[PitEvent, ...],
    *,
    baseline_present: bool,
    current_lap: int | None,
    final: bool,
    dry_tyre_requirement: str,
) -> dict[str, Any]:
    observed = observed_compounds(driver, observations)
    actual = _actual_strategy(driver, observations, pit_events)
    terminal = terminal_state(driver)
    if terminal is None and is_retired_indicated(driver):
        terminal = "RETIRED"
    comparable = tuple(option for option in options if option.order == StrategyOrder.ORDERED)
    matching = tuple(
        option
        for option in comparable
        if len(observed) <= len(option.compounds)
        and observed == [compound.value for compound in option.compounds[: len(observed)]]
    )
    if terminal is not None:
        relation = "TERMINAL"
    elif not baseline_present or not observed:
        relation = "UNKNOWN"
    elif not comparable:
        relation = "NOT_COMPARABLE"
    elif len(matching) == 1:
        relation = "MATCHING_ONE"
    elif len(matching) > 1:
        relation = "MATCHING_MULTIPLE"
    else:
        relation = "DIVERGED"

    windows: list[dict[str, Any]] = []
    if not final and relation in {"MATCHING_ONE", "MATCHING_MULTIPLE"}:
        completed_transitions = max(len(observed) - 1, 0)
        for option in matching:
            for stop_index, window in enumerate(option.pit_windows):
                if window is None:
                    continue
                windows.append(
                    {
                        "optionId": option.id,
                        "stopIndex": stop_index,
                        "startLap": window.start_lap,
                        "endLap": window.end_lap,
                        "state": (
                            "COMPLETED"
                            if stop_index < completed_transitions
                            else _window_state(
                                current_lap, window.start_lap, window.end_lap
                            )
                        ),
                    }
                )

    facts: list[str] = []
    sequence = _compact_sequence(observed)
    if relation == "TERMINAL":
        facts.append(f"{driver.code or driver.number} is {terminal} at this cursor.")
    elif relation == "MATCHING_ONE":
        facts.append(f"Observed {sequence} matches one published Pirelli option.")
    elif relation == "MATCHING_MULTIPLE":
        facts.append(
            f"{len(matching)} published Pirelli options remain compatible with observed {sequence}."
        )
    elif relation == "DIVERGED":
        facts.append(
            f"Observed {sequence} no longer matches an ordered published Pirelli option."
        )
    elif relation == "NOT_COMPARABLE":
        facts.append("Published Pirelli options do not define a comparable compound order.")
    passed = next((window for window in windows if window["state"] == "PASSED"), None)
    if passed is not None:
        facts.append(
            f"The car has passed the published L{passed['startLap']}–{passed['endLap']} window without the corresponding transition."
        )
    references = []
    for option in published_options:
        status, stop_comparisons = _reference_status(
            option,
            actual,
            baseline_present=baseline_present,
            current_lap=current_lap,
            terminal=terminal,
            final=final,
        )
        references.append(
            {
                "optionId": option.id,
                "status": status,
                "stopComparisons": stop_comparisons,
            }
        )
    assessment = min(
        (item["status"] for item in references),
        key=lambda item: _REFERENCE_PRIORITY[item],
        default="UNKNOWN",
    )
    return {
        "driverNumber": driver.number,
        "observedCompounds": observed,
        "relation": relation,
        "compatibleOptionIds": [option.id for option in matching],
        "windows": windows,
        "facts": facts[:3],
        "actualStrategy": actual,
        "dryTyreRequirement": dry_tyre_requirement,
        "pirelliAssessment": assessment,
        "pirelliSummary": _assessment_summary(assessment),
        "pirelliReferences": references,
    }


def build_published_strategy(
    *,
    availability: PirelliAvailability | None,
    evidence_cutoff: str,
    state: RaceState,
    evidence_by_driver: dict[str, tuple[LapObservation, ...]],
    lifecycle: str,
    pit_events_by_driver: dict[str, tuple[PitEvent, ...]] | None = None,
    dry_tyre_by_driver: dict[str, str] | None = None,
) -> dict[str, Any]:
    baseline, options, published_options = _baseline(availability, evidence_cutoff)
    baseline_present = (
        baseline["status"] == "PRESENT" and baseline["modelAdmissible"] is True
    )
    final = lifecycle == "FINAL"
    drivers = {
        number: _driver_published_strategy(
            driver,
            evidence_by_driver.get(number, ()),
            options,
            published_options,
            (pit_events_by_driver or {}).get(number, ()),
            baseline_present=baseline_present,
            current_lap=state.session.lap,
            final=final,
            dry_tyre_requirement=(dry_tyre_by_driver or {}).get(number, "UNKNOWN"),
        )
        for number, driver in state.drivers.items()
    }
    active_windows = [
        window
        for driver in drivers.values()
        for window in driver["windows"]
        if window["state"] == "ACTIVE"
    ]
    field_facts: list[str] = []
    if not final and state.weather.rainfall is True and baseline_present:
        field_facts.append(
            "Current rainfall means the published dry Pirelli baseline is not directly applicable."
        )
    if not final and active_windows:
        if len({(item["optionId"], item["startLap"], item["endLap"]) for item in active_windows}) > 1:
            field_facts.append("Multiple published Pirelli strategy windows overlap the current race lap.")
        else:
            option = next(
                (item for item in options if item.id == active_windows[0]["optionId"]),
                None,
            )
            if option is not None:
                field_facts.append(
                    f"Pirelli's published {_compact_sequence([compound.value for compound in option.compounds])} window "
                    f"L{active_windows[0]['startLap']}–{active_windows[0]['endLap']} is active at the current race lap."
                )
    track = str(state.session.track_status or "").upper()
    if not final and active_windows and (
        "SAFETY" in track or track in {"SC", "VSC", "VIRTUAL_SAFETY_CAR"}
    ):
        field_facts.append(
            "Safety Car or VSC is active while a published Pirelli stop window is open."
        )
    return {
        "status": "PRESENT" if baseline_present else "ABSENT",
        "lifecycle": lifecycle,
        "baseline": baseline,
        "fieldFacts": field_facts[:3],
        "drivers": drivers,
        "modelVersion": PUBLISHED_STRATEGY_MODEL_VERSION,
    }
