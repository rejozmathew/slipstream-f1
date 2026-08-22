"""Canonical, source-neutral driver lifecycle semantics.

The module deliberately exposes distinct predicates for session population,
current Strategy population, circulation and Battle eligibility. ``STOPPED``
is resumable and therefore non-terminal. Final results are terminal facts only
when their timestamp is reached by replay.
"""

from __future__ import annotations

from .state import DriverState, RaceState

CANONICAL_DRIVER_STATUSES = frozenset(
    {"RUNNING", "STOPPED", "RETIRED", "FINISHED", "DNF", "DNS", "DSQ", "UNKNOWN"}
)

_STATUS_ALIASES = {
    "": "UNKNOWN",
    "RACING": "RUNNING",
    "LIVE": "RUNNING",
    "STARTED": "RUNNING",
    "RETIREMENT": "RETIRED",
    "DISQUALIFIED": "DSQ",
    "DID_NOT_START": "DNS",
    "NOT_STARTING": "DNS",
    "SCRATCHED": "DNS",
}

TERMINAL_DRIVER_STATUSES = frozenset(
    {
        "RETIRED",
        "RETIREMENT",
        "FINISHED",
        "DNF",
        "DSQ",
        "DISQUALIFIED",
        "DNS",
        "DID_NOT_START",
        "NOT_STARTING",
        "SCRATCHED",
        "WITHDRAWN",
        "EXCLUDED",
    }
)

_TERMINAL_LABELS = {
    "RETIRED": "RETIRED",
    "RETIREMENT": "RETIRED",
    "FINISHED": "FINISHED",
    "DNF": "DNF",
    "DSQ": "DSQ",
    "DISQUALIFIED": "DSQ",
    "DNS": "DNS",
    "DID_NOT_START": "DNS",
    "NOT_STARTING": "DNS",
    "SCRATCHED": "DNS",
    "WITHDRAWN": "WITHDRAWN",
    "EXCLUDED": "WITHDRAWN",
}


def canonical_driver_status(status: object) -> str:
    """Return a canonical lifecycle value while retaining unknown source labels."""

    raw = str(status or "").strip().upper()
    return _STATUS_ALIASES.get(raw, raw or "UNKNOWN")


def is_session_participant(driver: DriverState) -> bool:
    """Return whether driver metadata identifies a session participant.

    Position is intentionally not required: metadata routinely arrives before
    classification or timing data.
    """

    return bool(driver.number)


def is_active_participant(driver: DriverState) -> bool:
    """Return whether the driver belongs to the current non-terminal population.

    STOPPED and UNKNOWN remain in this population; neither is silently treated
    as retirement. Position is intentionally not required.
    """

    return canonical_driver_status(driver.status) not in TERMINAL_DRIVER_STATUSES


def is_stopped(driver: DriverState) -> bool:
    """Return whether explicit evidence says the driver is temporarily stopped."""

    return canonical_driver_status(driver.status) == "STOPPED"


def is_terminal(driver: DriverState) -> bool:
    """Return whether the driver has a factual terminal state at this cursor."""

    return canonical_driver_status(driver.status) in TERMINAL_DRIVER_STATUSES


def is_circulating(driver: DriverState) -> bool:
    """Return whether positive lifecycle evidence says the driver is circulating."""

    return canonical_driver_status(driver.status) == "RUNNING"


def active_participants(state: RaceState) -> tuple[str, ...]:
    """Return driver numbers in the current non-terminal race population."""

    return tuple(
        number
        for number, driver in state.drivers.items()
        if is_active_participant(driver)
    )


def display_status_label(driver: DriverState) -> str | None:
    """Return the factual lifecycle label that should be visible to viewers."""

    status = canonical_driver_status(driver.status)
    if status == "STOPPED":
        return "STOPPED"
    if status in _TERMINAL_LABELS:
        return _TERMINAL_LABELS[status]
    if is_active_participant(driver):
        return None
    return status or "INACTIVE"


def is_battle_eligible(driver: DriverState) -> bool:
    """Return whether the driver can participate in a timing Battle."""

    return is_circulating(driver) and driver.position is not None


def terminal_state(driver: DriverState) -> str | None:
    """Return the factual terminal state, excluding resumable STOPPED."""

    status = canonical_driver_status(driver.status)
    if status in _TERMINAL_LABELS:
        return _TERMINAL_LABELS[status]
    return None


def transition_driver_status(current: object, requested: object) -> str:
    """Apply a legal factual lifecycle transition.

    STOPPED may resume only when an adapter emits positive RUNNING evidence.
    Terminal states never resume, although a later final classification may
    refine one terminal label into another terminal label at session end.
    """

    old = canonical_driver_status(current)
    new = canonical_driver_status(requested)
    if old in TERMINAL_DRIVER_STATUSES and new not in TERMINAL_DRIVER_STATUSES:
        return old
    return new
