"""Clocked, seekable replay over normalized events."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from datetime import timedelta

from .events import NormalizedEvent, parse_timestamp
from .state import RaceState

PlaybackCallback = Callable[[RaceState], None]


class ReplayController:
    """Own replay cursor, state, clock speed, pause, and seek behavior."""

    def __init__(
        self,
        events: Iterable[NormalizedEvent],
        *,
        sleep: Callable[[float], None] = time.sleep,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> None:
        self.events = sorted(
            events, key=lambda event: parse_timestamp(event.occurred_at)
        )
        self._sleep = sleep
        self.state = RaceState()
        self.cursor = 0
        self.playhead: str | None = None
        self.is_playing = False
        self.start_time = start_time or (
            self.events[0].occurred_at if self.events else None
        )
        self.end_time = end_time or (
            self.events[-1].occurred_at if self.events else None
        )

    @property
    def finished(self) -> bool:
        if self.cursor >= len(self.events):
            return True
        return bool(
            self.end_time
            and self.playhead
            and parse_timestamp(self.playhead) >= parse_timestamp(self.end_time)
        )

    def reset(self) -> RaceState:
        self.pause()
        self.state = RaceState()
        self.cursor = 0
        self.playhead = None
        return self.state

    def start(self) -> RaceState:
        """Reconstruct state at the official session start boundary."""
        if self.start_time is None:
            return self.reset()
        return self.seek(self.start_time)

    def seek(self, timestamp: str) -> RaceState:
        """Reset and reconstruct state through an inclusive session timestamp."""
        target = parse_timestamp(timestamp)
        self.reset()
        while self.cursor < len(self.events):
            event = self.events[self.cursor]
            if parse_timestamp(event.occurred_at) > target:
                break
            self._apply_next()
        self.playhead = timestamp
        return self.state

    def seek_cursor(self, cursor: int) -> RaceState:
        """Reset and reconstruct state through an event-count cursor."""
        if cursor < 0 or cursor > len(self.events):
            raise ValueError(f"cursor must be between 0 and {len(self.events)}")
        self.reset()
        while self.cursor < cursor:
            self._apply_next()
        return self.state

    def seek_delay(self, seconds: float) -> RaceState:
        """Seek to a point a number of seconds behind the newest event."""
        if seconds < 0:
            raise ValueError("delay must be zero or greater")
        if not self.events:
            return self.reset()
        target = parse_timestamp(self.events[-1].occurred_at) - timedelta(
            seconds=seconds
        )
        return self.seek(target.isoformat())

    def seek_relative(self, seconds: float) -> RaceState:
        """Seek by source-clock seconds from the current playhead."""
        if not self.events:
            return self.reset()
        current = parse_timestamp(self.playhead or self.events[0].occurred_at)
        start = parse_timestamp(self.start_time or self.events[0].occurred_at)
        end = parse_timestamp(self.end_time or self.events[-1].occurred_at)
        target = min(max(current + timedelta(seconds=seconds), start), end)
        return self.seek(target.isoformat())

    def advance(self, seconds: float) -> RaceState:
        """Advance the playhead without emitting every event as a snapshot."""
        if seconds < 0:
            return self.seek_relative(seconds)
        if not self.events or self.finished:
            return self.state
        current = parse_timestamp(self.playhead or self.events[0].occurred_at)
        end = parse_timestamp(self.end_time or self.events[-1].occurred_at)
        target = min(current + timedelta(seconds=seconds), end)
        while self.cursor < len(self.events):
            event = self.events[self.cursor]
            if parse_timestamp(event.occurred_at) > target:
                break
            self._apply_next()
        self.playhead = target.isoformat()
        return self.state

    def step(self) -> RaceState | None:
        """Apply exactly one event without waiting."""
        if self.finished:
            return None
        return self._apply_next()

    def play(
        self, *, speed: float = 1.0, on_state: PlaybackCallback | None = None
    ) -> RaceState:
        """Play from the current cursor until paused or exhausted."""
        if speed <= 0:
            raise ValueError("speed must be greater than zero")
        self.is_playing = True
        while self.is_playing and not self.finished:
            event = self.events[self.cursor]
            if self.playhead is not None:
                delay = (
                    parse_timestamp(event.occurred_at) - parse_timestamp(self.playhead)
                ).total_seconds()
                if delay > 0:
                    self._sleep(delay / speed)
            state = self._apply_next()
            if on_state is not None:
                on_state(state)
        self.is_playing = False
        return self.state

    def pause(self) -> None:
        self.is_playing = False

    def _apply_next(self) -> RaceState:
        event = self.events[self.cursor]
        self.state = self.state.apply(event)
        self.cursor += 1
        self.playhead = event.occurred_at
        return self.state
