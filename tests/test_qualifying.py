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
