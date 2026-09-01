"""Published Pirelli baseline contextualized by factual current-race evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .evidence import LapObservation
from .lifecycle import is_retired_indicated, terminal_state
from .pirelli.contracts import StrategyOption, StrategyOrder
from .pirelli.snapshot import PirelliEvidenceSnapshot
from .pirelli.store import PirelliAvailability
from .state import DriverState, RaceState

PUBLISHED_STRATEGY_MODEL_VERSION = "pirelli-published-strategy-v1"


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
) -> tuple[dict[str, Any], tuple[StrategyOption, ...]]:
    snapshot = availability.snapshot if availability is not None else None
    if availability is None or availability.status != "PRESENT" or snapshot is None:
        return (
            {
                "status": "ABSENT",
                "source": None,
                "publishedAt": None,
                "retrievedAt": None,
                "sourceUrl": None,
                "evidenceCutoff": evidence_cutoff,
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
        )
    latest = snapshot.latest_strategy_release
    options = latest.strategies if latest is not None else ()
    selection = snapshot.compound_selections[-1] if snapshot.compound_selections else None
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
            "sourceUrl": latest.source_url if latest else None,
            "evidenceCutoff": evidence_cutoff,
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
    *,
    baseline_present: bool,
    current_lap: int | None,
    final: bool,
) -> dict[str, Any]:
    observed = observed_compounds(driver, observations)
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
    return {
        "driverNumber": driver.number,
        "observedCompounds": observed,
        "relation": relation,
        "compatibleOptionIds": [option.id for option in matching],
        "windows": windows,
        "facts": facts[:3],
    }


def build_published_strategy(
    *,
    availability: PirelliAvailability | None,
    evidence_cutoff: str,
    state: RaceState,
    evidence_by_driver: dict[str, tuple[LapObservation, ...]],
    lifecycle: str,
) -> dict[str, Any]:
    baseline, options = _baseline(availability, evidence_cutoff)
    baseline_present = baseline["status"] == "PRESENT"
    final = lifecycle == "FINAL"
    drivers = {
        number: _driver_published_strategy(
            driver,
            evidence_by_driver.get(number, ()),
            options,
            baseline_present=baseline_present,
            current_lap=state.session.lap,
            final=final,
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
