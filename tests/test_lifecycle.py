"""Canonical active-participant lifecycle (v2.1 §8).

Pins the single status vocabulary that all current-population semantics
route through: Strategy field distributions, the evidence layer, and Battle
eligibility must all agree on who is active.
"""

from slipstream.lifecycle import (
    TERMINAL_DRIVER_STATUSES,
    active_participants,
    display_status_label,
    is_active_participant,
    is_battle_eligible,
    is_circulating,
    terminal_state,
    transition_driver_status,
)
from slipstream.state import DriverState, RaceState


def _state(*specs: tuple[str, int, str]) -> RaceState:
    drivers = {
        number: DriverState(number=number, position=position, status=status)
        for number, position, status in specs
    }
    return RaceState(drivers=drivers)


def test_terminal_statuses_are_the_union_of_the_old_two_vocabularies() -> None:
    # Every status either old vocabulary treated as inactive is terminal now.
    old_evidence = {"RETIRED", "DNS", "DID_NOT_START", "WITHDRAWN", "EXCLUDED"}
    old_analytics = {"RETIRED", "WITHDRAWN", "DNS", "DNF", "RETIREMENT", "NOT_STARTING", "SCRATCHED"}
    assert old_evidence | old_analytics <= TERMINAL_DRIVER_STATUSES


def test_active_participant_includes_the_previously_missing_dsq_dnf() -> None:
    state = _state(
        ("1", 1, "RACING"),
        ("2", 2, "DNF"),
        ("3", 3, "DSQ"),
        ("4", 4, "DISQUALIFIED"),
    )
    assert is_active_participant(state.drivers["1"]) is True
    assert is_active_participant(state.drivers["2"]) is False
    assert is_active_participant(state.drivers["3"]) is False
    assert is_active_participant(state.drivers["4"]) is False
    assert active_participants(state) == ("1",)


def test_stopped_is_an_active_participant_but_not_battle_eligible() -> None:
    state = _state(
        ("1", 1, "RACING"),
        ("2", 2, "STOPPED"),
    )
    # §8.1: a stopped car can resume, so it stays in the active field…
    assert is_active_participant(state.drivers["2"]) is True
    assert active_participants(state) == ("1", "2")
    # …but it is not actively circulating, so it cannot win/lose a Battle.
    assert is_battle_eligible(state.drivers["2"]) is False
    assert is_battle_eligible(state.drivers["1"]) is True


def test_unknown_status_is_never_silently_dropped() -> None:
    state = _state(("1", 1, "UNKNOWN"))
    assert is_active_participant(state.drivers["1"]) is True
    assert active_participants(state) == ("1",)


def test_terminal_labels_are_human_readable() -> None:
    assert display_status_label(DriverState(number="1", position=1, status="RACING")) is None
    assert display_status_label(DriverState(number="1", position=1, status="RETIRED")) == "RETIRED"
    assert display_status_label(DriverState(number="1", position=1, status="DSQ")) == "DSQ"
    assert display_status_label(DriverState(number="1", position=1, status="DNS")) == "DNS"
    assert display_status_label(DriverState(number="1", position=1, status="STOPPED")) == "STOPPED"
    # A stopped car is an active participant (may resume) but is not circulating.
    assert is_active_participant(DriverState(number="1", position=1, status="STOPPED")) is True
    assert display_status_label(DriverState(number="1", position=1, status="STOPPED")) == "STOPPED"


def test_case_insensitive_status_matching() -> None:
    assert is_active_participant(DriverState(number="1", position=1, status="retired")) is False
    assert is_active_participant(DriverState(number="1", position=1, status="racing")) is True


def test_positionless_driver_remains_a_nonterminal_participant() -> None:
    driver = DriverState(number="1", position=None, status="UNKNOWN")
    assert is_active_participant(driver) is True
    assert is_battle_eligible(driver) is False


def test_stopped_is_resumable_but_terminal_status_is_not() -> None:
    stopped = DriverState(number="1", position=1, status="STOPPED")
    retired = DriverState(number="1", position=1, status="RETIRED")
    assert terminal_state(stopped) is None
    assert is_circulating(stopped) is False
    assert transition_driver_status("STOPPED", "RUNNING") == "RUNNING"
    assert transition_driver_status("RETIRED", "RUNNING") == "RETIRED"
    assert terminal_state(retired) == "RETIRED"


def test_finished_is_a_terminal_factual_state() -> None:
    driver = DriverState(number="1", position=1, status="FINISHED")
    assert is_active_participant(driver) is False
    assert terminal_state(driver) == "FINISHED"
    assert display_status_label(driver) == "FINISHED"
