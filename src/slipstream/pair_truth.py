"""Source-neutral current pair comparison shared by analytics and evidence."""

from __future__ import annotations

from math import isfinite

from .lifecycle import is_battle_eligible, is_in_pit
from .state import DriverState, RaceState


def numeric_gap(value: str | None) -> float | None:
    if not value or "lap" in value.lower():
        return None
    try:
        gap = float(value.strip().lstrip("+").replace(",", "."))
    except ValueError:
        return None
    return gap if isfinite(gap) and gap >= 0 else None


def pair_comparison(state: RaceState, ahead: DriverState, behind: DriverState) -> dict:
    """Use an adjacent source interval, or two comparable numeric leader gaps."""
    result = {
        "aheadDriverNumber": ahead.number, "behindDriverNumber": behind.number,
        "gapSeconds": None, "gapBasis": None, "comparisonState": "NOT_COMPARABLE",
        "reason": None,
    }
    if state.session.layout_family != "race":
        reason = "Pair comparison is available for races only."
    elif not (is_battle_eligible(ahead) and is_battle_eligible(behind)) or is_in_pit(ahead) or is_in_pit(behind):
        reason = "Both drivers must be running on track."
    elif ahead.position is None or behind.position is None or ahead.position >= behind.position or any(
        sum(driver.position == position for driver in state.drivers.values()) != 1
        for position in (ahead.position, behind.position)
    ):
        reason = "Classification order is not established."
    elif ahead.lap is None or behind.lap is None:
        reason = "Both drivers' laps must be known."
    elif ahead.lap != behind.lap:
        reason = "The drivers are not on the same observed lap."
    else:
        adjacent = behind.position == ahead.position + 1
        if adjacent:
            gap = numeric_gap(behind.interval_to_ahead)
        else:
            left = 0.0 if ahead.position == 1 else numeric_gap(ahead.gap_to_leader)
            right = numeric_gap(behind.gap_to_leader)
            gap = round(right - left, 3) if left is not None and right is not None and right >= left else None
        if gap is not None:
            return {**result, "gapSeconds": gap,
                    "gapBasis": "interval_to_ahead" if adjacent else "leader_gap_difference",
                    "comparisonState": "COMPARABLE"}
        reason = "Comparable source gap is unavailable."
    return {**result, "reason": reason}


def recommendation_phase_available(state: RaceState) -> bool:
    return bool(state.session.layout_family == "race" and state.session.status == "RUNNING"
                and state.session.display_status == "GREEN"
                and state.session.lap is not None and state.session.lap >= 3)
