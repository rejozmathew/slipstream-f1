"""Practice leader comparisons use the same cursor as adjacent best-lap deltas."""

from slipstream.events import NormalizedEvent
from slipstream.replay import replay
from slipstream.serialization import state_envelope
from slipstream.state import RaceState


def event(kind, payload, second=0):
    return NormalizedEvent(kind, f"2026-09-11T15:00:{second:02d}Z", "test", payload)


def practice_events():
    return [
        event(
            "session",
            {
                "key": "11363",
                "name": "Practice 2",
                "session_type": "Practice",
                "session_kind": "practice_2",
                "layout_family": "practice",
            },
        ),
        event("timing", {"number": "12", "position": 1, "best_lap": "1:33.662"}, 1),
        event("timing", {"number": "16", "position": 2, "best_lap": "1:33.775"}, 2),
        event("timing", {"number": "44", "position": 3, "best_lap": "1:33.811"}, 3),
    ]


def test_practice_gap_and_interval_are_distinct_and_cursor_safe():
    events = practice_events()
    initial = replay(events)
    assert initial.drivers["12"].best_lap_delta_to_leader is None
    assert initial.drivers["16"].best_lap_delta_to_leader == "+0.113"
    assert initial.drivers["44"].best_lap_delta_to_leader == "+0.149"
    assert initial.drivers["44"].best_lap_delta_to_ahead == "+0.036"
    events.append(event("timing", {"number": "12", "best_lap": "1:33.600"}, 4))
    later = replay(events)
    assert later.drivers["44"].best_lap_delta_to_leader == "+0.211"
    assert later.drivers["44"].best_lap_delta_to_ahead == "+0.036"
    assert replay(events, event_limit=4) == initial
    assert initial.drivers["44"].best_lap_delta_to_leader == "+0.149"
    driver = state_envelope(later, sequence=5)["data"]["drivers"]["44"]
    assert driver["best_lap_delta_to_leader"] == "+0.211"
    assert driver["availability"]["best_lap_delta_to_leader"] == "available"


def test_missing_intermediate_best_lap_does_not_hide_known_leader_gap():
    state = replay(practice_events()).apply(
        event("timing", {"number": "16", "best_lap": None}, 4)
    )
    assert state.drivers["16"].best_lap_delta_to_leader is None
    assert state.drivers["44"].best_lap_delta_to_ahead is None
    assert state.drivers["44"].best_lap_delta_to_leader == "+0.149"
    state = state.apply(event("timing", {"number": "12", "best_lap": None}, 5))
    assert state.drivers["44"].best_lap_delta_to_leader is None
    assert state.drivers["44"].availability["best_lap_delta_to_leader"] == "unavailable"


def test_ambiguous_p1_never_selects_arbitrary_benchmark_and_recovers():
    state = replay(practice_events()).apply(
        event("timing", {"number": "16", "position": 1}, 4)
    )
    assert all(
        driver.best_lap_delta_to_leader is None for driver in state.drivers.values()
    )
    state = state.apply(event("timing", {"number": "12", "position": 2}, 5))
    assert state.drivers["44"].best_lap_delta_to_leader == "+0.036"
    # Sparse reclassification can transiently disagree with best laps. Keep the
    # signed factual comparison, rather than substituting the minimum lap.
    assert state.drivers["12"].best_lap_delta_to_leader == "-0.113"
    state = state.apply(event("timing", {"number": "44", "best_lap": "1:33.775"}, 6))
    assert state.drivers["44"].best_lap_delta_to_leader == "+0.000"


def test_missing_or_duplicate_driver_position_leaves_comparison_unavailable():
    state = replay(practice_events())
    state = state.apply(event("timing", {"number": "44", "position": 2}, 4))
    assert state.drivers["44"].best_lap_delta_to_leader is None
    assert state.drivers["16"].best_lap_delta_to_leader is None
    state = state.apply(event("timing", {"number": "44", "position": None}, 5))
    assert state.drivers["44"].best_lap_delta_to_leader is None
    assert state.drivers["16"].best_lap_delta_to_leader == "+0.113"


def test_non_practice_keeps_existing_gap_truth():
    for name in ("Race", "Qualifying"):
        state = RaceState().apply(
            event(
                "session",
                {
                    "name": name,
                    "session_type": name,
                    "session_kind": name.lower(),
                    "layout_family": name.lower(),
                },
            )
        )
        for number, position, best in (("12", 1, "1:33.662"), ("44", 2, "1:33.811")):
            state = state.apply(
                event(
                    "timing",
                    {
                        "number": number,
                        "position": position,
                        "best_lap": best,
                        "gap_to_leader": "+5.000",
                        "interval_to_ahead": "+1.250",
                    },
                    position,
                )
            )
        assert state.drivers["44"].best_lap_delta_to_leader is None
        assert state.drivers["44"].gap_to_leader == "+5.000"
        assert state.drivers["44"].interval_to_ahead == "+1.250"
