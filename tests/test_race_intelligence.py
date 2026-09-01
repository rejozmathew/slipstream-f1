from dataclasses import replace
from pathlib import Path

from slipstream.analytics import (
    AnalyticsService,
    _projection_gate,
    battle_recommendation,
    metric,
)
from slipstream.events import NormalizedEvent
from slipstream.evidence import LapObservation, SessionEvidence
from slipstream.library import ReplayResource, SessionDescriptor
from slipstream.race_intelligence import (
    field_distributions,
    finish_assessment,
    phase_weight,
    race_read,
)
from slipstream.state import DriverState, RaceState, SessionState
from slipstream.weekend import ContextAvailability


def _lap(
    lap: int,
    age: int,
    *,
    compound: str = "HARD",
    pit_in: bool = False,
    duration: float = 90.0,
) -> LapObservation:
    return LapObservation(
        lap=lap,
        started_at=f"2026-08-01T14:{lap:02d}:00+00:00",
        duration=duration,
        compound=compound,
        stint_number=1,
        tyre_age=age,
        pit_in=pit_in,
        previous_compound=compound if pit_in else None,
        new_compound="SOFT" if pit_in else None,
        quality="representative",
    )


def _state(*, track_status: str = "GREEN") -> RaceState:
    return RaceState(
        session=SessionState(
            key="300",
            session_kind="race",
            layout_family="race",
            status="STARTED",
            lap=60,
            total_laps=70,
            track_status=track_status,
        ),
        drivers={
            "1": DriverState(
                number="1",
                code="AAA",
                position=1,
                lap=60,
                compound="HARD",
                tyre_age=20,
                status="RUNNING",
            ),
            "2": DriverState(
                number="2",
                code="BBB",
                position=2,
                lap=60,
                compound="MEDIUM",
                tyre_age=10,
                status="RUNNING",
                interval_to_ahead="2.0",
            ),
        },
    )


def _finish_evidence() -> dict[str, tuple[LapObservation, ...]]:
    return {
        "1": (_lap(57, 18), _lap(58, 19), _lap(59, 20), _lap(60, 21)),
        "2": (
            _lap(42, 32, pit_in=True),
            _lap(50, 34, pit_in=True),
            _lap(55, 36, pit_in=True),
        ),
        "3": (_lap(56, 35, pit_in=True),),
    }


def test_phase_weight_prioritizes_same_race_phase() -> None:
    assert phase_weight(60, 62, 70) == 1.0
    assert phase_weight(10, 62, 70) < phase_weight(45, 62, 70)


def test_to_finish_requires_positive_same_race_evidence() -> None:
    state = _state()
    driver = state.drivers["1"]
    pace = metric(0.1, status="DERIVED", evidence=["clean current stint"], unit="s/lap")
    supported = finish_assessment(driver, state, _finish_evidence(), pace, "SATISFIED")
    assert supported["canFinish"] is True
    assert supported["status"] == "SUPPORTED"
    insufficient = finish_assessment(
        driver, state, {"1": _finish_evidence()["1"]}, pace, "SATISFIED"
    )
    assert insufficient["canFinish"] is None
    assert insufficient["status"] in {"UNKNOWN", "INSUFFICIENT"}


def test_generic_yellow_does_not_reset_but_safety_car_does() -> None:
    pace = metric(0.1, status="DERIVED", evidence=["clean current stint"], unit="s/lap")
    yellow = _state(track_status="YELLOW")
    assert (
        finish_assessment(
            yellow.drivers["1"], yellow, _finish_evidence(), pace, "SATISFIED"
        )["canFinish"]
        is True
    )
    safety_car = _state(track_status="SAFETY CAR")
    assert (
        finish_assessment(
            safety_car.drivers["1"], safety_car, _finish_evidence(), pace, "SATISFIED"
        )["canFinish"]
        is None
    )


def test_starting_and_current_tyre_populations_are_distinct() -> None:
    state = _state()
    state = replace(
        state,
        drivers={
            **state.drivers,
            "1": replace(state.drivers["1"], compound="SOFT"),
            "3": DriverState(
                number="3", compound="MEDIUM", status="RETIRED", position=3
            ),
        },
    )
    evidence = {
        "1": (_lap(1, 1, compound="HARD"), _lap(20, 1, compound="SOFT")),
        "2": (_lap(1, 1, compound="MEDIUM"),),
        "3": (_lap(1, 1, compound="MEDIUM"),),
    }
    result = field_distributions(state, evidence)
    assert result["startingTyreDistribution"] == {"HARD": 1, "MEDIUM": 2}
    assert result["currentTyreDistribution"] == {"MEDIUM": 1, "SOFT": 1}
    assert result["startingTyrePopulation"]["participants"] == 3
    assert result["currentTyrePopulation"]["running"] == 2


def test_observed_sequences_exclude_stopped_and_retired_drivers() -> None:
    state = _state()
    state = replace(
        state,
        drivers={
            **state.drivers,
            "3": DriverState(number="3", compound="SOFT", status="STOPPED"),
            "4": DriverState(number="4", compound="HARD", status="RETIRED"),
        },
    )
    evidence = {
        "1": (_lap(1, 1, compound="HARD"), _lap(20, 1, compound="SOFT")),
        "2": (_lap(1, 1, compound="MEDIUM"),),
        "3": (_lap(1, 1, compound="SOFT"),),
        "4": (_lap(1, 1, compound="HARD"),),
    }

    result = field_distributions(state, evidence)

    assert result["startingTyrePopulation"] == {"known": 4, "participants": 4}
    assert result["observedSequences"] == [
        {"sequence": "HARD → SOFT", "drivers": 1},
        {"sequence": "MEDIUM", "drivers": 1},
    ]


def test_observed_sequences_are_empty_for_a_settled_final_field() -> None:
    state = _state()
    state = replace(
        state,
        drivers={
            number: replace(
                driver,
                classification="FINISHED" if number == "1" else "DNF",
                status="FINISHED" if number == "1" else "DNF",
            )
            for number, driver in state.drivers.items()
        },
    )
    evidence = {
        "1": (_lap(1, 1, compound="HARD"), _lap(20, 1, compound="SOFT")),
        "2": (_lap(1, 1, compound="MEDIUM"),),
    }

    result = field_distributions(state, evidence)

    assert result["runningDriverCount"] == 0
    assert result["currentTyreDistribution"] == {}
    assert result["observedSequences"] == []


def test_race_read_is_structured_and_uses_current_race_pace_only() -> None:
    state = _state()
    evidence = _finish_evidence()
    distributions = field_distributions(state, evidence)
    models = {
        "1": {"pace": {"paceTrend": metric(0.16, status="DERIVED", evidence=["race"])}},
        "2": {
            "pace": {"paceTrend": metric(None, status="UNKNOWN", evidence=["missing"])}
        },
    }
    result = race_read(
        state,
        models,
        evidence,
        (),
        {"1": "SATISFIED", "2": "UNSATISFIED"},
        "LIVE",
        distributions,
    )
    assert result["population"] == {
        "participants": 2,
        "running": 2,
        "inPit": 0,
        "stopped": 0,
        "retired": 0,
        "unconfirmed": 0,
        "finished": 0,
        "dnf": 0,
        "dns": 0,
        "dsq": 0,
    }
    assert result["paceTrendDistribution"]["highFade"] == 1
    assert result["paceTrendDistribution"]["unknown"] == 1
    assert "current-race" in result["paceTrendDistribution"]["basis"]
    assert result["dryRequirementLandscape"]["denominator"] == 2


def test_race_read_population_is_truthful_and_reconciles() -> None:
    state = _state()
    state = replace(
        state,
        drivers={
            "1": state.drivers["1"],
            "2": replace(state.drivers["2"], activity="IN_PIT"),
            "3": DriverState(number="3", status="STOPPED", compound="SOFT"),
            "4": DriverState(number="4", status="UNKNOWN", compound="HARD"),
            "5": DriverState(number="5", status="DNF", compound="MEDIUM"),
        },
    )
    distributions = field_distributions(state, {})
    result = race_read(state, {}, {}, (), {}, "LIVE", distributions)

    assert result["population"] == {
        "participants": 5,
        "running": 1,
        "inPit": 1,
        "stopped": 1,
        "retired": 0,
        "unconfirmed": 1,
        "finished": 0,
        "dnf": 1,
        "dns": 0,
        "dsq": 0,
    }
    assert (
        sum(
            value
            for key, value in result["population"].items()
            if key != "participants"
        )
        == 5
    )
    assert distributions["runningDriverCount"] == 2
    assert distributions["currentTyrePopulation"] == {"known": 2, "running": 2}
    assert distributions["currentTyreDistribution"] == {"HARD": 1, "MEDIUM": 1}


def test_projection_gate_blocks_unstable_or_invalid_future() -> None:
    state = _state()
    strategy = {
        "pitWindow": metric([55, 72], status="ESTIMATE", evidence=["bad"], unit="lap"),
        "primaryStrategy": metric(
            "HARD → SOFT", status="ESTIMATE", evidence=["sample"]
        ),
        "alternateStrategy": metric(None, status="UNKNOWN", evidence=["none"]),
        "likelyNextCompound": metric("SOFT", status="ESTIMATE", evidence=["sample"]),
        "dryTyreRequirement": "SATISFIED",
        "finishAssessment": {"canFinish": None},
    }
    gate = _projection_gate(
        strategy,
        state,
        "LIVE_OUTLOOK",
        driver=state.drivers["1"],
        evidence_by_driver={"1": ()},
    )
    assert gate["hardValidity"]["status"] == "FAIL"
    assert gate["stability"]["status"] == "INSUFFICIENT"
    assert gate["publishAllowed"] is False


def test_battle_rejects_non_meaningful_large_gap() -> None:
    state = _state()
    drivers = [
        state.drivers["1"],
        replace(state.drivers["2"], interval_to_ahead="50.0"),
    ]
    models = {
        driver.number: {
            "pace": {
                "paceTrend": {"value": None},
                "degradation": {"value": None},
                "currentStintBaseline": None,
            },
            "strategy": {"pitWindow": {"value": None}},
        }
        for driver in drivers
    }
    assert (
        battle_recommendation(drivers, models, layout_family="race")["recommended"]
        is None
    )


def test_completed_gap_history_is_lap_scoped_and_request_order_independent(
    tmp_path: Path,
) -> None:
    events = (
        NormalizedEvent(
            "session",
            "2026-08-01T14:00:00+00:00",
            "test",
            {
                "key": "300",
                "session_kind": "race",
                "layout_family": "race",
                "status": "STARTED",
                "lap": 1,
                "total_laps": 70,
            },
        ),
        NormalizedEvent(
            "driver",
            "2026-08-01T14:00:01+00:00",
            "test",
            {"number": "1", "position": 1, "status": "RUNNING"},
        ),
        NormalizedEvent(
            "timing",
            "2026-08-01T14:01:00+00:00",
            "test",
            {
                "number": "2",
                "position": 2,
                "status": "RUNNING",
                "interval_to_ahead": "2.0",
                "lap_observation": {
                    "lap": 1,
                    "started_at": "2026-08-01T14:01:00+00:00",
                    "duration": 90.0,
                    "compound": "MEDIUM",
                    "tyre_age": 1,
                    "quality": "representative",
                },
            },
        ),
        NormalizedEvent(
            "timing",
            "2026-08-01T14:02:30+00:00",
            "test",
            {
                "number": "2",
                "position": 2,
                "status": "RUNNING",
                "interval_to_ahead": "1.8",
                "lap_observation": {
                    "lap": 2,
                    "started_at": "2026-08-01T14:02:30+00:00",
                    "duration": 90.0,
                    "compound": "MEDIUM",
                    "tyre_age": 2,
                    "quality": "representative",
                },
            },
        ),
    )
    evidence = SessionEvidence.from_events(events)
    assert [item.gap_seconds for item in evidence.completed_gap_history("1", "2")] == [
        2.0,
        1.8,
    ]
    state = _state()
    state = replace(
        state,
        session=replace(state.session, lap=2),
        drivers={
            "1": replace(state.drivers["1"], lap=2, compound="HARD", tyre_age=2),
            "2": replace(
                state.drivers["2"],
                lap=2,
                compound="MEDIUM",
                tyre_age=2,
                interval_to_ahead="1.8",
            ),
        },
    )
    descriptor = SessionDescriptor(
        key="300",
        year=2026,
        meeting_key="30",
        meeting_name="Test GP",
        session_name="Race",
        session_type="Race",
        circuit="Ring",
        location="Here",
        date_start="2026-08-01T14:00:00+00:00",
        date_end="2026-08-01T16:00:00+00:00",
        gmt_offset="00:00:00",
        path=tmp_path / "race.json",
        source="test",
        capabilities={},
    )
    resource = ReplayResource(descriptor, events, state, evidence, True, False)
    context = ContextAvailability("unavailable")
    direct = AnalyticsService().snapshot(
        resource, state, sequence=4, as_of=events[-1].occurred_at, context=context
    )
    reordered_service = AnalyticsService()
    reordered_service.snapshot(
        resource, state, sequence=2, as_of=events[1].occurred_at, context=context
    )
    reordered = reordered_service.snapshot(
        resource, state, sequence=4, as_of=events[-1].occurred_at, context=context
    )
    assert (
        direct["battle"]["heldRecommendation"]
        == reordered["battle"]["heldRecommendation"]
    )
    assert direct["battle"]["stabilizedRecommended"] is not None
