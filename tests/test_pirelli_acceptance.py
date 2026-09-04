import asyncio
import gzip
import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import slipstream.pirelli.backfill as backfill_module
from slipstream.api import create_app
from slipstream.catalog import CATALOG_FORMAT
from slipstream.pirelli.acquisition import AcquiredArtifact, PirelliPublicClient
from slipstream.pirelli.archive import PirelliArchive, save_normalized_release
from slipstream.pirelli.backfill import PirelliHistoricalCoordinator
from slipstream.pirelli.config import NORMALIZER_VERSION
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
    StrategyRank,
)
from slipstream.pirelli.discovery import PIRELLI_F1_RSS_URL
from slipstream.pirelli.ingest import PirelliIngestionService
from slipstream.pirelli.seed import (
    PIRELLI_SEED_NAME,
    import_bundled_pirelli_seed,
    import_pirelli_seed_bytes,
    validate_pirelli_seed,
)
from slipstream.pirelli.store import PirelliEvidenceStore


@dataclass(frozen=True)
class _Payload:
    body: bytes
    source_type: SourceType
    published_at: datetime | None = None
    media_type: str = "text/html"


class _FakePublicClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

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
            modified_at=payload.published_at,
            media_type=payload.media_type,
            collector_version="acceptance-fixture",
            extension="xml" if payload.source_type == SourceType.RSS else "html",
        )
        return AcquiredArtifact(artifact, payload.body)


def _write_audited_replays(data_root):
    sessions = (
        {
            "session_key": 11280,
            "meeting_key": 1284,
            "meeting_name": "Miami Grand Prix",
            "country_name": "United States",
            "location": "Miami Gardens",
            "circuit_short_name": "Miami",
            "date_start": "2026-05-03T17:00:00+00:00",
            "date_end": "2026-05-03T19:00:00+00:00",
        },
        {
            "session_key": 11291,
            "meeting_key": 1285,
            "meeting_name": "Canadian Grand Prix",
            "country_name": "Canada",
            "location": "Montreal",
            "circuit_short_name": "Montreal",
            "date_start": "2026-05-24T20:00:00+00:00",
            "date_end": "2026-05-24T22:00:00+00:00",
        },
        {
            "session_key": 11353,
            "meeting_key": 1292,
            "meeting_name": "Dutch Grand Prix",
            "country_name": "Netherlands",
            "location": "Zandvoort",
            "circuit_short_name": "Zandvoort",
            "date_start": "2026-08-23T13:00:00+00:00",
            "date_end": "2026-08-23T15:00:00+00:00",
        },
    )
    catalog = {
        "format": CATALOG_FORMAT,
        "schema_version": 1,
        "source": "fixture",
        "updated_at": "2026-09-02T00:00:00Z",
        "years": [2026],
        "meetings": {
            str(item["meeting_key"]): {
                "meeting_key": item["meeting_key"],
                "meeting_name": item["meeting_name"],
                "country_name": item["country_name"],
                "location": item["location"],
                "circuit_short_name": item["circuit_short_name"],
                "year": 2026,
            }
            for item in sessions
        },
        "sessions": [
            {
                **item,
                "session_name": "Race",
                "session_type": "Race",
                "year": 2026,
            }
            for item in sessions
        ],
    }
    (data_root / "catalog.json").write_text(
        json.dumps(catalog), encoding="utf-8"
    )
    for item in sessions:
        events = [
            {
                "kind": "session",
                "occurred_at": item["date_start"],
                "source": "fixture",
                "payload": {
                    "key": str(item["session_key"]),
                    "name": "Race",
                    "meeting_name": item["meeting_name"],
                    "session_type": "Race",
                    "started_at": item["date_start"],
                    "ended_at": item["date_end"],
                    "status": "RUNNING",
                },
            },
            {
                "kind": "session",
                "occurred_at": item["date_end"],
                "source": "fixture",
                "payload": {"status": "FINISHED", "control_status": "CHEQUERED"},
            },
        ]
        (data_root / f"race-{item['session_key']}.json").write_text(
            json.dumps(events), encoding="utf-8"
        )


def _option(baseline, compounds, start_lap, end_lap):
    return next(
        option
        for option in baseline["options"]
        if option["compounds"] == compounds
        and option["pitWindows"] == [
            {"startLap": start_lap, "endLap": end_lap}
        ]
    )


def _bundled_seed_without(meeting_key):
    seed_path = (
        Path(__file__).parents[1]
        / "src"
        / "slipstream"
        / "data"
        / PIRELLI_SEED_NAME
    )
    payload = json.loads(gzip.decompress(seed_path.read_bytes()))
    payload["meetings"] = [
        item for item in payload["meetings"] if item["meetingKey"] != meeting_key
    ]
    payload["materialized"] = {
        "meetingCount": len(payload["meetings"]),
        "releaseCount": sum(
            len(item["releases"]) for item in payload["meetings"]
        ),
        "meetingKeys": sorted(
            item["meetingKey"] for item in payload["meetings"]
        ),
    }
    base = {key: value for key, value in payload.items() if key != "integrity"}
    payload["integrity"] = {
        "algorithm": "sha256",
        "digest": hashlib.sha256(
            json.dumps(base, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    return gzip.compress(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() + b"\n",
        mtime=0,
    )


def test_bundled_seed_records_horizon_and_exact_materialized_contents():
    seed_path = (
        Path(__file__).parents[1]
        / "src"
        / "slipstream"
        / "data"
        / PIRELLI_SEED_NAME
    )
    payload = validate_pirelli_seed(seed_path)

    assert payload["normalizerVersion"] == NORMALIZER_VERSION
    assert payload["coverage"]["fromSeason"] == 2017
    assert payload["coverage"]["throughSeason"] == 2026
    assert payload["horizon"] == payload["coverage"]
    assert payload["materialized"] == {
        "meetingCount": 69,
        "releaseCount": 218,
        "meetingKeys": [
            "1141",
            "1142",
            "1143",
            "1207",
            "1208",
            "1210",
            "1211",
            "1213",
            "1214",
            "1215",
            "1216",
            "1217",
            "1218",
            "1219",
            "1220",
            "1221",
            "1222",
            "1225",
            "1229",
            "1230",
            "1231",
            "1232",
            "1234",
            "1236",
            "1237",
            "1239",
            "1240",
            "1241",
            "1242",
            "1243",
            "1244",
            "1245",
            "1246",
            "1247",
            "1250",
            "1251",
            "1252",
            "1254",
            "1255",
            "1256",
            "1257",
            "1258",
            "1259",
            "1261",
            "1262",
            "1263",
            "1264",
            "1265",
            "1266",
            "1268",
            "1269",
            "1270",
            "1271",
            "1274",
            "1275",
            "1276",
            "1277",
            "1279",
            "1280",
            "1281",
            "1284",
            "1285",
            "1286",
            "1288",
            "1289",
            "1290",
            "1291",
            "1292",
            "1293",
        ],
    }
    assert payload["integrity"]["digest"] == (
        "48546bae72e1cc81c43cddca30a67b18cd5a0dec7c396d385f3ccb50471c3ff4"
    )
    assert hashlib.sha256(seed_path.read_bytes()).hexdigest() == (
        "7f771803208629d6cd7e30eafc3b74aa9483df3faea024805acd8fba8082e709"
    )
    for meeting in payload["meetings"]:
        for release in meeting["releases"]:
            for fact in release["context_facts"]:
                statement = fact["statement"]
                assert len(
                    re.findall(
                        r"(?:^|\s)\d{1,2}\s+[A-Za-z]+\s+20\d{2}\s+[-–—]\s+",
                        statement,
                    )
                ) < 2
                assert "latest news" not in statement.casefold()
                assert not statement.casefold().endswith("newsroom")
    by_season = {
        season: [item for item in payload["meetings"] if item["season"] == season]
        for season in range(2017, 2027)
    }
    assert {
        season: (len(items), sum(len(item["releases"]) for item in items))
        for season, items in by_season.items()
    } == {
        2017: (0, 0),
        2018: (0, 0),
        2019: (0, 0),
        2020: (0, 0),
        2021: (0, 0),
        2022: (0, 0),
        2023: (18, 60),
        2024: (19, 52),
        2025: (20, 53),
        2026: (12, 53),
    }
    meetings = {item["meetingKey"]: item for item in payload["meetings"]}
    assert (meetings["1141"]["season"], meetings["1141"]["meetingName"]) == (
        2023,
        "Bahrain Grand Prix",
    )
    assert (meetings["1231"]["season"], meetings["1231"]["meetingName"]) == (
        2024,
        "Australian Grand Prix",
    )
    assert (meetings["1254"]["season"], meetings["1254"]["meetingName"]) == (
        2025,
        "Australian Grand Prix",
    )
    assert (meetings["1279"]["season"], meetings["1279"]["meetingName"]) == (
        2026,
        "Australian Grand Prix",
    )


def test_clean_install_seed_only_api_exposes_audited_dutch_and_canada(
    tmp_path, monkeypatch
):
    _write_audited_replays(tmp_path)
    assert not (tmp_path / ".slipstream" / "pirelli").exists()
    monkeypatch.delenv("SLIPSTREAM_PIRELLI_SEED_PATH", raising=False)
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_BACKFILL", "0")
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_REFRESH", "0")

    with TestClient(
        create_app(
            tmp_path,
            now=lambda: datetime(2026, 9, 2, tzinfo=UTC),
            public_live=False,
            prepare_weekend_context=lambda **_kwargs: {},
        )
    ) as client:
        catalog = client.get("/api/v1/catalog")
        dutch_response = client.get("/api/v1/analytics?session_key=11353")
        canada_response = client.get("/api/v1/analytics?session_key=11291")

    assert catalog.status_code == 200
    assert dutch_response.status_code == 200
    assert canada_response.status_code == 200
    assert (tmp_path / ".slipstream" / "pirelli").is_dir()

    dutch = dutch_response.json()["officialPreRace"]
    assert dutch["status"] == "PRESENT"
    assert dutch["modelAdmissible"] is True
    assert dutch["compoundSelection"] == {
        "hard": "C2",
        "medium": "C3",
        "soft": "C4",
    }
    medium_hard = _option(dutch, ["MEDIUM", "HARD"], 27, 33)
    soft_hard = _option(dutch, ["SOFT", "HARD"], 26, 32)
    assert medium_hard["rank"] == "FASTEST_PUBLISHED"
    assert soft_hard["rank"] == "ALTERNATIVE"
    assert soft_hard["publishedDeltaSeconds"] == 1.0
    dutch_context = " ".join(
        item["statement"] for item in dutch["contextFacts"]
    ).casefold()
    assert "bring forward their runs" not in dutch_context
    assert "monza" not in dutch_context
    assert any(
        item["category"] == "STRATEGY_OUTLOOK"
        for item in dutch["contextFacts"]
    )

    canada = canada_response.json()["officialPreRace"]
    assert canada["status"] == "PRESENT"
    assert canada["modelAdmissible"] is True
    assert canada["compoundSelection"] == {
        "hard": "C3",
        "medium": "C4",
        "soft": "C5",
    }
    assert any(
        item["category"] == "STRATEGY_OUTLOOK"
        and "one‑stop strategy could again be preferred" in item["statement"]
        for item in canada["contextFacts"]
    )


def test_bundled_seed_import_is_idempotent_on_an_empty_runtime(tmp_path):
    first = import_bundled_pirelli_seed(tmp_path)
    second = import_bundled_pirelli_seed(tmp_path)

    assert first.meetings == 69
    assert first.releases_imported == 218
    assert second.releases_imported == 0
    assert second.releases_preserved == 218


def test_startup_imports_seed_without_immediate_ten_year_metadata_scan(
    tmp_path, monkeypatch
):
    _write_audited_replays(tmp_path)
    metadata_calls = []

    def metadata_sync(*_args, **_kwargs):
        metadata_calls.append("called")
        raise AssertionError("startup must not perform an immediate horizon scan")

    coordinator = PirelliHistoricalCoordinator(
        tmp_path,
        PirelliIngestionService(PirelliArchive(tmp_path), _FakePublicClient({})),
        metadata_sync=metadata_sync,
    )
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_BACKFILL", "1")
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_REFRESH", "0")

    with TestClient(
        create_app(
            tmp_path,
            public_live=False,
            pirelli_historical_coordinator=coordinator,
            pirelli_backfill_initial_delay=3_600,
        )
    ) as client:
        assert client.get("/api/v1/catalog").status_code == 200

    assert metadata_calls == []


def test_miami_api_self_backfills_when_removed_from_production_seed_without_restart(
    tmp_path, monkeypatch
):
    _write_audited_replays(tmp_path)
    missing_seed = tmp_path / "production-seed-without-miami.json.gz"
    missing_seed.write_bytes(_bundled_seed_without("1284"))
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_SEED_PATH", str(missing_seed))
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_REFRESH", "0")
    nomination_url = (
        "https://press.pirelli.com/"
        "the-softest-trio-for-the-challenges-of-miami-and-montreal/"
    )
    strategy_url = (
        "https://press.pirelli.com/"
        "sprint-victory-for-norris-and-pole-position-for-antonelli/"
    )
    feed = (
        "<rss><channel>"
        "<item><title>The softest trio for the challenges of Miami and Montreal</title>"
        f"<link>{nomination_url}</link>"
        "<pubDate>Mon, 27 Apr 2026 10:00:00 GMT</pubDate>"
        "<category>2026 Miami Grand Prix</category>"
        "<description>Official Miami compound selection</description></item>"
        "<item><title>Sprint victory for Norris and pole position for Antonelli</title>"
        f"<link>{strategy_url}</link>"
        "<pubDate>Sat, 02 May 2026 23:07:00 GMT</pubDate>"
        "<category>2026 Miami Grand Prix</category>"
        "<description>Official guidance for tomorrow's Grand Prix</description></item>"
        "</channel></rss>"
    ).encode()
    nomination = (
        b"<html><main><p>The C3, C4 and C5 selection applies to the Miami Grand "
        b"Prix and Canadian Grand Prix.</p><p>In Miami degradation is mainly "
        b"thermal because of the high temperatures.</p></main></html>"
    )
    strategy = (
        b"<html><main><p>Kimi Antonelli secured pole position in today's qualifying "
        b"session. Lando Norris claimed victory in this morning's Sprint.</p>"
        b"<p>The one-stop strategy is confirmed as the fastest option for tomorrow, "
        b"as expected ahead of the race weekend. The compounds selected for Miami "
        b"have proven consistent and with low degradation. By contrast, a two-stop "
        b"strategy would be penalised by around 10 seconds compared to a single stop.</p>"
        b"<p>On paper, the Medium-Hard solution, with a pit window between laps 22 "
        b"and 28, is the quickest. The Soft could be a valid option, exploiting its "
        b"higher grip, when used in combination with the Hard. Starting on the C5, "
        b"the pit stop should be made between laps 16 and 22. Less effective in terms "
        b"of lap time is the Medium-Soft pairing, which would have a pit window between "
        b"laps 32 and 38.</p><p>The weather forecast could even lead to a wet race.</p>"
        b"</main></html>"
    )
    fake_client = _FakePublicClient(
        {
            PIRELLI_F1_RSS_URL: _Payload(
                feed, SourceType.RSS, media_type="application/rss+xml"
            ),
            nomination_url: _Payload(
                nomination,
                SourceType.NEWSROOM_HTML,
                datetime(2026, 4, 27, 10, tzinfo=UTC),
            ),
            strategy_url: _Payload(
                strategy,
                SourceType.NEWSROOM_HTML,
                datetime(2026, 5, 2, 23, 7, tzinfo=UTC),
            ),
        }
    )
    descriptor = SimpleNamespace(
        key="11280",
        session_kind="race",
        meeting_key="1284",
        date_start="2026-05-03T17:00:00+00:00",
        date_end="2026-05-03T19:00:00+00:00",
        year=2026,
        meeting_name="Miami Grand Prix",
        location="Miami Gardens",
        circuit="Miami",
        country="United States",
    )

    def metadata_sync(*_args, **_kwargs):
        return {
            "format": "slipstream.pirelli.metadata.v1",
            "updatedAt": "2026-09-02T00:00:00+00:00",
            "years": [2026],
            "meetings": {
                "1284": {
                    "meetingKey": "1284",
                    "meetingName": "Miami Grand Prix",
                    "year": 2026,
                }
            },
            "sessions": [
                {
                    "sessionKey": "11280",
                    "meetingKey": "1284",
                    "sessionName": "Race",
                    "sessionType": "Race",
                    "dateStart": descriptor.date_start,
                    "dateEnd": descriptor.date_end,
                    "year": 2026,
                }
            ],
        }

    coordinator = PirelliHistoricalCoordinator(
        tmp_path,
        PirelliIngestionService(PirelliArchive(tmp_path), fake_client),
        metadata_sync=metadata_sync,
    )
    app = create_app(
        tmp_path,
        now=lambda: datetime(2026, 9, 2, tzinfo=UTC),
        public_live=False,
        prepare_weekend_context=lambda **_kwargs: {},
        pirelli_historical_coordinator=coordinator,
        pirelli_backfill_initial_delay=3_600,
    )
    before = PirelliEvidenceStore(tmp_path).load(
        meeting_key="1284",
        target_session_key="11280",
        evidence_cutoff=descriptor.date_start,
        session_scope=SessionScope.RACE,
    )

    with TestClient(app) as client:
        first = client.get("/api/v1/analytics?session_key=11280")
        assert first.status_code == 200
        assert first.json()["officialPreRace"]["status"] == "FETCHING"
        present = None
        for _ in range(100):
            response = client.get("/api/v1/analytics?session_key=11280")
            baseline = response.json()["officialPreRace"]
            if baseline["status"] == "PRESENT":
                present = baseline
                break
            time.sleep(0.01)

    assert before.status == "ABSENT"
    assert present is not None
    assert present["compoundSelection"] == {
        "hard": "C3",
        "medium": "C4",
        "soft": "C5",
    }
    _option(present, ["MEDIUM", "HARD"], 22, 28)
    _option(present, ["MEDIUM", "SOFT"], 32, 38)
    assert any(
        option["compounds"] == ["SOFT", "HARD"]
        for option in present["options"]
    )
    categories = {fact["category"] for fact in present["contextFacts"]}
    assert {"STRATEGY_OUTLOOK", "DEGRADATION", "WEATHER"} <= categories
    assert any(
        "around 10 seconds" in fact["statement"]
        for fact in present["contextFacts"]
    )
    assert fake_client.calls[0] == PIRELLI_F1_RSS_URL
    assert {nomination_url, strategy_url} <= set(fake_client.calls)


def test_miami_api_keeps_partial_worker_result_fetching_until_complete(
    tmp_path, monkeypatch
):
    _write_audited_replays(tmp_path)
    monkeypatch.delenv("SLIPSTREAM_PIRELLI_SEED_PATH", raising=False)
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_SEED", "0")
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_REFRESH", "0")
    started = threading.Event()
    release = threading.Event()
    descriptor = SimpleNamespace(
        key="11280",
        session_kind="race",
        meeting_key="1284",
        date_start="2026-05-03T17:00:00+00:00",
        date_end="2026-05-03T19:00:00+00:00",
        year=2026,
        meeting_name="Miami Grand Prix",
        location="Miami Gardens",
        circuit="Miami",
        country="United States",
    )

    def save_release(*, complete: bool) -> None:
        published = datetime(2026, 5, 2, 20, tzinfo=UTC)
        source_url = f"https://press.pirelli.com/miami-{'complete' if complete else 'partial'}"
        archive = PirelliArchive(tmp_path)
        artifact = archive.archive_artifact(
            meeting_key="1284",
            source_url=source_url,
            source_type=SourceType.NEWSROOM_HTML,
            body=(b"complete Miami strategy" if complete else b"partial Miami context"),
            retrieved_at=published,
            published_at=published,
            modified_at=published,
            media_type="text/html",
            collector_version="partial-worker-test",
            extension="html",
        )
        scope = FactApplicability(
            meeting_key="1284",
            session_scope=SessionScope.RACE,
            target_session_key="11280",
        )
        evidence = SourceEvidence(
            artifact.artifact_id,
            source_url,
            EvidenceKind.TEXT,
            ExtractionMethod.DETERMINISTIC_PROSE,
        )
        save_normalized_release(
            archive,
            meeting_key="1284",
            release=PirelliRelease(
                release_id=artifact.artifact_id,
                source_url=source_url,
                published_at=published,
                modified_at=published,
                retrieved_at=published,
                content_hash=artifact.content_hash,
                source_type=SourceType.NEWSROOM_HTML,
                extraction_method=ExtractionMethod.DETERMINISTIC_PROSE,
                normalizer_version=(NORMALIZER_VERSION if complete else "partial-v0"),
                artifact_ids=(artifact.artifact_id,),
                applicability=scope,
                strategies=(
                    (
                        StrategyOption(
                            id="miami-complete",
                            rank=StrategyRank.FASTEST_PUBLISHED,
                            stop_count=1,
                            compounds=(Compound.MEDIUM, Compound.HARD),
                            pit_windows=(PitWindow(22, 28),),
                            source_evidence=(evidence,),
                            applicability=scope,
                        ),
                    )
                    if complete
                    else ()
                ),
                context_facts=(
                    ContextFact(
                        category="STRATEGY_OUTLOOK",
                        statement=(
                            "Complete Miami strategy guidance"
                            if complete
                            else "Partial Miami context"
                        ),
                        source_evidence=(evidence,),
                        applicability=scope,
                    ),
                ),
            ),
        )

    async def production_sync(*_args, **_kwargs):
        save_release(complete=False)
        started.set()
        release.wait(timeout=2)
        save_release(complete=True)
        return SimpleNamespace(
            items=(SimpleNamespace(status="PRESENT", issue=None),)
        )

    def metadata_sync(*_args, **_kwargs):
        return {
            "format": "slipstream.pirelli.metadata.v1",
            "updatedAt": "2026-09-02T00:00:00+00:00",
            "years": [2026],
            "meetings": {
                "1284": {
                    "meetingKey": "1284",
                    "meetingName": descriptor.meeting_name,
                    "year": descriptor.year,
                }
            },
            "sessions": [
                {
                    "sessionKey": descriptor.key,
                    "meetingKey": descriptor.meeting_key,
                    "sessionName": "Race",
                    "sessionType": "Race",
                    "dateStart": descriptor.date_start,
                    "dateEnd": descriptor.date_end,
                    "year": descriptor.year,
                }
            ],
        }

    monkeypatch.setattr(backfill_module, "sync_pirelli_backfill", production_sync)
    coordinator = PirelliHistoricalCoordinator(
        tmp_path,
        PirelliIngestionService(PirelliArchive(tmp_path), PirelliPublicClient()),
        metadata_sync=metadata_sync,
    )
    coordinator.prioritize("1284")
    app = create_app(
        tmp_path,
        now=lambda: datetime(2026, 9, 2, tzinfo=UTC),
        public_live=False,
        prepare_weekend_context=lambda **_kwargs: {},
        pirelli_historical_coordinator=coordinator,
        pirelli_backfill_initial_delay=3_600,
    )

    try:
        with TestClient(app) as client:
            assert started.wait(timeout=1)
            partial_store = PirelliEvidenceStore(tmp_path).load(
                meeting_key="1284",
                target_session_key="11280",
                evidence_cutoff=descriptor.date_start,
                session_scope=SessionScope.RACE,
            )
            assert partial_store.status == "PRESENT"
            assert any(
                fact.statement == "Partial Miami context"
                for fact in partial_store.snapshot.context_facts
            )
            partial = client.get("/api/v1/analytics?session_key=11280").json()[
                "officialPreRace"
            ]
            assert partial["status"] == "FETCHING"
            assert partial["contextFacts"] == []
            release.set()
            complete = None
            for _ in range(100):
                baseline = client.get(
                    "/api/v1/analytics?session_key=11280"
                ).json()["officialPreRace"]
                if baseline["status"] == "PRESENT" and baseline["options"]:
                    complete = baseline
                    break
                time.sleep(0.01)
    finally:
        release.set()

    assert complete is not None
    _option(complete, ["MEDIUM", "HARD"], 22, 28)


def test_miami_api_reports_metadata_backoff_as_retrying(tmp_path, monkeypatch):
    _write_audited_replays(tmp_path)
    monkeypatch.delenv("SLIPSTREAM_PIRELLI_SEED_PATH", raising=False)
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_SEED", "0")
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_REFRESH", "0")
    clock = datetime(2026, 9, 2, tzinfo=UTC)

    def fail_metadata(*_args, **_kwargs):
        raise RuntimeError("fixture metadata unavailable")

    coordinator = PirelliHistoricalCoordinator(
        tmp_path,
        PirelliIngestionService(PirelliArchive(tmp_path), _FakePublicClient({})),
        metadata_sync=fail_metadata,
    )
    assert asyncio.run(coordinator.run_once(now=clock)).status == "FAILURE"
    app = create_app(
        tmp_path,
        now=lambda: clock,
        public_live=False,
        prepare_weekend_context=lambda **_kwargs: {},
        pirelli_historical_coordinator=coordinator,
        pirelli_backfill_initial_delay=3_600,
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/analytics?session_key=11280")

    assert response.status_code == 200
    assert response.json()["officialPreRace"]["status"] == "RETRYING"


def test_missing_canada_is_prioritized_and_self_backfills_without_restart(tmp_path):
    import_pirelli_seed_bytes(_bundled_seed_without("1285"), tmp_path)

    descriptor = SimpleNamespace(
        key="11291",
        session_kind="race",
        meeting_key="1285",
        date_start="2026-05-24T20:00:00+00:00",
        date_end="2026-05-24T22:00:00+00:00",
        year=2026,
        meeting_name="Canadian Grand Prix",
        location="Montreal",
        circuit="Montreal",
        country="Canada",
    )
    store = PirelliEvidenceStore(tmp_path)
    before = store.load(
        meeting_key="1285",
        target_session_key="11291",
        evidence_cutoff=descriptor.date_start,
        session_scope=SessionScope.RACE,
    )
    article_url = "https://press.pirelli.com/the-first-sprint-in-montreal/"
    feed_url = "https://press.pirelli.com/tagfeed/en/tags/formula__1"
    published = datetime(2026, 5, 18, 13, 23, 25, tzinfo=UTC)
    feed = (
        "<rss><channel><item><title>The first Sprint in Montreal</title>"
        f"<link>{article_url}</link>"
        "<pubDate>Mon, 18 May 2026 13:23:25 GMT</pubDate>"
        "<category>2026 Canadian Grand Prix</category>"
        "<description>Official Canadian Grand Prix preview</description>"
        "</item></channel></rss>"
    ).encode()
    article = (
        "<html><main><p>The three compounds selected for the weekend are C3, C4 "
        "and C5.</p><p>As seen in Miami, teams tend to favour cautious choices in "
        "the race, where a one‑stop strategy could again be preferred this year."
        "</p></main></html>"
    ).encode()
    client = _FakePublicClient(
        {
            feed_url: _Payload(feed, SourceType.RSS, media_type="application/rss+xml"),
            article_url: _Payload(article, SourceType.NEWSROOM_HTML, published),
        }
    )
    coordinator = PirelliHistoricalCoordinator(
        tmp_path,
        PirelliIngestionService(PirelliArchive(tmp_path), client),
    )
    coordinator.prioritize("1285")

    repaired = asyncio.run(
        coordinator.run_once(
            now=datetime(2026, 9, 2, tzinfo=UTC), descriptors=(descriptor,)
        )
    )
    after = store.load(
        meeting_key="1285",
        target_session_key="11291",
        evidence_cutoff=descriptor.date_start,
        session_scope=SessionScope.RACE,
    )

    assert before.status == "ABSENT"
    assert repaired.status == "PRESENT"
    assert repaired.meeting_key == "1285"
    assert client.calls == [feed_url, article_url]
    assert after.status == "PRESENT"
    assert after.snapshot.compound_selections[-1].hard == "C3"
    assert any(
        fact.category == "STRATEGY_OUTLOOK"
        for fact in after.snapshot.context_facts
    )
