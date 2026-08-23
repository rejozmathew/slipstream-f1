"""Source-neutral events accepted by the RaceState reducer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

EventKind = Literal["session", "circuit", "driver", "timing", "weather", "race_control"]


def parse_timestamp(value: str) -> datetime:
    """Parse an event timestamp as an aware UTC datetime.

    Canonical events include an explicit offset. Some upstream fields that are
    explicitly documented as UTC omit the suffix, and older live recordings
    may therefore contain a naive value. Treat those legacy values as UTC so a
    recovered session can be ordered with canonical events.
    """
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class NormalizedEvent:
    kind: EventKind
    occurred_at: str
    source: str
    payload: dict[str, Any]
    received_at: str | None = None

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> NormalizedEvent:
        missing = {"kind", "occurred_at", "source", "payload"} - raw.keys()
        if missing:
            raise ValueError(
                f"Replay event missing fields: {', '.join(sorted(missing))}"
            )
        return cls(
            kind=raw["kind"],
            occurred_at=raw["occurred_at"],
            source=raw["source"],
            payload=raw["payload"],
            received_at=raw.get("received_at"),
        )
