from dataclasses import replace
from datetime import UTC, datetime

from slipstream.evidence import LapObservation, PitEvent
from slipstream.pirelli.contracts import (
    Compound,
    CompoundCount,
    CompoundSelection,
    ContextFact,
    DriverTyreBank,
    EvidenceKind,
    ExtractionMethod,
    FactApplicability,
    PitWindow,
    SessionScope,
    SourceEvidence,
    StrategyOption,
    StrategyOrder,
    StrategyRank,
    TyreBankCoverage,
    TyreBankSnapshot,
)
from slipstream.pirelli.snapshot import PirelliEvidenceSnapshot, StrategyReleaseView
from slipstream.pirelli.store import PirelliAvailability
from slipstream.published_strategy import build_published_strategy
from slipstream.state import DriverState, RaceState, SessionState, WeatherState


def _evidence():
    return SourceEvidence(
        artifact_id="a",
        source_url="https://press.pirelli.com/race",
        kind=EvidenceKind.TEXT,
        extraction_method=ExtractionMethod.DETERMINISTIC_PROSE,
        text="published option",
    )


def _option(
    option_id: str,
    compounds: tuple[Compound, ...],
    *,
    rank: StrategyRank = StrategyRank.FASTEST_PUBLISHED,
    order: StrategyOrder = StrategyOrder.ORDERED,
    windows: tuple[PitWindow | None, ...] | None = None,
):
    return StrategyOption(
        id=option_id,
        rank=rank,
        order=order,
        stop_count=len(compounds) - 1,
        compounds=compounds,
        pit_windows=windows or tuple(None for _ in compounds[1:]),
        source_evidence=(_evidence(),),
        applicability=FactApplicability(
            meeting_key="30", session_scope=SessionScope.RACE
        ),
    )


def _availability(
    *options: StrategyOption,
    selection: bool = False,
    bank: bool = False,
    context: bool = False,
):
    published = datetime(2026, 7, 25, tzinfo=UTC)
    snapshot = PirelliEvidenceSnapshot(
        release_ids=("release",),
        compound_selections=(
            CompoundSelection(
                "C3",
                "C4",
                "C5",
                (_evidence(),),
                FactApplicability(meeting_key="30", session_scope=SessionScope.WEEKEND),
            ),
        )
        if selection
        else (),
        strategy_releases=(
            StrategyReleaseView(
                "release",
                "https://press.pirelli.com/race",
                published,
                published,
                tuple(options),
            ),
        )
        if options
        else (),
        tyre_bank_snapshots=(
            TyreBankSnapshot(
                as_of=published,
                target_session="race",
                drivers=(
                    DriverTyreBank(
                        "Driver",
                        CompoundCount(1, 0),
                        CompoundCount(0, 1),
                        CompoundCount(2, 0),
                        1.0,
                        (_evidence(),),
                        "1",
                        "AAA",
                    ),
                ),
                source_evidence=(_evidence(),),
                coverage=TyreBankCoverage.PARTIAL,
            ),
        )
        if bank
        else (),
        context_facts=(
            ContextFact(
                "WEATHER",
                "The weather forecast could lead to a wet race.",
                (_evidence(),),
                FactApplicability(
                    meeting_key="30", session_scope=SessionScope.RACE
                ),
            ),
        )
        if context
        else (),
    )
    return PirelliAvailability("PRESENT", snapshot)


def _state(
    *,
    compound: str | None = "MEDIUM",
    lap: int = 20,
    status: str = "RUNNING",
    track: str = "GREEN",
    rainfall: bool | None = False,
    final: bool = False,
    pit_count: int = 0,
):
    return RaceState(
        session=SessionState(
            key="race",
            session_kind="race",
            layout_family="race",
            lap=lap,
            total_laps=70,
            track_status="CHEQUERED" if final else track,
            status="FINISHED" if final else "STARTED",
        ),
        weather=WeatherState(rainfall=rainfall),
        drivers={
            "1": DriverState(
                number="1",
                code="AAA",
                compound=compound,
                status=status,
                pit_count=pit_count,
            )
        },
    )


def _pit(
    sequence: int,
    lap: int,
    previous: str | None,
    new: str | None,
    ordinal: int,
) -> PitEvent:
    return PitEvent(
        sequence=sequence,
        occurred_at=f"2026-07-26T13:{sequence:02d}:00Z",
        driver_number="1",
        lap=lap,
        previous_compound=previous,
        new_compound=new,
        ordinal=ordinal,
    )


def _build(
    availability,
    state,
    observations=(),
    lifecycle="LIVE",
    pit_events=(),
    dry_tyre_requirement="UNKNOWN",
):
    return build_published_strategy(
        availability=availability,
        evidence_cutoff="2026-07-26T13:00:00Z",
        state=state,
        evidence_by_driver={"1": tuple(observations)},
        lifecycle=lifecycle,
        pit_events_by_driver={"1": tuple(pit_events)},
        dry_tyre_by_driver={"1": dry_tyre_requirement},
    )


def test_published_baseline_preserves_physical_nomination_and_missing_bank():
    result = _build(
        _availability(
            _option(
                "mh",
                (Compound.MEDIUM, Compound.HARD),
                windows=(PitWindow(17, 23),),
            ),
            selection=True,
        ),
        _state(),
    )
    assert result["baseline"]["compoundSelection"] == {
        "hard": "C3",
        "medium": "C4",
        "soft": "C5",
    }
    assert result["baseline"]["tyreBank"]["status"] == "ABSENT"
    assert result["baseline"]["options"][0]["rank"] == "FASTEST_PUBLISHED"


def test_context_only_baseline_is_present_with_zero_strategy_options():
    result = _build(_availability(context=True), _state())

    assert result["baseline"]["status"] == "PRESENT"
    assert result["baseline"]["options"] == []
    assert result["baseline"]["sourceUrl"] == "https://press.pirelli.com/race"
    assert result["baseline"]["contextFacts"] == [
        {
            "category": "WEATHER",
            "statement": "The weather forecast could lead to a wet race.",
        }
    ]


def test_fetching_and_retrying_availability_remain_truthful_non_present_states():
    fetching = _build(
        PirelliAvailability("FETCHING", error="official_pirelli_context_queued"),
        _state(),
    )
    retrying = _build(
        PirelliAvailability(
            "RETRYING", error="official_pirelli_context_retry_scheduled"
        ),
        _state(),
    )

    assert fetching["baseline"]["status"] == "FETCHING"
    assert retrying["baseline"]["status"] == "RETRYING"
    assert fetching["status"] == "ABSENT"
    assert retrying["status"] == "ABSENT"


def test_ordered_prefix_matching_and_window_state_are_server_authored():
    result = _build(
        _availability(
            _option(
                "mh",
                (Compound.MEDIUM, Compound.HARD),
                windows=(PitWindow(17, 23),),
            )
        ),
        _state(lap=20),
    )
    driver = result["drivers"]["1"]
    assert driver["relation"] == "MATCHING_ONE"
    assert driver["compatibleOptionIds"] == ["mh"]
    assert driver["windows"][0]["state"] == "ACTIVE"


def test_archived_later_baseline_is_displayed_but_never_models_windows() -> None:
    display_only = replace(
        _availability(
            _option(
                "mh",
                (Compound.MEDIUM, Compound.HARD),
                windows=(PitWindow(17, 23),),
            )
        ),
        model_admissible=False,
        evidence_tier="DISPLAY_ONLY_OFFICIAL_HISTORICAL",
        provenance_label="PUBLISHED PRE-RACE · ARCHIVED LATER",
    )

    result = _build(display_only, _state(lap=20))

    assert result["baseline"]["status"] == "PRESENT"
    assert result["baseline"]["options"][0]["id"] == "mh"
    assert result["baseline"]["modelAdmissible"] is False
    assert result["baseline"]["provenanceLabel"] == (
        "PUBLISHED PRE-RACE · ARCHIVED LATER"
    )
    assert result["drivers"]["1"]["relation"] == "UNKNOWN"
    assert result["drivers"]["1"]["compatibleOptionIds"] == []
    assert result["drivers"]["1"]["windows"] == []
    assert result["drivers"]["1"]["pirelliAssessment"] == "REFERENCE_ONLY"
    assert result["drivers"]["1"]["pirelliReferences"][0]["status"] == (
        "REFERENCE_ONLY"
    )
    assert result["fieldFacts"] == []


def test_equivalent_options_remain_multiple_without_inventing_preference():
    result = _build(
        _availability(
            _option(
                "mh",
                (Compound.MEDIUM, Compound.HARD),
                rank=StrategyRank.EQUIVALENT_FASTEST,
            ),
            _option(
                "ms",
                (Compound.MEDIUM, Compound.SOFT),
                rank=StrategyRank.EQUIVALENT_FASTEST,
            ),
        ),
        _state(),
    )
    assert [item["rank"] for item in result["baseline"]["options"]] == [
        "EQUIVALENT_FASTEST",
        "EQUIVALENT_FASTEST",
    ]
    assert result["drivers"]["1"]["relation"] == "MATCHING_MULTIPLE"
    assert result["drivers"]["1"]["compatibleOptionIds"] == ["mh", "ms"]


def test_unordered_option_is_explicitly_not_comparable():
    result = _build(
        _availability(
            _option(
                "any",
                (Compound.MEDIUM, Compound.HARD),
                order=StrategyOrder.ANY_ORDER,
            )
        ),
        _state(),
    )
    assert result["drivers"]["1"]["relation"] == "NOT_COMPARABLE"


def test_observed_transition_can_diverge_or_complete_next_window():
    laps = (
        LapObservation(1, "2026-07-26T13:01:00Z", compound="MEDIUM"),
        LapObservation(19, "2026-07-26T13:30:00Z", compound="HARD"),
    )
    result = _build(
        _availability(
            _option(
                "mhs",
                (Compound.MEDIUM, Compound.HARD, Compound.SOFT),
                windows=(PitWindow(17, 23), PitWindow(40, 46)),
            )
        ),
        _state(compound="HARD", lap=25),
        laps,
    )
    driver = result["drivers"]["1"]
    assert driver["observedCompounds"] == ["MEDIUM", "HARD"]
    assert driver["relation"] == "MATCHING_ONE"
    assert driver["windows"] == [
        {
            "optionId": "mhs",
            "stopIndex": 0,
            "startLap": 17,
            "endLap": 23,
            "state": "COMPLETED",
        },
        {
            "optionId": "mhs",
            "stopIndex": 1,
            "startLap": 40,
            "endLap": 46,
            "state": "BEFORE",
        }
    ]


def test_terminal_and_final_states_never_publish_live_window_language():
    option = _option(
        "mh",
        (Compound.MEDIUM, Compound.HARD),
        windows=(PitWindow(17, 23),),
    )
    terminal = _build(_availability(option), _state(status="RETIRED"))
    assert terminal["drivers"]["1"]["relation"] == "TERMINAL"
    final = _build(_availability(option), _state(final=True), lifecycle="FINAL")
    assert final["baseline"]["status"] == "PRESENT"
    assert final["drivers"]["1"]["relation"] == "MATCHING_ONE"
    assert final["drivers"]["1"]["windows"] == []
    assert final["fieldFacts"] == []


def test_current_retired_indication_suppresses_windows_but_can_recover() -> None:
    option = _option(
        "mh",
        (Compound.MEDIUM, Compound.HARD),
        windows=(PitWindow(17, 23),),
    )
    base = _state(lap=20)
    indicated = RaceState(
        session=base.session,
        weather=base.weather,
        drivers={
            "1": DriverState(
                number="1",
                code="AAA",
                compound="MEDIUM",
                source_condition="RETIRED_INDICATED",
                source_retired=True,
            )
        },
    )
    out = _build(_availability(option), indicated)
    recovered = _build(_availability(option), base)

    assert out["drivers"]["1"]["relation"] == "TERMINAL"
    assert out["drivers"]["1"]["windows"] == []
    assert recovered["drivers"]["1"]["relation"] == "MATCHING_ONE"
    assert recovered["drivers"]["1"]["windows"]


def test_rain_and_neutralization_facts_are_predicate_bound():
    option = _option(
        "mh",
        (Compound.MEDIUM, Compound.HARD),
        windows=(PitWindow(17, 23),),
    )
    result = _build(
        _availability(option),
        _state(lap=20, rainfall=True, track="VSC"),
    )
    assert any("rainfall" in fact for fact in result["fieldFacts"])
    assert any("Safety Car or VSC" in fact for fact in result["fieldFacts"])


def test_missing_pirelli_baseline_keeps_driver_relation_unknown():
    result = _build(PirelliAvailability("ABSENT", error="missing"), _state())
    assert result["status"] == "ABSENT"
    assert result["drivers"]["1"]["relation"] == "UNKNOWN"
    assert result["baseline"]["reason"] == "missing"


def test_unranked_options_preserve_source_order_and_rank():
    result = _build(
        _availability(
            _option("ms", (Compound.MEDIUM, Compound.SOFT), rank=StrategyRank.UNRANKED),
            _option("mh", (Compound.MEDIUM, Compound.HARD), rank=StrategyRank.UNRANKED),
        ),
        _state(),
    )
    assert [(item["id"], item["rank"]) for item in result["baseline"]["options"]] == [
        ("ms", "UNRANKED"),
        ("mh", "UNRANKED"),
    ]


def test_native_tyre_bank_is_published_only_when_present():
    result = _build(_availability(bank=True), _state())
    bank = result["baseline"]["tyreBank"]
    assert bank["status"] == "PRESENT"
    assert bank["drivers"]["1"]["hard"] == {"new": 1, "used": 0}


def test_divergence_does_not_generate_a_replacement_plan():
    observations = (
        LapObservation(1, "2026-07-26T13:01:00Z", compound="MEDIUM"),
        LapObservation(19, "2026-07-26T13:30:00Z", compound="SOFT"),
    )
    result = _build(
        _availability(_option("mh", (Compound.MEDIUM, Compound.HARD))),
        _state(compound="SOFT", lap=25),
        observations,
    )
    driver = result["drivers"]["1"]
    assert driver["relation"] == "DIVERGED"
    assert driver["compatibleOptionIds"] == []
    assert driver["windows"] == []


def test_cursor_rebuild_rewinds_and_advances_published_relation_deterministically():
    option = _option(
        "mhs",
        (Compound.MEDIUM, Compound.HARD, Compound.SOFT),
        windows=(PitWindow(17, 23), PitWindow(40, 46)),
    )
    before = _build(_availability(option), _state(lap=16))
    after_observations = (
        LapObservation(1, "2026-07-26T13:01:00Z", compound="MEDIUM"),
        LapObservation(19, "2026-07-26T13:30:00Z", compound="HARD"),
    )
    after = _build(
        _availability(option), _state(compound="HARD", lap=25), after_observations
    )
    rewound = _build(_availability(option), _state(lap=16))

    assert before == rewound
    assert before["drivers"]["1"]["windows"][0]["state"] == "BEFORE"
    assert after["drivers"]["1"]["observedCompounds"] == ["MEDIUM", "HARD"]
    assert [window["state"] for window in after["drivers"]["1"]["windows"]] == [
        "COMPLETED",
        "BEFORE",
    ]


def test_actual_strategy_preserves_same_compound_stops():
    result = _build(
        _availability(_option("sh", (Compound.SOFT, Compound.HARD))),
        _state(compound="SOFT", lap=3, pit_count=1),
        pit_events=(_pit(1, 2, "SOFT", "SOFT", 1),),
        dry_tyre_requirement="UNSATISFIED",
    )

    driver = result["drivers"]["1"]
    assert driver["actualStrategy"] == {
        "compounds": ["SOFT", "SOFT"],
        "stopLaps": [2],
        "completedStops": 1,
        "observedStops": 1,
        "evidenceComplete": True,
    }
    assert driver["pirelliAssessment"] == "EXTRA_SAME_COMPOUND_STOP"
    assert driver["dryTyreRequirement"] == "UNSATISFIED"


def test_actual_strategy_preserves_repeated_compound_in_multi_stop_sequence():
    result = _build(
        _availability(
            _option(
                "mh",
                (Compound.MEDIUM, Compound.HARD),
                windows=(PitWindow(20, 28),),
            )
        ),
        _state(compound="HARD", lap=30, pit_count=2),
        pit_events=(
            _pit(1, 12, "MEDIUM", "MEDIUM", 1),
            _pit(2, 25, "MEDIUM", "HARD", 2),
        ),
    )

    driver = result["drivers"]["1"]
    assert driver["actualStrategy"]["compounds"] == ["MEDIUM", "MEDIUM", "HARD"]
    assert driver["actualStrategy"]["stopLaps"] == [12, 25]
    assert driver["pirelliAssessment"] == "EXTRA_SAME_COMPOUND_STOP"
    assert driver["pirelliReferences"][0]["stopComparisons"][0]["actualLap"] == 25


def test_no_stop_strategy_remains_applicable_without_fabricating_a_stop():
    result = _build(
        _availability(
            _option(
                "mh",
                (Compound.MEDIUM, Compound.HARD),
                windows=(PitWindow(27, 33),),
            )
        ),
        _state(compound="MEDIUM", lap=6),
    )

    driver = result["drivers"]["1"]
    assert driver["actualStrategy"]["compounds"] == ["MEDIUM"]
    assert driver["actualStrategy"]["stopLaps"] == []
    assert driver["pirelliAssessment"] == "STILL_APPLICABLE"
    assert driver["pirelliReferences"][0]["stopComparisons"][0]["status"] == (
        "NOT_OCCURRED"
    )


def test_no_stop_strategy_is_not_still_applicable_after_its_window_or_final():
    option = _option(
        "mh",
        (Compound.MEDIUM, Compound.HARD),
        windows=(PitWindow(27, 33),),
    )
    passed = _build(_availability(option), _state(compound="MEDIUM", lap=40))
    final = _build(
        _availability(option),
        _state(compound="MEDIUM", lap=72, final=True),
        lifecycle="FINAL",
    )

    assert passed["drivers"]["1"]["pirelliAssessment"] == "NO_MATCH"
    assert final["drivers"]["1"]["pirelliAssessment"] == "REFERENCE_ONLY"


def test_matching_compounds_distinguish_aligned_and_different_stop_timing():
    option = _option(
        "mh",
        (Compound.MEDIUM, Compound.HARD),
        windows=(PitWindow(27, 33),),
    )
    early = _build(
        _availability(option),
        _state(compound="HARD", lap=4, pit_count=1),
        pit_events=(_pit(1, 2, "MEDIUM", "HARD", 1),),
    )
    aligned = _build(
        _availability(option),
        _state(compound="HARD", lap=31, pit_count=1),
        pit_events=(_pit(1, 29, "MEDIUM", "HARD", 1),),
    )

    assert early["drivers"]["1"]["pirelliAssessment"] == (
        "SAME_COMPOUNDS_DIFFERENT_TIMING"
    )
    assert early["drivers"]["1"]["pirelliReferences"][0]["stopComparisons"][0] == {
        "stopIndex": 0,
        "actualLap": 2,
        "publishedStartLap": 27,
        "publishedEndLap": 33,
        "status": "OUTSIDE",
    }
    assert aligned["drivers"]["1"]["pirelliAssessment"] == "ALIGNED"


def test_partial_multi_stop_strategy_retains_completed_stop_timing_difference():
    option = _option(
        "mhs",
        (Compound.MEDIUM, Compound.HARD, Compound.SOFT),
        windows=(PitWindow(27, 33), PitWindow(45, 50)),
    )
    result = _build(
        _availability(option),
        _state(compound="HARD", lap=20, pit_count=1),
        pit_events=(_pit(1, 2, "MEDIUM", "HARD", 1),),
    )

    driver = result["drivers"]["1"]
    assert driver["actualStrategy"]["compounds"] == ["MEDIUM", "HARD"]
    assert driver["pirelliAssessment"] == "SAME_COMPOUNDS_DIFFERENT_TIMING"
    assert driver["pirelliReferences"][0]["stopComparisons"][0]["status"] == (
        "OUTSIDE"
    )


def test_incomplete_pit_evidence_stays_neutral():
    post_stop_observation = LapObservation(
        18,
        "2026-07-26T13:18:00Z",
        compound="HARD",
    )
    result = _build(
        _availability(_option("mh", (Compound.MEDIUM, Compound.HARD))),
        _state(compound="HARD", lap=20, pit_count=1),
        observations=(post_stop_observation,),
        pit_events=(_pit(1, 18, None, "HARD", 1),),
    )

    driver = result["drivers"]["1"]
    assert driver["actualStrategy"]["compounds"] == [None, "HARD"]
    assert driver["actualStrategy"]["evidenceComplete"] is False
    assert driver["pirelliAssessment"] == "UNKNOWN"


def test_stop_count_mismatch_keeps_actual_strategy_incomplete():
    result = _build(
        _availability(_option("mh", (Compound.MEDIUM, Compound.HARD))),
        _state(compound="HARD", lap=20, pit_count=0),
        pit_events=(_pit(1, 18, "MEDIUM", "HARD", 1),),
    )

    driver = result["drivers"]["1"]
    assert driver["actualStrategy"]["evidenceComplete"] is False
    assert driver["pirelliAssessment"] == "UNKNOWN"


def test_actual_strategy_reports_no_pirelli_match_truthfully():
    result = _build(
        _availability(_option("mh", (Compound.MEDIUM, Compound.HARD))),
        _state(compound="SOFT", lap=20, pit_count=1),
        pit_events=(_pit(1, 18, "MEDIUM", "SOFT", 1),),
    )

    assert result["drivers"]["1"]["pirelliAssessment"] == "NO_MATCH"


def test_non_comparable_option_keeps_mixed_no_match_assessment_neutral():
    result = _build(
        _availability(
            _option("mh", (Compound.MEDIUM, Compound.HARD)),
            _option(
                "any",
                (Compound.MEDIUM, Compound.HARD),
                order=StrategyOrder.ANY_ORDER,
            ),
        ),
        _state(compound="MEDIUM", lap=20, pit_count=1),
        pit_events=(_pit(1, 18, "HARD", "MEDIUM", 1),),
    )

    driver = result["drivers"]["1"]
    assert [item["status"] for item in driver["pirelliReferences"]] == [
        "NO_MATCH",
        "NOT_COMPARABLE",
    ]
    assert driver["pirelliAssessment"] == "NOT_COMPARABLE"
