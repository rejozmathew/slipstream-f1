"""Bounded resource ownership and synthetic live recovery contracts."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

import pytest

from slipstream.events import NormalizedEvent
from slipstream.library import ReplayBusyError, ReplayLibrary
from slipstream.live_recording import NormalizedLiveRecorder
from slipstream.session_completion import session_completion
from slipstream.source_time import source_local_utc


def recording(root, key):
    events = [
        NormalizedEvent(
            "session",
            "2026-09-05T14:00:00Z",
            "synthetic",
            {
                "key": key,
                "name": "Qualifying",
                "session_kind": "qualifying",
                "started_at": "2026-09-05T14:00:00Z",
                "status": "RUNNING",
            },
        )
    ]
    events += [
        NormalizedEvent(
            "timing",
            f"2026-09-05T14:{i // 60:02}:{i % 60:02}Z",
            "synthetic",
            {"number": "44", "lap": i},
        )
        for i in range(1, 1100)
    ]
    (root / f"live-{key}.json").write_text(json.dumps([asdict(e) for e in events]))
    return events


def test_coalesced_load_prepare_private_cursors_and_monitor_cache(tmp_path):
    recording(tmp_path, "100")
    library = ReplayLibrary(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        resources = list(pool.map(lambda _: library.get("100"), range(4)))
        list(pool.map(lambda resource: resource.prepare(), resources))
    assert len({id(resource) for resource in resources}) == 1
    assert library.loads == 1
    first, second = resources[0].controller(), resources[0].controller()
    first.seek_cursor(1099)
    second.seek_cursor(512)
    assert first.state.drivers["44"].lap == 1098
    assert second.state.drivers["44"].lap == 511
    for _ in range(20):
        library.seed_events("100")
        library.catalog()
    assert library.get("100") is resources[0]
    assert library.loads == 1


def test_pinned_resources_obey_budget_and_release_allows_retry(tmp_path):
    for key in ("100", "200", "300"):
        recording(tmp_path, key)
    library = ReplayLibrary(tmp_path, cache_entries=2, cache_bytes=100 * 1024**2)
    first, second = library.acquire("100"), library.acquire("200")
    with pytest.raises(ReplayBusyError):
        library.get("300")
    assert library.get("100") is first
    library.release(second)
    third = library.get("300")
    assert third.descriptor.key == "300"
    assert library.get("100") is first
    assert library.diagnostics["reservedBytes"] <= 100 * 1024**2
    library.release(first)


def test_legacy_partial_final_file_recovers_without_modifying_original(tmp_path):
    events = recording(tmp_path, "100")
    path = tmp_path / "live-100.json"
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    recorder = NormalizedLiveRecorder(tmp_path, "100")
    assert len(recorder.events) == len(events)
    extra = NormalizedEvent(
        "timing", "2026-09-05T14:30:00Z", "synthetic", {"number": "44", "lap": 1101}
    )
    recorder.append((events[-1], extra))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original
    restarted = NormalizedLiveRecorder(tmp_path, "100")
    assert len(restarted.events) == len(events) + 1
    assert restarted.events[-1].payload["lap"] == 1101


@pytest.mark.parametrize(
    ("local", "offset", "expected"),
    [
        ("2026-09-05T16:00:00", "02:00:00", "2026-09-05T14:00:00Z"),
        ("2026-09-05T08:30:00", "-05:30:00", "2026-09-05T14:00:00Z"),
        ("2026-09-05T19:45:00", "+05:45:00", "2026-09-05T14:00:00Z"),
        ("2026-09-05T14:00:00Z", "02:00:00", "2026-09-05T14:00:00Z"),
    ],
)
def test_source_offsets_are_applied_exactly_once(local, offset, expected):
    assert source_local_utc(local, offset) == expected


def test_early_finish_overrun_and_qualifying_segment_completion():
    def event(at, **payload):
        return NormalizedEvent("session", at, "synthetic", payload)

    events = [
        event(
            "2026-09-05T14:00:00Z",
            session_kind="qualifying",
            qualifying_phase="Q1",
            ended_at="2026-09-05T14:10:00Z",
        ),
        event("2026-09-05T14:18:00Z", status="FINISHED"),
        event("2026-09-05T14:25:00Z", status="RUNNING", qualifying_phase="Q2"),
    ]
    assert not session_completion(events).complete
    shortened = events + [
        event("2026-09-05T14:27:00Z", status="FINISHED", session_complete=True)
    ]
    assert session_completion(shortened).complete
    race = [
        event(
            "2026-09-05T14:00:00Z", session_kind="race", ended_at="2026-09-05T16:00:00Z"
        ),
        event("2026-09-05T14:25:00Z", status="FINISHED"),
    ]
    assert session_completion(race).complete
    assert not session_completion(
        race + [event("2026-09-05T16:01:00Z", status="RUNNING")]
    ).complete
