"""Optional external strategy-intelligence boundary; disabled by default."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

EXTERNAL_INTELLIGENCE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ExternalStrategyItem:
    source: str
    title: str
    summary: str
    published_at: str | None
    retrieved_at: str
    evidence_cutoff: str
    source_class: str
    trust_level: str
    observations: tuple[str, ...] = ()


class ExternalIntelligenceProvider(Protocol):
    def collect(self, *, meeting_key: str, evidence_cutoff: str) -> tuple[ExternalStrategyItem, ...]: ...


def disabled_external_intelligence() -> dict[str, object]:
    return {
        "schema_version": EXTERNAL_INTELLIGENCE_SCHEMA_VERSION,
        "status": "disabled",
        "provider": None,
        "items": [],
    }


def serialize_external_items(items: tuple[ExternalStrategyItem, ...]) -> list[dict[str, object]]:
    return [asdict(item) for item in items]
