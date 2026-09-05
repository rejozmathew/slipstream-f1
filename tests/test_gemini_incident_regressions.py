"""Baseline regression tests for incident handling and playback invariants in Slipstream.

Isolation & scope:
- Targeted for: tests/test_gemini_incident_regressions.py
- Baseline revision: d72ddd6652f1e2f6d13c8949c253d2944b2eac1a
- Authored from requirements and evidence in .codex-tmp/evidence/live-11357.json.
- No production edits; candidate code behavior tested strictly against requirements.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC
from pathlib import Path
from typing import Any

from slipstream.events import NormalizedEvent, parse_timestamp
from slipstream.live import PublicLiveSession
from slipstream.playback import ReplayController
from slipstream.replay import replay


def _create_synthetic_event(
    kind: str,
    occurred_at: str,
    payload: dict[str, Any],
    *,
    source: str = "SYNTHETIC",
    received_at: str | None = None,
) -> NormalizedEvent:
    """Helper creating synthetic events marked clearly as SYNTHETIC."""
    return NormalizedEvent(
        kind=kind,  # type: ignore[arg-type]
        occurred_at=occurred_at,
        source=source,
        payload=payload,
        received_at=received_at,
    )


# ---------------------------------------------------------------------------
# Test 2: In-session phase transition (Q1 FINISHED vs Q2 RUNNING) handling
# ---------------------------------------------------------------------------
def test_qualifying_catchup_during_q2_does_not_finalize_session(tmp_path: Path):
    """During Q2 catch-up, an older Q1 FINISHED must not complete/finalize overall Qualifying."""

    async def forever_source() -> AsyncIterator[dict[str, Any]]:
        while True:
            await asyncio.sleep(3600)
            yield {}

    async def scenario():
        session = PublicLiveSession(
            row_source=forever_source,
            normalized_recording_dir=tmp_path,
            finalization_drain=0.0,
        )
        await session.start("11357")
        try:
            # Sequence simulating batch catch-up at receipt 14:28:53:
            # Contains older Q1 FINISHED (14:18:00), then Q2 SCHEDULED (14:24:04),
            # Q2 RUNNING (14:25:00), session RUNNING (14:28:53), and Q2 timing.
            synthetic_batch = [
                _create_synthetic_event(
                    "session",
                    "2026-09-05T14:18:00.071000Z",
                    {"status": "FINISHED", "qualifying_phase": "Q1"},
                    received_at="2026-09-05T14:28:53.183684Z",
                ),
                _create_synthetic_event(
                    "race_control",
                    "2026-09-05T14:18:00Z",
                    {
                        "category": "Flag",
                        "message": "CHEQUERED FLAG",
                        "flag": "CHEQUERED",
                        "scope": "Track",
                    },
                    received_at="2026-09-05T14:28:53.183684Z",
                ),
                _create_synthetic_event(
                    "session",
                    "2026-09-05T14:24:04.538000Z",
                    {"status": "SCHEDULED", "qualifying_phase": "Q2"},
                    received_at="2026-09-05T14:28:53.183684Z",
                ),
                _create_synthetic_event(
                    "session",
                    "2026-09-05T14:25:00.073000Z",
                    {"status": "RUNNING", "qualifying_phase": "Q2"},
                    received_at="2026-09-05T14:28:53.183684Z",
                ),
                _create_synthetic_event(
                    "session",
                    "2026-09-05T14:28:53.183684Z",
                    {
                        "key": "11357",
                        "name": "Qualifying",
                        "session_type": "Qualifying",
                        "session_kind": "qualifying",
                        "status": "RUNNING",
                        "qualifying_phase": "Q2",
                    },
                    received_at="2026-09-05T14:28:53.183684Z",
                ),
                _create_synthetic_event(
                    "timing",
                    "2026-09-05T14:28:53.276Z",
                    {
                        "number": "30",
                        "position": 2,
                        "lap": 12,
                        "best_lap": "1:22.828",
                        "qualifying_phase_reached": "Q2",
                    },
                    received_at="2026-09-05T14:28:53.276Z",
                ),
            ]

            session._apply(synthetic_batch, received_at="2026-09-05T14:28:53.276Z")

            # The session must remain LIVE / not finalized because the latest chronological
            # status is RUNNING in Q2, even though an older Q1 FINISHED arrived in the same catchup batch.
            view = session.view("11357")
            assert view.phase != "FINALIZING", (
                f"Session entered {view.phase} despite subsequent RUNNING status in Q2"
            )
            assert not session._completion_observed, (
                "Completion must not be triggered by a superseded FINISHED event from Q1"
            )

            # Verify timing data continues to be accepted after catchup
            late_timing = [
                _create_synthetic_event(
                    "timing",
                    "2026-09-05T14:29:00.000Z",
                    {"number": "63", "position": 1, "lap": 13, "best_lap": "1:22.500"},
                    received_at="2026-09-05T14:29:00.000Z",
                )
            ]
            accepted = session._apply(
                late_timing, received_at="2026-09-05T14:29:00.000Z"
            )
            assert accepted is True
            assert "63" in session.state.drivers
            assert session.state.drivers["63"].best_lap == "1:22.500"
        finally:
            await session.stop()

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# Test 3: Genuine Q3 completion not reopened by older source-time RUNNING
# ---------------------------------------------------------------------------
def test_genuine_q3_completion_not_reopened_by_older_source_time_running(
    tmp_path: Path,
):
    """Genuine Q3 completion must not be reopened by older source-time RUNNING events arriving late."""

    async def forever_source() -> AsyncIterator[dict[str, Any]]:
        while True:
            await asyncio.sleep(3600)
            yield {}

    async def scenario():
        session = PublicLiveSession(
            row_source=forever_source,
            normalized_recording_dir=tmp_path,
            finalization_drain=0.0,
        )
        await session.start("11357")
        try:
            # Feed genuine Q3 completion at 15:05:00 UTC
            final_events = [
                _create_synthetic_event(
                    "session",
                    "2026-09-05T15:05:00.000Z",
                    {
                        "key": "11357",
                        "status": "FINISHED",
                        "name": "Qualifying",
                        "session_kind": "qualifying",
                        "qualifying_phase": "Q3",
                    },
                    received_at="2026-09-05T15:05:01.000Z",
                )
            ]
            session._apply(final_events, received_at="2026-09-05T15:05:01.000Z")
            assert session._completion_observed is True

            # Inject delayed history with older occurred_at timestamp RUNNING
            stale_running_event = [
                _create_synthetic_event(
                    "session",
                    "2026-09-05T14:50:00.000Z",  # Older source time (Q2 era)
                    {"status": "RUNNING", "qualifying_phase": "Q2"},
                    received_at="2026-09-05T15:06:00.000Z",  # Delivered late
                )
            ]
            session._apply(stale_running_event, received_at="2026-09-05T15:06:00.000Z")

            # Chronologically, FINISHED (15:05:00) remains the terminal status;
            # the session must remain completed and not reopened to RUNNING.
            assert session._completion_observed is True
            assert session.state.session.status == "FINISHED"
        finally:
            await session.stop()

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# Test 4: Chronological UTC stable ordering and source local session boundary
# ---------------------------------------------------------------------------
def test_chronological_utc_stable_ordering_and_session_boundary_resolution():
    """Verify chronological UTC stable ordering before event_limit and source local boundary resolution."""
    # Requirement: Source local session boundary 16:00 with +02:00 must resolve 14 UTC
    t_local = "2026-09-05T16:00:00+02:00"
    dt = parse_timestamp(t_local)
    assert dt.tzinfo is not None
    assert dt.astimezone(UTC).hour == 14
    assert dt.isoformat() == "2026-09-05T14:00:00+00:00"

    # Verify equivalent representations across offsets normalize to the identical aware UTC instant
    t_utc = "2026-09-05T14:00:00Z"
    t_other = "2026-09-05T15:00:00+01:00"
    assert parse_timestamp(t_utc) == dt == parse_timestamp(t_other)

    # Verify chronological UTC stable ordering before event_limit
    # Events out of chronological order in input list:
    e_earlier = _create_synthetic_event(
        "session", "2026-09-05T14:00:00Z", {"status": "SCHEDULED", "circuit": "Monza"}
    )
    e_middle = _create_synthetic_event(
        "session", "2026-09-05T14:05:00Z", {"status": "RUNNING"}
    )
    e_later = _create_synthetic_event(
        "session", "2026-09-05T14:10:00Z", {"status": "FINISHED"}
    )

    # Input list with out-of-order timestamps
    unordered_events = [e_middle, e_earlier, e_later]

    # ReplayController stably sorts events chronologically by UTC instant
    ctrl = ReplayController(unordered_events)
    assert list(ctrl.events) == [e_earlier, e_middle, e_later]

    # Stable tie-breaking: identical UTC instants preserve original encounter order
    e_tie_1 = _create_synthetic_event(
        "session", "2026-09-05T14:00:00Z", {"status": "A"}
    )
    e_tie_2 = _create_synthetic_event(
        "session", "2026-09-05T16:00:00+02:00", {"status": "B"}
    )
    ctrl_tie = ReplayController([e_tie_1, e_tie_2])
    assert [e.payload["status"] for e in ctrl_tie.events] == ["A", "B"]

    # When chronologically ordered, replay with event_limit respects chronological sequence
    state_limit_1 = replay(unordered_events, event_limit=1)
    assert state_limit_1.session.status == "SCHEDULED"

    state_limit_2 = replay(unordered_events, event_limit=2)
    assert state_limit_2.session.status == "RUNNING"


# ---------------------------------------------------------------------------
# Test 5: No future data leaks
# ---------------------------------------------------------------------------
def test_no_future_data_leaks():
    """Reconstructed state at an earlier timestamp or cursor must not contain future data."""
    events = [
        _create_synthetic_event(
            "driver",
            "2026-09-05T14:10:00Z",
            {"number": "44", "code": "HAM", "name": "Lewis HAMILTON"},
        ),
        _create_synthetic_event(
            "timing",
            "2026-09-05T14:10:05Z",
            {"number": "44", "position": 1, "lap": 1, "best_lap": "1:22.847"},
        ),
        _create_synthetic_event(
            "race_control",
            "2026-09-05T14:10:10Z",
            {
                "category": "Flag",
                "message": "GREEN LIGHT - PIT EXIT OPEN",
                "flag": "GREEN",
                "scope": "Track",
            },
        ),
        _create_synthetic_event(
            "driver",
            "2026-09-05T14:20:00Z",
            {"number": "1", "code": "VER", "name": "Max VERSTAPPEN"},
        ),
        _create_synthetic_event(
            "timing",
            "2026-09-05T14:20:05Z",
            {"number": "1", "position": 2, "lap": 5, "best_lap": "1:21.500"},
        ),
        _create_synthetic_event(
            "race_control",
            "2026-09-05T14:20:10Z",
            {
                "category": "Flag",
                "message": "CHEQUERED FLAG",
                "flag": "CHEQUERED",
                "scope": "Track",
            },
        ),
    ]

    # Replay through cutoff 14:15:00 UTC
    state_past = replay(events, at="2026-09-05T14:15:00Z")
    assert "44" in state_past.drivers
    assert state_past.drivers["44"].best_lap == "1:22.847"
    assert state_past.drivers["44"].lap == 1

    # Future driver, timing, and race control must NOT leak into past state
    assert "1" not in state_past.drivers, (
        "Future driver identity leaked into past state"
    )
    assert len(state_past.race_control) == 1
    assert state_past.race_control[0].message == "GREEN LIGHT - PIT EXIT OPEN"

    # Playback seek to 14:15:00 UTC must also strictly exclude future data
    ctrl = ReplayController(events)
    ctrl.seek("2026-09-05T14:15:00Z")
    assert "44" in ctrl.state.drivers
    assert "1" not in ctrl.state.drivers
    assert len(ctrl.state.race_control) == 1
    assert ctrl.state.race_control[0].message == "GREEN LIGHT - PIT EXIT OPEN"

    # Playback seek forward to 14:25:00 UTC incorporates later data cleanly
    ctrl.seek("2026-09-05T14:25:00Z")
    assert "44" in ctrl.state.drivers
    assert "1" in ctrl.state.drivers
    assert ctrl.state.drivers["1"].best_lap == "1:21.500"
    assert len(ctrl.state.race_control) == 2
    assert ctrl.state.race_control[1].message == "CHEQUERED FLAG"
