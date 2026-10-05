"""Private live-viewer transport state; never authors sporting facts."""

from __future__ import annotations

from datetime import datetime, timedelta
from math import isfinite

MAX_LIVE_DELAY = 300.0


class LiveViewer:
    """Follow the authoritative source edge, or hold one private source cursor."""

    def __init__(self, delay: float = 0, paused_at: datetime | None = None):
        self.requested_delay = self.validate_delay(delay)
        self.cursor = paused_at
        self.paused = paused_at is not None
        self.delay = 0.0
        self.available_delay = 0.0
        self.generation = 0
        self.notice: str | None = None
        self._stale = False
        self._edge: datetime | None = None

    @staticmethod
    def validate_delay(value: float) -> float:
        if not isfinite(value) or not 0 <= value <= MAX_LIVE_DELAY:
            raise ValueError("live delay must be between 0 and 300 seconds")
        return value

    def update(
        self, edge: datetime | None, earliest: datetime | None, *, stale: bool = False,
        tail_elapsed: timedelta = timedelta(),
    ) -> datetime | None:
        if edge is None or earliest is None:
            return self.cursor
        # Only a completed/retained tail drains by elapsed time. An active source
        # never advances because a browser frame or server wall-clock tick ran.
        source_edge = edge + max(tail_elapsed, timedelta())
        if stale and self._edge is not None:
            source_edge = self._edge
        if self._stale and not stale:
            self.generation += 1
        self._stale = stale
        self._edge = source_edge
        self.available_delay = min(MAX_LIVE_DELAY, max(0, (source_edge - earliest).total_seconds()))
        lower = max(earliest, source_edge - timedelta(seconds=MAX_LIVE_DELAY))
        # Finalized source tails cannot create a cursor beyond their last fact.
        lower = min(lower, edge)
        if self.paused and self.cursor is not None:
            accrued = max(0, (source_edge - self.cursor).total_seconds())
            self.requested_delay = min(MAX_LIVE_DELAY, accrued)
            if accrued >= MAX_LIVE_DELAY:
                self.paused = False
                self.generation += 1
                self.notice = "Playback resumed: the 5:00 live delay limit was reached."
        if not self.paused:
            self.cursor = min(edge, max(lower, source_edge - timedelta(seconds=self.requested_delay)))
        elif self.cursor is not None:
            self.cursor = min(edge, max(lower, self.cursor))
        self.delay = min(MAX_LIVE_DELAY, max(0, (source_edge - self.cursor).total_seconds()))
        return self.cursor

    def pause(self) -> None:
        if self.cursor is not None:
            self.paused = True
            self.notice = None

    def play(self) -> None:
        if self.paused:
            self.requested_delay = self.delay
        self.paused = False
        self.notice = None

    def set_delay(self, seconds: float) -> None:
        self.requested_delay = self.validate_delay(seconds)
        self.paused = False
        self.notice = None
        self.generation += 1

    def payload(self) -> dict:
        return {
            "delaySeconds": self.delay,
            "requestedDelaySeconds": self.requested_delay,
            "availableDelaySeconds": self.available_delay,
            "paused": self.paused,
            "edgeTime": self._edge.isoformat() if self._edge else None,
            "navigationGeneration": self.generation,
            "notice": self.notice,
        }
