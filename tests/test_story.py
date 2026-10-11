from datetime import UTC, datetime, timedelta

import pytest

from slipstream.events import NormalizedEvent
from slipstream.evidence import SessionEvidence
from slipstream.state import RaceState


def at(seconds):
    return (datetime(2026, 7, 26, 13, tzinfo=UTC) + timedelta(seconds=seconds)).isoformat()


def event(kind, seconds, **payload):
    return NormalizedEvent(kind, at(seconds), "test", payload)


def initial():
    return [
        event("session", 0, key="truth", layout_family="race", session_kind="race", status="RUNNING", marshal_status="ALL_CLEAR", lap=14, total_laps=70),
        event("driver", 0, number="41", code="LIN", position=8, lap=14, source_condition="RUNNING", activity="ON_TRACK", compound="SOFT"),
        event("driver", 0, number="44", code="HAM", position=9, lap=14, source_condition="RUNNING", activity="ON_TRACK", compound="MEDIUM"),
    ]


def pass_events():
    return initial() + [
        event("timing", 1179, number="44", position=8),
        event("timing", 1179, number="41", position=9),
        event("timing", 1184, number="44", track_position=.3),
        event("timing", 1184, number="41", track_position=.29),
    ]


def story(events, sequence=None, clock=None):
    evidence = SessionEvidence.from_events(tuple(events))
    seq = len(events) if sequence is None else sequence
    return evidence.story.snapshot(seq, clock or (events[seq - 1].occurred_at if seq else at(-1)), limit=None)


def test_order_is_neutral_until_both_cars_corroborate_after_confirmation_window():
    events = pass_events()
    before = story(events, 5)
    assert not any(e["kind"] == "PASS" for e in before["events"])
    observation = next(e for e in before["events"] if e["kind"] == "ORDER_CHANGE")
    assert observation["title"] == "HAM moves ahead of LIN"
    assert observation["state"] == "provisional"
    assert not any(e["kind"] == "PASS" for e in story(events, 6)["events"])
    confirmed = next(e for e in story(events)["events"] if e["kind"] == "PASS")
    assert confirmed["occurredAt"] == at(1179)
    assert confirmed["availableAt"] == at(1184)
    assert confirmed["availableSequence"] == 7
    assert confirmed["supersedes"] == observation["id"]
    assert observation["id"] not in {e["id"] for e in story(events)["events"]}


def test_same_timestamp_sequence_and_clock_both_gate_publication():
    events = pass_events()
    assert not any(e["kind"] == "PASS" for e in story(events, 6, at(1184))["events"])
    assert not any(e["kind"] == "PASS" for e in story(events, 7, at(1183.999))["events"])
    assert any(e["kind"] == "PASS" for e in story(events, 7, at(1184))["events"])


def test_long_silence_cannot_confirm_an_expired_pass_candidate():
    events = pass_events()[:6] + [event("timing", 1210, number="41", track_position=.29)]
    assert not any(e["kind"] == "PASS" for e in story(events)["events"])


@pytest.mark.parametrize("flag", ["YELLOW", "VSC", "SAFETY_CAR", "RED_FLAG"])
def test_caution_cancels_pass_confirmation(flag):
    events = pass_events()[:5] + [event("session", 1180, track_status=flag)] + pass_events()[5:]
    assert not any(e["kind"] in {"PASS", "BATTLE"} for e in story(events)["events"])


def test_pit_entry_never_borrows_later_exit_or_compound_evidence():
    events = initial() + [
        event("timing", 10, number="44", source_condition="IN_PIT", activity="IN_PIT", pit_count=1),
        event("timing", 30, number="44", source_condition="RUNNING", activity="ON_TRACK"),
        event("timing", 34, number="44", compound="HARD", tyre_age=0),
    ]
    entry = next(e for e in story(events, 4)["events"] if e["kind"] == "PIT_IN")
    assert entry["data"] == {"position": 9, "previousCompound": "MEDIUM"}
    exit_event = next(e for e in story(events)["events"] if e["kind"] == "PIT_EXIT")
    assert exit_event["data"]["compound"] is None
    assert "not yet confirmed" in exit_event["detail"]


def test_initial_in_pit_observation_does_not_invent_a_pit_entry():
    events = initial()[:2] + [event("driver", 10, number="44", code="HAM", source_condition="IN_PIT", activity="IN_PIT")]
    assert not any(e["kind"] == "PIT_IN" for e in story(events)["events"])


def test_stopped_recovery_is_not_retirement():
    events = initial() + [
        event("timing", 10, number="44", source_condition="STOPPED", source_stopped=True),
        event("timing", 20, number="44", source_condition="RUNNING", source_stopped=False, activity="ON_TRACK"),
    ]
    kinds = [e["kind"] for e in story(events)["events"]]
    assert "STOPPED" in kinds and "RUNNING" in kinds
    assert "CLASSIFICATION" not in kinds


def test_prestart_installation_laps_do_not_fill_the_race_pit_story():
    events = [event("session", 0, key="race", layout_family="race", status="RUNNING", started_at=at(100))] + initial()[1:] + [
        event("timing", 10, number="44", source_condition="IN_PIT", activity="IN_PIT"),
        event("timing", 20, number="44", source_condition="RUNNING", activity="ON_TRACK"),
    ]
    assert not any(e["kind"] in {"PIT_IN", "PIT_EXIT"} for e in story(events)["events"])


def test_result_correction_preserves_original_before_new_classification():
    events = initial() + [
        event("session", 500, status="FINISHED", control_status="CHEQUERED"),
        event("timing", 501, number="44", position=1, classification="FINISHED"),
        event("timing", 510, number="44", position=2),
        event("timing", 510, number="41", position=1, classification="FINISHED"),
    ]
    earlier = story(events, 5)
    original = next(e for e in earlier["events"] if e["kind"] == "RESULT")
    later = story(events)
    correction = next(e for e in later["events"] if e["kind"] == "RESULT_CORRECTION")
    assert correction["supersedes"] == original["id"]
    assert correction["state"] == "corrected"
    assert original["id"] not in {e["id"] for e in later["events"]}
    assert later["result"]["state"] == "provisional"


def test_result_requires_cursor_eligible_winner_and_stays_provisional():
    events = initial() + [
        event("timing", 10, number="44", position=1),
        event("session", 20, status="FINISHED", control_status="CHEQUERED"),
        event("timing", 21, number="44", classification="FINISHED"),
    ]
    assert story(events, 4)["result"]["state"] == "none"
    assert story(events, 5)["result"]["state"] == "none"
    result = story(events)
    assert result["result"]["state"] == "provisional"
    winner = next(e for e in result["events"] if e["kind"] == "RESULT")
    assert winner["driverNumbers"] == ["44"]
    assert winner["data"] == {"position": 1}


def test_duplicate_leaders_cannot_publish_a_winner_until_order_is_coherent():
    events = initial() + [
        event("timing", 10, number="41", position=1),
        event("session", 20, status="FINISHED", control_status="CHEQUERED"),
        event("timing", 21, number="44", position=1, classification="FINISHED"),
        event("timing", 22, number="41", position=2),
    ]
    assert story(events, 6)["result"]["state"] == "none"
    assert not any(item["kind"] == "RESULT" for item in story(events, 6)["events"])
    assert next(item for item in story(events)["events"] if item["kind"] == "RESULT")["driverNumbers"] == ["44"]


def test_every_prefix_equals_truncation_and_queries_are_order_independent():
    events = pass_events() + [
        event("race_control", 1190, category="Other", message="CAR 44 TIME DELETED", driver_number="44"),
        event("timing", 1191, number="44", source_condition="IN_PIT", activity="IN_PIT"),
        event("timing", 1210, number="44", source_condition="RUNNING", activity="ON_TRACK"),
        event("timing", 1215, number="44", compound="HARD"),
    ]
    full = SessionEvidence.from_events(tuple(events))
    for count in [len(events), 2, 7, 5, *range(1, len(events) + 1)]:
        time = events[count - 1].occurred_at
        assert full.story.snapshot(count, time, limit=None) == story(events[:count])


def test_incremental_append_matches_one_pass_preparation():
    events = pass_events()
    state = RaceState()
    incremental = SessionEvidence()
    for seq, item in enumerate(events, 1):
        state = state.apply(item)
        incremental = incremental.append(item, sequence=seq, state=state)
    assert incremental.story.snapshot(len(events), at(1184), limit=None) == story(events)


def test_story_ids_survive_earlier_unrelated_event_insertion():
    original = pass_events()
    amended = original[:3] + [event("weather", 100, air_temperature=30)] + original[3:]
    assert [e["id"] for e in story(original)["events"]] == [e["id"] for e in story(amended)["events"]]


def test_paginated_history_exposes_all_events_without_silent_loss():
    events = initial() + [event("race_control", second, category="Other", message=f"Notice {second}") for second in range(1, 101)]
    evidence = SessionEvidence.from_events(tuple(events))
    first = evidence.story.snapshot(len(events), at(100))
    second = evidence.story.snapshot(len(events), at(100), offset=first["nextOffset"])
    assert first["hasMore"] is True
    assert second["hasMore"] is False
    assert len(first["events"]) + len(second["events"]) == first["total"] == 100
