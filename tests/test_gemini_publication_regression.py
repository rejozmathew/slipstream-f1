"""Gemini's permanent-publication reproduction, asserting the repaired contract."""

import asyncio

from slipstream.events import NormalizedEvent
from slipstream.live import PublicLiveSession
from slipstream.live_recording import NormalizedLiveRecorder


def test_failed_publication_releases_drain_and_keeps_retry_error_visible(
    tmp_path, monkeypatch
):
    attempts = []

    def failure(recorder):
        attempts.append(recorder.session_key)
        raise OSError("SYNTHETIC persistent publication failure")

    monkeypatch.setattr(NormalizedLiveRecorder, "finalize", failure)

    async def rows():
        while True:
            await asyncio.sleep(1)
            yield {}

    async def scenario():
        live = PublicLiveSession(
            row_source=rows,
            normalized_recording_dir=tmp_path,
            finalization_drain=0.01,
            maximum_backoff=0.02,
        )
        await live.start(
            "100",
            seed_events=[
                NormalizedEvent(
                    "session",
                    "2026-09-05T13:00:00Z",
                    "synthetic",
                    {
                        "key": "100",
                        "name": "Practice 3",
                        "session_kind": "practice",
                        "status": "FINISHED",
                        "session_complete": True,
                    },
                )
            ],
        )
        try:
            for _ in range(100):
                if live.view("100").error:
                    break
                await asyncio.sleep(0.005)
            assert "retrying" in live.view("100").error
            # Before repair this await exceeded the timeout; no assertion is skipped.
            await asyncio.wait_for(live.finish_pending(), timeout=0.2)
            await live.start(
                "200",
                seed_events=[
                    NormalizedEvent(
                        "session",
                        "2026-09-05T14:00:00Z",
                        "synthetic",
                        {
                            "key": "200",
                            "name": "Qualifying",
                            "session_kind": "qualifying",
                            "status": "RUNNING",
                        },
                    )
                ],
            )
            for _ in range(10):
                old = live.view("100")
                assert old.phase == "FINALIZING"
                assert "retrying" in old.error
                assert not old.replay_ready
                assert live.target_session_key == "200"
                assert live.state.session.key == "200"
                await asyncio.sleep(0.005)
            assert len(attempts) >= 2
        finally:
            await live.stop()

    asyncio.run(scenario())


def test_publication_contexts_are_bounded_and_keep_recoverable_journals(
    tmp_path, monkeypatch
):
    """Gemini-authored bounds scenario, extended to verify recovery and cleanup."""

    def failure(_recorder):
        raise OSError("SYNTHETIC persistent publication failure")

    monkeypatch.setattr(NormalizedLiveRecorder, "finalize", failure)

    async def rows():
        while True:
            await asyncio.sleep(1)
            yield {}

    async def scenario():
        live = PublicLiveSession(
            row_source=rows,
            normalized_recording_dir=tmp_path,
            finalization_drain=0,
            maximum_backoff=0.01,
        )
        tasks = []
        try:
            for key in ("100", "200", "300", "400"):
                await live.start(
                    key,
                    seed_events=[
                        NormalizedEvent(
                            "session",
                            "2026-09-05T14:00:00Z",
                            "synthetic",
                            {
                                "key": key,
                                "name": "Practice 3",
                                "status": "FINISHED",
                                "session_complete": True,
                            },
                        )
                    ],
                )
                await asyncio.wait_for(live.finish_pending(), 0.2)
                tasks.append(live._publications[key].task)
            assert set(live._publications) == {"200", "300", "400"}
            assert len(NormalizedLiveRecorder(tmp_path, "100").events) == 1
        finally:
            await live.stop()
        assert all(task.done() for task in tasks)
        assert all(
            (tmp_path / f"live-{key}.in-progress.jsonl").exists()
            for key in ("100", "200", "300", "400")
        )

    asyncio.run(scenario())
