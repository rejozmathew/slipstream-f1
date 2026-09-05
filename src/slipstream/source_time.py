"""Explicit UTC conversion for source-local session boundaries."""

from datetime import UTC, datetime, timedelta, timezone
from functools import lru_cache


@lru_cache(maxsize=64)
def source_timezone(offset: str) -> timezone:
    sign = -1 if offset.startswith("-") else 1
    parts = offset.lstrip("+-").split(":")
    if len(parts) not in {2, 3}:
        raise ValueError("source offset must be HH:MM or HH:MM:SS")
    hours, minutes = int(parts[0]), int(parts[1])
    seconds = int(parts[2]) if len(parts) == 3 else 0
    if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
        raise ValueError("invalid source UTC offset")
    return timezone(sign * timedelta(hours=hours, minutes=minutes, seconds=seconds))


def source_local_utc(value: str, offset: str | None) -> str:
    """Apply a supplied offset only to naive source-local identity values.

    An aware value already identifies an instant. Preserve its representation
    for compatibility; event timestamps themselves do not use this function.
    An ambiguous local value without an offset fails closed.
    """
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        return value
    if not offset:
        raise ValueError("source-local session boundary has no UTC offset")
    return (
        parsed.replace(tzinfo=source_timezone(offset))
        .astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def session_boundaries(payload: dict) -> dict:
    """Copy and correct F1 identity boundaries without changing evidence files."""
    result = dict(payload)
    for key in ("started_at", "ended_at"):
        value = result.get(key)
        if isinstance(value, str) and value:
            try:
                result[key] = source_local_utc(value, result.get("gmt_offset"))
            except ValueError:
                # Do not overwrite a known UTC seed with ambiguous source data.
                result.pop(key, None)
    return result
