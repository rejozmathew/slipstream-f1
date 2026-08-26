from pathlib import Path

from slipstream.analytics import build_analytics_snapshot
from slipstream.events import NormalizedEvent
from slipstream.evidence import SessionEvidence
from slipstream.library import ReplayResource, SessionDescriptor
from slipstream.live import F1LiveAdapter
from slipstream.replay import replay
from slipstream.state import RaceState
from slipstream.weekend import ContextAvailability


def _events() -> tuple[NormalizedEvent, ...]:
    return (
        NormalizedEvent(
            "session",
            "2026-08-01T14:00:00+00:00",
            "fixture",
            {
                "key": "lifecycle-fixture",
                "session_kind": "race",
                "layout_family": "race",
                "status": "STARTED",
                "track_status": "GREEN",
                "lap": 1,
                "total_laps": 5,
            },
        ),
        NormalizedEvent(
            "driver",
            "2026-08-01T14:00:01+00:00",
            "fixture",
            {
                "number": "1",
                "code": "AAA",
                "position": 1,
                "status": "RUNNING",
                "compound": "MEDIUM",
                "pit_count": 1,
            },
        ),
        NormalizedEvent(
            "driver",
            "2026-08-01T14:00:02+00:00",
            "fixture",
            {
                "number": "2",
                "code": "BBB",
                "position": 2,
                "status": "RUNNING",
                "compound": "HARD",
                "pit_count": 1,
            },
        ),
        NormalizedEvent(
            "timing",
            "2026-08-01T14:01:00+00:00",
            "fixture",
            {"number": "2", "status": "STOPPED"},
        ),
        # Positive source-neutral timing evidence permits STOPPED to resume.
        NormalizedEvent(
            "timing",
            "2026-08-01T14:02:00+00:00",
            "fixture",
            {"number": "2", "status": "RUNNING", "lap": 2},
        ),
        NormalizedEvent(
            "timing",
            "2026-08-01T14:03:00+00:00",
            "fixture",
            {"number": "2", "status": "RETIRED"},
        ),
        # A late packet cannot resurrect a terminal driver.
        NormalizedEvent(
            "timing",
            "2026-08-01T14:04:00+00:00",
            "fixture",
            {"number": "2", "status": "RUNNING", "lap": 3},
        ),
        NormalizedEvent(
            "driver",
            "2026-08-01T14:05:00+00:00",
            "fixture",
            {"number": "2", "status": "DNF"},
        ),
        NormalizedEvent(
            "session",
            "2026-08-01T14:06:00+00:00",
            "fixture",
            {
                "status": "FINISHED",
                "track_status": "CHEQUERED",
                "lap": 5,
            },
        ),
    )


def _resource(tmp_path: Path, events: tuple[NormalizedEvent, ...]) -> ReplayResource:
    descriptor = SessionDescriptor(
        key="lifecycle-fixture",
        year=2026,
        meeting_key="m1",
        meeting_name="Lifecycle GP",
        session_name="Race",
        session_type="Race",
        circuit="Fixture Ring",
        location="Fixture",
        date_start=events[0].occurred_at,
        date_end=events[-1].occurred_at,
        gmt_offset="00:00:00",
        path=tmp_path / "lifecycle.json",
        source="fixture",
        capabilities={},
    )
    return ReplayResource(
        descriptor,
        events,
        replay(list(events)),
        SessionEvidence.from_events(events),
        True,
        False,
    )


def _analytics(resource: ReplayResource, sequence: int):
    state = replay(list(resource.events), event_limit=sequence)
    return state, build_analytics_snapshot(
        resource,
        state,
        sequence=sequence,
        as_of=state.updated_at,
        context=ContextAvailability("unavailable"),
    )


def test_stopped_resumes_only_with_positive_evidence_and_terminal_never_resumes(
    tmp_path: Path,
) -> None:
    resource = _resource(tmp_path, _events())

    running, running_analytics = _analytics(resource, 3)
    assert running.drivers["2"].status == "RUNNING"
    assert running_analytics["drivers"]["2"]["strategy"]["terminalState"] is None
    assert running_analytics["raceRead"]["population"] == {
        "participants": 2,
        "active": 2,
        "circulating": 2,
        "stopped": 0,
        "terminal": 0,
    }

    stopped, stopped_analytics = _analytics(resource, 4)
    assert stopped.drivers["2"].status == "STOPPED"
    assert stopped_analytics["drivers"]["2"]["strategy"]["terminalState"] is None
    assert stopped_analytics["raceRead"]["population"] == {
        "participants": 2,
        "active": 2,
        "circulating": 1,
        "stopped": 1,
        "terminal": 0,
    }
    assert all(
        candidate["aheadDriverNumber"] != "2" and candidate["behindDriverNumber"] != "2"
        for candidate in stopped_analytics["battle"]["candidates"]
    )

    resumed, resumed_analytics = _analytics(resource, 5)
    assert resumed.drivers["2"].status == "RUNNING"
    assert resumed_analytics["drivers"]["2"]["strategy"]["terminalState"] is None

    retired, retired_analytics = _analytics(resource, 6)
    assert retired.drivers["2"].status == "RETIRED"
    assert retired_analytics["raceRead"]["population"] == {
        "participants": 2,
        "active": 1,
        "circulating": 1,
        "stopped": 0,
        "terminal": 1,
    }
    strategy = retired_analytics["drivers"]["2"]["strategy"]
    assert strategy["terminalState"] == "RETIRED"
    assert strategy["disposition"] == "UNKNOWN"
    assert strategy["windowState"] == "UNKNOWN"
    assert strategy["pitWindow"]["value"] is None
    assert strategy["primaryStrategy"]["value"] is None
    assert all(
        candidate["aheadDriverNumber"] != "2" and candidate["behindDriverNumber"] != "2"
        for candidate in retired_analytics["battle"]["candidates"]
    )

    late_packet, _ = _analytics(resource, 7)
    assert late_packet.drivers["2"].status == "RETIRED"


def test_final_cursor_suppresses_all_future_strategy_without_hindsight(
    tmp_path: Path,
) -> None:
    resource = _resource(tmp_path, _events())

    final_state, final_analytics = _analytics(resource, len(resource.events))
    assert final_state.drivers["2"].status == "DNF"
    assert final_analytics["strategyLifecycle"] == "FINAL"
    assert final_analytics["strategyValidity"] == "UNAVAILABLE"
    assert final_analytics["raceStrategy"]["windowState"] == "FINAL"
    assert final_analytics["raceStrategy"]["disposition"] == "UNKNOWN"
    assert final_analytics["raceStrategy"]["pitWindow"]["value"] is None
    for model in final_analytics["drivers"].values():
        strategy = model["strategy"]
        assert strategy["windowState"] == "FINAL"
        assert strategy["disposition"] == "UNKNOWN"
        assert strategy["pitWindow"]["value"] is None
        assert strategy["primaryStrategy"]["value"] is None
        assert strategy["alternateStrategy"]["value"] is None

    # Asking for an earlier cursor after the final cursor produces the same
    # state as asking for it first. Final classification never leaks backward.
    earlier_after_final, earlier_analytics = _analytics(resource, 5)
    earlier_first, earlier_first_analytics = _analytics(resource, 5)
    assert earlier_after_final == earlier_first
    assert earlier_analytics == earlier_first_analytics
    assert earlier_after_final.drivers["2"].status == "RUNNING"
    assert earlier_analytics["strategyLifecycle"] != "FINAL"


def test_stroll_live_retirement_is_terminal_at_exact_normalized_cursor() -> None:
    adapter = F1LiveAdapter("11353")
    rows = [
        {
            "received_at": "2026-08-23T14:36:45Z",
            "stream": "SessionInfo",
            "initial": True,
            "payload": {"Key": 11353, "Name": "Race", "Type": "Race"},
        },
        {
            "received_at": "2026-08-23T14:36:45.500Z",
            "stream": "DriverList",
            "initial": False,
            "payload": {
                "18": {
                    "RacingNumber": "18",
                    "Tla": "STR",
                    "FullName": "Lance STROLL",
                    "TeamName": "Aston Martin",
                }
            },
        },
        {
            "received_at": "2026-08-23T14:36:46.926204Z",
            "stream": "TimingData",
            "initial": False,
            "payload": {
                "Lines": {
                    "18": {
                        "RacingNumber": "18",
                        "Retired": True,
                        "Stopped": True,
                        "InPit": True,
                        "Position": "20",
                        "NumberOfLaps": 45,
                        "NumberOfPitStops": 4,
                    }
                }
            },
        },
    ]
    events = []
    for row in rows:
        events.extend(adapter.ingest(row))
    retirement_cursor = next(
        index
        for index, event in enumerate(events, start=1)
        if event.kind == "timing"
        and event.occurred_at == "2026-08-23T14:36:46.926204Z"
        and event.payload.get("number") == "18"
    )
    assert events[retirement_cursor - 1].payload["status"] == "RETIRED"

    incremental = RaceState()
    for event in events[:retirement_cursor]:
        incremental = incremental.apply(event)
    replayed = replay(events, event_limit=retirement_cursor)
    assert incremental.drivers["18"].status == "RETIRED"
    assert replayed.drivers["18"].status == "RETIRED"
    assert incremental == replayed
