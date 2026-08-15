import asyncio
import json
from pathlib import Path
from threading import Event

from slipstream.adapters.openf1 import OpenF1Client, recording_to_events
from slipstream.analytics import build_analytics_snapshot, pace_model
from slipstream.events import NormalizedEvent
from slipstream.evidence import LapObservation, SessionEvidence
from slipstream.library import ReplayResource, SessionDescriptor
from slipstream.replay import replay
from slipstream.session import LayoutFamily, SessionKind, classify_session
from slipstream.state import DriverState, RaceState, SessionState
from slipstream.weekend import (
    ContextAvailability,
    WeekendContextCoordinator,
    WeekendContextStore,
)


def descriptor(tmp_path: Path, *, kind: str = "Race") -> SessionDescriptor:
    return SessionDescriptor(
        key="300",
        year=2026,
        meeting_key="30",
        meeting_name="Context Grand Prix",
        session_name=kind,
        session_type="Race",
        circuit="Context Ring",
        location="Somewhere",
        date_start="2026-08-01T14:00:00+00:00",
        date_end="2026-08-01T16:00:00+00:00",
        gmt_offset="00:00:00",
        path=tmp_path / "race.json",
        source="test",
        capabilities={},
    )


def test_session_kind_and_layout_family_cover_sprint_weekends() -> None:
    assert classify_session("Practice", "Practice 1").kind is SessionKind.PRACTICE_1
    assert classify_session("Qualifying", "Sprint Qualifying") == (
        classify_session("Qualifying", "Sprint Shootout")
    )
    assert classify_session("Qualifying", "Sprint Qualifying").kind is SessionKind.SPRINT_QUALIFYING
    assert classify_session("Race", "Sprint").layout_family is LayoutFamily.RACE
    assert classify_session("Race", "Race").kind is SessionKind.RACE


def test_weekend_context_excludes_target_and_future_sessions() -> None:
    sessions = [
        {"meeting_key": 3, "session_key": 10, "session_name": "Practice 1", "session_type": "Practice", "date_start": "2026-07-31T10:00:00+00:00", "date_end": "2026-07-31T11:00:00+00:00"},
        {"meeting_key": 3, "session_key": 30, "session_name": "Race", "session_type": "Race", "date_start": "2026-08-01T14:00:00+00:00", "date_end": "2026-08-01T16:00:00+00:00"},
        {"meeting_key": 3, "session_key": 40, "session_name": "Test", "session_type": "Practice", "date_start": "2026-08-02T10:00:00+00:00", "date_end": "2026-08-02T11:00:00+00:00"},
        {"meeting_key": 99, "session_key": 9, "session_name": "Prior Grand Prix", "session_type": "Race", "date_start": "2026-07-20T14:00:00+00:00", "date_end": "2026-07-20T16:00:00+00:00"},
    ]

    class Client(OpenF1Client):
        def get(self, endpoint: str, *, allow_not_found: bool = False, **params: object) -> list[dict[str, object]]:
            if endpoint == "sessions":
                return sessions
            return []

    context = Client(minimum_interval=0).capture_weekend_context(
        meeting_key="3",
        target_session_key="30",
        evidence_cutoff="2026-08-01T14:00:00+00:00",
        meeting_name="Context Grand Prix",
        inventory=[],
    )

    assert [item["session_key"] for item in context["sessions"]] == ["10"]
    assert {item["session_key"] for item in context["session_inventory"]} == {"10", "30", "40"}
    assert all(item["meeting_key"] == "3" for item in context["sessions"])
    assert context["evidence_cutoff"] == "2026-08-01T14:00:00+00:00"


def test_weekend_context_store_rejects_cross_meeting_evidence(tmp_path: Path) -> None:
    item = descriptor(tmp_path)
    store = WeekendContextStore(tmp_path)
    payload = {
        "format": "slipstream.weekend-context.v1",
        "schema_version": 1,
        "generated_at": "2026-08-01T13:00:00Z",
        "evidence_cutoff": item.date_start,
        "model_version": "weekend-context-v1",
        "meeting_key": item.meeting_key,
        "target_session_key": item.key,
        "sessions": [
            {
                "meeting_key": "another-meeting",
                "session_key": "foreign-practice",
                "lap_observations": [],
            }
        ],
    }
    store.save(item, payload)

    assert store.load(item) is None


def test_context_preparation_is_non_blocking_and_persisted(tmp_path: Path) -> None:
    item = descriptor(tmp_path)
    started = Event()
    release = Event()

    def builder(**kwargs: object) -> dict[str, object]:
        started.set()
        release.wait(timeout=1)
        return {
            "format": "slipstream.weekend-context.v1",
            "schema_version": 1,
            "generated_at": "2026-08-01T13:00:00Z",
            "evidence_cutoff": kwargs["evidence_cutoff"],
            "model_version": "weekend-context-v1",
            "meeting_key": kwargs["meeting_key"],
            "target_session_key": kwargs["target_session_key"],
            "sessions": [],
        }

    async def exercise() -> None:
        coordinator = WeekendContextCoordinator(WeekendContextStore(tmp_path), builder)
        first = coordinator.ensure(item, (item,))
        assert first.status == "preparing"
        assert await asyncio.to_thread(started.wait, 0.5)
        assert coordinator.current(item).status == "preparing"
        release.set()
        await coordinator._tasks[item.key]
        assert coordinator.current(item).status == "ready"

    asyncio.run(exercise())
    assert WeekendContextStore(tmp_path).load(item) is not None


def test_clean_lap_pace_model_ignores_contaminated_outlier() -> None:
    laps = tuple(
        LapObservation(
            lap=index + 1,
            started_at=f"2026-08-01T14:0{index}:00Z",
            duration=duration,
            compound="MEDIUM",
            stint_number=1,
            tyre_age=index + 1,
            quality=quality,
            contamination_reasons=("pit_in",) if quality == "contaminated" else (),
        )
        for index, (duration, quality) in enumerate(
            [(90.0, "representative"), (90.2, "representative"), (150.0, "contaminated"), (90.6, "representative"), (90.8, "representative"), (91.0, "representative")]
        )
    )

    model = pace_model(laps)

    assert model["currentStintBaseline"] == 90.6
    assert model["degradation"]["status"] == "DERIVED"
    assert 0.19 <= model["degradation"]["value"] <= 0.21
    assert model["samples"][2]["quality"] == "contaminated"


def test_pre_race_and_live_outlook_keep_unknown_values_truthful(tmp_path: Path) -> None:
    session_event = NormalizedEvent(
        kind="session",
        occurred_at="2026-08-01T14:00:00+00:00",
        source="test",
        payload={"key": "300", "session_kind": "race", "layout_family": "race", "status": "STARTED"},
    )
    lap_event = NormalizedEvent(
        kind="timing",
        occurred_at="2026-08-01T14:02:00+00:00",
        source="test",
        payload={"number": "1", "lap": 2, "lap_observation": {"lap": 2, "started_at": "2026-08-01T14:00:30+00:00", "duration": 90.0, "compound": "MEDIUM", "stint_number": 1, "tyre_age": 2, "quality": "representative"}},
    )
    events = (session_event, lap_event)
    state = RaceState(
        session=SessionState(key="300", session_kind="race", layout_family="race", status="STARTED"),
        drivers={"1": DriverState(number="1", position=1, compound="MEDIUM")},
    )
    resource = ReplayResource(descriptor(tmp_path), events, replay(list(events)), SessionEvidence.from_events(events), True, False)

    pre_race = build_analytics_snapshot(resource, state, sequence=1, as_of=session_event.occurred_at, context=ContextAvailability("preparing"))
    live = build_analytics_snapshot(resource, state, sequence=2, as_of=lap_event.occurred_at, context=ContextAvailability("ready", {"generated_at": "2026-08-01T13:00:00Z", "model_version": "weekend-context-v1", "sessions": [], "external_intelligence": {"status": "disabled", "items": []}}))

    assert pre_race["stage"] == "BASELINE_AVAILABLE"
    assert pre_race["context"]["meetingKey"] == "30"
    assert pre_race["drivers"]["1"]["strategy"]["primaryStrategy"]["status"] == "UNKNOWN"
    assert live["stage"] == "LIVE_OUTLOOK"
    assert live["drivers"]["1"]["strategy"]["degradation"]["status"] == "UNKNOWN"


def test_same_meeting_context_enriches_prerace_degradation(tmp_path: Path) -> None:
    session_event = NormalizedEvent(
        kind="session",
        occurred_at="2026-08-01T14:00:00+00:00",
        source="test",
        payload={
            "key": "300",
            "session_kind": "race",
            "layout_family": "race",
            "status": "SCHEDULED",
        },
    )
    state = RaceState(
        session=SessionState(
            key="300",
            session_kind="race",
            layout_family="race",
            status="SCHEDULED",
        ),
        drivers={"1": DriverState(number="1", position=1, compound="MEDIUM")},
    )
    resource = ReplayResource(
        descriptor(tmp_path),
        (session_event,),
        state,
        SessionEvidence.from_events((session_event,)),
        True,
        False,
    )
    laps = [
        {
            "driver_number": "1",
            "lap": lap,
            "started_at": f"2026-07-31T10:{lap:02d}:00Z",
            "duration": duration,
            "compound": "MEDIUM",
            "stint_number": 2,
            "tyre_age": lap,
            "quality": "representative",
            "contamination_reasons": [],
        }
        for lap, duration in enumerate((90.0, 90.2, 90.4, 90.6, 90.8), start=1)
    ]
    context = ContextAvailability(
        "ready",
        {
            "meeting_key": "30",
            "generated_at": "2026-08-01T13:00:00Z",
            "model_version": "weekend-context-v1",
            "sessions": [
                {
                    "meeting_key": "30",
                    "session_key": "practice-2",
                    "session_name": "Practice 2",
                    "lap_observations": laps,
                }
            ],
            "external_intelligence": {"status": "disabled", "items": []},
        },
    )

    snapshot = build_analytics_snapshot(
        resource,
        state,
        sequence=1,
        as_of=session_event.occurred_at,
        context=context,
    )

    degradation = snapshot["drivers"]["1"]["strategy"]["degradation"]
    assert snapshot["stage"] == "WEEKEND_MODEL_READY"
    assert degradation["status"] == "ESTIMATE"
    assert degradation["value"] == 0.2


def test_driver_context_and_recommended_battle_share_one_model(tmp_path: Path) -> None:
    events = (
        NormalizedEvent(
            kind="session",
            occurred_at="2026-08-01T14:00:00+00:00",
            source="test",
            payload={"key": "300", "session_kind": "race", "layout_family": "race", "status": "STARTED"},
        ),
    )
    state = RaceState(
        session=SessionState(key="300", session_kind="race", layout_family="race", status="STARTED"),
        drivers={
            "1": DriverState(number="1", code="AAA", position=1, gap_to_leader=None),
            "2": DriverState(number="2", code="BBB", position=2, gap_to_leader="+1.250", interval_to_ahead="+1.250"),
            "3": DriverState(number="3", code="CCC", position=3, gap_to_leader="+9.000", interval_to_ahead="+7.750"),
        },
    )
    resource = ReplayResource(descriptor(tmp_path), events, state, SessionEvidence.from_events(events), True, False)

    snapshot = build_analytics_snapshot(resource, state, sequence=1, as_of=events[0].occurred_at, context=ContextAvailability("unavailable"))

    assert snapshot["drivers"]["2"]["ahead"]["driverNumber"] == "1"
    assert snapshot["drivers"]["2"]["behind"]["driverNumber"] == "3"
    assert snapshot["battle"]["recommended"]["aheadDriverNumber"] == "1"
    assert snapshot["battle"]["recommended"]["behindDriverNumber"] == "2"
    assert snapshot["battle"]["hysteresis"] == {"minimumHoldSeconds": 20, "switchMargin": 8}


def test_pit_event_keeps_compound_transition_and_distinct_durations() -> None:
    fixture = Path(__file__).parent / "fixtures" / "openf1" / "stint-transition.json"
    raw = json.loads(fixture.read_text(encoding="utf-8"))
    raw["endpoints"]["pit"][0].update({"lane_duration": 22.1, "stop_duration": 2.4})
    evidence = SessionEvidence.from_events(tuple(recording_to_events(raw)))

    event = evidence.pit_events_for_driver("4")[0]
    assert event.previous_compound == "MEDIUM"
    assert event.new_compound == "HARD"
    assert event.stop_duration == 2.4
    assert event.pit_lane_duration == 22.1
