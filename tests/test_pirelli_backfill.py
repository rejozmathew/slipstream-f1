import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from slipstream.pirelli.acquisition import AcquiredArtifact
from slipstream.pirelli.archive import PirelliArchive, save_normalized_release
from slipstream.pirelli.backfill import (
    format_pirelli_backfill_report,
    sync_pirelli_backfill,
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
    StrategyRank,
)
from slipstream.pirelli.discovery import (
    PIRELLI_F1_RSS_URL,
    MeetingDiscoveryTarget,
    entries_from_event_archive,
    pirelli_event_archive_url,
    pirelli_event_tag,
)
from slipstream.pirelli.extractors.base import HtmlDocument
from slipstream.pirelli.ingest import (
    PirelliIngestionReport,
    PirelliIngestionService,
    PirelliIngestionTarget,
)
from slipstream.pirelli.store import PirelliEvidenceStore
from slipstream.state import DriverState, RaceState


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
        self.calls: list[str] = []

    async def acquire(self, *, archive, meeting_key, url, now):
        self.calls.append(url)
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


class _Library:
    def __init__(self, descriptors) -> None:
        self.descriptors = {descriptor.key: descriptor for descriptor in descriptors}

    def get(self, _key):
        return SimpleNamespace(
            final_state=RaceState(
                drivers={"1": DriverState(number="1", code="AAA", name="Driver A")}
            )
        )


def _descriptor(year: int, meeting_key: str, name: str, race_start: datetime):
    return SimpleNamespace(
        key=f"race-{meeting_key}",
        session_kind="race",
        meeting_key=meeting_key,
        date_start=race_start.isoformat(),
        date_end=(race_start + timedelta(hours=2)).isoformat(),
        year=year,
        meeting_name=name,
        location=name.removesuffix(" Grand Prix"),
        circuit=name,
    )


def _feed(entries: list[tuple[str, str, datetime, str]]) -> bytes:
    items = "".join(
        f"<item><title>{title}</title><link>{url}</link>"
        f"<pubDate>{published.strftime('%a, %d %b %Y %H:%M:%S GMT')}</pubDate>"
        f"<category>{category}</category>"
        f"<description>Published race strategy evidence</description></item>"
        for title, url, published, category in entries
    )
    return f"<rss><channel>{items}</channel></rss>".encode()


def _page(text: str) -> bytes:
    return f"<html><main>{text}</main></html>".encode()


def test_backfill_fixture_covers_current_prior_and_multi_option_races(tmp_path):
    races = (
        _descriptor(
            2024,
            "10",
            "Example Multi Grand Prix",
            datetime(2024, 6, 9, 13, tzinfo=UTC),
        ),
        _descriptor(
            2025,
            "20",
            "Example Prior Grand Prix",
            datetime(2025, 7, 6, 13, tzinfo=UTC),
        ),
        _descriptor(
            2026,
            "30",
            "Example Current Grand Prix",
            datetime(2026, 8, 30, 13, tzinfo=UTC),
        ),
    )
    articles = {
        "10": (
            "The fastest one-stop race strategy is Medium-Hard, with the stop between "
            "laps 17 and 23. A two-stop race strategy is also possible: Soft-Hard-Medium, "
            "switching to Hard between laps 10 and 15 and Medium between laps 38 and 45."
        ),
        "20": (
            "A one-stop strategy is clearly fastest for tomorrow's Grand Prix. "
            "The quickest race strategy is Soft-Hard, with the stop between laps 18 and 24."
        ),
        "30": (
            "A one-stop strategy is clearly fastest for tomorrow's Grand Prix. "
            "The quickest race strategy is Medium-Hard, with the stop between laps 20 and 26."
        ),
    }
    entries: list[tuple[str, str, datetime, str]] = []
    payloads: dict[str, _Payload] = {}
    for descriptor in races:
        published = datetime.fromisoformat(descriptor.date_start) - timedelta(days=1)
        url = f"https://press.pirelli.com/race-{descriptor.meeting_key}"
        entries.append(
            (
                f"Race strategies for {descriptor.meeting_name}",
                url,
                published,
                pirelli_event_tag(descriptor.year, descriptor.meeting_name),
            )
        )
        payloads[url] = _Payload(
            _page(articles[descriptor.meeting_key]),
            SourceType.NEWSROOM_HTML,
            published,
            published,
        )
    payloads[PIRELLI_F1_RSS_URL] = _Payload(
        _feed(entries), SourceType.RSS, media_type="application/rss+xml"
    )
    archive = PirelliArchive(tmp_path)
    client = _FakeClient(payloads)
    service = PirelliIngestionService(archive, client)

    report = asyncio.run(
        sync_pirelli_backfill(
            tmp_path,
            years=(2024, 2025, 2026),
            force=True,
            now=datetime(2026, 8, 30, 18, tzinfo=UTC),
            library=_Library(races),
            service=service,
        )
    )

    assert report.meetings_attempted == 3
    assert report.count("PRESENT") == 3
    assert client.calls.count(PIRELLI_F1_RSS_URL) == 1
    calls_after_first_sync = tuple(client.calls)
    repeat = asyncio.run(
        sync_pirelli_backfill(
            tmp_path,
            years=(2024, 2025, 2026),
            now=datetime(2026, 8, 30, 19, tzinfo=UTC),
            library=_Library(races),
            service=service,
        )
    )
    assert repeat.meetings_attempted == 0
    assert repeat.count("PRESENT") == 3
    assert tuple(client.calls) == calls_after_first_sync
    store = PirelliEvidenceStore(tmp_path)
    for descriptor in races:
        availability = store.load(
            meeting_key=descriptor.meeting_key,
            target_session_key=descriptor.key,
            evidence_cutoff=descriptor.date_start,
            session_scope=SessionScope.RACE,
        )
        assert availability.status == "PRESENT"
    multi = store.load(
        meeting_key="10",
        target_session_key="race-10",
        evidence_cutoff=races[0].date_start,
        session_scope=SessionScope.RACE,
    )
    assert len(multi.snapshot.latest_strategy_release.strategies) >= 2


class _MixedService:
    def __init__(self, archive: PirelliArchive) -> None:
        self.archive = archive

    async def refresh(self, target, *, now):
        if target.meeting.meeting_key == "absent":
            return PirelliIngestionReport((), (), ())
        artifact = self.archive.archive_artifact(
            meeting_key=target.meeting.meeting_key,
            source_url="https://press.pirelli.com/retrieved-only",
            source_type=SourceType.NEWSROOM_HTML,
            body=b"retrieved-only strategy",
            retrieved_at=now,
            published_at=None,
            modified_at=None,
            media_type="text/html",
            collector_version="test",
            extension="html",
        )
        scope = FactApplicability(
            meeting_key=target.meeting.meeting_key,
            session_scope=SessionScope.RACE,
            target_session_key=target.target_session_key,
        )
        evidence = SourceEvidence(
            artifact.artifact_id,
            artifact.source_url,
            EvidenceKind.TEXT,
            ExtractionMethod.DETERMINISTIC_PROSE,
            text="Medium-Hard",
        )
        release = PirelliRelease(
            release_id=artifact.artifact_id,
            source_url=artifact.source_url,
            published_at=None,
            modified_at=None,
            retrieved_at=now,
            content_hash=artifact.content_hash,
            source_type=artifact.source_type,
            extraction_method=ExtractionMethod.DETERMINISTIC_PROSE,
            normalizer_version="test",
            artifact_ids=(artifact.artifact_id,),
            applicability=scope,
            strategies=(
                StrategyOption(
                    id="mh",
                    rank=StrategyRank.FASTEST_PUBLISHED,
                    stop_count=1,
                    compounds=(Compound.MEDIUM, Compound.HARD),
                    pit_windows=(PitWindow(17, 23),),
                    source_evidence=(evidence,),
                    applicability=scope,
                ),
            ),
        )
        save_normalized_release(
            self.archive,
            meeting_key=target.meeting.meeting_key,
            release=release,
        )
        return PirelliIngestionReport((release.release_id,), (), ())


def test_backfill_distinguishes_absent_from_provenance_rejected(tmp_path):
    races = (
        _descriptor(
            2025,
            "absent",
            "Absent Grand Prix",
            datetime(2025, 7, 6, 13, tzinfo=UTC),
        ),
        _descriptor(
            2025,
            "late",
            "Late Grand Prix",
            datetime(2025, 8, 3, 13, tzinfo=UTC),
        ),
    )
    report = asyncio.run(
        sync_pirelli_backfill(
            tmp_path,
            years=(2025,),
            force=True,
            now=datetime(2026, 8, 30, tzinfo=UTC),
            library=_Library(races),
            service=_MixedService(PirelliArchive(tmp_path)),
        )
    )

    assert report.count("ABSENT") == 1
    assert report.count("PROVENANCE_REJECTED") == 1
    assert report.count("PRESENT") == 0
    assert "Provenance-rejected: 1" in format_pirelli_backfill_report(report)


def test_backfill_dry_run_and_meeting_filter_do_not_fetch(tmp_path):
    races = (
        _descriptor(
            2026,
            "30",
            "Selected Grand Prix",
            datetime(2026, 8, 30, 13, tzinfo=UTC),
        ),
        _descriptor(
            2026,
            "31",
            "Other Grand Prix",
            datetime(2026, 9, 6, 13, tzinfo=UTC),
        ),
    )
    report = asyncio.run(
        sync_pirelli_backfill(
            tmp_path,
            years=(2026,),
            meeting_keys=("30",),
            dry_run=True,
            library=_Library(races),
        )
    )

    assert report.selected == 1
    assert report.meetings_attempted == 0
    assert report.count("PLANNED") == 1


def test_malformed_rss_falls_back_per_event_and_one_failure_is_isolated(tmp_path):
    races = (
        _descriptor(
            2026,
            "30",
            "Dutch Grand Prix",
            datetime(2026, 8, 23, 13, tzinfo=UTC),
        ),
        _descriptor(
            2026,
            "31",
            "Missing Grand Prix",
            datetime(2026, 9, 6, 13, tzinfo=UTC),
        ),
    )
    dutch_target = MeetingDiscoveryTarget(
        meeting_key="30",
        canonical_name="Dutch Grand Prix",
        season=2026,
        weekend_start=datetime(2026, 8, 21, tzinfo=UTC),
        weekend_end=datetime(2026, 8, 23, 18, tzinfo=UTC),
        exact_tag="2026 Dutch Grand Prix",
    )
    article_url = "https://press.pirelli.com/dutch-race-strategies"
    published = datetime(2026, 8, 22, 18, tzinfo=UTC)
    payloads = {
        PIRELLI_F1_RSS_URL: _Payload(
            b"<rss><channel><![CDATA[unclosed",
            SourceType.RSS,
            media_type="application/rss+xml",
        ),
        pirelli_event_archive_url(dutch_target): _Payload(
            f'<html><a href="{article_url}">2026 Race strategies for Dutch Grand Prix</a></html>'.encode(),
            SourceType.NEWSROOM_HTML,
        ),
        article_url: _Payload(
            _page(
                "A one-stop strategy is clearly fastest for tomorrow's Grand Prix. "
                "The quickest race strategy is Medium-Hard, with the stop between laps 20 and 26."
            ),
            SourceType.NEWSROOM_HTML,
            published,
            published,
        ),
    }
    client = _FakeClient(payloads)
    service = PirelliIngestionService(PirelliArchive(tmp_path), client)

    report = asyncio.run(
        sync_pirelli_backfill(
            tmp_path,
            years=(2026,),
            force=True,
            now=datetime(2026, 9, 7, tzinfo=UTC),
            library=_Library(races),
            service=service,
        )
    )

    assert report.selected == 2
    assert report.meetings_attempted == 2
    assert report.count("PRESENT") == 1
    assert report.count("FAILURE") == 1
    assert client.calls.count(PIRELLI_F1_RSS_URL) == 1
    assert pirelli_event_archive_url(dutch_target) in client.calls


def test_event_archive_discards_unscoped_navigation_links() -> None:
    target = MeetingDiscoveryTarget(
        meeting_key="30",
        canonical_name="Dutch Grand Prix",
        season=2026,
        weekend_start=datetime(2026, 8, 21, tzinfo=UTC),
        weekend_end=datetime(2026, 8, 23, tzinfo=UTC),
        exact_tag="2026 Dutch Grand Prix",
    )
    document = HtmlDocument(
        title="Archive",
        article_text="",
        published_at_text=None,
        modified_at_text=None,
        links=(
            ("https://press.pirelli.com/corporate", "Corporate", "text/html"),
            (
                "https://press.pirelli.com/dutch-strategies",
                "2026 Race strategies for Dutch Grand Prix",
                "text/html",
            ),
        ),
        tables=(),
    )

    entries = entries_from_event_archive(document, target)
    assert [entry.url for entry in entries] == [
        "https://press.pirelli.com/dutch-strategies"
    ]


def test_event_archive_rejects_same_event_name_from_another_season() -> None:
    target = MeetingDiscoveryTarget(
        meeting_key="30",
        canonical_name="Dutch Grand Prix",
        season=2026,
        weekend_start=datetime(2026, 8, 21, tzinfo=UTC),
        weekend_end=datetime(2026, 8, 23, tzinfo=UTC),
    )
    document = HtmlDocument(
        title="Archive",
        article_text="",
        published_at_text=None,
        modified_at_text=None,
        links=(
            (
                "https://press.pirelli.com/2025-dutch-strategy",
                "2025 Race strategies for Dutch Grand Prix",
                "text/html",
            ),
            (
                "https://press.pirelli.com/2026-dutch-strategy",
                "2026 Race strategies for Dutch Grand Prix",
                "text/html",
            ),
        ),
        tables=(),
    )

    entries = entries_from_event_archive(document, target)
    assert [entry.url for entry in entries] == [
        "https://press.pirelli.com/2026-dutch-strategy"
    ]


def test_needs_review_rss_match_still_uses_exact_event_archive(tmp_path) -> None:
    target = MeetingDiscoveryTarget(
        meeting_key="30",
        canonical_name="Dutch Grand Prix",
        season=2026,
        weekend_start=datetime(2026, 8, 21, tzinfo=UTC),
        weekend_end=datetime(2026, 8, 23, tzinfo=UTC),
        exact_tag="2026 Dutch Grand Prix",
    )
    rss_url = "https://press.pirelli.com/untrusted-preview"
    archive_release = "https://press.pirelli.com/2026-dutch-strategy"
    published = datetime(2026, 8, 22, 18, tzinfo=UTC)
    payloads = {
        PIRELLI_F1_RSS_URL: _Payload(
            _feed(
                [
                    (
                        "Dutch Grand Prix preview",
                        rss_url,
                        published,
                        "formula 1",
                    )
                ]
            ),
            SourceType.RSS,
            media_type="application/rss+xml",
        ),
        pirelli_event_archive_url(target): _Payload(
            f'<html><a href="{archive_release}">2026 Race strategies for Dutch Grand Prix</a></html>'.encode(),
            SourceType.NEWSROOM_HTML,
        ),
        archive_release: _Payload(
            _page(
                "The quickest race strategy is Medium-Hard, with the stop between laps 20 and 26."
            ),
            SourceType.NEWSROOM_HTML,
            published,
            published,
        ),
    }
    client = _FakeClient(payloads)
    service = PirelliIngestionService(PirelliArchive(tmp_path), client)

    report = asyncio.run(
        service.refresh(
            PirelliIngestionTarget(target, "race-30", SessionScope.RACE),
            now=published,
        )
    )

    assert report.normalized_release_ids
    assert pirelli_event_archive_url(target) in client.calls
    assert rss_url not in client.calls
