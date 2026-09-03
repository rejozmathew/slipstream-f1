"""Shared Pirelli history configuration."""

from __future__ import annotations

DEFAULT_PIRELLI_HISTORY_YEARS = 10
NORMALIZER_VERSION = "slipstream-pirelli-v5-adapted.6"


def validate_history_years(value: int) -> int:
    """Return one validated private-history horizon."""

    if value < 1:
        raise ValueError("Pirelli history horizon must be at least one season")
    return value
