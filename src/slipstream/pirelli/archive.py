"""Immutable artifact/version archive and derived evidence representations."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import cast

from .contracts import (
    ArtifactVersion,
    Compound,
    CompoundCount,
    CompoundSelection,
    ContextFact,
    DriverTyreBank,
    EvidenceArtifact,
    EvidenceKind,
    ExtractionMethod,
    FactApplicability,
    PirelliRelease,
    PitWindow,
    SessionScope,
    SourceEvidence,
    SourceType,
    StrategyFieldEvidence,
    StrategyOption,
    StrategyOrder,
    StrategyRank,
    TyreBankCoverage,
    TyreBankSnapshot,
)

ARCHIVE_FORMAT = "slipstream.pirelli.archive.v5"
NORMALIZED_FORMAT = "slipstream.pirelli.normalized-release.v5"
TEXT_REPRESENTATION_FORMAT = "slipstream.pirelli.text-representation.v1"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat() if dt else None


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _jsonable(value: object) -> object:
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _jsonable(getattr(value, field.name)) for field in fields(value)
        }
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists():
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(encoded, encoding="utf-8")
    tmp.replace(path)


def _replace_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(encoded, encoding="utf-8")
    tmp.replace(path)


class PirelliArchive:
    """Content-addressed immutable archive beneath `.slipstream/pirelli/<meeting>/`."""

    def __init__(self, data_root: Path) -> None:
        self.root = data_root / ".slipstream" / "pirelli"

    def meeting_root(self, meeting_key: str) -> Path:
        return self.root / str(meeting_key)

    def archive_artifact(
        self,
        *,
        meeting_key: str,
        source_url: str,
        source_type: SourceType,
        body: bytes,
        retrieved_at: datetime,
        published_at: datetime | None,
        modified_at: datetime | None,
        media_type: str | None,
        collector_version: str,
        extension: str,
    ) -> ArtifactVersion:
        content_hash = sha256_bytes(body)
        root = self.meeting_root(meeting_key)
        asset_dir = root / "assets"
        release_dir = root / "releases"
        asset_dir.mkdir(parents=True, exist_ok=True)
        release_dir.mkdir(parents=True, exist_ok=True)

        ext = extension.lstrip(".") or "bin"
        asset_rel = f"assets/{content_hash}.{ext}"
        asset_path = root / asset_rel
        if not asset_path.exists():
            tmp = asset_path.with_suffix(asset_path.suffix + ".tmp")
            tmp.write_bytes(body)
            tmp.replace(asset_path)

        timestamp = (
            (published_at or retrieved_at).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        )
        artifact_id = f"{timestamp}-{content_hash[:16]}"
        metadata = {
            "format": ARCHIVE_FORMAT,
            "artifactId": artifact_id,
            "sourceUrl": source_url,
            "sourceType": source_type.value,
            "publishedAt": _iso(published_at),
            "modifiedAt": _iso(modified_at),
            "retrievedAt": _iso(retrieved_at),
            "contentHash": content_hash,
            "mediaType": media_type,
            "localRelpath": asset_rel,
            "collectorVersion": collector_version,
        }
        metadata_path = release_dir / f"{artifact_id}.json"
        if metadata_path.exists():
            try:
                existing = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = None
            if (
                isinstance(existing, dict)
                and existing.get("contentHash") == content_hash
                and existing.get("sourceUrl") == source_url
                and not existing.get("localRelpath")
            ):
                # A normalized seed intentionally carries provenance without raw
                # bytes. Exact later reacquisition hydrates only its path: replacing
                # its timestamps could erase the original replay-cutoff proof.
                _replace_json(metadata_path, {**existing, "localRelpath": asset_rel})
                hydrated = self.get_version(meeting_key, artifact_id)
                if hydrated is not None:
                    return hydrated
            else:
                _atomic_json(metadata_path, metadata)
        else:
            _atomic_json(metadata_path, metadata)
        return ArtifactVersion(
            artifact_id=artifact_id,
            source_url=source_url,
            source_type=source_type,
            published_at=published_at,
            modified_at=modified_at,
            retrieved_at=retrieved_at,
            content_hash=content_hash,
            media_type=media_type,
            local_relpath=asset_rel,
            collector_version=collector_version,
        )

    def save_artifact_metadata(
        self, *, meeting_key: str, artifact: ArtifactVersion
    ) -> Path:
        """Install provenance-only metadata without copying the source artifact."""

        path = (
            self.meeting_root(meeting_key)
            / "releases"
            / f"{artifact.artifact_id}.json"
        )
        _atomic_json(
            path,
            {
                "format": ARCHIVE_FORMAT,
                "artifactId": artifact.artifact_id,
                "sourceUrl": artifact.source_url,
                "sourceType": artifact.source_type.value,
                "publishedAt": _iso(artifact.published_at),
                "modifiedAt": _iso(artifact.modified_at),
                "retrievedAt": _iso(artifact.retrieved_at),
                "contentHash": artifact.content_hash,
                "mediaType": artifact.media_type,
                "localRelpath": None,
                "collectorVersion": artifact.collector_version,
            },
        )
        return path

    def list_versions(self, meeting_key: str) -> tuple[ArtifactVersion, ...]:
        release_dir = self.meeting_root(meeting_key) / "releases"
        out: list[ArtifactVersion] = []
        if not release_dir.exists():
            return ()
        for path in sorted(release_dir.glob("*.json")):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
                if item.get("format") != ARCHIVE_FORMAT:
                    continue
                out.append(
                    ArtifactVersion(
                        artifact_id=str(item["artifactId"]),
                        source_url=str(item["sourceUrl"]),
                        source_type=SourceType(str(item["sourceType"])),
                        published_at=_parse(item.get("publishedAt")),
                        modified_at=_parse(item.get("modifiedAt")),
                        retrieved_at=_parse(item.get("retrievedAt"))
                        or datetime.min.replace(tzinfo=UTC),
                        content_hash=str(item["contentHash"]),
                        media_type=item.get("mediaType"),
                        local_relpath=item.get("localRelpath"),
                        collector_version=str(
                            item.get("collectorVersion") or "unknown"
                        ),
                    )
                )
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
        return tuple(
            sorted(
                out,
                key=lambda item: (
                    item.published_at or item.retrieved_at,
                    item.artifact_id,
                ),
            )
        )

    def get_version(self, meeting_key: str, artifact_id: str) -> ArtifactVersion | None:
        return next(
            (
                item
                for item in self.list_versions(meeting_key)
                if item.artifact_id == artifact_id
            ),
            None,
        )

    def load_asset_bytes(self, meeting_key: str, artifact_id: str) -> bytes | None:
        artifact = self.get_version(meeting_key, artifact_id)
        if artifact is None or artifact.local_relpath is None:
            return None
        try:
            return (
                self.meeting_root(meeting_key) / artifact.local_relpath
            ).read_bytes()
        except OSError:
            return None

    def save_text_representation(
        self,
        *,
        meeting_key: str,
        artifact_id: str,
        text: str,
        representation_tool: str,
        page_texts: tuple[str, ...] = (),
    ) -> Path:
        """Persist the exact immutable text representation used for extraction/evidence."""
        artifact = self.get_version(meeting_key, artifact_id)
        if artifact is None:
            raise KeyError(f"unknown artifact {artifact_id}")
        payload = {
            "format": TEXT_REPRESENTATION_FORMAT,
            "artifactId": artifact_id,
            "sourceContentHash": artifact.content_hash,
            "representationTool": representation_tool,
            "text": text,
            "pageTexts": list(page_texts),
        }
        digest = sha256_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))[:12]
        path = (
            self.meeting_root(meeting_key)
            / "derived"
            / f"{artifact_id}-text-{digest}.json"
        )
        _atomic_json(path, payload)
        return path

    def load_evidence_artifact(
        self,
        *,
        meeting_key: str,
        artifact_id: str,
        image_dimensions: tuple[int, int] | None = None,
    ) -> EvidenceArtifact | None:
        artifact = self.get_version(meeting_key, artifact_id)
        if artifact is None:
            return None
        candidates = sorted(
            (self.meeting_root(meeting_key) / "derived").glob(
                f"{artifact_id}-text-*.json"
            )
        )
        if candidates:
            try:
                data = json.loads(candidates[-1].read_text(encoding="utf-8"))
                if (
                    data.get("format") == TEXT_REPRESENTATION_FORMAT
                    and data.get("sourceContentHash") == artifact.content_hash
                ):
                    return EvidenceArtifact(
                        artifact_id=artifact_id,
                        text=str(data.get("text") or ""),
                        page_texts=tuple(
                            str(value) for value in data.get("pageTexts", [])
                        ),
                        image_dimensions=image_dimensions,
                    )
            except (OSError, json.JSONDecodeError):
                pass
        return EvidenceArtifact(
            artifact_id=artifact_id, image_dimensions=image_dimensions
        )


def normalized_release_payload(release: PirelliRelease) -> dict[str, object]:
    payload = _jsonable(release)
    if not isinstance(payload, dict):
        raise TypeError("normalized release did not serialize to object")
    return {"format": NORMALIZED_FORMAT, **cast(dict[str, object], payload)}


def save_normalized_release(
    archive: PirelliArchive,
    *,
    meeting_key: str,
    release: PirelliRelease,
) -> Path:
    root = archive.meeting_root(meeting_key)
    payload = normalized_release_payload(release)
    encoded = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    normalized_hash = sha256_bytes(encoded)
    path = root / "normalized" / f"{release.release_id}-{normalized_hash[:12]}.json"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(encoded)
        tmp.replace(path)
    return path


def _ev(raw: dict[str, object]) -> SourceEvidence:
    region_raw = raw.get("region")
    region = (
        tuple(int(x) for x in region_raw)
        if isinstance(region_raw, list) and len(region_raw) == 4
        else None
    )
    return SourceEvidence(
        artifact_id=str(raw["artifact_id"]),
        source_url=str(raw["source_url"]),
        kind=EvidenceKind(str(raw["kind"])),
        extraction_method=ExtractionMethod(str(raw["extraction_method"])),
        page=int(raw["page"]) if isinstance(raw.get("page"), int) else None,
        text=str(raw["text"]) if raw.get("text") is not None else None,
        text_start=int(raw["text_start"])
        if isinstance(raw.get("text_start"), int)
        else None,
        text_end=int(raw["text_end"]) if isinstance(raw.get("text_end"), int) else None,
        region=cast(tuple[int, int, int, int] | None, region),
        model_id=str(raw["model_id"]) if raw.get("model_id") is not None else None,
        confidence=float(raw["confidence"])
        if isinstance(raw.get("confidence"), (int, float))
        else None,
    )


def _app(raw: object) -> FactApplicability:
    if not isinstance(raw, dict):
        return FactApplicability()
    return FactApplicability(
        meeting_key=str(raw["meeting_key"])
        if raw.get("meeting_key") is not None
        else None,
        source_meeting_name=str(raw["source_meeting_name"])
        if raw.get("source_meeting_name") is not None
        else None,
        session_scope=SessionScope(str(raw.get("session_scope", "UNKNOWN"))),
        target_session_key=str(raw["target_session_key"])
        if raw.get("target_session_key") is not None
        else None,
    )


def release_from_payload(raw: dict[str, object]) -> PirelliRelease:
    strategies: list[StrategyOption] = []
    for item_raw in cast(list[object], raw.get("strategies", [])):
        if not isinstance(item_raw, dict):
            continue
        windows = tuple(
            PitWindow(int(w["start_lap"]), int(w["end_lap"]))
            if isinstance(w, dict)
            else None
            for w in cast(list[object], item_raw.get("pit_windows", []))
        )
        source_evidence = tuple(
            _ev(cast(dict[str, object], x))
            for x in cast(list[object], item_raw.get("source_evidence", []))
            if isinstance(x, dict)
        )
        fe_raw = item_raw.get("field_evidence")
        field_evidence = None
        if isinstance(fe_raw, dict):

            def ev_group(
                key: str, raw: dict[object, object] = fe_raw
            ) -> tuple[SourceEvidence, ...]:
                return tuple(
                    _ev(cast(dict[str, object], x))
                    for x in cast(list[object], raw.get(key, []))
                    if isinstance(x, dict)
                )

            pit_groups = tuple(
                tuple(
                    _ev(cast(dict[str, object], x))
                    for x in group
                    if isinstance(x, dict)
                )
                for group in cast(list[list[object]], fe_raw.get("pit_windows", []))
            )
            field_evidence = StrategyFieldEvidence(
                ev_group("sequence"),
                ev_group("rank"),
                pit_groups,
                ev_group("delta"),
                ev_group("conditions"),
            )
        strategies.append(
            StrategyOption(
                id=str(item_raw["id"]),
                rank=StrategyRank(str(item_raw["rank"])),
                stop_count=int(item_raw["stop_count"]),
                compounds=tuple(
                    Compound(str(x)) for x in cast(list[object], item_raw["compounds"])
                ),
                pit_windows=windows,
                order=StrategyOrder(str(item_raw.get("order", "ORDERED"))),
                published_delta_seconds=float(item_raw["published_delta_seconds"])
                if isinstance(item_raw.get("published_delta_seconds"), (int, float))
                else None,
                published_delta_seconds_range=tuple(
                    float(x)
                    for x in cast(
                        list[object], item_raw["published_delta_seconds_range"]
                    )
                )
                if isinstance(item_raw.get("published_delta_seconds_range"), list)
                else None,
                conditions=tuple(
                    str(x) for x in cast(list[object], item_raw.get("conditions", []))
                ),
                caveats=tuple(
                    str(x) for x in cast(list[object], item_raw.get("caveats", []))
                ),
                source_evidence=source_evidence,
                field_evidence=field_evidence,
                applicability=_app(item_raw.get("applicability")),
            )
        )
    selections: list[CompoundSelection] = []
    for item in cast(list[object], raw.get("compound_selections", [])):
        if isinstance(item, dict):
            selections.append(
                CompoundSelection(
                    str(item["hard"]),
                    str(item["medium"]),
                    str(item["soft"]),
                    tuple(
                        _ev(cast(dict[str, object], x))
                        for x in cast(list[object], item.get("source_evidence", []))
                        if isinstance(x, dict)
                    ),
                    _app(item.get("applicability")),
                )
            )
    banks: list[TyreBankSnapshot] = []
    for item in cast(list[object], raw.get("tyre_bank_snapshots", [])):
        if not isinstance(item, dict):
            continue
        drivers: list[DriverTyreBank] = []
        for row in cast(list[object], item.get("drivers", [])):
            if not isinstance(row, dict):
                continue

            def cc(key: str, source_row: dict[object, object] = row) -> CompoundCount:
                value = cast(dict[str, object], source_row[key])
                return CompoundCount(int(value["new"]), int(value["used"]))

            drivers.append(
                DriverTyreBank(
                    str(row["source_driver_name"]),
                    cc("hard"),
                    cc("medium"),
                    cc("soft"),
                    float(row["confidence"]),
                    tuple(
                        _ev(cast(dict[str, object], x))
                        for x in cast(list[object], row.get("source_evidence", []))
                        if isinstance(x, dict)
                    ),
                    str(row["driver_number"])
                    if row.get("driver_number") is not None
                    else None,
                    str(row["driver_code"])
                    if row.get("driver_code") is not None
                    else None,
                )
            )
        banks.append(
            TyreBankSnapshot(
                _parse(cast(str | None, item.get("as_of"))),
                str(item["target_session"])
                if item.get("target_session") is not None
                else None,
                tuple(drivers),
                tuple(
                    _ev(cast(dict[str, object], x))
                    for x in cast(list[object], item.get("source_evidence", []))
                    if isinstance(x, dict)
                ),
                TyreBankCoverage(str(item.get("coverage", "UNKNOWN"))),
                int(item["expected_driver_count"])
                if isinstance(item.get("expected_driver_count"), int)
                else None,
                _app(item.get("applicability")),
            )
        )
    context: list[ContextFact] = []
    for item in cast(list[object], raw.get("context_facts", [])):
        if isinstance(item, dict):
            context.append(
                ContextFact(
                    str(item["category"]),
                    str(item["statement"]),
                    tuple(
                        _ev(cast(dict[str, object], x))
                        for x in cast(list[object], item.get("source_evidence", []))
                        if isinstance(x, dict)
                    ),
                    _app(item.get("applicability")),
                )
            )
    return PirelliRelease(
        release_id=str(raw["release_id"]),
        source_url=str(raw["source_url"]),
        published_at=_parse(cast(str | None, raw.get("published_at"))),
        modified_at=_parse(cast(str | None, raw.get("modified_at"))),
        retrieved_at=_parse(cast(str | None, raw.get("retrieved_at")))
        or datetime.min.replace(tzinfo=UTC),
        content_hash=str(raw["content_hash"]),
        source_type=SourceType(str(raw["source_type"])),
        extraction_method=ExtractionMethod(str(raw["extraction_method"])),
        normalizer_version=str(raw["normalizer_version"]),
        artifact_ids=tuple(
            str(x) for x in cast(list[object], raw.get("artifact_ids", []))
        ),
        applicability=_app(raw.get("applicability")),
        compound_selections=tuple(selections),
        strategies=tuple(strategies),
        tyre_bank_snapshots=tuple(banks),
        context_facts=tuple(context),
    )


def list_normalized_releases(
    archive: PirelliArchive, meeting_key: str
) -> tuple[PirelliRelease, ...]:
    root = archive.meeting_root(meeting_key) / "normalized"
    if not root.exists():
        return ()
    releases: list[PirelliRelease] = []
    for path in sorted(root.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw.get("format") != NORMALIZED_FORMAT:
                continue
            releases.append(release_from_payload(raw))
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    # Normalized outputs remain immutable on disk, but one exact source artifact
    # can be reprocessed by a newer deterministic normalizer. Consumers must not
    # treat those derivations as separate releases or select an older output by
    # filename/hash ordering.
    current: dict[tuple[str, str], PirelliRelease] = {}
    for release in releases:
        key = (release.release_id, release.content_hash)
        selected = current.get(key)
        if selected is None or _normalizer_order(
            release.normalizer_version
        ) > _normalizer_order(selected.normalizer_version):
            current[key] = release
    return tuple(
        sorted(
            current.values(),
            key=lambda r: (r.published_at or r.retrieved_at, r.release_id),
        )
    )


def _normalizer_order(value: str) -> tuple[tuple[int, ...], str]:
    return tuple(int(part) for part in re.findall(r"\d+", value)), value
