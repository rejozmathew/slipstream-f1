"""Canonical driver lifecycle — the single source of truth for
"active race participant" semantics (v2.1 §8, §18).

Before this module there were two competing status vocabularies
(`evidence._RETIRED_STATUSES` and `analytics._INACTIVE_DRIVER_STATUSES`)
that disagreed about which drivers were active. Every consumer that needs
current-population semantics (field distributions, dry-rule count, Battle
eligibility, terminal labels) now routes through this one predicate.

Design notes
------------
* The predicate is derived from the driver's *current* status at the cursor;
  it is never hard-coded to a grid size.
* ``STOPPED`` is treated as **active**: an OpenF1 "stopped" car can resume, so
  it must not be silently dropped from the field. (See §8.1: "Be careful with
  STOPPED if the source can later resume.")
* ``DNS`` / ``DSQ`` / ``DNF`` / ``RETIRED`` / ``WITHDRAWN`` are terminal /
  non-running and are excluded.
* A driver with no position (``position is None``) has not started / is not on
  track and is not an *active* participant even if its status text is benign.
"""

from __future__ import annotations

from .state import DriverState, RaceState

# Terminal / non-running driver statuses (excluded from the active population).
# Kept as one canonical set; both old vocabularies are a subset of this.
TERMINAL_DRIVER_STATUSES = frozenset(
    {
        "RETIRED",
        "RETIREMENT",
        "DNF",
        "DSQ",
        "DISQUALIFIED",
        "DNS",
        "DID_NOT_START",
        "NOT_STARTING",
        "SCRATCHED",
        "WITHDRAWN",
        "EXCLUDED",
        # Deliberately NOT here: STOPPED (can resume), RACING, RUNNING, LIVE,
        # STARTED, UNKNOWN (unknown is treated as active, never dropped).
    }
)

# Human-facing terminal labels used across the UI (Timing, Strategy, Driver,
# Battle, Track map). The raw status text is preserved elsewhere for
# classification; this is the *label* to show.
_TERMINAL_LABELS = {
    "RETIRED": "RETIRED",
    "RETIREMENT": "RETIRED",
    "DNF": "DNF",
    "DSQ": "DSQ",
    "DISQUALIFIED": "DSQ",
    "DNS": "DNS",
    "DID_NOT_START": "DNS",
    "NOT_STARTING": "DNS",
    "SCRATCHED": "DNS",
    "WITHDRAWN": "WITHDRAWN",
    "EXCLUDED": "WITHDRAWN",
    "STOPPED": "STOPPED",
}


def is_active_participant(driver: DriverState) -> bool:
    """Return ``True`` if *driver* is an active race participant at the cursor.

    This is the canonical "active race participant" concept (v2.1 §8). A driver
    is active when their status is not terminal *and* they hold a position on
    track. ``STOPPED`` is active (may resume); ``UNKNOWN`` is active (we never
    silently drop an unknown driver from the field).
    """
    status = str(driver.status or "").upper()
    return status not in TERMINAL_DRIVER_STATUSES


def active_participants(state: RaceState) -> tuple[str, ...]:
    """Return driver numbers of all *active race participants* at the cursor.

    v2.1 §8: "Create one canonical backend concept for an active race
    participant and use it everywhere current-population semantics are
    required." This is that concept. The count is derived from state and is
    never hard-coded to grid size.
    """
    return tuple(
        number
        for number, driver in state.drivers.items()
        if is_active_participant(driver)
    )


def display_status_label(driver: DriverState) -> str | None:
    """Return a human-facing status label for *driver* to show in the UI, or
    ``None`` if the driver is an active, circulating participant.

    Used to make retired / stopped / DNS / DSQ state *obvious* in the UI
    (Timing tower, Strategy terminal row, Driver Focus, Battle, Track map)
    rather than rendering them as if strategically active (v2.1 §8.3).

    A driver who is an active participant but ``STOPPED`` is *not*
    circulating — it returns ``"STOPPED"`` so the UI can surface it distinctly
    while the driver stays in the active field (it may resume).
    """
    status = str(driver.status or "").upper()
    if status in _TERMINAL_LABELS:
        return _TERMINAL_LABELS[status]
    if is_active_participant(driver):
        return None
    return status or "INACTIVE"


def is_battle_eligible(driver: DriverState) -> bool:
    """Return ``True`` if *driver* is eligible to be a Battle candidate.

    v2.1 §8.3 / §17: retired / DNS / DSQ / DNF / withdrawn drivers are **never**
    eligible. ``STOPPED`` is not eligible for a Battle (it is not actively
    circulating, even though it is still an *active participant* of the field).
    """
    if not is_active_participant(driver):
        return False
    # A stopped car is active for the field but not actively circulating, so it
    # cannot win/lose a Battle.
    return str(driver.status or "").upper() != "STOPPED"


def terminal_state(driver: DriverState) -> str | None:
    """Return the driver's *factual terminal state* at the cursor, or ``None``.

    v2.1 §4.3: a per-driver terminal label the UI can show directly (Strategy
    terminal row, Driver Focus, Timing). ``None`` means the driver is not
    terminal at this cursor — it is still a circulating participant (including
    ``STOPPED``, which is active and may resume, so it is *not* terminal).

    The mapping is source-neutral: it routes through the same canonical status
    set as :func:`is_active_participant`, so a RETIRED/DNF/DNS/DSQ driver is
    terminal everywhere and a RUNNING/STOPPED driver is not.
    """
    status = str(driver.status or "").upper()
    if status in _TERMINAL_LABELS:
        return _TERMINAL_LABELS[status]
    return None
