import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from slipstream.events import NormalizedEvent
from slipstream.library import ReplayLibrary
from slipstream.qualifying import _advancing_count, build_qualifying_snapshot
from slipstream.replay import replay


def _resource(tmp_path: Path):
    events = [
        NormalizedEvent(
            "session",
            "2026-07-25T14:00:00+00:00",
            "fixture",
            {
                "key": "qual-2026",
                "name": "Qualifying",
                "meeting_name": "Fixture Grand Prix",
                "session_type": "Qualifying",
                "session_kind": "qualifying",
                "layout_family": "qualifying",
                "started_at": "2026-07-25T14:00:00+00:00",
                "ended_at": "2026-07-25T15:00:00+00:00",
                "qualifying_phase": "Q1",
                "eligible_field_size": 22,
                "session_clock": "00:15:42",
                "session_clock_running": True,
                "status": "RUNNING",
            },
        )
    ]
    for position in range(1, 23):
        number = str(position)
        events.append(
            NormalizedEvent(
                "driver",
                "2026-07-25T14:00:01+00:00",
                "fixture",
                {
                    "number": number,
                    "code": f"D{position}",
                    "name": f"Driver {position}",
                    "team": f"Team {position % 11}",
                    "position": position,
                    "best_lap": f"1:{19 + position / 10:06.3f}",
                    "compound": "SOFT",
                    "tyre_age": 1,
                    "tyre_usage": "NEW",
                    "activity": "ON_TRACK" if position == 1 else "IN_PIT",
                    "qualifying_eliminated": position == 22,
                },
            )
        )
    events.append(
        NormalizedEvent(
            "timing",
            "2026-07-25T14:10:00+00:00",
            "fixture",
            {
                "number": "1",
                "lap": 4,
                "last_lap": "1:19.100",
                "best_lap": "1:19.100",
                "sector_1": 25.1,
                "sector_2": 28.2,
                "sector_3": 25.8,
                "compound": "SOFT",
                "tyre_age": 1,
                "tyre_usage": "NEW",
                "activity": "ON_TRACK",
                "lap_observation": {
                    "lap": 4,
                    "started_at": "2026-07-25T14:08:40+00:00",
                    "duration": 79.1,
                    "sector_1": 25.1,
                    "sector_2": 28.2,
                    "sector_3": 25.8,
                    "compound": "SOFT",
                    "tyre_age": 1,
                    "qualifying_phase": "Q1",
                    "tyre_usage": "NEW",
                    "lap_validity": "UNKNOWN",
                    "quality": "representative",
                    "contamination_reasons": [],
                },
            },
        )
    )
    path = tmp_path / "qualifying.json"
    path.write_text(json.dumps([asdict(event) for event in events]), encoding="utf-8")
    return ReplayLibrary(path).get(), events


def test_qualifying_contract_authors_phase_clock_cut_and_attempts(
    tmp_path: Path,
) -> None:
    resource, events = _resource(tmp_path)
    snapshot = build_qualifying_snapshot(
        resource,
        replay(events),
        sequence=len(events),
    )

    assert snapshot["phase"] == "Q1"
    assert snapshot["final"] is False
    assert snapshot["sessionClock"] == "00:05:42"
    assert snapshot["benchmark"]["driverNumber"] == "1"
    assert snapshot["drivers"]["1"]["benchmarkDelta"] == 0
    assert snapshot["drivers"]["2"]["benchmarkDelta"] is None
    assert snapshot["cutLine"]["advancePosition"] == 16
    assert snapshot["cutLine"]["cutoff"]["driverNumber"] == "16"
    assert snapshot["cutLine"]["firstOut"]["driverNumber"] == "17"
    assert snapshot["drivers"]["1"]["cutState"] == "ADVANCING"
    assert snapshot["drivers"]["17"]["cutState"] == "BELOW_CUT"
    assert snapshot["drivers"]["22"]["cutState"] == "ELIMINATED"
    assert snapshot["drivers"]["1"]["attempts"][0]["tyreUsage"] == "NEW"
    assert snapshot["drivers"]["1"]["attempts"][0]["classification"] == "TIMED"
    assert snapshot["drivers"]["1"]["latestLap"] == {
        "lap": 4,
        "lapTime": 79.1,
        "sector1": 25.1,
        "sector2": 28.2,
        "sector3": 25.8,
        "classification": "TIMED",
    }
    assert sum(snapshot["drivers"]["1"]["latestLap"][key] for key in ("sector1", "sector2", "sector3")) == pytest.approx(snapshot["drivers"]["1"]["latestLap"]["lapTime"])


def test_qualifying_attempt_history_is_cursor_safe(tmp_path: Path) -> None:
    resource, events = _resource(tmp_path)
    before_attempt = build_qualifying_snapshot(
        resource,
        replay(events, event_limit=len(events) - 1),
        sequence=len(events) - 1,
    )
    after_attempt = build_qualifying_snapshot(
        resource,
        replay(events),
        sequence=len(events),
    )

    assert before_attempt["drivers"]["1"]["attempts"] == []
    assert len(after_attempt["drivers"]["1"]["attempts"]) == 1

    physically_truncated = tuple(resource.events[: len(events) - 1])
    truncated_resource = resource.__class__(
        descriptor=resource.descriptor,
        events=physically_truncated,
        final_state=replay(physically_truncated),
        evidence=resource.evidence.from_events(physically_truncated),
        replay_available=resource.replay_available,
        is_live=resource.is_live,
    )
    truncated = build_qualifying_snapshot(
        truncated_resource,
        replay(physically_truncated),
        sequence=len(physically_truncated),
    )
    assert before_attempt == truncated


def test_partial_snapshot_does_not_change_stable_roster_rule(tmp_path: Path) -> None:
    resource, events = _resource(tmp_path)
    state = replay(events)
    reduced = dict(state.drivers)
    reduced.pop("22")
    from dataclasses import replace

    snapshot = build_qualifying_snapshot(
        resource,
        replace(state, drivers=reduced),
        sequence=len(events),
    )

    assert snapshot["cutLine"]["status"] == "AVAILABLE"
    assert snapshot["cutLine"]["advancePosition"] == 16


def test_missing_stable_roster_never_invents_a_cut_line(tmp_path: Path) -> None:
    resource, events = _resource(tmp_path)
    state = replay(events)
    from dataclasses import replace

    snapshot = build_qualifying_snapshot(
        resource,
        replace(state, session=replace(state.session, eligible_field_size=None)),
        sequence=len(events),
    )

    assert snapshot["cutLine"]["status"] == "UNKNOWN"
    assert snapshot["cutLine"]["advancePosition"] is None


def test_unknown_normalized_phase_uses_cursor_safe_observed_segment_start(tmp_path: Path) -> None:
    resource, events = _resource(tmp_path)
    from dataclasses import replace

    state = replay(events)
    snapshot = build_qualifying_snapshot(
        resource,
        replace(state, session=replace(state.session, qualifying_phase=None)),
        sequence=len(events),
    )

    assert snapshot["phase"] == "Q1"
    assert snapshot["phaseEvidence"] == "cursor-safe observed SessionStatus segment starts"
    assert snapshot["benchmark"]["scope"] == "SEGMENT"
    assert snapshot["benchmark"]["driverNumber"] == "1"


@pytest.mark.parametrize(
    ("year", "field_size", "phase", "expected"),
    [
        (2024, 20, "Q1", 15),
        (2024, 20, "Q2", 10),
        (2024, 20, "SQ1", 15),
        (2024, 20, "SQ2", 10),
        (2025, 20, "Q1", 15),
        (2025, 20, "Q2", 10),
        (2025, 20, "SQ1", 15),
        (2025, 20, "SQ2", 10),
        (2026, 22, "Q1", 16),
        (2026, 22, "Q2", 10),
        (2026, 22, "SQ1", 16),
        (2026, 22, "SQ2", 10),
    ],
)
def test_verified_advancement_profiles(
    year: int, field_size: int, phase: str, expected: int
) -> None:
    assert _advancing_count(year, field_size, phase) == expected


def test_result_matrix_is_cursor_safe_and_uses_approved_final_statuses(
    tmp_path: Path,
) -> None:
    resource, events = _resource(tmp_path)
    live_state = replay(events)
    live = build_qualifying_snapshot(
        resource,
        live_state,
        sequence=len(events),
    )

    assert live["drivers"]["1"]["segmentResults"] == [79.1, None, None]
    assert live["drivers"]["1"]["qStatus"] is None

    final_drivers = dict(live_state.drivers)
    final_drivers["1"] = replace(
        final_drivers["1"],
        qualifying_results=(72.695, 71.628, 71.163),
        qualifying_phase_reached="Q3",
        qualifying_eliminated=False,
    )
    final_drivers["2"] = replace(
        final_drivers["2"],
        qualifying_results=(73.115, 72.616, None),
        qualifying_phase_reached="Q2",
        qualifying_eliminated=True,
    )
    final = build_qualifying_snapshot(
        resource,
        replace(live_state, drivers=final_drivers),
        sequence=len(events),
    )
    terminal = build_qualifying_snapshot(
        resource,
        replace(
            live_state,
            session=replace(
                live_state.session,
                qualifying_phase="Q3",
                status="FINISHED",
            ),
            drivers=final_drivers,
        ),
        sequence=len(events),
    )

    assert final["final"] is False
    assert terminal["final"] is True
    assert final["drivers"]["1"]["segmentResults"] == [72.695, 71.628, 71.163]
    assert final["drivers"]["1"]["qStatus"] == "Q3"
    assert final["drivers"]["2"]["segmentResults"] == [73.115, 72.616, None]
    assert final["drivers"]["2"]["qStatus"] == "OUT Q2"


def test_unknown_source_phases_follow_observed_segment_starts_without_future_leakage(
    tmp_path: Path,
) -> None:
    _, events = _resource(tmp_path)
    q1_payload = dict(events[-1].payload)
    q1_observation = dict(q1_payload["lap_observation"])
    q1_observation["qualifying_phase"] = "UNKNOWN"
    q1_payload["lap_observation"] = q1_observation
    q1_event = replace(events[-1], payload=q1_payload)
    segment_start = NormalizedEvent(
        "race_control",
        "2026-07-25T14:25:00+00:00",
        "fixture",
        {"category": "SessionStatus", "message": "SESSION STARTED"},
    )
    q2_payload = dict(q1_payload)
    q2_payload.update({"lap": 8, "last_lap": "1:18.500", "best_lap": "1:18.500"})
    q2_observation = dict(q1_observation)
    q2_observation.update(
        {
            "lap": 8,
            "started_at": "2026-07-25T14:26:00+00:00",
            "duration": 78.5,
        }
    )
    q2_payload["lap_observation"] = q2_observation
    q2_event = replace(
        q1_event,
        occurred_at="2026-07-25T14:27:18.500000+00:00",
        payload=q2_payload,
    )
    unknown_events = [*events[:-1], q1_event, segment_start, q2_event]
    path = tmp_path / "unknown-phase-qualifying.json"
    path.write_text(
        json.dumps([asdict(event) for event in unknown_events]), encoding="utf-8"
    )
    resource = ReplayLibrary(path).get()

    q1 = build_qualifying_snapshot(
        resource,
        replay(unknown_events, event_limit=len(unknown_events) - 2),
        sequence=len(unknown_events) - 2,
    )
    q2 = build_qualifying_snapshot(
        resource,
        replay(unknown_events),
        sequence=len(unknown_events),
    )

    assert q1["drivers"]["1"]["segmentResults"] == [79.1, None, None]
    assert q2["drivers"]["1"]["segmentResults"] == [79.1, 78.5, None]


@pytest.mark.parametrize("prefix", ["Q", "SQ"])
@pytest.mark.parametrize("segment", [1, 2, 3])
def test_timing_deltas_use_only_the_active_segment(tmp_path, prefix, segment):
    resource, events = _resource(tmp_path)
    state = replay(events)
    phase = f"{prefix}{segment}"
    # Earlier segments are faster, so accidental session-wide comparisons differ.
    times = {"1": (70.0, 80.0, 90.0), "2": (70.2, 80.4, 90.6),
             "3": (70.5, 80.9, 91.3), "4": (71.0, None, None)}
    drivers = {
        number: replace(state.drivers[number], qualifying_results=results)
        for number, results in times.items()
    }
    drivers["4"] = replace(drivers["4"], qualifying_eliminated=True,
                           qualifying_phase_reached=f"{prefix}1")
    session = replace(state.session, qualifying_phase=phase,
                      status="FINISHED" if segment == 3 else "RUNNING")
    snapshot = build_qualifying_snapshot(
        resource, replace(state, session=session, drivers=drivers), sequence=len(events),
    )
    rows = snapshot["drivers"]
    assert rows["1"]["intervalToAhead"] is None
    assert rows["2"]["benchmarkDelta"] == pytest.approx((0.2, 0.4, 0.6)[segment - 1])
    assert rows["3"]["intervalToAhead"] == pytest.approx((0.3, 0.5, 0.7)[segment - 1])
    assert rows["4"]["qStatus"] == f"OUT {prefix}1"
    if segment > 1:
        assert rows["4"]["scopeBest"] is None
        assert rows["4"]["benchmarkDelta"] is None
        assert rows["4"]["intervalToAhead"] is None
        assert rows["1"]["scopeLatestLap"] is None
    assert snapshot["final"] is (segment == 3)


@pytest.mark.parametrize("positions, times, expected", [
    ((1, 2, 3), (70.0, 70.4, 70.9), 0.5),
    ((1, 2, 3), (70.0, 70.4, 70.4), 0.0),
    ((1, 2, 3), (70.0, 70.9, 70.4), -0.5),
    ((1, 2, 3), (70.0, None, 70.9), None),
    ((1, 2, 3), (70.0, 70.4, None), None),
    ((1, 3, 4), (70.0, 70.4, 70.9), None),
    ((1, 2, 2), (70.0, 70.4, 70.9), None),
    ((2, 2, 3), (70.0, 70.4, 70.9), None),
    ((1, None, 3), (70.0, 70.4, 70.9), None),
])
def test_interval_never_skips_missing_or_ambiguous_classification(tmp_path, positions, times, expected):
    resource, events = _resource(tmp_path)
    state = replay(events)
    drivers = {
        str(index): replace(state.drivers[str(index)], position=position,
                            qualifying_results=(time, None, None))
        for index, (position, time) in enumerate(zip(positions, times), start=1)
    }
    snapshot = build_qualifying_snapshot(
        resource, replace(state, drivers=drivers), sequence=len(events),
    )
    # The missing P2 case is asserted on P3, rather than P4 (which has an adjacent P3).
    target = "2" if positions == (1, 3, 4) else "3"
    assert snapshot["drivers"][target]["intervalToAhead"] == expected


def test_scope_latest_lap_clears_on_segment_change_and_respects_cursor(tmp_path):
    _, events = _resource(tmp_path)
    transition = NormalizedEvent("session", "2026-07-25T14:25:00+00:00", "fixture",
                                 {"qualifying_phase": "Q2"})
    payload = dict(events[-1].payload)
    observation = dict(payload["lap_observation"])
    observation.update(lap=8, qualifying_phase="Q2", duration=78.0,
                       sector_1=25.0, sector_2=28.0, sector_3=25.0)
    payload.update(lap=8, last_lap="1:18.000", lap_observation=observation)
    q2_lap = replace(events[-1], occurred_at="2026-07-25T14:28:00+00:00", payload=payload)
    all_events = [*events, transition, q2_lap]
    path = tmp_path / "segment-transition.json"
    path.write_text(json.dumps([asdict(event) for event in all_events]), encoding="utf-8")
    resource = ReplayLibrary(path).get()
    snapshots = [build_qualifying_snapshot(resource, replay(all_events, event_limit=cursor),
                                           sequence=cursor)
                 for cursor in (len(events), len(events) + 1, len(events) + 2)]
    q1, q2_start, q2_timed = [snapshot["drivers"]["1"] for snapshot in snapshots]
    assert q1["scopeLatestLap"]["lapTime"] == 79.1
    assert q2_start["scopeLatestLap"] is None
    assert q2_start["scopeBest"] is None
    assert q2_start["latestLap"]["lapTime"] == 79.1
    assert q2_timed["scopeLatestLap"]["lapTime"] == 78.0
    assert q2_timed["scopeLatestLap"]["sector1"] == 25.0
    assert [q2_timed["scopeLatestLap"][f"sector{i}Status"] for i in (1, 2, 3)] == ["SESSION_BEST"] * 3
    assert q2_timed["segmentResults"] == [79.1, 78.0, None]


def test_invalid_attempt_cannot_set_scope_best_or_interval(tmp_path):
    from slipstream.qualifying import _scope_best

    _, events = _resource(tmp_path)
    driver = replay(events).drivers["1"]
    attempts = [
        {"lapTime": 69.0, "phase": "Q1", "validity": "INVALID"},
        {"lapTime": 71.0, "phase": "Q1", "validity": "VALID"},
        {"lapTime": 70.0, "phase": "Q2", "validity": "VALID"},
    ]
    assert _scope_best(driver, attempts, "Q1") == (71.0, "1:11.000")
    assert _scope_best(driver, attempts, "UNKNOWN") == (70.0, "1:10.000")
    assert _scope_best(driver, attempts[:1], "Q1") is None


def test_sector_grades_follow_completed_laps_and_cursor_not_active_sectors(tmp_path):
    _, events = _resource(tmp_path)
    baseline = events[-1]

    def lap(number, seconds, lap_number, timestamp):
        observation = {**baseline.payload["lap_observation"], "lap": lap_number,
                       "sector_1": seconds[0], "sector_2": seconds[1], "sector_3": seconds[2]}
        return replace(baseline, occurred_at=timestamp,
                       payload={**baseline.payload, "number": number, "lap": lap_number,
                                "lap_observation": observation})

    all_events = [*events,
                  lap("2", (24.0, 29.0, 26.0), 4, "2026-07-25T14:11:00+00:00"),
                  lap("1", (25.0, 28.5, 25.8), 5, "2026-07-25T14:12:00+00:00"),
                  NormalizedEvent("timing", "2026-07-25T14:12:10+00:00", "fixture",
                                  {"number": "1", "sector_1": 20.0}),
                  lap("2", (24.0, 28.0, 25.0), 5, "2026-07-25T14:13:00+00:00")]
    path = tmp_path / "sectors.json"
    path.write_text(json.dumps([asdict(event) for event in all_events]), encoding="utf-8")
    resource = ReplayLibrary(path).get()

    def latest(cursor):
        return build_qualifying_snapshot(resource, replay(all_events, event_limit=cursor),
                                         sequence=cursor)["drivers"]["1"]["scopeLatestLap"]

    before = latest(len(events))
    assert [before[f"sector{i}Status"] for i in (1, 2, 3)] == ["SESSION_BEST"] * 3
    completed = latest(len(events) + 2)
    assert [completed[f"sector{i}Status"] for i in (1, 2, 3)] == ["PERSONAL_BEST", "SLOWER", "SESSION_BEST"]
    assert latest(len(events) + 3) == completed
    assert latest(len(all_events))["sector3Status"] == "PERSONAL_BEST"
    assert latest(len(events)) == before  # Seeking backwards never sees the later field best.


@pytest.mark.parametrize("classification,validity,value,expected", [
    ("TIMED", "VALID", 25.0, "SESSION_BEST"),
    ("TIMED", "UNKNOWN", 25.0, "SESSION_BEST"),
    ("TIMED", "INVALID", 24.0, "UNKNOWN"),
    ("OUT", "VALID", 24.0, "UNKNOWN"),
    ("NON_REP", "VALID", 24.0, "SESSION_BEST"),
    ("NON_REP", "UNKNOWN", 24.0, "SESSION_BEST"),
    ("TIMED", "VALID", None, "UNKNOWN"),
    ("TIMED", "VALID", 0, "UNKNOWN"),
])
def test_sector_grades_keep_unusable_evidence_neutral(classification, validity, value, expected):
    from slipstream.qualifying import _graded_latest_lap, _sector_bests

    attempt = {"lap": 1, "lapTime": 80, "classification": classification, "validity": validity,
               "sector1": value, "sector2": None, "sector3": None}
    bests = _sector_bests([attempt])
    result = _graded_latest_lap([attempt], bests, bests)
    assert result["sector1Status"] == expected
    assert result["sector2Status"] == "UNKNOWN"
    if expected == "UNKNOWN":
        assert bests[0] is None


def test_best_lap_sectors_survive_slow_laps_and_history_compares_only_within_segment(tmp_path):
    _, events = _resource(tmp_path)
    baseline = events[-1]

    def lap(number, phase, seconds, lap_number, minute):
        return replace(baseline, occurred_at=f"2026-07-25T14:{minute}:00+00:00",
                       payload={**baseline.payload, "number": number, "lap": lap_number,
                                "lap_observation": {**baseline.payload["lap_observation"],
                                                    "lap": lap_number, "qualifying_phase": phase,
                                                    "duration": sum(seconds), "sector_1": seconds[0],
                                                    "sector_2": seconds[1], "sector_3": seconds[2]}})

    all_events = [*events,
                  lap("1", "Q1", (30, 35, 30), 5, "12"),
                  lap("2", "Q1", (24, 29, 26), 4, "13"),
                  NormalizedEvent("session", "2026-07-25T14:25:00+00:00", "fixture", {"qualifying_phase": "Q2"}),
                  lap("1", "Q2", (23, 25, 24), 8, "28")]
    path = tmp_path / "best-sectors.json"
    path.write_text(json.dumps([asdict(event) for event in all_events]), encoding="utf-8")
    resource = ReplayLibrary(path).get()

    def driver_at(cursor):
        return build_qualifying_snapshot(resource, replay(all_events, event_limit=cursor),
                                         sequence=cursor)["drivers"]["1"]

    first = driver_at(len(events))
    slow = driver_at(len(events) + 1)
    assert slow["scopeBestLap"] == first["scopeBestLap"]
    assert slow["scopeLatestLap"]["lapTime"] == 95
    assert slow["attempts"][-1]["sector1Status"] == "SLOWER"
    q1 = driver_at(len(events) + 2)
    assert q1["scopeBestLap"]["sector1Status"] == "PERSONAL_BEST"
    assert q1["scopeBestLap"]["sector2Status"] == "SESSION_BEST"
    q2_start = driver_at(len(events) + 3)
    assert q2_start["scopeBestLap"] is None
    q2 = driver_at(len(all_events))
    assert q2["scopeBestLap"]["lapTime"] == 72
    assert q2["attempts"][:-1] == q1["attempts"]
    assert q2["attempts"][-1]["sector1Status"] == "SESSION_BEST"
    assert driver_at(len(events)) == first


def test_best_lap_sectors_require_matching_authoritative_result_and_keep_missing_values(tmp_path):
    resource, events = _resource(tmp_path)
    state = replay(events)
    for authoritative, expected in [(78.0, None), (79.1, 79.1), (None, None)]:
        driver = replace(state.drivers["1"], qualifying_results=(authoritative, None, None))
        snapshot = build_qualifying_snapshot(resource, replace(state, drivers={"1": driver}), sequence=len(events))
        best = snapshot["drivers"]["1"]["scopeBestLap"]
        assert (best["lapTime"] if best else None) == expected

    from slipstream.qualifying import _graded_best_lap

    attempt = {"lap": 1, "lapTime": 80, "classification": "TIMED", "validity": "INVALID",
               "sector1": 25, "sector2": None, "sector3": 26}
    assert _graded_best_lap([attempt], 80, [25, None, 26], [25, None, 26]) is None
    attempt["validity"] = "UNKNOWN"
    best = _graded_best_lap([attempt], 80, [25, None, 26], [25, None, 26])
    assert best["sector2"] is None
    assert best["sector2Status"] == "UNKNOWN"


def test_official_history_collapses_reconnects_without_renumbering_conflicting_laps(tmp_path):
    _, events = _resource(tmp_path)
    first = replace(events[-1], source="f1-signalr-public")
    repeated = replace(first, occurred_at="2026-07-25T14:11:00+00:00")
    conflicting = replace(first, occurred_at="2026-07-25T14:12:00+00:00", payload={
        **first.payload, "lap_observation": {**first.payload["lap_observation"], "duration": 100.0},
    })
    actual_next = replace(first, occurred_at="2026-07-25T14:14:00+00:00", payload={
        **first.payload, "lap": 5, "lap_observation": {**first.payload["lap_observation"], "lap": 5},
    })
    all_events = [*events[:-1], first, repeated, conflicting,
                  replace(conflicting, occurred_at="2026-07-25T14:13:00+00:00"), actual_next]
    path = tmp_path / "repeat-laps.json"
    path.write_text(json.dumps([asdict(event) for event in all_events]), encoding="utf-8")
    resource = ReplayLibrary(path).get()

    def attempts(cursor):
        return build_qualifying_snapshot(resource, replay(all_events, event_limit=cursor), sequence=cursor)["drivers"]["1"]["attempts"]

    before = attempts(len(events))
    assert len(before) == 1
    assert attempts(len(events) + 1) == before
    result = attempts(len(all_events))
    assert [item["lap"] for item in result] == [4, None, 5]
    assert [item["lapTime"] for item in result] == [79.1, 100.0, 79.1]
    assert result[1]["lapNumberStatus"] == "UNCONFIRMED"
    assert result[0]["occurredAt"] == first.occurred_at
    assert attempts(len(events)) == before
