"""Pirelli evidence package public surface."""

from ..context_types import OfficialPreRaceContext
from .contracts import PirelliRelease, StrategyOption
from .store import PirelliAvailability, PirelliEvidenceStore

__all__ = [
    "PirelliAvailability",
    "PirelliEvidenceStore",
    "PirelliRelease",
    "StrategyOption",
    "acquire_pirelli_context_spike",
]


def acquire_pirelli_context_spike(
    url: str, session_cutoff: str | None = None
) -> OfficialPreRaceContext | None:
    """Compatibility boundary: explicit server ingestion supersedes the old spike."""
    _ = (url, session_cutoff)
    return None
