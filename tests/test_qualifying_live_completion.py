import asyncio

import pytest

from slipstream.events import NormalizedEvent
from slipstream.live import F1LiveAdapter, PublicLiveSession


def event(second, **payload):
    return NormalizedEvent("session", f"2026-10-24T21:00:{second:02d}Z", "test", payload)


@pytest.mark.parametrize("kind,prefix", [("qualifying", "Q"), ("sprint_qualifying", "SQ")])
def test_segment_finishes_keep_recording_until_final_segment(tmp_path, kind, prefix):
    async def run():
        live = PublicLiveSession(normalized_recording_dir=tmp_path, finalization_drain=0)
        live._target_session_key = "11392"
        from slipstream.live_recording import NormalizedLiveRecorder
        live._normalized_recorder = NormalizedLiveRecorder(tmp_path, "11392")
        live._apply([event(0, key="11392", session_kind=kind)], "2026-10-24T21:00:00Z")
        for phase in range(1, 4):
            live._apply([
                event(phase * 10, qualifying_phase=f"{prefix}{phase}", status="RUNNING"),
                event(phase * 10 + 1, status="FINISHED"),
            ], "2026-10-24T21:01:00Z")
            await live._finalize_after_drain()
            assert live.view("11392").replay_ready is (phase == 3)
            assert (tmp_path / "live-11392.json").exists() is (phase == 3)
    asyncio.run(run())


def test_recovered_q1_and_late_finish_do_not_complete_q2():
    live = PublicLiveSession(finalization_drain=0)
    live._restore_recorded_events((
        event(0, session_kind="qualifying", qualifying_phase="Q1"),
        event(10, status="FINISHED"),
    ))
    assert not live._completion_observed
    live._apply([event(20, status="RUNNING", qualifying_phase="Q2")], "2026-10-24T21:00:20Z")
    live._apply([event(11, status="FINISHED")], "2026-10-24T21:00:21Z")
    assert not live._completion_observed


@pytest.mark.parametrize("kind,prefix", [("qualifying", "Q"), ("sprint_qualifying", "SQ")])
def test_next_phase_announcement_does_not_inherit_previous_finished_status(kind, prefix):
    live = PublicLiveSession(finalization_drain=0)
    live._restore_recorded_events((
        event(0, session_kind=kind, qualifying_phase=f"{prefix}2"),
        event(10, status="FINISHED"),
        event(20, qualifying_phase=f"{prefix}3"),
    ))
    assert live.state.session.status == "FINISHED"
    assert not live._completion_observed


@pytest.mark.parametrize("status", ["Ends", "Finalised", "Finalized"])
def test_explicit_whole_session_completion_survives_normalization(status):
    adapter = F1LiveAdapter("11392")
    adapter.ingest({"stream": "SessionInfo", "payload": {"Key": 11392, "Type": "Qualifying", "Name": "Qualifying"},
                    "source_timestamp": "2026-10-24T21:00:00Z", "received_at": "2026-10-24T21:00:00Z"})
    events = adapter.ingest({"stream": "SessionStatus", "payload": {"Status": status},
                             "source_timestamp": "2026-10-24T21:00:00Z",
                             "received_at": "2026-10-24T21:00:00Z"})
    assert any(e.payload.get("session_complete") is True for e in events)
