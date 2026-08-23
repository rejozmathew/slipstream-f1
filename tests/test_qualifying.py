import json
from dataclasses import asdict
from pathlib import Path

from slipstream.events import NormalizedEvent
from slipstream.library import ReplayLibrary
from slipstream.qualifying import build_qualifying_snapshot
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
                "session_clock": "00:05:42",
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


def test_qualifying_contract_authors_phase_clock_cut_and_attempts(tmp_path: Path) -> None:
    resource, events = _resource(tmp_path)
    snapshot = build_qualifying_snapshot(
        resource,
        replay(events),
        sequence=len(events),
    )

    assert snapshot["phase"] == "Q1"
    assert snapshot["sessionClock"] == "00:05:42"
    assert snapshot["benchmark"]["driverNumber"] == "1"
    assert snapshot["cutLine"]["advancePosition"] == 16
    assert snapshot["cutLine"]["cutoff"]["driverNumber"] == "16"
    assert snapshot["cutLine"]["firstOut"]["driverNumber"] == "17"
    assert snapshot["drivers"]["1"]["cutState"] == "ADVANCING"
    assert snapshot["drivers"]["17"]["cutState"] == "BELOW_CUT"
    assert snapshot["drivers"]["22"]["cutState"] == "ELIMINATED"
    assert snapshot["drivers"]["1"]["attempts"][0]["tyreUsage"] == "NEW"


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


def test_unverified_field_size_never_invents_a_cut_line(tmp_path: Path) -> None:
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

    assert snapshot["cutLine"]["status"] == "UNKNOWN"
    assert snapshot["cutLine"]["advancePosition"] is None
