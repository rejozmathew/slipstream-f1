import asyncio
import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from slipstream.api import create_app
from slipstream.catalog import CATALOG_FORMAT
from slipstream.pirelli.acquisition import AcquiredArtifact
from slipstream.pirelli.archive import PirelliArchive
from slipstream.pirelli.backfill import PirelliHistoricalCoordinator
from slipstream.pirelli.config import NORMALIZER_VERSION
from slipstream.pirelli.contracts import SessionScope, SourceType
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


def test_bundled_seed_is_real_current_and_records_ten_season_coverage():
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
    assert {item["meetingKey"] for item in payload["meetings"]} == {"1285", "1292"}
    assert sum(len(item["releases"]) for item in payload["meetings"]) == 5


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

    assert first.meetings == 2
    assert first.releases_imported == 5
    assert second.releases_imported == 0
    assert second.releases_preserved == 5


def test_missing_canada_is_prioritized_and_self_backfills_without_restart(tmp_path):
    seed_path = (
        Path(__file__).parents[1]
        / "src"
        / "slipstream"
        / "data"
        / PIRELLI_SEED_NAME
    )
    payload = json.loads(gzip.decompress(seed_path.read_bytes()))
    payload["meetings"] = [
        item for item in payload["meetings"] if item["meetingKey"] != "1285"
    ]
    base = {key: value for key, value in payload.items() if key != "integrity"}
    payload["integrity"] = {
        "algorithm": "sha256",
        "digest": hashlib.sha256(
            json.dumps(base, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    dutch_only = gzip.compress(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() + b"\n",
        mtime=0,
    )
    import_pirelli_seed_bytes(dutch_only, tmp_path)

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
