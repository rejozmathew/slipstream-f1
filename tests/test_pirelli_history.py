import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from slipstream.catalog import CATALOG_FORMAT
from slipstream.library import ReplayLibrary
from slipstream.pirelli.archive import PirelliArchive, save_normalized_release
from slipstream.pirelli.backfill import PirelliHistoricalCoordinator
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
from slipstream.pirelli.ingest import PirelliIngestionReport
from slipstream.pirelli.metadata import (
    PIRELLI_METADATA_FORMAT,
    metadata_descriptors,
    metadata_path,
    sync_pirelli_metadata,
)


def _descriptor(year: int, meeting_key: str):
    start = datetime(year, 6, 9, 13, tzinfo=UTC)
    return SimpleNamespace(
        key=f"race-{meeting_key}",
        session_kind="race",
        meeting_key=meeting_key,
        date_start=start.isoformat(),
        date_end=(start + timedelta(hours=2)).isoformat(),
        year=year,
        meeting_name=f"Meeting {meeting_key} Grand Prix",
        location=f"Meeting {meeting_key}",
        circuit=f"Circuit {meeting_key}",
    )


class _SlowService:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = []
        self.active = 0
        self.max_active = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.fail = fail

    async def refresh(self, target, *, now):
        self.calls.append(target)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.started.set()
        await self.release.wait()
        self.active -= 1
        if self.fail:
            raise RuntimeError("isolated historical failure")
        return PirelliIngestionReport((), (), ())


class _ImmediateService:
    def __init__(self) -> None:
        self.calls = []

    async def refresh(self, target, *, now):
        self.calls.append(target)
        return PirelliIngestionReport((), (), ())


def _save_covered(data_root, descriptor) -> None:
    archive = PirelliArchive(data_root)
    published = datetime.fromisoformat(descriptor.date_start) - timedelta(days=1)
    artifact = archive.archive_artifact(
        meeting_key=descriptor.meeting_key,
        source_url="https://press.pirelli.com/covered",
        source_type=SourceType.NEWSROOM_HTML,
        body=b"covered published strategy",
        retrieved_at=published,
        published_at=published,
        modified_at=published,
        media_type="text/html",
        collector_version="test",
        extension="html",
    )
    scope = FactApplicability(
        meeting_key=descriptor.meeting_key,
        session_scope=SessionScope.RACE,
        target_session_key=descriptor.key,
    )
    evidence = SourceEvidence(
        artifact.artifact_id,
        artifact.source_url,
        EvidenceKind.TEXT,
        ExtractionMethod.DETERMINISTIC_PROSE,
    )
    save_normalized_release(
        archive,
        meeting_key=descriptor.meeting_key,
        release=PirelliRelease(
            release_id=artifact.artifact_id,
            source_url=artifact.source_url,
            published_at=published,
            modified_at=published,
            retrieved_at=published,
            content_hash=artifact.content_hash,
            source_type=artifact.source_type,
            extraction_method=ExtractionMethod.DETERMINISTIC_PROSE,
            normalizer_version=NORMALIZER_VERSION,
            artifact_ids=(artifact.artifact_id,),
            applicability=FactApplicability(
                meeting_key=descriptor.meeting_key,
                session_scope=SessionScope.WEEKEND,
            ),
            strategies=(
                StrategyOption(
                    id="covered",
                    rank=StrategyRank.FASTEST_PUBLISHED,
                    stop_count=1,
                    compounds=(Compound.MEDIUM, Compound.HARD),
                    pit_windows=(PitWindow(18, 24),),
                    source_evidence=(evidence,),
                    applicability=scope,
                ),
            ),
        ),
    )


def test_quiet_backfill_is_single_concurrency_and_skips_covered_meetings(tmp_path):
    covered = _descriptor(2024, "covered")
    missing = _descriptor(2025, "missing")
    _save_covered(tmp_path, covered)
    service = _SlowService()
    coordinator = PirelliHistoricalCoordinator(tmp_path, service, history_years=10)
    coordinator.prioritize("missing")

    async def exercise():
        first = asyncio.create_task(
            coordinator.run_once(
                now=datetime(2026, 9, 2, tzinfo=UTC),
                descriptors=(covered, missing),
            )
        )
        await service.started.wait()
        concurrent = await coordinator.run_once(
            now=datetime(2026, 9, 2, tzinfo=UTC),
            descriptors=(covered, missing),
        )
        service.release.set()
        return await first, concurrent

    result, concurrent = asyncio.run(exercise())
    assert result.meeting_key == "missing"
    assert concurrent.status == "BUSY"
    assert service.max_active == 1
    assert [call.meeting.meeting_key for call in service.calls] == ["missing"]


def test_catchup_failure_is_returned_and_persisted_without_raising(tmp_path):
    service = _SlowService(fail=True)
    service.release.set()
    coordinator = PirelliHistoricalCoordinator(tmp_path, service)

    result = asyncio.run(
        coordinator.run_once(
            now=datetime(2026, 9, 2, tzinfo=UTC),
            descriptors=(_descriptor(2025, "failure"),),
        )
    )

    assert result.status == "FAILURE"
    state = json.loads(
        (tmp_path / ".slipstream" / "pirelli-backfill-state.json").read_text()
    )
    assert state["meetings"]["failure"]["status"] == "FAILURE"
    assert state["meetings"]["failure"]["nextAttemptAt"]


def test_metadata_failure_is_persisted_and_not_retried_in_a_restart_loop(tmp_path):
    attempts = []

    def fail_metadata(*_args, **_kwargs):
        attempts.append("attempt")
        raise RuntimeError("metadata unavailable")

    coordinator = PirelliHistoricalCoordinator(
        tmp_path, _SlowService(), metadata_sync=fail_metadata
    )
    clock = datetime(2026, 9, 2, tzinfo=UTC)

    first = asyncio.run(coordinator.run_once(now=clock))
    second = asyncio.run(coordinator.run_once(now=clock + timedelta(minutes=5)))

    assert first.status == "FAILURE"
    assert second.status == "DEFERRED"
    assert attempts == ["attempt"]
    state = json.loads(
        (tmp_path / ".slipstream" / "pirelli-backfill-state.json").read_text()
    )
    assert state["meetings"]["__metadata__"]["status"] == "FAILURE"


def test_selected_missing_meeting_wakes_low_frequency_backfill(tmp_path):
    first = _descriptor(2024, "first")
    selected = _descriptor(2025, "selected")
    service = _ImmediateService()

    def metadata_sync(*_args, **_kwargs):
        return {
            "format": PIRELLI_METADATA_FORMAT,
            "updatedAt": "2026-09-02T00:00:00+00:00",
            "years": [2024, 2025],
            "meetings": {
                item.meeting_key: {
                    "meetingKey": item.meeting_key,
                    "meetingName": item.meeting_name,
                    "year": item.year,
                }
                for item in (first, selected)
            },
            "sessions": [
                {
                    "sessionKey": item.key,
                    "meetingKey": item.meeting_key,
                    "sessionName": "Race",
                    "sessionType": "Race",
                    "dateStart": item.date_start,
                    "dateEnd": item.date_end,
                    "year": item.year,
                }
                for item in (first, selected)
            ],
        }

    coordinator = PirelliHistoricalCoordinator(
        tmp_path,
        service,
        interval=timedelta(hours=6),
        metadata_sync=metadata_sync,
    )

    async def exercise():
        task = asyncio.create_task(
            coordinator.run_forever(
                lambda: datetime(2026, 9, 2, tzinfo=UTC), initial_delay=0
            )
        )
        while len(service.calls) < 1:
            await asyncio.sleep(0)
        coordinator.prioritize("selected")
        while len(service.calls) < 2:
            await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(asyncio.wait_for(exercise(), timeout=2))
    assert [call.meeting.meeting_key for call in service.calls] == [
        "first",
        "selected",
    ]


class _MetadataClient:
    def __init__(self) -> None:
        self.calls = []

    def get(self, endpoint, **params):
        self.calls.append((endpoint, params["year"]))
        if endpoint == "meetings":
            return [
                {
                    "meeting_key": 19,
                    "meeting_name": "Old Grand Prix",
                    "location": "Old",
                    "circuit_short_name": "Old Circuit",
                    "date_start": "2019-06-07T00:00:00+00:00",
                    "date_end": "2019-06-09T16:00:00+00:00",
                    "year": 2019,
                }
            ]
        return [
            {
                "session_key": 190,
                "meeting_key": 19,
                "session_name": "Race",
                "session_type": "Race",
                "date_start": "2019-06-09T13:00:00+00:00",
                "date_end": "2019-06-09T15:00:00+00:00",
                "year": 2019,
            }
        ]


def test_private_pirelli_metadata_can_cover_years_outside_ui_catalog(tmp_path):
    catalog = {
        "format": CATALOG_FORMAT,
        "schema_version": 1,
        "source": "openf1",
        "updated_at": "2026-09-02T00:00:00Z",
        "years": [2026],
        "meetings": {
            "26": {
                "meeting_key": 26,
                "meeting_name": "Recent Grand Prix",
                "year": 2026,
            }
        },
        "sessions": [
            {
                "session_key": 260,
                "meeting_key": 26,
                "session_name": "Race",
                "session_type": "Race",
                "date_start": "2026-06-09T13:00:00+00:00",
                "date_end": "2026-06-09T15:00:00+00:00",
                "year": 2026,
            }
        ],
    }
    (tmp_path / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    metadata = sync_pirelli_metadata(
        metadata_path(tmp_path),
        (2019,),
        client=_MetadataClient(),
        now=datetime(2026, 9, 2, tzinfo=UTC),
    )

    assert metadata["format"] == PIRELLI_METADATA_FORMAT
    assert set(ReplayLibrary(tmp_path).descriptors) == {"260"}
    old = metadata_descriptors(metadata)
    assert [item.key for item in old] == ["190"]

    service = _SlowService()
    service.release.set()
    coordinator = PirelliHistoricalCoordinator(tmp_path, service)
    result = asyncio.run(
        coordinator.run_once(
            now=datetime(2026, 9, 2, tzinfo=UTC), descriptors=old
        )
    )
    assert result.meeting_key == "19"
    assert service.calls[0].meeting.season == 2019
