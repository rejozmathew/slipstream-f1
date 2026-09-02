from dataclasses import replace
from datetime import UTC, datetime

from slipstream.pirelli.archive import (
    PirelliArchive,
    list_normalized_releases,
    save_normalized_release,
)
from slipstream.pirelli.contracts import (
    Compound,
    ContextFact,
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
from slipstream.pirelli.extractors.html import parse_html
from slipstream.pirelli.extractors.prose import extract_strategy_prose
from slipstream.pirelli.extractors.structured import (
    extract_compound_nominations,
    extract_context_facts,
)
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
    context_facts = tuple(
        replace(
            fact,
            source_evidence=tuple(
                replace(evidence, artifact_id=artifact.artifact_id)
                for evidence in fact.source_evidence
            ),
        )
        for fact in release.context_facts
    )
    saved = replace(
        release,
        release_id=artifact.artifact_id,
        artifact_ids=(artifact.artifact_id,),
        strategies=strategies,
        context_facts=context_facts,
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


def test_context_only_race_baseline_is_present_but_remains_target_scoped(tmp_path):
    release = _release(
        meeting="miami", retrieved=datetime(2026, 7, 25, tzinfo=UTC)
    )
    evidence = release.strategies[0].source_evidence[0]
    context_only = replace(
        release,
        strategies=(),
        context_facts=(
            ContextFact(
                "STRATEGY_OUTLOOK",
                "The one-stop strategy is the fastest option for tomorrow.",
                (evidence,),
                FactApplicability(
                    meeting_key="miami",
                    session_scope=SessionScope.RACE,
                    target_session_key="race-miami",
                ),
            ),
        ),
    )
    _save_release(
        PirelliArchive(tmp_path), meeting="miami", release=context_only
    )
    store = PirelliEvidenceStore(tmp_path)

    present = store.load(
        meeting_key="miami",
        target_session_key="race-miami",
        evidence_cutoff="2026-07-26T17:00:00Z",
        session_scope=SessionScope.RACE,
    )
    wrong_session = store.load(
        meeting_key="miami",
        target_session_key="other-race",
        evidence_cutoff="2026-07-26T17:00:00Z",
        session_scope=SessionScope.RACE,
    )
    wrong_meeting = store.load(
        meeting_key="montreal",
        target_session_key="race-miami",
        evidence_cutoff="2026-07-26T17:00:00Z",
        session_scope=SessionScope.RACE,
    )
    session_only = replace(
        context_only,
        release_id="session-only",
        applicability=FactApplicability(
            meeting_key="session-only", session_scope=SessionScope.WEEKEND
        ),
        context_facts=tuple(
            replace(
                context_only.context_facts[0],
                applicability=FactApplicability(
                    meeting_key="session-only",
                    session_scope=scope,
                    target_session_key=f"{scope.value.casefold()}-session",
                ),
            )
            for scope in (SessionScope.QUALIFYING, SessionScope.PRACTICE)
        ),
    )
    _save_release(
        PirelliArchive(tmp_path), meeting="session-only", release=session_only
    )
    race_from_other_sessions = store.load(
        meeting_key="session-only",
        target_session_key="race-session",
        evidence_cutoff="2026-07-26T17:00:00Z",
        session_scope=SessionScope.RACE,
    )

    assert present.status == "PRESENT"
    assert present.snapshot is not None
    assert present.snapshot.latest_strategy_release is None
    assert [fact.category for fact in present.snapshot.context_facts] == [
        "STRATEGY_OUTLOOK"
    ]
    assert wrong_session.status == "ABSENT"
    assert wrong_meeting.status == "ABSENT"
    assert race_from_other_sessions.status == "ABSENT"


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
    assert option.published_delta_seconds == 1.0


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


def test_one_nomination_triplet_can_apply_to_two_named_meetings():
    result = extract_compound_nominations(
        "The C2, C3 and C4 selection applies to the Dutch Grand Prix and Spanish Grand Prix.",
        source_url="https://press.pirelli.com/shared-selection",
        artifact_id="shared-selection",
        meeting_aliases={
            "Dutch Grand Prix": "nl",
            "Spanish Grand Prix": "es",
        },
    )

    assert result.accepted
    assert [fact.applicability.meeting_key for fact in result.facts] == ["nl", "es"]
    assert [(fact.hard, fact.medium, fact.soft) for fact in result.facts] == [
        ("C2", "C3", "C4"),
        ("C2", "C3", "C4"),
    ]


def test_exact_event_nomination_inherits_proven_event_scope():
    scope = FactApplicability(
        meeting_key="canada-2026",
        source_meeting_name="Canadian Grand Prix",
        session_scope=SessionScope.WEEKEND,
        target_session_key="race-canada-2026",
    )
    result = extract_compound_nominations(
        "The three compounds selected for the weekend are C3, C4 and C5.",
        source_url="https://press.pirelli.com/the-first-sprint-in-montreal/",
        artifact_id="canada-preview",
        meeting_aliases={"Canadian Grand Prix": "canada-2026", "Canada": "canada-2026"},
        default_applicability=scope,
        exact_event_scope=True,
    )

    assert result.accepted
    assert len(result.facts) == 1
    assert result.facts[0].applicability == scope
    assert (result.facts[0].hard, result.facts[0].medium, result.facts[0].soft) == (
        "C3",
        "C4",
        "C5",
    )


def test_multi_event_nomination_accepts_target_clause_without_foreign_contamination():
    result = extract_compound_nominations(
        "The C2, C3 and C4 selection applies to the Dutch and Spanish Grands Prix. "
        "For Monza, the chosen compounds are C1, C2 and C3.",
        source_url="https://press.pirelli.com/tyre-compounds-selected-for-zandvoort-monza-and-madrid/",
        artifact_id="multi-event-selection",
        meeting_aliases={"Dutch": "dutch-2026", "Zandvoort": "dutch-2026"},
        default_applicability=FactApplicability(
            meeting_key="dutch-2026", session_scope=SessionScope.WEEKEND
        ),
    )

    assert result.accepted
    assert len(result.facts) == 1
    assert result.facts[0].applicability.meeting_key == "dutch-2026"
    assert (result.facts[0].hard, result.facts[0].medium, result.facts[0].soft) == (
        "C2",
        "C3",
        "C4",
    )


def test_context_is_meeting_local_and_window_is_not_wind():
    scope = FactApplicability(
        meeting_key="nl", session_scope=SessionScope.WEEKEND
    )
    sections = (
        "DUTCH GRAND PRIX",
        "All three compounds are in play and degradation is expected to be low.",
        "SPANISH GRAND PRIX",
        "Strong wind and high tyre stress are forecast for the race.",
        "The pit window should open around lap 20.",
    )
    facts = extract_context_facts(
        "\n\n".join(sections),
        source_url="https://press.pirelli.com/multi-event-preview",
        artifact_id="multi-event-preview",
        applicability=scope,
        meeting_aliases={"Dutch Grand Prix": "nl"},
        sections=sections,
    )

    assert {fact.category for fact in facts} == {
        "COMPOUND_OUTLOOK",
        "DEGRADATION",
    }
    assert all("Spanish" not in fact.statement for fact in facts)
    assert not extract_context_facts(
        "The pit window should open around lap 20.",
        source_url="https://press.pirelli.com/window",
        artifact_id="window",
        applicability=scope,
    )
    assert not extract_context_facts(
        "All three compounds are not viable race options.",
        source_url="https://press.pirelli.com/negated-outlook",
        artifact_id="negated-outlook",
        applicability=scope,
    )


def test_race_context_excludes_qualifying_weather_and_keeps_strategy_outlook():
    facts = extract_context_facts(
        "A few drops during qualifying led teams to bring forward their runs. "
        "During qualifying, rain made the track slippery. "
        "For the Grand Prix, a one-stop strategy could again be preferred. "
        "Two-stop strategies can be competitive for cars running in clean air.",
        source_url="https://press.pirelli.com/race-context",
        artifact_id="race-context",
        applicability=FactApplicability(
            meeting_key="race", session_scope=SessionScope.RACE
        ),
    )

    assert {fact.category for fact in facts} == {"STRATEGY_OUTLOOK"}
    assert len(facts) == 2
    assert all("qualifying" not in fact.statement.casefold() for fact in facts)


def test_race_context_handles_presspage_hyphens_and_rejects_historical_context():
    facts = extract_context_facts(
        "As seen in Miami, teams tend to favour cautious choices in the race, where "
        "a one‑stop strategy could again be preferred this year. "
        "IN 2025 The two‑stop strategy proved to be the quickest. "
        "The 2011 race was interrupted by torrential rain. "
        "The Soft will offer optimal grip over a single lap.",
        source_url="https://press.pirelli.com/the-first-sprint-in-montreal/",
        artifact_id="canada-preview",
        applicability=FactApplicability(
            meeting_key="canada-2026", session_scope=SessionScope.RACE
        ),
    )

    assert [(fact.category, fact.statement) for fact in facts] == [
        (
            "STRATEGY_OUTLOOK",
            (
                "As seen in Miami, teams tend to favour cautious choices in the race, "
                "where a one‑stop strategy could again be preferred this year."
            ),
        )
    ]


def test_strategy_delta_range_conditions_and_caveats_are_source_local():
    exact = extract_strategy_prose(
        "The alternative Medium-Hard race strategy is around one second slower in clean air.",
        source_url="https://press.pirelli.com/exact",
        artifact_id="exact",
    )
    ranged = extract_strategy_prose(
        "The alternative Soft-Hard strategy is between 1.5 and 2 seconds slower "
        "in traffic, but traffic might make the stop less effective.",
        source_url="https://press.pirelli.com/range",
        artifact_id="range",
    )

    exact_option = exact.facts[0]
    range_option = ranged.facts[0]
    assert exact_option.published_delta_seconds == 1.0
    assert exact_option.published_delta_seconds_range is None
    assert exact_option.conditions == ("In clean air",)
    assert range_option.published_delta_seconds is None
    assert range_option.published_delta_seconds_range == (1.5, 2.0)
    assert range_option.conditions == ("In traffic",)
    assert range_option.caveats == ("But traffic might make the stop less effective",)


def test_strategy_annotations_reject_nearer_pit_stop_subject():
    result = extract_strategy_prose(
        "The Medium-Hard race strategy is quickest, but a pit stop under green is "
        "around 12 seconds slower than under a VSC.",
        source_url="https://press.pirelli.com/vsc-pit-loss",
        artifact_id="vsc-pit-loss",
    )

    option = result.facts[0]
    assert option.published_delta_seconds is None
    assert option.published_delta_seconds_range is None
    assert option.conditions == ()
    assert option.caveats == ()


def test_json_ld_article_body_owns_context_sections_over_dom_shell():
    document = parse_html(
        """
        <main><p>Strong wind and high tyre stress are forecast.</p></main>
        <script type="application/ld+json">
          {"@type":"NewsArticle","headline":"Race preview",
           "articleBody":"All three compounds are in play and viable."}
        </script>
        """,
        "https://press.pirelli.com/race-preview",
    )
    facts = extract_context_facts(
        document.article_text,
        source_url="https://press.pirelli.com/race-preview",
        artifact_id="json-ld",
        applicability=FactApplicability(
            meeting_key="100", session_scope=SessionScope.WEEKEND
        ),
        sections=document.article_sections,
    )

    assert document.article_sections == (
        "All three compounds are in play and viable.",
    )
    assert {fact.category for fact in facts} == {"COMPOUND_OUTLOOK"}


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
