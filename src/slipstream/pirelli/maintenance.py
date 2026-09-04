"""Maintainer-only Pirelli archive repair and seed refresh workflows."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .archive import PirelliArchive, has_normalizer_release, list_normalized_releases
from .backfill import PirelliBackfillReport, sync_pirelli_backfill
from .config import NORMALIZER_VERSION
from .coordinator import build_ingestion_target
from .ingest import PirelliIngestionService
from .metadata import (
    metadata_descriptors,
    metadata_path,
    read_pirelli_metadata,
    sync_pirelli_metadata,
)
from .seed import PirelliSeedReport, build_pirelli_seed


@dataclass(frozen=True)
class PirelliRenormalizeItem:
    meeting_key: str
    meeting_name: str
    year: int
    status: str
    releases_written: int
    current_release_count: int
    issue: str | None = None


@dataclass(frozen=True)
class PirelliRenormalizeReport:
    normalizer_version: str
    years: tuple[int, ...]
    items: tuple[PirelliRenormalizeItem, ...]

    @property
    def releases_written(self) -> int:
        return sum(item.releases_written for item in self.items)


@dataclass(frozen=True)
class PirelliSeedRefreshReport:
    from_year: int
    through_year: int
    renormalized: PirelliRenormalizeReport
    backfill: PirelliBackfillReport
    seed: PirelliSeedReport


async def renormalize_pirelli(
    data_root: Path,
    *,
    years: tuple[int, ...],
    meeting_keys: tuple[str, ...] = (),
    metadata: dict[str, Any] | None = None,
    service: PirelliIngestionService | None = None,
) -> PirelliRenormalizeReport:
    """Upgrade immutable archived sources without performing network acquisition."""

    selected_years = tuple(sorted({int(year) for year in years}))
    if not selected_years:
        raise ValueError("at least one Pirelli re-normalization season is required")
    selected_meetings = {str(value) for value in meeting_keys}
    payload = metadata if metadata is not None else read_pirelli_metadata(
        metadata_path(data_root)
    )
    descriptors = tuple(
        item
        for item in metadata_descriptors(payload)
        if item.session_kind == "race"
        and item.year in selected_years
        and (not selected_meetings or item.meeting_key in selected_meetings)
    )
    if selected_meetings:
        found = {item.meeting_key for item in descriptors}
        missing = selected_meetings - found
        if missing:
            raise ValueError(
                "Pirelli metadata is missing requested meeting(s): "
                + ", ".join(sorted(missing))
            )

    archive = PirelliArchive(data_root)
    ingestion = service or PirelliIngestionService(archive)
    by_meeting: dict[str, object] = {}
    for descriptor in descriptors:
        by_meeting[descriptor.meeting_key] = descriptor
    inventory = metadata_descriptors(payload)
    items: list[PirelliRenormalizeItem] = []
    for meeting_key, descriptor in sorted(
        by_meeting.items(), key=lambda item: item[1].date_start
    ):
        meeting_inventory = sorted(
            (
                item
                for item in inventory
                if item.meeting_key == meeting_key
            ),
            key=lambda item: item.date_start,
        )
        target = build_ingestion_target(
            meeting_key, descriptor, meeting_inventory, None
        )
        report = await ingestion.renormalize_archived(target)
        current = tuple(
            release
            for release in list_normalized_releases(archive, meeting_key)
            if release.normalizer_version == NORMALIZER_VERSION
        )
        issue = "; ".join(report.issues) if report.issues else None
        status = (
            "UPDATED"
            if report.normalized_release_ids
            else "CURRENT"
            if has_normalizer_release(archive, meeting_key, NORMALIZER_VERSION)
            else "UNAVAILABLE"
        )
        items.append(
            PirelliRenormalizeItem(
                meeting_key,
                str(descriptor.meeting_name),
                int(descriptor.year),
                status,
                len(report.normalized_release_ids),
                len(current),
                issue,
            )
        )
    return PirelliRenormalizeReport(
        NORMALIZER_VERSION, selected_years, tuple(items)
    )


async def refresh_pirelli_seed(
    data_root: Path,
    *,
    from_year: int,
    through_year: int,
    output: Path,
    now: datetime | None = None,
    metadata_sync: Any = sync_pirelli_metadata,
    service: PirelliIngestionService | None = None,
) -> PirelliSeedRefreshReport:
    """Refresh metadata, repair archives, backfill gaps, and build a release seed."""

    if from_year > through_year:
        raise ValueError("Pirelli seed from-year must not exceed through-year")
    years = tuple(range(from_year, through_year + 1))
    clock = (now or datetime.now(UTC)).astimezone(UTC)
    metadata = await asyncio.to_thread(
        metadata_sync, metadata_path(data_root), years, now=clock
    )
    archive = PirelliArchive(data_root)
    ingestion = service or PirelliIngestionService(archive)
    renormalized = await renormalize_pirelli(
        data_root,
        years=years,
        metadata=metadata,
        service=ingestion,
    )
    descriptors = metadata_descriptors(metadata)
    backfill = await sync_pirelli_backfill(
        data_root,
        years=years,
        now=clock,
        library=_MetadataLibrary(descriptors),
        service=ingestion,
    )
    seed = build_pirelli_seed(
        data_root,
        from_year=from_year,
        through_year=through_year,
        output=output,
        require_nonempty=True,
    )
    return PirelliSeedRefreshReport(
        from_year, through_year, renormalized, backfill, seed
    )


def format_renormalize_report(report: PirelliRenormalizeReport) -> str:
    lines = [
        f"Pirelli normalizer: {report.normalizer_version}",
        f"Seasons: {', '.join(str(year) for year in report.years)}",
        f"Releases written: {report.releases_written}",
    ]
    for item in report.items:
        suffix = f" · {item.issue}" if item.issue else ""
        lines.append(
            f"[{item.status}] {item.year} {item.meeting_name} "
            f"(meeting {item.meeting_key}, current releases "
            f"{item.current_release_count}){suffix}"
        )
    return "\n".join(lines)


def format_seed_refresh_report(report: PirelliSeedRefreshReport) -> str:
    return "\n".join(
        (
            format_renormalize_report(report.renormalized),
            f"Backfill attempted: {report.backfill.meetings_attempted}",
            f"Backfill PRESENT: {report.backfill.count('PRESENT')}",
            f"Seed: {report.seed.meetings} meetings / {report.seed.releases} releases",
            f"Coverage: {report.from_year}-{report.through_year}",
            f"Bytes: {report.seed.bytes_written}",
            f"SHA256: {report.seed.digest}",
        )
    )


class _MetadataLibrary:
    metadata_only = True

    def __init__(self, descriptors: tuple[object, ...]) -> None:
        self.descriptors = {str(item.key): item for item in descriptors}

    def get(self, _key: str) -> None:
        return None
