from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

from fastapi.testclient import TestClient

from slipstream.api import create_app
from slipstream.pirelli.ingest import PirelliIngestionReport, PirelliIngestionService


def test_diagnostics_expose_completed_refresh_and_next_background_check(
    tmp_path, monkeypatch
):
    source = Path(__file__).parent / "fixtures" / "openf1" / "session-9165.json"
    (tmp_path / "race.json").write_bytes(source.read_bytes())
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_SEED", "0")
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_BACKFILL", "0")
    monkeypatch.setenv("SLIPSTREAM_PIRELLI_REFRESH", "1")
    refreshed = Event()

    async def refresh(_service, _target, *, now):
        refreshed.set()
        return PirelliIngestionReport(("release-1",), ("ignored-session-report",), ())

    monkeypatch.setattr(PirelliIngestionService, "refresh", refresh)
    now = datetime(2023, 9, 17, 10, tzinfo=UTC)
    with TestClient(create_app(tmp_path, public_live=False, now=lambda: now)) as client:
        assert refreshed.wait(5)
        diagnostics = client.get("/api/v1/diagnostics").json()["pirelli"]
        assert diagnostics["enabled"] and diagnostics["taskRunning"]
        assert datetime.fromisoformat(diagnostics["lastCheckAt"]) == now
        assert datetime.fromisoformat(diagnostics["nextCheckAt"]) == now + timedelta(
            minutes=30
        )
        meeting = diagnostics["meetings"]["1219"]
        assert meeting["last_attempt_at"] == meeting["last_success_at"]
        assert meeting["last_reason"]
        assert meeting["last_error"] is None
        assert meeting["normalized_releases"] == 1
        assert meeting["skipped_releases"] == 1
