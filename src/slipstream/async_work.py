"""Cancellation boundaries for operations whose side effects must finish."""

import asyncio
from contextlib import suppress


async def finish_owned(task: asyncio.Task):
    """Propagate cancellation only after the owned operation can no longer act."""
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            with suppress(asyncio.CancelledError, Exception):
                await asyncio.shield(task)
        if not task.cancelled():
            task.exception()
        raise
