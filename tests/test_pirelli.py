from dataclasses import replace
from datetime import UTC, datetime

from slipstream.pirelli.archive import (
    PirelliArchive,
    list_normalized_releases,
    save_normalized_release,
)
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


def _save_release(archive: PirelliArchive, *, meeting: str, release: PirelliRelease):
    artifact = archive.archive_artifact(
        meeting_key=meeting,
        source_url=release.source_url,
        source_type=release.source_type,
        body=release.release_id.encode(),
        retrieved_at=release.retrieved_at,
        published_at=release.published_at,
        modified_at=release.modified_at,
        media_type="text/html",
        collector_version="test",
        extension="html",
    )
    strategies = tuple(
        replace(
            option,
            source_evidence=tuple(
                replace(evidence, artifact_id=artifact.artifact_id)
                for evidence in option.source_evidence
            ),
        )
        for option in release.strategies
    )
    saved = replace(
        release,
        release_id=artifact.artifact_id,
        artifact_ids=(artifact.artifact_id,),
        strategies=strategies,
    )
    save_normalized_release(archive, meeting_key=meeting, release=saved)
    return saved


def test_store_is_meeting_scoped_and_cursor_safe(tmp_path):
    archive = PirelliArchive(tmp_path)
    _save_release(
        archive,
        meeting="hungary",
        release=_release(
            meeting="hungary", retrieved=datetime(2026, 7, 25, tzinfo=UTC)
        ),
    )
    _save_release(
        archive,
        meeting="austria",
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
    wrong_target = store.load(
        meeting_key="hungary",
        target_session_key="other-race",
        evidence_cutoff="2026-07-26T12:00:00Z",
    )
    assert wrong_target.status == "ABSENT"


def test_post_cutoff_official_pre_race_content_is_display_only(tmp_path):
    archive = PirelliArchive(tmp_path)
    _save_release(
        archive,
        meeting="hungary",
        release=_release(meeting="hungary", retrieved=datetime(2026, 8, 1, tzinfo=UTC)),
    )
    result = PirelliEvidenceStore(tmp_path).load(
        meeting_key="hungary",
        target_session_key="race",
        evidence_cutoff="2026-07-26T12:00:00Z",
    )
    assert result.status == "PRESENT"
    assert result.model_admissible is False
    assert result.evidence_tier == "DISPLAY_ONLY_OFFICIAL_HISTORICAL"
    assert result.provenance_label == "PUBLISHED PRE-RACE · ARCHIVED LATER"
    assert not PirelliEvidenceStore(tmp_path).releases_as_of(
        "hungary", evidence_cutoff="2026-07-26T12:00:00Z"
    )


def test_source_version_timestamp_can_prove_late_archive_existed_at_cutoff(tmp_path):
    archive = PirelliArchive(tmp_path)
    _save_release(
        archive,
        meeting="hungary",
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
    assert result.model_admissible is True
    assert result.evidence_tier == "STRICT_MODEL"


def test_newer_normalizer_supersedes_same_immutable_source_version(tmp_path):
    archive = PirelliArchive(tmp_path)
    saved = _save_release(
        archive,
        meeting="hungary",
        release=replace(
            _release(
                meeting="hungary", retrieved=datetime(2026, 7, 25, tzinfo=UTC)
            ),
            normalizer_version="slipstream-pirelli-v5-adapted.1",
        ),
    )
    newer = replace(
        saved,
        normalizer_version="slipstream-pirelli-v5-adapted.2",
        strategies=(
            replace(saved.strategies[0], pit_windows=(PitWindow(27, 33),)),
        ),
    )
    save_normalized_release(archive, meeting_key="hungary", release=newer)

    releases = list_normalized_releases(archive, "hungary")

    assert len(releases) == 1
    assert releases[0].normalizer_version == "slipstream-pirelli-v5-adapted.2"
    assert releases[0].strategies[0].pit_windows == (PitWindow(27, 33),)


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


def test_modern_pirelli_strategy_phrasings_preserve_explicit_options_and_windows():
    cases = (
        (
            (
                "A one-stop strategy is clearly the fastest for tomorrow. Whether to start on "
                "the Mediums or the Softs will depend on grid position. In both cases, the longer "
                "stint will be on the Hard tyres, to be fitted between laps 17 and 23, or between "
                "15 and 21."
            ),
            {("M-H", ((17, 23),)), ("S-H", ((15, 21),))},
        ),
        (
            (
                "There is no difference in overall race time between a one-stop and a two-stop "
                "strategy. The Medium tyre is still likely to be the preferred compound for the "
                "start. Those opting for a one-stop strategy could then complete the race on the "
                "Hard compound, with the pit stop window falling between laps 26 and 32."
            ),
            {("M-H", ((26, 32),))},
        ),
        (
            (
                "One option is to start on the Medium and switch to the Hard between laps 20 and "
                "26. An alternative is to start on the Hard and then take advantage of the Soft’s "
                "extra performance by stopping between laps 39 and 45."
            ),
            {("M-H", ((20, 26),)), ("H-S", ((39, 45),))},
        ),
        (
            (
                "Two-stop strategies are the competitive options. Starting on the Soft, its "
                "replacement could come between laps 14 and 20, switching to Medium before "
                "finishing on Hard."
            ),
            {("S-M-H", ((14, 20), None))},
        ),
        (
            (
                "The quickest strategy is therefore a one-stop, starting on the Medium "
                "and running until laps 27-33 before switching to the Hard for the "
                "remainder of the race."
            ),
            {("M-H", ((27, 33),))},
        ),
        (
            (
                "An alternative, around one second slower, involves starting on the Soft, "
                "using it until the window between laps 26 and 32, and then finishing the "
                "race on the Hard."
            ),
            {("S-H", ((26, 32),))},
        ),
    )

    for text, expected in cases:
        result = extract_strategy_prose(
            text,
            source_url="https://press.pirelli.com/modern",
            artifact_id="modern",
        )
        actual = {
            (
                option.sequence,
                tuple(
                    (window.start_lap, window.end_lap) if window is not None else None
                    for window in option.pit_windows
                ),
            )
            for option in result.facts
            if isinstance(option, StrategyOption)
        }
        assert expected <= actual


def test_exact_dutch_soft_hard_option_is_source_ranked_alternative():
    result = extract_strategy_prose(
        "An alternative, around one second slower, involves starting on the Soft, "
        "using it until the window between laps 26 and 32, and then finishing the "
        "race on the Hard.",
        source_url="https://press.pirelli.com/dutch-2026",
        artifact_id="dutch-2026",
    )
    option = next(
        fact
        for fact in result.facts
        if isinstance(fact, StrategyOption) and fact.sequence == "S-H"
    )
    assert option.rank == StrategyRank.ALTERNATIVE
    assert option.pit_windows == (PitWindow(26, 32),)


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
    _save_release(archive, meeting="hungary", release=race)
    _save_release(archive, meeting="hungary", release=sprint)
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
