import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from slipstream.pirelli.acquisition import AcquiredArtifact
from slipstream.pirelli.archive import PirelliArchive, save_normalized_release
from slipstream.pirelli.contracts import (
    Compound,
    CompoundCount,
    DriverTyreBank,
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
    TyreBankSnapshot,
)
from slipstream.pirelli.coordinator import PirelliRuntimeCoordinator
from slipstream.pirelli.discovery import (
    PIRELLI_F1_RSS_URL,
    MeetingDiscoveryTarget,
    pirelli_event_tag,
)
from slipstream.pirelli.ingest import (
    PirelliIngestionService,
    PirelliIngestionTarget,
)
from slipstream.pirelli.store import PirelliEvidenceStore
from slipstream.published_strategy import build_published_strategy
from slipstream.state import DriverState, RaceState, SessionState


@dataclass(frozen=True)
class _Payload:
    body: bytes
    source_type: SourceType
    published_at: datetime | None = None
    modified_at: datetime | None = None
    media_type: str = "text/html"


class _FakeClient:
    def __init__(self, payloads: dict[str, _Payload]) -> None:
        self.payloads = payloads

    async def acquire(self, *, archive, meeting_key, url, now):
        payload = self.payloads[url]
        artifact = archive.archive_artifact(
            meeting_key=meeting_key,
            source_url=url,
            source_type=payload.source_type,
            body=payload.body,
            retrieved_at=now,
            published_at=payload.published_at,
            modified_at=payload.modified_at,
            media_type=payload.media_type,
            collector_version="test",
            extension="xml" if payload.source_type == SourceType.RSS else "html",
        )
        return AcquiredArtifact(artifact, payload.body)


def _feed(*entries: tuple[str, str, str, str]) -> bytes:
    items = "".join(
        f"<item><title>{title}</title><link>{url}</link><pubDate>{published}</pubDate>"
        f"<category>{category}</category><description>Published strategy evidence</description></item>"
        for title, url, published, category in entries
    )
    return f"<rss><channel>{items}</channel></rss>".encode()


def _page(text: str) -> bytes:
    return f"<html><main>{text}</main></html>".encode()


def _meeting(name: str = "Hungarian Grand Prix") -> MeetingDiscoveryTarget:
    return MeetingDiscoveryTarget(
        meeting_key="30",
        canonical_name=name,
        season=2026,
        weekend_start=datetime(2026, 7, 24, tzinfo=UTC),
        weekend_end=datetime(2026, 7, 26, 15, tzinfo=UTC),
        aliases=("Hungary", "Hungaroring"),
        exact_tag=pirelli_event_tag(2026, name),
    )


def test_runtime_discovery_reacquires_feed_for_later_strategy_release(tmp_path) -> None:
    preview = (
        "Preview for Hungarian Grand Prix",
        "https://press.pirelli.com/preview",
        "Fri, 24 Jul 2026 09:00:00 GMT",
        "2026 Hungarian Grand Prix",
    )
    strategy = (
        "Race strategy for Hungarian Grand Prix",
        "https://press.pirelli.com/strategy",
        "Sat, 25 Jul 2026 09:00:00 GMT",
        "2026 Hungarian Grand Prix",
    )

    class SequencedClient:
        def __init__(self) -> None:
            self.calls = 0

        async def acquire(self, *, archive, meeting_key, url, now):
            assert url == PIRELLI_F1_RSS_URL
            self.calls += 1
            body = _feed(preview) if self.calls == 1 else _feed(preview, strategy)
            artifact = archive.archive_artifact(
                meeting_key=meeting_key,
                source_url=url,
                source_type=SourceType.RSS,
                body=body,
                retrieved_at=now,
                published_at=None,
                modified_at=None,
                media_type="application/rss+xml",
                collector_version="test",
                extension="xml",
            )
            return AcquiredArtifact(artifact, body)

    client = SequencedClient()
    service = PirelliIngestionService(PirelliArchive(tmp_path), client)
    first = asyncio.run(service.discovery_entries(now=datetime(2026, 7, 24, tzinfo=UTC)))
    second = asyncio.run(service.discovery_entries(now=datetime(2026, 7, 25, tzinfo=UTC)))

    assert client.calls == 2
    assert len(first) == 1
    assert len(second) == 2


def _descriptor(kind: str = "race"):
    return SimpleNamespace(
        key=f"{kind}-30",
        session_kind=kind,
        meeting_key="30",
        date_start=datetime(2026, 7, 26, 13, tzinfo=UTC)
        if kind == "race"
        else datetime(2026, 7, 25, 10, tzinfo=UTC),
        date_end=datetime(2026, 7, 26, 15, tzinfo=UTC)
        if kind == "race"
        else datetime(2026, 7, 25, 11, tzinfo=UTC),
        year=2026,
        meeting_name="Hungarian Grand Prix",
        location="Hungary",
        circuit="Hungaroring",
    )


def _resource():
    return SimpleNamespace(final_state=RaceState())


def _run_race_article_pipeline(
    tmp_path,
    *,
    meeting_key: str,
    meeting_name: str,
    title: str,
    article: str,
    published_at: datetime,
    race_start: datetime,
    current_lap: int,
):
    session_key = f"race-{meeting_key}"
    release_url = f"https://press.pirelli.com/{meeting_key}-strategy"
    category = pirelli_event_tag(2026, meeting_name)
    payloads = {
        PIRELLI_F1_RSS_URL: _Payload(
            _feed(
                (
                    title,
                    release_url,
                    published_at.strftime("%a, %d %b %Y %H:%M:%S GMT"),
                    category,
                )
            ),
            SourceType.RSS,
            media_type="application/rss+xml",
        ),
        release_url: _Payload(
            _page(article),
            SourceType.NEWSROOM_HTML,
            published_at=published_at,
            modified_at=published_at,
        ),
    }
    descriptor = SimpleNamespace(
        key=session_key,
        session_kind="race",
        meeting_key=meeting_key,
        date_start=race_start,
        date_end=race_start + timedelta(hours=2),
        year=2026,
        meeting_name=meeting_name,
        location=meeting_name.removesuffix(" Grand Prix"),
        circuit=meeting_name,
    )
    archive = PirelliArchive(tmp_path)
    coordinator = PirelliRuntimeCoordinator(
        PirelliIngestionService(archive, _FakeClient(payloads))
    )
    asyncio.run(
        coordinator.refresh_relevant(
            {session_key: descriptor},
            default_key=session_key,
            resource_loader=lambda _key: _resource(),
            now=race_start - timedelta(hours=2),
        )
    )
    availability = PirelliEvidenceStore(tmp_path).load(
        meeting_key=meeting_key,
        target_session_key=session_key,
        evidence_cutoff=race_start,
        session_scope=SessionScope.RACE,
    )
    published = build_published_strategy(
        availability=availability,
        evidence_cutoff=race_start.isoformat(),
        state=RaceState(
            session=SessionState(
                key=session_key,
                lap=current_lap,
                total_laps=70,
            ),
            drivers={"1": DriverState(number="1", compound="MEDIUM")},
        ),
        evidence_by_driver={"1": ()},
        lifecycle="LIVE",
    )
    return availability, published


def _published_option(published, compounds, windows):
    return any(
        option["compounds"] == compounds and option["pitWindows"] == windows
        for option in published["baseline"]["options"]
    )


def test_china_qualifying_day_article_admits_race_strategy_despite_sprint_language(
    tmp_path,
):
    availability, published = _run_race_article_pipeline(
        tmp_path,
        meeting_key="china-2026",
        meeting_name="Chinese Grand Prix",
        title="Mercedes strike twice as Antonelli breaks record",
        published_at=datetime(2026, 3, 14, 10, tzinfo=UTC),
        race_start=datetime(2026, 3, 15, 7, tzinfo=UTC),
        current_lap=20,
        article=(
            "George Russell won the first Sprint of the season. Following the Sprint race, "
            "the teams prepared for Formula 1 qualifying, where Antonelli secured pole. "
            "A one-stop strategy is clearly the fastest for tomorrow. Whether to start on "
            "the Mediums or the Softs will depend on grid position. In both cases, the longer "
            "stint will be on the Hard tyres, to be fitted between laps 17 and 23, or between "
            "15 and 21. Formula 2 also held a Sprint before its Feature Race qualifying."
        ),
    )

    assert availability.status == "PRESENT"
    assert published["baseline"]["status"] == "PRESENT"
    assert _published_option(
        published,
        ["MEDIUM", "HARD"],
        [{"startLap": 17, "endLap": 23}],
    )
    assert _published_option(
        published,
        ["SOFT", "HARD"],
        [{"startLap": 15, "endLap": 21}],
    )


def test_miami_qualifying_article_admits_explicit_grand_prix_guidance(tmp_path):
    availability, published = _run_race_article_pipeline(
        tmp_path,
        meeting_key="1284",
        meeting_name="Miami Grand Prix",
        title="Sprint victory for Norris and pole position for Antonelli",
        published_at=datetime(2026, 5, 2, 23, 7, tzinfo=UTC),
        race_start=datetime(2026, 5, 3, 17, tzinfo=UTC),
        current_lap=24,
        article=(
            "<p>Kimi Antonelli secured pole position in today's qualifying session. "
            "Lando Norris claimed victory in this morning's Sprint. During the Sprint "
            "all Pirelli compounds were used.</p><p>The one-stop strategy is confirmed as "
            "the fastest option for tomorrow, as expected ahead of the race weekend. "
            "The compounds selected for Miami have proven consistent and with low "
            "degradation. By contrast, a two-stop strategy would be penalised by around "
            "10 seconds compared to a single stop.</p><p>On paper, the Medium-Hard solution, "
            "with a pit window between laps 22 and 28, is the quickest. The Soft could "
            "be a valid option, exploiting its higher grip, when used in combination "
            "with the Hard. Starting on the C5, the pit stop should be made between laps "
            "16 and 22. Less effective in terms of lap time is the Medium-Soft pairing, "
            "which would have a pit window between laps 32 and 38.</p><p>The weather forecast "
            "could even lead to a wet race.</p>"
        ),
    )

    assert availability.status == "PRESENT"
    assert published["baseline"]["status"] == "PRESENT"
    assert _published_option(
        published,
        ["MEDIUM", "HARD"],
        [{"startLap": 22, "endLap": 28}],
    )
    assert _published_option(
        published,
        ["MEDIUM", "SOFT"],
        [{"startLap": 32, "endLap": 38}],
    )
    assert any(
        option["compounds"] == ["SOFT", "HARD"]
        and option["pitWindows"] == [None]
        for option in published["baseline"]["options"]
    )
    categories = {
        fact["category"] for fact in published["baseline"]["contextFacts"]
    }
    assert {"STRATEGY_OUTLOOK", "DEGRADATION", "WEATHER"} <= categories
    assert any(
        "around 10 seconds" in fact["statement"]
        for fact in published["baseline"]["contextFacts"]
    )


def test_hungary_qualifying_day_article_admits_grand_prix_strategy_before_support_sprints(
    tmp_path,
):
    availability, published = _run_race_article_pipeline(
        tmp_path,
        meeting_key="hungary-2026",
        meeting_name="Hungarian Grand Prix",
        title="Norris on pole in Hungary, tyre sets will shape tomorrow's strategies",
        published_at=datetime(2026, 7, 25, 17, tzinfo=UTC),
        race_start=datetime(2026, 7, 26, 13, tzinfo=UTC),
        current_lap=28,
        article=(
            "Norris secured pole after Formula 1 qualifying and the final practice session. "
            "There is no difference in overall race time between a one-stop and a two-stop "
            "strategy for the Hungarian Grand Prix. The Medium tyre is still likely to be the "
            "preferred compound for the start. Those opting for a one-stop strategy could then "
            "complete the race on the Hard compound, with the pit stop window falling between "
            "laps 26 and 32. A two-stop strategy has windows between laps 16 and 22 and between "
            "laps 40 and 46. Formula 2 and Formula 3 Sprint races were followed by qualifying."
        ),
    )

    assert availability.status == "PRESENT"
    assert published["baseline"]["status"] == "PRESENT"
    assert _published_option(
        published,
        ["MEDIUM", "HARD"],
        [{"startLap": 26, "endLap": 32}],
    )
    assert any(
        window["state"] == "ACTIVE"
        for window in published["drivers"]["1"]["windows"]
    )


def test_genuine_sprint_strategy_article_never_enters_race_published_baseline(tmp_path):
    availability, published = _run_race_article_pipeline(
        tmp_path,
        meeting_key="sprint-only-2026",
        meeting_name="Chinese Grand Prix",
        title="Sprint strategy for the Chinese Grand Prix weekend",
        published_at=datetime(2026, 3, 13, 10, tzinfo=UTC),
        race_start=datetime(2026, 3, 15, 7, tzinfo=UTC),
        current_lap=10,
        article=(
            "The fastest Sprint strategy is Soft-Medium, with the change between laps 8 and 10. "
            "Sprint Qualifying set the grid and Formula 2 qualifying followed later in the day."
        ),
    )

    assert availability.status == "ABSENT"
    assert published["baseline"]["status"] == "ABSENT"
    assert published["baseline"]["options"] == []


def test_runtime_exact_tag_discovers_ingests_stores_and_publishes_race_baseline(
    tmp_path,
):
    release_url = "https://press.pirelli.com/race-strategy"
    payloads = {
        PIRELLI_F1_RSS_URL: _Payload(
            _feed(
                (
                    "Norris on pole in Hungary, tyre sets will shape tomorrow's strategies",
                    release_url,
                    "Sun, 26 Jul 2026 09:00:00 GMT",
                    "2026 Hungarian Grand Prix",
                )
            ),
            SourceType.RSS,
            media_type="application/rss+xml",
        ),
        release_url: _Payload(
            _page(
                "A one-stop strategy is clearly the fastest for tomorrow's Grand Prix. "
                "The quickest race strategy is Medium-Hard, with the stop between laps 17 and 23."
            ),
            SourceType.NEWSROOM_HTML,
            published_at=datetime(2026, 7, 26, 9, tzinfo=UTC),
            modified_at=datetime(2026, 7, 26, 9, tzinfo=UTC),
        ),
    }
    archive = PirelliArchive(tmp_path)
    service = PirelliIngestionService(archive, _FakeClient(payloads))
    coordinator = PirelliRuntimeCoordinator(service)
    descriptor = _descriptor()

    asyncio.run(
        coordinator.refresh_relevant(
            {descriptor.key: descriptor},
            default_key=descriptor.key,
            resource_loader=lambda _key: _resource(),
            now=datetime(2026, 7, 26, 10, tzinfo=UTC),
        )
    )

    availability = PirelliEvidenceStore(tmp_path).load(
        meeting_key="30",
        target_session_key="race-30",
        evidence_cutoff=datetime(2026, 7, 26, 13, tzinfo=UTC),
        session_scope=SessionScope.RACE,
    )
    state = RaceState(
        session=SessionState(key="race-30", lap=20, total_laps=70),
        drivers={"1": DriverState(number="1", compound="MEDIUM")},
    )
    published = build_published_strategy(
        availability=availability,
        evidence_cutoff="2026-07-26T13:00:00+00:00",
        state=state,
        evidence_by_driver={"1": ()},
        lifecycle="LIVE",
    )

    assert coordinator.states["30"].last_success_at is not None
    assert availability.status == "PRESENT"
    assert published["baseline"]["status"] == "PRESENT"
    assert published["drivers"]["1"]["relation"] == "MATCHING_ONE"
    assert published["drivers"]["1"]["windows"][0]["state"] == "ACTIVE"


def test_discovery_ingestion_keeps_race_sprint_and_weekend_facts_isolated(tmp_path):
    race_url = "https://press.pirelli.com/race"
    sprint_url = "https://press.pirelli.com/sprint"
    practice_url = "https://press.pirelli.com/practice"
    nomination_url = "https://press.pirelli.com/nomination"
    category = "2026 Hungarian Grand Prix"
    payloads = {
        PIRELLI_F1_RSS_URL: _Payload(
            _feed(
                ("Race strategies for 2026 Hungarian Grand Prix", race_url, "Fri, 24 Jul 2026 09:00:00 GMT", category),
                ("Sprint strategy for 2026 Hungarian Grand Prix", sprint_url, "Fri, 24 Jul 2026 09:10:00 GMT", category),
                ("Friday practice at 2026 Hungarian Grand Prix", practice_url, "Fri, 24 Jul 2026 09:20:00 GMT", category),
                ("Compound choices for 2026 Hungarian Grand Prix", nomination_url, "Fri, 24 Jul 2026 09:30:00 GMT", category),
            ),
            SourceType.RSS,
            media_type="application/rss+xml",
        ),
        race_url: _Payload(_page("The fastest race strategy is Medium-Hard."), SourceType.NEWSROOM_HTML, datetime(2026, 7, 24, 9, tzinfo=UTC), datetime(2026, 7, 24, 9, tzinfo=UTC)),
        sprint_url: _Payload(_page("The fastest sprint strategy is Soft-Medium."), SourceType.NEWSROOM_HTML, datetime(2026, 7, 24, 9, 10, tzinfo=UTC), datetime(2026, 7, 24, 9, 10, tzinfo=UTC)),
        practice_url: _Payload(_page("The fastest strategy in practice was Soft-Hard."), SourceType.NEWSROOM_HTML, datetime(2026, 7, 24, 9, 20, tzinfo=UTC), datetime(2026, 7, 24, 9, 20, tzinfo=UTC)),
        nomination_url: _Payload(_page("Hungary will use C3, C4 and C5."), SourceType.NEWSROOM_HTML, datetime(2026, 7, 24, 9, 30, tzinfo=UTC), datetime(2026, 7, 24, 9, 30, tzinfo=UTC)),
    }
    archive = PirelliArchive(tmp_path)
    service = PirelliIngestionService(archive, _FakeClient(payloads))
    asyncio.run(service.refresh(PirelliIngestionTarget(_meeting(), "race-30", SessionScope.RACE), now=datetime(2026, 7, 24, 10, tzinfo=UTC)))
    asyncio.run(service.refresh(PirelliIngestionTarget(_meeting(), "sprint-30", SessionScope.SPRINT), now=datetime(2026, 7, 24, 10, tzinfo=UTC)))
    store = PirelliEvidenceStore(tmp_path)
    race = store.load(meeting_key="30", target_session_key="race-30", evidence_cutoff=datetime(2026, 7, 26, 13, tzinfo=UTC), session_scope=SessionScope.RACE)
    sprint = store.load(meeting_key="30", target_session_key="sprint-30", evidence_cutoff=datetime(2026, 7, 25, 10, tzinfo=UTC), session_scope=SessionScope.SPRINT)

    assert [item.sequence for item in race.snapshot.latest_strategy_release.strategies] == ["M-H"]
    assert [item.sequence for item in sprint.snapshot.latest_strategy_release.strategies] == ["S-M"]
    assert race.snapshot.compound_selections[-1].hard == "C3"
    assert sprint.snapshot.compound_selections[-1].soft == "C5"
    assert all(item.sequence != "S-H" for release in race.snapshot.strategy_releases for item in release.strategies)


def test_post_cutoff_pdf_fact_does_not_borrow_parent_html_version_proof(tmp_path):
    archive = PirelliArchive(tmp_path)
    parent = archive.archive_artifact(
        meeting_key="30",
        source_url="https://press.pirelli.com/race",
        source_type=SourceType.NEWSROOM_HTML,
        body=b"race strategy",
        retrieved_at=datetime(2026, 8, 1, tzinfo=UTC),
        published_at=datetime(2026, 7, 24, tzinfo=UTC),
        modified_at=datetime(2026, 7, 25, tzinfo=UTC),
        media_type="text/html",
        collector_version="test",
        extension="html",
    )
    child = archive.archive_artifact(
        meeting_key="30",
        source_url="https://content.presspage.com/tyre-bank.pdf",
        source_type=SourceType.PDF,
        body=b"native pdf text fetched too late",
        retrieved_at=datetime(2026, 8, 1, tzinfo=UTC),
        published_at=None,
        modified_at=None,
        media_type="application/pdf",
        collector_version="test",
        extension="pdf",
    )
    scope = FactApplicability(
        meeting_key="30",
        session_scope=SessionScope.RACE,
        target_session_key="race-30",
    )
    parent_evidence = SourceEvidence(
        parent.artifact_id,
        parent.source_url,
        EvidenceKind.TEXT,
        ExtractionMethod.DETERMINISTIC_PROSE,
        text="Medium-Hard",
    )
    child_evidence = SourceEvidence(
        child.artifact_id,
        child.source_url,
        EvidenceKind.TABLE,
        ExtractionMethod.PDF_TEXT,
        text="Driver tyre bank",
    )
    release = PirelliRelease(
        release_id=parent.artifact_id,
        source_url=parent.source_url,
        published_at=parent.published_at,
        modified_at=parent.modified_at,
        retrieved_at=parent.retrieved_at,
        content_hash=parent.content_hash,
        source_type=parent.source_type,
        extraction_method=ExtractionMethod.HYBRID,
        normalizer_version="test",
        artifact_ids=(parent.artifact_id, child.artifact_id),
        applicability=scope,
        strategies=(
            StrategyOption(
                id="mh",
                rank=StrategyRank.FASTEST_PUBLISHED,
                stop_count=1,
                compounds=(Compound.MEDIUM, Compound.HARD),
                pit_windows=(PitWindow(17, 23),),
                source_evidence=(parent_evidence,),
                applicability=scope,
            ),
        ),
        tyre_bank_snapshots=(
            TyreBankSnapshot(
                as_of=datetime(2026, 7, 25, tzinfo=UTC),
                target_session="race-30",
                drivers=(
                    DriverTyreBank(
                        "Driver",
                        CompoundCount(1, 0),
                        CompoundCount(1, 0),
                        CompoundCount(1, 0),
                        1.0,
                        (child_evidence,),
                        "1",
                        "AAA",
                    ),
                ),
                source_evidence=(child_evidence,),
                applicability=scope,
            ),
        ),
    )
    save_normalized_release(archive, meeting_key="30", release=release)

    result = PirelliEvidenceStore(tmp_path).load(
        meeting_key="30",
        target_session_key="race-30",
        evidence_cutoff=datetime(2026, 7, 26, 13, tzinfo=UTC),
        session_scope=SessionScope.RACE,
    )

    assert result.status == "PRESENT"
    assert result.snapshot.latest_strategy_release is not None
    assert result.snapshot.latest_tyre_bank is None


def test_admitted_pirelli_fixture_exercises_published_strategy_state_matrix(tmp_path):
    archive = PirelliArchive(tmp_path)
    published_at = datetime(2026, 7, 26, 9, tzinfo=UTC)
    artifact = archive.archive_artifact(
        meeting_key="30",
        source_url="https://press.pirelli.com/race-state-matrix",
        source_type=SourceType.NEWSROOM_HTML,
        body=b"two ordered race options and one any-order option",
        retrieved_at=published_at,
        published_at=published_at,
        modified_at=published_at,
        media_type="text/html",
        collector_version="test",
        extension="html",
    )
    scope = FactApplicability(
        meeting_key="30",
        session_scope=SessionScope.RACE,
        target_session_key="race-30",
    )
    evidence = SourceEvidence(
        artifact.artifact_id,
        artifact.source_url,
        EvidenceKind.TEXT,
        ExtractionMethod.DETERMINISTIC_PROSE,
        text="published race options",
    )
    options = (
        StrategyOption(
            id="mh",
            rank=StrategyRank.EQUIVALENT_FASTEST,
            stop_count=1,
            compounds=(Compound.MEDIUM, Compound.HARD),
            pit_windows=(PitWindow(17, 23),),
            source_evidence=(evidence,),
            applicability=scope,
        ),
        StrategyOption(
            id="ms",
            rank=StrategyRank.EQUIVALENT_FASTEST,
            stop_count=1,
            compounds=(Compound.MEDIUM, Compound.SOFT),
            pit_windows=(PitWindow(18, 24),),
            source_evidence=(evidence,),
            applicability=scope,
        ),
        StrategyOption(
            id="any",
            rank=StrategyRank.ALTERNATIVE,
            stop_count=1,
            compounds=(Compound.SOFT, Compound.HARD),
            pit_windows=(None,),
            order=StrategyOrder.ANY_ORDER,
            source_evidence=(evidence,),
            applicability=scope,
        ),
    )
    save_normalized_release(
        archive,
        meeting_key="30",
        release=PirelliRelease(
            release_id=artifact.artifact_id,
            source_url=artifact.source_url,
            published_at=published_at,
            modified_at=published_at,
            retrieved_at=published_at,
            content_hash=artifact.content_hash,
            source_type=artifact.source_type,
            extraction_method=ExtractionMethod.DETERMINISTIC_PROSE,
            normalizer_version="test",
            artifact_ids=(artifact.artifact_id,),
            applicability=scope,
            strategies=options,
        ),
    )
    availability = PirelliEvidenceStore(tmp_path).load(
        meeting_key="30",
        target_session_key="race-30",
        evidence_cutoff=datetime(2026, 7, 26, 13, tzinfo=UTC),
        session_scope=SessionScope.RACE,
    )

    def build(compound, lap, observations=(), lifecycle="LIVE"):
        return build_published_strategy(
            availability=availability,
            evidence_cutoff="2026-07-26T13:00:00+00:00",
            state=RaceState(
                session=SessionState(key="race-30", lap=lap, total_laps=70),
                drivers={"1": DriverState(number="1", compound=compound)},
            ),
            evidence_by_driver={"1": observations},
            lifecycle=lifecycle,
        )

    multiple = build("MEDIUM", 20)
    completed = build(
        "HARD",
        25,
        (
            SimpleNamespace(compound="MEDIUM"),
            SimpleNamespace(compound="HARD"),
        ),
    )
    diverged = build(
        "WET",
        25,
        (
            SimpleNamespace(compound="MEDIUM"),
            SimpleNamespace(compound="WET"),
        ),
    )
    final = build("MEDIUM", 70, lifecycle="FINAL")

    assert availability.status == "PRESENT"
    assert multiple["baseline"]["tyreBank"]["status"] == "ABSENT"
    assert multiple["baseline"]["options"][2]["order"] == "ANY_ORDER"
    assert multiple["drivers"]["1"]["relation"] == "MATCHING_MULTIPLE"
    assert {window["state"] for window in multiple["drivers"]["1"]["windows"]} == {"ACTIVE"}
    assert completed["drivers"]["1"]["relation"] == "MATCHING_ONE"
    assert completed["drivers"]["1"]["windows"][0]["state"] == "COMPLETED"
    assert diverged["drivers"]["1"]["relation"] == "DIVERGED"
    assert final["lifecycle"] == "FINAL"
    assert final["drivers"]["1"]["windows"] == []


class _FailingService:
    def __init__(self) -> None:
        self.attempts = 0

    async def refresh(self, _target, *, now):
        self.attempts += 1
        raise OSError("newsroom unavailable")


def test_failed_refresh_is_observable_and_retries_without_twelve_hour_suppression():
    service = _FailingService()
    coordinator = PirelliRuntimeCoordinator(service)  # type: ignore[arg-type]
    descriptor = _descriptor()
    start = datetime(2026, 7, 26, 10, tzinfo=UTC)

    for now in (start, start + timedelta(minutes=29), start + timedelta(minutes=30)):
        asyncio.run(
            coordinator.refresh_relevant(
                {descriptor.key: descriptor},
                default_key=descriptor.key,
                resource_loader=lambda _key: _resource(),
                now=now,
            )
        )

    state = coordinator.states["30"]
    assert service.attempts == 2
    assert state.last_success_at is None
    assert state.last_reason == "retry_after_failure"
    assert state.last_error == "OSError: newsroom unavailable"


def test_current_coordinator_does_not_refresh_an_old_default_replay():
    service = _FailingService()
    coordinator = PirelliRuntimeCoordinator(service)  # type: ignore[arg-type]
    descriptor = _descriptor()

    asyncio.run(
        coordinator.refresh_relevant(
            {descriptor.key: descriptor},
            default_key=descriptor.key,
            resource_loader=lambda _key: _resource(),
            now=datetime(2026, 9, 2, tzinfo=UTC),
        )
    )

    assert service.attempts == 0
    assert coordinator.states == {}
