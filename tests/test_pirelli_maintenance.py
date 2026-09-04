import asyncio
from datetime import UTC, datetime

from slipstream.pirelli.archive import (
    PirelliArchive,
    list_normalized_derivations,
    list_normalized_releases,
    save_normalized_release,
)
from slipstream.pirelli.config import NORMALIZER_VERSION
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
from slipstream.pirelli.discovery import MeetingDiscoveryTarget
from slipstream.pirelli.ingest import PirelliIngestionService, PirelliIngestionTarget
from slipstream.pirelli.maintenance import refresh_pirelli_seed
from slipstream.pirelli.metadata import PIRELLI_METADATA_FORMAT
from slipstream.pirelli.seed import import_pirelli_seed, validate_pirelli_seed
from slipstream.pirelli.store import PirelliEvidenceStore


class _OfflineClient:
    async def acquire(self, **_kwargs):
        raise AssertionError("offline re-normalization attempted network acquisition")


def _archived_dutch_source(data_root):
    archive = PirelliArchive(data_root)
    published = datetime(2026, 8, 29, 18, tzinfo=UTC)
    article = b"""
    <html><head><meta property="og:title" content="Norris to start from the front at Zandvoort"></head>
    <main>
      <p>A few drops during qualifying led teams to bring forward their runs.</p>
      <p>Pirelli will supply C2 as Hard, C3 as Medium and C4 as Soft.</p>
      <p>The quickest strategy is therefore a one-stop, starting on the Medium and
      running until laps 27-33 before switching to the Hard for the remainder of the race.</p>
      <p>An alternative, around one second slower, involves starting on the Soft,
      using it until the window between laps 26 and 32, and then finishing the race on the Hard.</p>
      <p>Two-stop strategies can therefore be competitive for cars running in clean air.</p>
    </main></html>
    """
    artifact = archive.archive_artifact(
        meeting_key="1292",
        source_url=(
            "https://press.pirelli.com/norris-to-start-from-the-front-at-"
            "zandvoort-all-three-compounds-in-play-for-the-race/"
        ),
        source_type=SourceType.NEWSROOM_HTML,
        body=article,
        retrieved_at=published,
        published_at=published,
        modified_at=published,
        media_type="text/html",
        collector_version="fixture",
        extension="html",
    )
    scope = FactApplicability(
        meeting_key="1292",
        source_meeting_name="Dutch Grand Prix",
        session_scope=SessionScope.RACE,
        target_session_key="race-1292",
    )
    evidence = SourceEvidence(
        artifact.artifact_id,
        artifact.source_url,
        EvidenceKind.TEXT,
        ExtractionMethod.DETERMINISTIC_PROSE,
        text="outdated fixture derivation",
    )
    save_normalized_release(
        archive,
        meeting_key="1292",
        release=PirelliRelease(
            release_id=artifact.artifact_id,
            source_url=artifact.source_url,
            published_at=published,
            modified_at=published,
            retrieved_at=published,
            content_hash=artifact.content_hash,
            source_type=SourceType.NEWSROOM_HTML,
            extraction_method=ExtractionMethod.DETERMINISTIC_PROSE,
            normalizer_version="slipstream-pirelli-v5-adapted.4",
            artifact_ids=(artifact.artifact_id,),
            applicability=scope,
            strategies=(
                StrategyOption(
                    id="old-medium-hard",
                    rank=StrategyRank.FASTEST_PUBLISHED,
                    stop_count=1,
                    compounds=(Compound.MEDIUM, Compound.HARD),
                    pit_windows=(PitWindow(20, 26),),
                    source_evidence=(evidence,),
                    applicability=scope,
                ),
            ),
        ),
    )


def _metadata():
    return {
        "format": PIRELLI_METADATA_FORMAT,
        "updatedAt": "2026-09-02T00:00:00+00:00",
        "years": list(range(2017, 2027)),
        "meetings": {
            "1292": {
                "meetingKey": "1292",
                "meetingName": "Dutch Grand Prix",
                "location": "Zandvoort",
                "country": "Netherlands",
                "circuit": "Zandvoort",
                "year": 2026,
            }
        },
        "sessions": [
            {
                "sessionKey": "race-1292",
                "meetingKey": "1292",
                "sessionName": "Race",
                "sessionType": "Race",
                "dateStart": "2026-08-30T13:00:00+00:00",
                "dateEnd": "2026-08-30T15:00:00+00:00",
                "year": 2026,
            }
        ],
    }


def test_refresh_seed_upgrades_adapted4_archives_and_preserves_old_derivation(tmp_path):
    _archived_dutch_source(tmp_path)
    metadata_calls = []

    def metadata_sync(_path, years, *, now):
        metadata_calls.append((tuple(years), now))
        return _metadata()

    seed_path = tmp_path / "pirelli-seed-v1.json.gz"
    report = asyncio.run(
        refresh_pirelli_seed(
            tmp_path,
            from_year=2017,
            through_year=2026,
            output=seed_path,
            now=datetime(2026, 9, 2, tzinfo=UTC),
            metadata_sync=metadata_sync,
            service=PirelliIngestionService(
                PirelliArchive(tmp_path), _OfflineClient()
            ),
        )
    )

    derivations = list_normalized_derivations(PirelliArchive(tmp_path), "1292")
    current = list_normalized_releases(PirelliArchive(tmp_path), "1292")
    payload = validate_pirelli_seed(seed_path)

    assert metadata_calls[0][0] == tuple(range(2017, 2027))
    assert report.renormalized.releases_written == 1
    assert report.backfill.count("PRESENT") == 1
    assert report.seed.meetings == 1
    assert report.seed.releases == 1
    assert {release.normalizer_version for release in derivations} == {
        "slipstream-pirelli-v5-adapted.4",
        NORMALIZER_VERSION,
    }
    assert current[0].normalizer_version == NORMALIZER_VERSION
    assert current[0].compound_selections[0].code_map() == {
        "C2": Compound.HARD,
        "C3": Compound.MEDIUM,
        "C4": Compound.SOFT,
    }
    assert [(item.sequence, item.pit_windows) for item in current[0].strategies] == [
        ("M-H", (PitWindow(27, 33),)),
        ("S-H", (PitWindow(26, 32),)),
    ]
    assert current[0].strategies[1].published_delta_seconds == 1.0
    assert {fact.category for fact in current[0].context_facts} == {
        "STRATEGY_OUTLOOK"
    }
    assert payload["coverage"]["fromSeason"] == 2017
    assert payload["coverage"]["throughSeason"] == 2026
    assert payload["normalizerVersion"] == NORMALIZER_VERSION

    destination = tmp_path / "clean-install"
    imported = import_pirelli_seed(seed_path, destination)
    availability = PirelliEvidenceStore(destination).load(
        meeting_key="1292",
        target_session_key="race-1292",
        evidence_cutoff=datetime(2026, 8, 30, 13, tzinfo=UTC),
        session_scope=SessionScope.RACE,
    )
    assert imported.releases_imported == 1
    assert availability.status == "PRESENT"
    assert availability.snapshot.latest_strategy_release.strategies[1].sequence == "S-H"


def test_renormalization_does_not_invent_exact_event_scope(tmp_path):
    archive = PirelliArchive(tmp_path)
    published = datetime(2026, 5, 20, 14, tzinfo=UTC)
    artifact = archive.archive_artifact(
        meeting_key="1285",
        source_url="https://press.pirelli.com/tyre-compounds-selected/",
        source_type=SourceType.NEWSROOM_HTML,
        body=(
            b'<html><meta property="og:title" content="Tyre compounds selected">'
            b"<main>Pirelli will supply C3 as Hard, C4 as Medium and C5 as Soft.</main></html>"
        ),
        retrieved_at=published,
        published_at=published,
        modified_at=published,
        media_type="text/html",
        collector_version="fixture",
        extension="html",
    )
    scope = FactApplicability(
        meeting_key="1285",
        source_meeting_name="Canadian Grand Prix",
        session_scope=SessionScope.RACE,
        target_session_key="race-1285",
    )
    evidence = SourceEvidence(
        artifact.artifact_id,
        artifact.source_url,
        EvidenceKind.TEXT,
        ExtractionMethod.DETERMINISTIC_PROSE,
        text="legacy unproven binding",
    )
    save_normalized_release(
        archive,
        meeting_key="1285",
        release=PirelliRelease(
            release_id=artifact.artifact_id,
            source_url=artifact.source_url,
            published_at=published,
            modified_at=published,
            retrieved_at=published,
            content_hash=artifact.content_hash,
            source_type=SourceType.NEWSROOM_HTML,
            extraction_method=ExtractionMethod.DETERMINISTIC_PROSE,
            normalizer_version="slipstream-pirelli-v5-adapted.3",
            artifact_ids=(artifact.artifact_id,),
            applicability=scope,
            strategies=(
                StrategyOption(
                    id="legacy",
                    rank=StrategyRank.FASTEST_PUBLISHED,
                    stop_count=1,
                    compounds=(Compound.MEDIUM, Compound.HARD),
                    pit_windows=(PitWindow(20, 26),),
                    source_evidence=(evidence,),
                    applicability=scope,
                ),
            ),
        ),
    )
    target = PirelliIngestionTarget(
        MeetingDiscoveryTarget(
            meeting_key="1285",
            canonical_name="Canadian Grand Prix",
            season=2026,
            weekend_start=datetime(2026, 5, 22, tzinfo=UTC),
            weekend_end=datetime(2026, 5, 24, 22, tzinfo=UTC),
            aliases=("Canada", "Montreal"),
            exact_tag="2026 Canadian Grand Prix",
        ),
        "race-1285",
        SessionScope.RACE,
    )

    report = asyncio.run(
        PirelliIngestionService(archive, _OfflineClient()).renormalize_archived(
            target
        )
    )

    assert report.normalized_release_ids == ()
    assert artifact.source_url in report.skipped_release_urls
    assert {
        release.normalizer_version
        for release in list_normalized_derivations(archive, "1285")
    } == {"slipstream-pirelli-v5-adapted.3"}
