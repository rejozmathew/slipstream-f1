from dataclasses import replace
from datetime import UTC, datetime

from slipstream.pirelli.archive import PirelliArchive, save_normalized_release
from slipstream.pirelli.contracts import (
    Compound,
    EvidenceKind,
    ExtractionMethod,
    FactApplicability,
    PirelliRelease,
    PitWindow,
    SessionScope,
    SourceEvidence,
    SourceType,
    StrategyOption,
    StrategyOrder,
    StrategyRank,
)
from slipstream.pirelli.extractors.prose import extract_strategy_prose
from slipstream.pirelli.extractors.structured import extract_compound_nominations
from slipstream.pirelli.store import PirelliEvidenceStore


def _release(*, meeting: str, retrieved: datetime, modified: datetime | None = None):
    source = "https://press.pirelli.com/test"
    evidence = SourceEvidence(
        artifact_id="artifact",
        source_url=source,
        kind=EvidenceKind.TEXT,
        extraction_method=ExtractionMethod.DETERMINISTIC_PROSE,
        text="Medium-Hard between laps 17 and 23",
        confidence=1.0,
    )
    option = StrategyOption(
        id="mh",
        rank=StrategyRank.FASTEST_PUBLISHED,
        stop_count=1,
        compounds=(Compound.MEDIUM, Compound.HARD),
        pit_windows=(PitWindow(17, 23),),
        order=StrategyOrder.ORDERED,
        source_evidence=(evidence,),
        applicability=FactApplicability(
            meeting_key=meeting,
            session_scope=SessionScope.RACE,
            target_session_key="race",
        ),
    )
    return PirelliRelease(
        release_id=f"release-{meeting}-{retrieved.timestamp()}",
        source_url=source,
        published_at=datetime(2026, 7, 24, tzinfo=UTC),
        modified_at=modified,
        retrieved_at=retrieved,
        content_hash="abc",
        source_type=SourceType.NEWSROOM_HTML,
        extraction_method=ExtractionMethod.DETERMINISTIC_PROSE,
        normalizer_version="test",
        artifact_ids=("artifact",),
        applicability=FactApplicability(
            meeting_key=meeting, session_scope=SessionScope.WEEKEND
        ),
        strategies=(option,),
    )


def test_store_is_meeting_scoped_and_cursor_safe(tmp_path):
    archive = PirelliArchive(tmp_path)
    save_normalized_release(
        archive,
        meeting_key="hungary",
        release=_release(
            meeting="hungary", retrieved=datetime(2026, 7, 25, tzinfo=UTC)
        ),
    )
    save_normalized_release(
        archive,
        meeting_key="austria",
        release=_release(
            meeting="austria", retrieved=datetime(2026, 7, 25, tzinfo=UTC)
        ),
    )
    store = PirelliEvidenceStore(tmp_path)
    result = store.load(
        meeting_key="hungary",
        target_session_key="race",
        evidence_cutoff="2026-07-26T12:00:00Z",
    )
    assert result.status == "PRESENT"
    assert result.snapshot is not None
    assert [item.id for item in result.snapshot.latest_strategy_release.strategies] == [
        "mh"
    ]


def test_post_cutoff_content_without_exact_version_proof_is_rejected(tmp_path):
    archive = PirelliArchive(tmp_path)
    save_normalized_release(
        archive,
        meeting_key="hungary",
        release=_release(meeting="hungary", retrieved=datetime(2026, 8, 1, tzinfo=UTC)),
    )
    result = PirelliEvidenceStore(tmp_path).load(
        meeting_key="hungary",
        target_session_key="race",
        evidence_cutoff="2026-07-26T12:00:00Z",
    )
    assert result.status == "ABSENT"
    assert result.error == "no_admissible_pirelli_release"


def test_source_version_timestamp_can_prove_late_archive_existed_at_cutoff(tmp_path):
    archive = PirelliArchive(tmp_path)
    save_normalized_release(
        archive,
        meeting_key="hungary",
        release=_release(
            meeting="hungary",
            retrieved=datetime(2026, 8, 1, tzinfo=UTC),
            modified=datetime(2026, 7, 25, tzinfo=UTC),
        ),
    )
    result = PirelliEvidenceStore(tmp_path).load(
        meeting_key="hungary",
        target_session_key="race",
        evidence_cutoff="2026-07-26T12:00:00Z",
    )
    assert result.status == "PRESENT"


def test_three_leg_strategy_is_not_truncated_into_false_two_leg_fact():
    text = (
        "A two-stopper is also possible: soft-hard-medium, albeit not as quick as stopping once. "
        "The fastest tactic in that case would be to start on soft, switch to hard "
        "between laps 10 and 15, and then go onto medium between laps 38 and 45."
    )
    result = extract_strategy_prose(
        text, source_url="https://press.pirelli.com/australia", artifact_id="aus"
    )
    options = [fact for fact in result.facts if isinstance(fact, StrategyOption)]
    assert [option.sequence for option in options] == ["S-H-M"]
    assert [
        (window.start_lap, window.end_lap)
        for window in options[0].pit_windows
        if window is not None
    ] == [(10, 15), (38, 45)]


def test_multi_event_nomination_keeps_each_meeting_binding():
    result = extract_compound_nominations(
        "Belgium will use C1, C2 and C3. Hungary will use C3, C4 and C5.",
        source_url="https://press.pirelli.com/selection",
        artifact_id="selection",
        meeting_aliases={"Belgium": "belgium", "Hungary": "hungary"},
    )
    assert [fact.applicability.meeting_key for fact in result.facts] == [
        "belgium",
        "hungary",
    ]
    assert result.facts[1].code_map() == {
        "C3": Compound.HARD,
        "C4": Compound.MEDIUM,
        "C5": Compound.SOFT,
    }


def test_sprint_and_race_strategy_releases_remain_isolated(tmp_path):
    archived_at = datetime(2026, 7, 25, tzinfo=UTC)
    race = _release(meeting="hungary", retrieved=archived_at)
    sprint_option = replace(
        race.strategies[0],
        id="sprint-mh",
        applicability=FactApplicability(
            meeting_key="hungary",
            session_scope=SessionScope.SPRINT,
            target_session_key="sprint",
        ),
    )
    sprint = replace(
        race,
        release_id="release-hungary-sprint",
        applicability=FactApplicability(
            meeting_key="hungary", session_scope=SessionScope.SPRINT
        ),
        strategies=(sprint_option,),
    )
    archive = PirelliArchive(tmp_path)
    save_normalized_release(archive, meeting_key="hungary", release=race)
    save_normalized_release(archive, meeting_key="hungary", release=sprint)
    store = PirelliEvidenceStore(tmp_path)

    race_result = store.load(
        meeting_key="hungary",
        target_session_key="race",
        evidence_cutoff="2026-07-26T12:00:00Z",
        session_scope=SessionScope.RACE,
    )
    sprint_result = store.load(
        meeting_key="hungary",
        target_session_key="sprint",
        evidence_cutoff="2026-07-26T12:00:00Z",
        session_scope=SessionScope.SPRINT,
    )

    assert [
        item.id for item in race_result.snapshot.latest_strategy_release.strategies
    ] == ["mh"]
    assert [
        item.id for item in sprint_result.snapshot.latest_strategy_release.strategies
    ] == ["sprint-mh"]
