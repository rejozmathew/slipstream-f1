"""Regression for completed preparation cleanup starving graceful shutdown."""

import asyncio
import inspect

from slipstream.api import create_app


def test_shutdown_retires_completed_cleanup_without_waiting_for_done_callback(
    tmp_path, monkeypatch
):
    for feature in ("SEED", "REFRESH", "BACKFILL"):
        monkeypatch.setenv(f"SLIPSTREAM_PIRELLI_{feature}", "0")
    app = create_app(tmp_path, public_live=False)
    shutdown = app.router.on_shutdown[0]
    cleanups = inspect.getclosurevars(shutdown).nonlocals["preparation_cleanup"]
    original_gather = asyncio.gather

    async def run():
        cleanup = asyncio.create_task(asyncio.sleep(0))
        await cleanup
        cleanups.add(cleanup)
        # The task finished; its registry-discard callback is queued, not run.
        cleanup.add_done_callback(cleanups.discard)
        waits = 0

        def checked_gather(*tasks, **kwargs):
            nonlocal waits
            if cleanup in tasks:
                waits += 1
                # Fail deterministically rather than wedging pytest's event loop.
                assert waits == 1, (
                    "shutdown spins on completed cleanup before its discard callback can run"
                )
                # Python 3.13 can complete this gather without a loop turn.
                # Exercise that scheduling boundary on older Python versions too.
                if all(task.done() for task in tasks):
                    completed = asyncio.get_running_loop().create_future()
                    completed.set_result([task.result() for task in tasks])
                    return completed
            return original_gather(*tasks, **kwargs)

        monkeypatch.setattr(asyncio, "gather", checked_gather)
        await shutdown()
        assert not cleanups
        assert waits == 1

    asyncio.run(run())


def test_shutdown_waits_for_cleanup_registered_while_draining(tmp_path, monkeypatch):
    for feature in ("SEED", "REFRESH", "BACKFILL"):
        monkeypatch.setenv(f"SLIPSTREAM_PIRELLI_{feature}", "0")
    app = create_app(tmp_path, public_live=False)
    shutdown = app.router.on_shutdown[0]
    cleanups = inspect.getclosurevars(shutdown).nonlocals["preparation_cleanup"]
    original_gather = asyncio.gather

    async def run():
        first_waited = asyncio.Event()
        second_waited = asyncio.Event()
        release_second = asyncio.Event()
        completed = []
        second = None

        async def later_cleanup():
            await release_second.wait()
            completed.append("second")

        async def first_cleanup():
            nonlocal second
            await first_waited.wait()
            second = asyncio.create_task(later_cleanup())
            cleanups.add(second)
            second.add_done_callback(cleanups.discard)
            completed.append("first")

        first = asyncio.create_task(first_cleanup())
        cleanups.add(first)
        first.add_done_callback(cleanups.discard)

        def observe_gather(*tasks, **kwargs):
            if first in tasks:
                first_waited.set()
            if second is not None and second in tasks:
                second_waited.set()
            return original_gather(*tasks, **kwargs)

        monkeypatch.setattr(asyncio, "gather", observe_gather)
        stopping = asyncio.create_task(shutdown())
        try:
            await asyncio.wait_for(second_waited.wait(), timeout=1)
            assert completed == ["first"]
            assert not stopping.done(), "shutdown returned with cleanup still running"
        finally:
            release_second.set()
            await asyncio.wait_for(stopping, timeout=1)
        assert completed == ["first", "second"]
        assert not cleanups

    asyncio.run(run())
