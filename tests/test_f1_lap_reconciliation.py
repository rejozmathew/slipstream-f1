from datetime import UTC, datetime, timedelta

import pytest

from slipstream.live import F1LiveAdapter


def adapter(history=()):
    result = F1LiveAdapter("1", lap_history=history)
    result.ingest(
        {
            "stream": "SessionInfo",
            "payload": {"Key": 1},
            "source_timestamp": "2026-10-09T12:00:00Z",
        }
    )
    return result


def timing(target, seconds, payload):
    at = (
        datetime(2026, 10, 9, 12, tzinfo=UTC) + timedelta(seconds=seconds)
    ).isoformat()
    return target.ingest(
        {
            "stream": "TimingData",
            "payload": {"Lines": {"1": payload}},
            "source_timestamp": at,
        }
    )


def observations(events):
    return [
        event.payload["lap_observation"]
        for event in events
        if "lap_observation" in event.payload
    ]


@pytest.mark.parametrize("time_first", [True, False])
def test_split_lap_updates_wait_for_both_feed_facts(time_first):
    target = adapter()
    timing(target, 0, {"NumberOfLaps": 4, "LastLapTime": {"Value": "1:20.000"}})
    packets = [{"LastLapTime": {"Value": "1:21.000"}}, {"NumberOfLaps": 5}]
    if not time_first:
        packets.reverse()
    first = timing(target, 81, packets[0])
    assert observations(first) == []
    second = timing(target, 82, packets[1])
    assert [(lap["lap"], lap["duration"]) for lap in observations(second)] == [(5, 81)]
    # Same duration on a different explicitly supplied lap remains a real lap.
    third = timing(
        target, 163, {"NumberOfLaps": 6, "LastLapTime": {"Value": "1:21.000"}}
    )
    assert observations(third)[0]["lap"] == 6


def test_first_time_before_any_counter_is_buffered_without_guessing_number():
    target = adapter()
    assert (
        observations(timing(target, 80, {"LastLapTime": {"Value": "1:20.000"}})) == []
    )
    assert observations(timing(target, 81, {"NumberOfLaps": 4}))[0]["lap"] == 4


def test_reconnect_repeats_and_flags_never_create_completed_laps():
    target = adapter()
    initial = timing(
        target, 80, {"NumberOfLaps": 5, "LastLapTime": {"Value": "1:20.000"}}
    )
    assert len(observations(initial)) == 1
    assert (
        observations(timing(target, 81, {"LastLapTime": {"PersonalFastest": True}}))
        == []
    )
    resumed = adapter(initial)
    assert (
        observations(
            timing(
                resumed, 83, {"NumberOfLaps": 5, "LastLapTime": {"Value": "1:20.000"}}
            )
        )
        == []
    )
    assert observations(timing(resumed, 84, {"NumberOfLaps": 6})) == []
    actual = timing(resumed, 85, {"LastLapTime": {"Value": "1:20.000"}})
    assert observations(actual)[0]["lap"] == 6


@pytest.mark.parametrize("barrier", ["timeout", "pit", "phase", "clear"])
def test_unmatched_time_cannot_attach_to_a_later_lap(barrier):
    target = adapter()
    timing(target, 80, {"NumberOfLaps": 5, "LastLapTime": {"Value": "1:20.000"}})
    assert (
        observations(timing(target, 160, {"LastLapTime": {"Value": "1:21.000"}})) == []
    )
    if barrier == "pit":
        timing(target, 161, {"InPit": True})
    elif barrier == "phase":
        target._qualifying_phase = "SQ2"
    elif barrier == "clear":
        timing(target, 161, {"LastLapTime": {"Value": ""}})
    assert (
        observations(
            timing(target, 170 if barrier == "timeout" else 162, {"NumberOfLaps": 6})
        )
        == []
    )


def test_full_packet_uses_actual_feed_counter_even_when_it_skips():
    target = adapter()
    timing(target, 80, {"NumberOfLaps": 4, "LastLapTime": {"Value": "1:20.000"}})
    result = timing(
        target, 400, {"NumberOfLaps": 9, "LastLapTime": {"Value": "1:19.000"}}
    )
    assert observations(result)[0]["lap"] == 9


def test_split_update_uses_pit_annotation_of_confirmed_lap_not_previous_counter():
    target = adapter()
    target._lap_annotations = {"1": {4: {"pit_out": True}, 5: {"pit_in": True}}}
    timing(target, 80, {"NumberOfLaps": 4, "LastLapTime": {"Value": "1:20.000"}})
    timing(target, 160, {"LastLapTime": {"Value": "1:21.000"}})
    lap = observations(timing(target, 161, {"NumberOfLaps": 5}))[0]
    assert lap["pit_in"] is True
    assert lap["pit_out"] is None
    assert "pit_out" not in lap["contamination_reasons"]
    assert "pit_in" in lap["contamination_reasons"]
