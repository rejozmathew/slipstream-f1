"""v2.1 Phase B: strategy evidence primitives consumed by Phase C.

Pins the deterministic, cursor-scoped evidence helpers that the strategy
core uses for dry-tyre state, stint life, pit-loss inputs, and the
active-runner population (v2.1 §12/§15/§17.1/§18).
"""

from slipstream.evidence import (
    LapEvidence,
    LapObservation,
    SessionEvidence,
    active_runners,
)
from slipstream.state import DriverState, RaceState

T = "2026-08-01T14:{:02d}:00+00:00"


def _obs(lap: int, compound: str | None = None, pit_in: bool | None = None,
         pit_lane: float | None = None) -> LapObservation:
    return LapObservation(
        lap=lap,
        started_at=T.format(lap),
        compound=compound,
        pit_in=pit_in,
        pit_lane_duration=pit_lane,
    )


def _ev(*rows) -> SessionEvidence:
    return SessionEvidence(
        tuple(
            LapEvidence(
                sequence=i + 1,
                occurred_at=T.format(lap),
                driver_number="1",
                observation=_obs(lap, c, p, pl),
            )
            for i, (lap, c, p, pl) in enumerate(rows)
        )
    )


def test_dry_compound_history_excludes_wet_and_keeps_first_seen_order() -> None:
    ev = _ev((1, "SOFT", None, None), (2, "WET", None, None),
             (3, "SOFT", None, None), (4, "MEDIUM", None, None))
    assert ev.dry_compound_history("1") == ("SOFT", "MEDIUM")


def test_dry_compound_history_respects_cursor() -> None:
    ev = _ev((1, "SOFT", None, None), (5, "HARD", None, None))
    # Before the HARD lap is visible, only SOFT has been used.
    assert ev.dry_compound_history("1", at="2026-08-01T14:03:00+00:00") == ("SOFT",)


def test_stint_lengths_delimited_by_pit_in() -> None:
    ev = _ev(
        (1, "SOFT", None, None), (2, "SOFT", None, None),
        (3, "SOFT", True, 22.0),  # pit-in closes stint 1
        (4, "MEDIUM", None, None), (5, "MEDIUM", None, None),
        (6, "MEDIUM", None, None),  # in-progress stint 2
    )
    assert ev.stint_lengths("1") == (2, 3)


def test_pit_lane_durations_collects_observed_values() -> None:
    ev = _ev((3, "SOFT", True, 22.0), (9, "SOFT", True, 21.5))
    assert ev.pit_lane_durations() == (22.0, 21.5)


def test_active_runners_excludes_retired_and_dns() -> None:
    state = RaceState(
        drivers={
            "1": DriverState(number="1", position=1, status="RACING"),
            "2": DriverState(number="2", position=2, status="RACING"),
            "3": DriverState(number="3", position=3, status="RETIRED"),
            "4": DriverState(number="4", status="DNS"),
        }
    )
    assert active_runners(state) == ("1", "2")


def test_active_runners_is_never_hardcoded_to_grid_size() -> None:
    state = RaceState(
        drivers={
            "7": DriverState(number="7", position=1, status="RACING"),
            "8": DriverState(number="8", position=2, status="RACING"),
            "9": DriverState(number="9", position=3, status="RACING"),
        }
    )
    assert active_runners(state) == ("7", "8", "9")
