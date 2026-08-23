from datetime import UTC, datetime

from slipstream.evidence import LapObservation
from slipstream.pirelli.contracts import (
    Compound,
    CompoundCount,
    CompoundSelection,
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
    *options: StrategyOption, selection: bool = False, bank: bool = False
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
        context_facts=(),
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
            "1": DriverState(number="1", code="AAA", compound=compound, status=status)
        },
    )


def _build(availability, state, observations=(), lifecycle="LIVE"):
    return build_published_strategy(
        availability=availability,
        evidence_cutoff="2026-07-26T13:00:00Z",
        state=state,
        evidence_by_driver={"1": tuple(observations)},
        lifecycle=lifecycle,
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
