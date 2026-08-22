"""Historical-context boundary.

Prior-season evidence is optional, separately labelled context. It is never
silently blended into current-meeting or current-session evidence.
"""

from typing import Any

from .context_types import absent_historical, historical_comparability


def generate_historical_context_spike(
    season: int, circuit_id: str, local_archive_path: str
) -> dict[str, Any]:
    """Return UNAVAILABLE until a compatible archive is actually inspected.

    The legacy spike returned realistic-looking invented distributions. Merely
    receiving a season, circuit and path does not prove that compatible source
    evidence exists, so this boundary fails closed.
    """
    _ = (season, circuit_id, local_archive_path)
    return absent_historical(reason="no_compatible_context_ingested")


__all__ = ["generate_historical_context_spike", "historical_comparability"]
