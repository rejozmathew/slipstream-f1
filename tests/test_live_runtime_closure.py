import asyncio
import json
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from slipstream.api import create_app
from slipstream.catalog import CATALOG_FORMAT
from slipstream.events import NormalizedEvent
from slipstream.library import ReplayLibrary
from slipstream.live import PublicLiveSession
from slipstream.live_recording import NormalizedLiveRecorder
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
    StrategyRank,
)
from slipstream.pirelli.store import PirelliEvidenceStore
from slipstream.weekend import (
    WEEKEND_CONTEXT_FORMAT,
    WEEKEND_CONTEXT_MODEL_VERSION,
    WEEKEND_CONTEXT_SCHEMA_VERSION,
    WeekendContextStore,
)


def _completion_rows(session_key: str) -> list[dict[str, object]]:
    return [
        {
            "received_at": "2026-08-23T15:00:00Z",
            "stream": "SessionInfo",
            "source_timestamp": "2026-08-23T15:00:00Z",
            "initial": True,
            "payload": {
                "Key": int(session_key),
                "Name": "Race",
                "Type": "Race",
                "StartDate": "2026-08-23T13:00:00Z",
                "EndDate": "2026-08-23T15:00:00Z",
            },
        },
        {
            "received_at": "2026-08-23T15:00:01Z",
            "stream": "SessionStatus",
            "source_timestamp": "2026-08-23T15:00:01Z",
            "initial": False,
            "payload": {"Status": "Ends"},
        },
    ]


def _catalog(sessions: list[dict[str, object]]) -> dict[str, object]:
    return {
        "format": CATALOG_FORMAT,
        "schema_version": 1,
        "source": "openf1",
        "updated_at": "2026-08-23T14:00:00Z",
        "years": [2026],
        "meetings": {
            "M": {
                "meeting_key": "M",
                "meeting_name": "Test Grand Prix",
                "location": "Test City",
                "circuit_short_name": "Test Circuit",
                "circuit": {
                    "key": "7",
                    "name": "Test Circuit",
                    "year": 2026,
                    "rotation": 12,
                    "path": [[0, 0], [10, 0], [5, 8]],
                    "source": "catalog-cache",
                    "availability": {"path": "available"},
                },
            }
        },
        "sessions": sessions,
    }


def _session(key: str, name: str, start: str, end: str) -> dict[str, object]:
    return {
        "session_key": key,
        "meeting_key": "M",
        "session_name": name,
        "session_type": "Race",
        "circuit_short_name": "Test Circuit",
        "location": "Test City",
        "date_start": start,
        "date_end": end,
        "gmt_offset": "02:00:00",
        "year": 2026,
    }


def test_noop_rows_do_not_extend_live_finalization_drain(tmp_path: Path) -> None:
    async def scenario() -> None:
        upstream_closed = asyncio.Event()

        async def rows():
            try:
                for row in _completion_rows("100"):
                    yield row
                for index in range(40):
                    await asyncio.sleep(0.005)
                    yield {
                        "received_at": f"2026-08-23T15:00:{index + 2:02d}Z",
                        "stream": "Heartbeat",
                        "source_timestamp": None,
                        "initial": False,
                        "payload": {"Utc": "2026-08-23T15:00:00Z"},
                    }
                await asyncio.sleep(1)
            finally:
                upstream_closed.set()

        live = PublicLiveSession(
            row_source=rows,
            normalized_recording_dir=tmp_path,
            finalization_drain=0.02,
        )
        await live.start("100")
        for _ in range(50):
            if live.view("100").phase == "REPLAY_READY":
                break
            await asyncio.sleep(0.005)

        view = live.view("100")
        assert view.phase == "REPLAY_READY"
        assert view.status == "OFFLINE"
        assert view.connected is False
        assert view.replay_ready is True
        assert {"COMPLETE", "REPLAY_READY"}.issubset(live.phase_history)
        await asyncio.wait_for(upstream_closed.wait(), timeout=0.2)
        await live.stop()

    asyncio.run(scenario())


def test_replay_ready_session_rolls_over_to_upcoming_session_without_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_REFRESH", "0")
    sessions = [
        _session("100", "Race A", "2026-08-23T13:00:00Z", "2026-08-23T16:00:00Z"),
        _session("200", "Race B", "2026-08-23T17:00:00Z", "2026-08-23T19:00:00Z"),
    ]
    (tmp_path / "catalog.json").write_text(
        json.dumps(_catalog(sessions)), encoding="utf-8"
    )
    source_sessions: list[str] = []

    def row_source():
        source_sessions.append("100")

        async def rows():
            for row in _completion_rows("100"):
                yield row
            await asyncio.sleep(1)

        return rows()

    now = lambda: datetime(2026, 8, 23, 15, 30, tzinfo=UTC)
    live = PublicLiveSession(
        row_source=row_source, finalization_drain=0.01, now=now
    )

    with TestClient(
        create_app(
            tmp_path,
            now=now,
            public_live=True,
            live_session=live,
            prepare_weekend_context=lambda **_: {},
        )
    ) as client:
        payload = {}
        for _ in range(100):
            payload = client.get("/api/v1/catalog").json()
            if payload["liveSessionKey"] == "200":
                break
            time.sleep(0.01)

        by_key = {item["sessionKey"]: item for item in payload["sessions"]}
        assert payload["liveSessionKey"] == "200"
        assert live.target_session_key == "200"
        assert live.view("200").phase == "PRE_EVENT"
        assert by_key["100"]["available"] is True
        assert by_key["100"]["replayReady"] is True
        assert by_key["100"]["liveAvailable"] is False
        assert (tmp_path / "live-100.json").is_file()
        assert source_sessions == ["100"]


def _save_pirelli_fixture(root: Path, meeting_key: str, session_key: str) -> None:
    archive = PirelliArchive(root)
    retrieved = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)
    artifact = archive.archive_artifact(
        meeting_key=meeting_key,
        source_url="https://press.pirelli.com/test",
        source_type=SourceType.NEWSROOM_HTML,
        body=b"Medium-Hard between laps 17 and 23",
        retrieved_at=retrieved,
        published_at=retrieved,
        modified_at=None,
        media_type="text/html",
        collector_version="test",
        extension="html",
    )
    evidence = SourceEvidence(
        artifact_id=artifact.artifact_id,
        source_url=artifact.source_url,
        kind=EvidenceKind.TEXT,
        extraction_method=ExtractionMethod.DETERMINISTIC_PROSE,
        text="Medium-Hard between laps 17 and 23",
        confidence=1.0,
    )
    strategy = StrategyOption(
        id="mh",
        rank=StrategyRank.FASTEST_PUBLISHED,
        stop_count=1,
        compounds=(Compound.MEDIUM, Compound.HARD),
        pit_windows=(PitWindow(17, 23),),
        source_evidence=(evidence,),
        applicability=FactApplicability(
            meeting_key=meeting_key,
            session_scope=SessionScope.RACE,
            target_session_key=session_key,
        ),
    )
    release = PirelliRelease(
        release_id=artifact.artifact_id,
        source_url=artifact.source_url,
        published_at=retrieved,
        modified_at=None,
        retrieved_at=retrieved,
        content_hash=artifact.content_hash,
        source_type=SourceType.NEWSROOM_HTML,
        extraction_method=ExtractionMethod.DETERMINISTIC_PROSE,
        normalizer_version="test",
        artifact_ids=(artifact.artifact_id,),
        applicability=FactApplicability(
            meeting_key=meeting_key, session_scope=SessionScope.WEEKEND
        ),
        strategies=(strategy,),
    )
    save_normalized_release(archive, meeting_key=meeting_key, release=release)


def test_normalized_live_replay_overlays_catalog_identity_and_context(
    tmp_path: Path,
) -> None:
    session = _session(
        "100", "Grand Prix", "2026-08-23T13:00:00Z", "2026-08-23T15:00:00Z"
    )
    (tmp_path / "catalog.json").write_text(
        json.dumps(_catalog([session])), encoding="utf-8"
    )
    catalog_descriptor = ReplayLibrary(tmp_path).descriptors["100"]
    context = {
        "format": WEEKEND_CONTEXT_FORMAT,
        "schema_version": WEEKEND_CONTEXT_SCHEMA_VERSION,
        "model_version": WEEKEND_CONTEXT_MODEL_VERSION,
        "generated_at": "2026-08-22T12:00:00Z",
        "evidence_cutoff": catalog_descriptor.date_start,
        "meeting_key": "M",
        "target_session_key": "100",
        "sessions": [],
    }
    WeekendContextStore(tmp_path).save(catalog_descriptor, context)
    _save_pirelli_fixture(tmp_path, "M", "100")

    events = [
        NormalizedEvent(
            kind="session",
            occurred_at="2026-08-23T13:00:00Z",
            source="f1-signalr-public",
            payload={
                "key": "100",
                "name": "Race",
                "session_type": "Race",
                "started_at": "2026-08-23T13:00:00Z",
                "ended_at": "2026-08-23T15:00:00Z",
                "status": "FINISHED",
            },
        )
    ]
    (tmp_path / "live-100.json").write_text(
        json.dumps([asdict(event) for event in events]), encoding="utf-8"
    )

    descriptor = ReplayLibrary(tmp_path).descriptors["100"]
    assert descriptor.key == "100"
    assert descriptor.meeting_key == "M"
    assert descriptor.year == 2026
    assert descriptor.meeting_name == "Test Grand Prix"
    assert descriptor.date_start == "2026-08-23T13:00:00Z"
    assert descriptor.gmt_offset == "02:00:00"
    assert descriptor.circuit == "Test Circuit"
    assert descriptor.available is True
    assert descriptor.capabilities["historical_replay"] is True
    assert descriptor.capabilities["circuit_shape"] is True
    assert WeekendContextStore(tmp_path).load(descriptor) == context

    pirelli = PirelliEvidenceStore(tmp_path).load(
        meeting_key=descriptor.meeting_key,
        target_session_key=descriptor.key,
        evidence_cutoff=descriptor.date_start,
        session_scope=SessionScope.RACE,
    )
    assert pirelli.status == "PRESENT"


def test_in_progress_recording_recovers_deduplicates_and_finalizes_both_parts(
    tmp_path: Path,
) -> None:
    before = NormalizedEvent(
        kind="session",
        occurred_at="2026-08-23T13:00:00Z",
        source="f1-signalr-public",
        payload={"key": "100", "status": "STARTED"},
    )
    after = NormalizedEvent(
        kind="timing",
        occurred_at="2026-08-23T13:01:00Z",
        source="f1-signalr-public",
        payload={"number": "44", "lap": 1},
    )
    first_process = NormalizedLiveRecorder(tmp_path, "100")
    assert first_process.append((before,)) == (before,)

    restarted = NormalizedLiveRecorder(tmp_path, "100")
    assert restarted.events == (before,)
    assert restarted.append((before, after)) == (after,)
    finalized = json.loads(restarted.finalize().read_text(encoding="utf-8"))

    assert [item["payload"] for item in finalized] == [
        {"key": "100", "status": "STARTED"},
        {"number": "44", "lap": 1},
    ]


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("not-json", "line 1"),
        (
            json.dumps(
                asdict(
                    NormalizedEvent(
                        kind="session",
                        occurred_at="2026-08-23T13:00:00Z",
                        source="f1-signalr-public",
                        payload={"key": "different"},
                    )
                )
            ),
            "belongs to different",
        ),
    ],
)
def test_in_progress_recording_rejects_malformed_or_incompatible_recovery(
    tmp_path: Path, line: str, message: str
) -> None:
    path = tmp_path / "live-100.in-progress.jsonl"
    path.write_text(line + "\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match=message):
        NormalizedLiveRecorder(tmp_path, "100")
