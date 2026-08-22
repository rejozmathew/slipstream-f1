"""Fail-closed resolution from Pirelli row labels to weekend driver identity."""

from __future__ import annotations

import re
import unicodedata

from .contracts import (
    DriverResolution,
    ExtractionIssue,
    ExtractionStatus,
    WeekendDriverIdentity,
)


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def resolve_driver(
    source_name: str,
    weekend_drivers: tuple[WeekendDriverIdentity, ...],
    *,
    source_number: str | None = None,
    source_code: str | None = None,
) -> DriverResolution:
    """Resolve only exact normalized identifiers/aliases; never fuzzy-match."""

    candidates: list[WeekendDriverIdentity] = []
    for driver in weekend_drivers:
        exact = False
        if source_number and source_number.strip().lstrip("#") == driver.driver_number:
            exact = True
        if source_code and source_code.strip().casefold() == driver.driver_code.casefold():
            exact = True
        source_norm = _norm(source_name)
        names = (driver.full_name, driver.driver_code, driver.driver_number, *driver.aliases)
        if source_norm and source_norm in {_norm(item) for item in names if item}:
            exact = True
        if exact:
            candidates.append(driver)

    unique = {item.driver_number: item for item in candidates}
    if len(unique) == 1:
        driver = next(iter(unique.values()))
        return DriverResolution(
            status=ExtractionStatus.ACCEPTED,
            source_name=source_name,
            driver_number=driver.driver_number,
            driver_code=driver.driver_code,
        )
    if len(unique) > 1:
        return DriverResolution(
            status=ExtractionStatus.NEEDS_REVIEW,
            source_name=source_name,
            issue=ExtractionIssue(
                "driver_resolution_ambiguous",
                f"{source_name!r} matched multiple weekend drivers",
            ),
        )
    return DriverResolution(
        status=ExtractionStatus.UNKNOWN,
        source_name=source_name,
        issue=ExtractionIssue(
            "driver_resolution_unknown",
            f"{source_name!r} did not exactly resolve to a weekend driver",
        ),
    )
