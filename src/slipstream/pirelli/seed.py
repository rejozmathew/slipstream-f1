"""Deterministic normalized Pirelli seed build, validation, and import."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .archive import (
    NORMALIZED_FORMAT,
    PirelliArchive,
    list_normalized_releases,
    normalized_release_payload,
    release_from_payload,
    save_normalized_release,
)
from .contracts import ArtifactVersion, PirelliRelease, SourceType
from .metadata import metadata_path, read_pirelli_metadata

PIRELLI_SEED_FORMAT = "slipstream.pirelli.seed.v1"
PIRELLI_SEED_NAME = "pirelli-seed-v1.json.gz"
_MAX_SEED_BYTES = 50 * 1024 * 1024
_ARTIFACT_ID = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{16}")


@dataclass(frozen=True)
class PirelliSeedReport:
    digest: str
    from_season: int
    through_season: int
    meetings: int
    releases: int
    bytes_written: int


@dataclass(frozen=True)
class PirelliSeedImportReport:
    digest: str
    meetings: int
    artifacts_imported: int
    releases_imported: int
    releases_preserved: int


def build_pirelli_seed(
    data_root: Path,
    *,
    from_year: int,
    through_year: int,
    output: Path,
) -> PirelliSeedReport:
    if from_year > through_year:
        raise ValueError("Pirelli seed from-year must not exceed through-year")
    archive = PirelliArchive(data_root)
    metadata = read_pirelli_metadata(metadata_path(data_root))
    meeting_metadata = metadata.get("meetings", {})
    if not isinstance(meeting_metadata, dict):
        meeting_metadata = {}

    meetings: list[dict[str, Any]] = []
    release_count = 0
    latest_source_time: datetime | None = None
    if archive.root.exists():
        meeting_roots = sorted(
            (path for path in archive.root.iterdir() if path.is_dir()),
            key=lambda path: path.name,
        )
    else:
        meeting_roots = []
    for root in meeting_roots:
        meeting_key = root.name
        releases = list_normalized_releases(archive, meeting_key)
        if not releases:
            continue
        raw_metadata = meeting_metadata.get(meeting_key, {})
        if not isinstance(raw_metadata, dict):
            raw_metadata = {}
        season = _meeting_season(raw_metadata, releases)
        if season is None or not from_year <= season <= through_year:
            continue
        artifacts = _artifacts_for_releases(archive, meeting_key, releases)
        if artifacts is None:
            raise ValueError(
                f"Pirelli seed source meeting {meeting_key} has incomplete provenance"
            )
        normalized = tuple(_seed_release_payload(release) for release in releases)
        # Round-trip through the runtime normalized contract before distribution.
        for release_payload in normalized:
            release_from_payload(release_payload)
        meeting_name = str(
            raw_metadata.get("meetingName")
            or next(
                (
                    release.applicability.source_meeting_name
                    for release in releases
                    if release.applicability.source_meeting_name
                ),
                "Grand Prix",
            )
        )
        meetings.append(
            {
                "meetingKey": meeting_key,
                "season": season,
                "meetingName": meeting_name,
                "artifacts": [_artifact_payload(item) for item in artifacts],
                "releases": list(normalized),
            }
        )
        release_count += len(normalized)
        for release in releases:
            timestamp = release.published_at or release.modified_at or release.retrieved_at
            if latest_source_time is None or timestamp > latest_source_time:
                latest_source_time = timestamp

    base: dict[str, Any] = {
        "format": PIRELLI_SEED_FORMAT,
        "coverage": {
            "fromSeason": from_year,
            "throughSeason": through_year,
            "throughPublishedAt": (
                latest_source_time.astimezone(UTC).isoformat()
                if latest_source_time is not None
                else None
            ),
        },
        "meetings": sorted(meetings, key=lambda item: item["meetingKey"]),
    }
    encoded_base = _canonical(base)
    digest = hashlib.sha256(encoded_base).hexdigest()
    payload = {**base, "integrity": {"algorithm": "sha256", "digest": digest}}
    compressed = gzip.compress(_canonical(payload) + b"\n", mtime=0)
    validate_pirelli_seed_bytes(compressed)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_bytes(compressed)
    temporary.replace(output)
    return PirelliSeedReport(
        digest,
        from_year,
        through_year,
        len(meetings),
        release_count,
        len(compressed),
    )


def validate_pirelli_seed(path: Path) -> dict[str, Any]:
    return validate_pirelli_seed_bytes(path.read_bytes())


def validate_pirelli_seed_bytes(data: bytes) -> dict[str, Any]:
    if len(data) > _MAX_SEED_BYTES:
        raise ValueError("Pirelli seed exceeds the 50 MiB validation bound")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
            decoded = compressed.read(_MAX_SEED_BYTES + 1)
        if len(decoded) > _MAX_SEED_BYTES:
            raise ValueError("Pirelli seed expands beyond the 50 MiB validation bound")
        payload = json.loads(decoded)
    except (OSError, EOFError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid compressed Pirelli seed: {error}") from error
    if not isinstance(payload, dict) or payload.get("format") != PIRELLI_SEED_FORMAT:
        raise ValueError("unsupported Pirelli seed format")
    integrity = payload.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256":
        raise ValueError("Pirelli seed integrity metadata is missing")
    base = {key: value for key, value in payload.items() if key != "integrity"}
    expected = hashlib.sha256(_canonical(base)).hexdigest()
    if integrity.get("digest") != expected:
        raise ValueError("Pirelli seed integrity check failed")
    coverage = payload.get("coverage")
    if not isinstance(coverage, dict):
        raise ValueError("Pirelli seed coverage is missing")  # noqa: TRY004
    start, end = coverage.get("fromSeason"), coverage.get("throughSeason")
    if not isinstance(start, int) or not isinstance(end, int) or start > end:
        raise ValueError("Pirelli seed coverage bounds are invalid")

    meetings = payload.get("meetings")
    if not isinstance(meetings, list):
        raise ValueError("Pirelli seed meetings must be a list")  # noqa: TRY004
    seen_meetings: set[str] = set()
    for meeting in meetings:
        if not isinstance(meeting, dict):
            raise ValueError("Pirelli seed meeting entry is invalid")  # noqa: TRY004
        meeting_key = str(meeting.get("meetingKey") or "")
        season = meeting.get("season")
        if not meeting_key.isdecimal():
            raise ValueError("Pirelli seed meeting keys must be canonical numeric IDs")
        if meeting_key in seen_meetings:
            raise ValueError("Pirelli seed meeting keys must be unique and non-empty")
        if not isinstance(season, int) or not start <= season <= end:
            raise ValueError("Pirelli seed meeting is outside declared coverage")
        seen_meetings.add(meeting_key)
        artifacts = meeting.get("artifacts")
        releases = meeting.get("releases")
        if not isinstance(artifacts, list) or not isinstance(releases, list):
            raise ValueError("Pirelli seed meeting facts are invalid")  # noqa: TRY004
        if any(not isinstance(item, dict) for item in artifacts):
            raise ValueError("Pirelli seed artifact metadata is invalid")
        artifact_versions = tuple(_artifact_from_payload(item) for item in artifacts)
        artifact_map = {item.artifact_id: item for item in artifact_versions}
        artifact_ids = set(artifact_map)
        if len(artifact_ids) != len(artifacts):
            raise ValueError("Pirelli seed artifact metadata is invalid")
        for raw_release in releases:
            if not isinstance(raw_release, dict) or raw_release.get("format") != NORMALIZED_FORMAT:
                raise ValueError("Pirelli seed normalized release format is invalid")
            release = release_from_payload(raw_release)
            if release.applicability.meeting_key != meeting_key:
                raise ValueError("Pirelli seed release meeting scope does not match")
            parent = artifact_map.get(release.release_id)
            if (
                parent is None
                or parent.source_url != release.source_url
                or parent.content_hash != release.content_hash
            ):
                raise ValueError("Pirelli seed release parent provenance does not match")
            required = set(release.artifact_ids)
            for fact in (
                *release.compound_selections,
                *release.strategies,
                *release.tyre_bank_snapshots,
                *release.context_facts,
            ):
                required.update(evidence.artifact_id for evidence in fact.source_evidence)
            if not required.issubset(artifact_ids):
                raise ValueError("Pirelli seed release provenance is incomplete")
            for fact in (
                *release.compound_selections,
                *release.strategies,
                *release.tyre_bank_snapshots,
                *release.context_facts,
            ):
                if any(
                    artifact_map[evidence.artifact_id].source_url
                    != evidence.source_url
                    for evidence in fact.source_evidence
                ):
                    raise ValueError("Pirelli seed fact provenance URL does not match")
    return payload


def import_pirelli_seed(path: Path, data_root: Path) -> PirelliSeedImportReport:
    return import_pirelli_seed_bytes(path.read_bytes(), data_root)


def import_pirelli_seed_bytes(
    data: bytes, data_root: Path
) -> PirelliSeedImportReport:
    payload = validate_pirelli_seed_bytes(data)
    digest = str(payload["integrity"]["digest"])
    archive = PirelliArchive(data_root)
    artifact_count = 0
    release_count = 0
    preserved = 0
    for meeting in payload["meetings"]:
        meeting_key = str(meeting["meetingKey"])
        for raw_artifact in meeting["artifacts"]:
            artifact = _artifact_from_payload(raw_artifact)
            if archive.get_version(meeting_key, artifact.artifact_id) is None:
                archive.save_artifact_metadata(
                    meeting_key=meeting_key, artifact=artifact
                )
                artifact_count += 1
        existing = list_normalized_releases(archive, meeting_key)
        for raw_release in meeting["releases"]:
            release = release_from_payload(raw_release)
            same_source = [
                item
                for item in existing
                if (item.release_id, item.content_hash)
                == (release.release_id, release.content_hash)
            ]
            if same_source and max(_release_quality(item) for item in same_source) >= _release_quality(release):
                preserved += 1
                continue
            save_normalized_release(
                archive, meeting_key=meeting_key, release=release
            )
            existing = (*existing, release)
            release_count += 1
    marker = data_root / ".slipstream" / "pirelli-seed-imports" / f"{digest}.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    if not marker.exists():
        temporary = marker.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"format": PIRELLI_SEED_FORMAT, "digest": digest},
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(marker)
    return PirelliSeedImportReport(
        digest,
        len(payload["meetings"]),
        artifact_count,
        release_count,
        preserved,
    )


def import_bundled_pirelli_seed(data_root: Path) -> PirelliSeedImportReport:
    seed = resources.files("slipstream").joinpath("data", PIRELLI_SEED_NAME)
    return import_pirelli_seed_bytes(seed.read_bytes(), data_root)


def _meeting_season(
    metadata: dict[str, Any], releases: tuple[PirelliRelease, ...]
) -> int | None:
    value = metadata.get("year")
    if isinstance(value, int):
        return value
    timestamp = next(
        (
            release.published_at or release.modified_at or release.retrieved_at
            for release in releases
        ),
        None,
    )
    return timestamp.year if timestamp is not None else None


def _artifacts_for_releases(
    archive: PirelliArchive,
    meeting_key: str,
    releases: tuple[PirelliRelease, ...],
) -> tuple[ArtifactVersion, ...] | None:
    ids: set[str] = set()
    for release in releases:
        ids.update(release.artifact_ids)
        for fact in (
            *release.compound_selections,
            *release.strategies,
            *release.tyre_bank_snapshots,
            *release.context_facts,
        ):
            ids.update(evidence.artifact_id for evidence in fact.source_evidence)
    artifacts: list[ArtifactVersion] = []
    for artifact_id in sorted(ids):
        artifact = archive.get_version(meeting_key, artifact_id)
        if artifact is None:
            return None
        artifacts.append(artifact)
    return tuple(artifacts)


def _seed_release_payload(release: PirelliRelease) -> dict[str, Any]:
    payload = normalized_release_payload(release)
    return _strip_evidence_text(payload)


def _strip_evidence_text(value: Any) -> Any:
    if isinstance(value, list):
        return [_strip_evidence_text(item) for item in value]
    if not isinstance(value, dict):
        return value
    cleaned = {key: _strip_evidence_text(item) for key, item in value.items()}
    if {"artifact_id", "source_url", "kind", "extraction_method"}.issubset(cleaned):
        for key in ("text", "text_start", "text_end", "region"):
            cleaned.pop(key, None)
    return cleaned


def _artifact_payload(artifact: ArtifactVersion) -> dict[str, Any]:
    return {
        "artifactId": artifact.artifact_id,
        "sourceUrl": artifact.source_url,
        "sourceType": artifact.source_type.value,
        "publishedAt": _iso(artifact.published_at),
        "modifiedAt": _iso(artifact.modified_at),
        "retrievedAt": _iso(artifact.retrieved_at),
        "contentHash": artifact.content_hash,
        "mediaType": artifact.media_type,
        "collectorVersion": artifact.collector_version,
    }


def _artifact_from_payload(raw: dict[str, Any]) -> ArtifactVersion:
    artifact_id = str(raw.get("artifactId") or "")
    if _ARTIFACT_ID.fullmatch(artifact_id) is None:
        raise ValueError("Pirelli seed artifact ID is invalid")
    source_url = str(raw.get("sourceUrl") or "")
    parsed_url = urlparse(source_url)
    host = (parsed_url.hostname or "").casefold()
    if parsed_url.scheme.casefold() != "https":
        raise ValueError("Pirelli seed artifact source must use HTTPS")
    if host != "pirelli.com" and not host.endswith(".pirelli.com") and host != "content.presspage.com":
        raise ValueError("Pirelli seed artifact source is not official")
    retrieved = _parse_dt(raw.get("retrievedAt"))
    if retrieved is None:
        raise ValueError("Pirelli seed artifact retrieval time is missing")
    content_hash = str(raw.get("contentHash") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
        raise ValueError("Pirelli seed artifact content hash is invalid")
    return ArtifactVersion(
        artifact_id=artifact_id,
        source_url=source_url,
        source_type=SourceType(str(raw["sourceType"])),
        published_at=_parse_dt(raw.get("publishedAt")),
        modified_at=_parse_dt(raw.get("modifiedAt")),
        retrieved_at=retrieved,
        content_hash=content_hash,
        media_type=str(raw["mediaType"]) if raw.get("mediaType") else None,
        local_relpath=None,
        collector_version=str(raw.get("collectorVersion") or "seed"),
    )


def _release_quality(release: PirelliRelease) -> tuple[tuple[int, ...], int, datetime]:
    facts = (
        len(release.compound_selections)
        + len(release.strategies)
        + len(release.tyre_bank_snapshots)
        + len(release.context_facts)
    )
    version = tuple(int(part) for part in re.findall(r"\d+", release.normalizer_version))
    return version, facts, release.retrieved_at


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
