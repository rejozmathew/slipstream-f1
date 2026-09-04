import gzip
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from slipstream.pirelli.archive import (
    PirelliArchive,
    list_normalized_releases,
    save_normalized_release,
)
from slipstream.pirelli.config import NORMALIZER_VERSION
from slipstream.pirelli.contracts import (
    Compound,
    EvidenceKind,
    ExtractionMethod,
    FactApplicability,
    PirelliRelease,
    PitWindow,
    SessionScope,
    SourceEvidence,
    SourceType,
    StrategyOption,
    StrategyRank,
)
from slipstream.pirelli.seed import (
    build_pirelli_seed,
    import_pirelli_seed,
    import_pirelli_seed_bytes,
    validate_pirelli_seed,
)
from slipstream.pirelli.store import PirelliEvidenceStore


def _save_source(
    data_root,
    *,
    normalizer: str = NORMALIZER_VERSION,
    compounds=(Compound.MEDIUM, Compound.HARD),
):
    archive = PirelliArchive(data_root)
    body = b"Public fixture article body for a published Medium-Hard race strategy."
    published = datetime(2024, 6, 8, 17, tzinfo=UTC)
    artifact = archive.archive_artifact(
        meeting_key="100",
        source_url="https://press.pirelli.com/public-fixture",
        source_type=SourceType.NEWSROOM_HTML,
        body=body,
        retrieved_at=published,
        published_at=published,
        modified_at=published,
        media_type="text/html",
        collector_version="test",
        extension="html",
    )
    scope = FactApplicability(
        meeting_key="100",
        source_meeting_name="Fixture Grand Prix",
        session_scope=SessionScope.RACE,
        target_session_key="race-100",
    )
    evidence = SourceEvidence(
        artifact.artifact_id,
        artifact.source_url,
        EvidenceKind.TEXT,
        ExtractionMethod.DETERMINISTIC_PROSE,
        text="This raw evidence sentence must not enter the seed.",
    )
    release = PirelliRelease(
        release_id=artifact.artifact_id,
        source_url=artifact.source_url,
        published_at=published,
        modified_at=published,
        retrieved_at=published,
        content_hash=artifact.content_hash,
        source_type=artifact.source_type,
        extraction_method=ExtractionMethod.DETERMINISTIC_PROSE,
        normalizer_version=normalizer,
        artifact_ids=(artifact.artifact_id,),
        applicability=replace(scope, session_scope=SessionScope.WEEKEND),
        strategies=(
            StrategyOption(
                id="fixture-strategy",
                rank=StrategyRank.FASTEST_PUBLISHED,
                stop_count=1,
                compounds=compounds,
                pit_windows=(PitWindow(18, 24),),
                source_evidence=(evidence,),
                applicability=scope,
            ),
        ),
    )
    save_normalized_release(archive, meeting_key="100", release=release)
    return body, artifact, release


def test_seed_build_is_deterministic_and_import_is_idempotent(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    _body, _artifact, _release = _save_source(source)
    first = tmp_path / "first.json.gz"
    second = tmp_path / "second.json.gz"

    report = build_pirelli_seed(
        source, from_year=2024, through_year=2024, output=first
    )
    build_pirelli_seed(source, from_year=2024, through_year=2024, output=second)

    assert first.read_bytes() == second.read_bytes()
    assert report.meetings == 1
    assert report.releases == 1
    assert b"This raw evidence sentence" not in gzip.decompress(first.read_bytes())
    payload = validate_pirelli_seed(first)
    assert payload["integrity"]["digest"] == report.digest
    assert payload["horizon"] == payload["coverage"]
    assert payload["materialized"] == {
        "meetingCount": 1,
        "releaseCount": 1,
        "meetingKeys": ["100"],
    }

    imported = import_pirelli_seed(first, destination)
    repeated = import_pirelli_seed(first, destination)
    assert imported.artifacts_imported == 1
    assert imported.releases_imported == 1
    assert repeated.artifacts_imported == 0
    assert repeated.releases_imported == 0
    assert repeated.releases_preserved == 1
    availability = PirelliEvidenceStore(destination).load(
        meeting_key="100",
        target_session_key="race-100",
        evidence_cutoff=datetime(2024, 6, 9, 13, tzinfo=UTC),
        session_scope=SessionScope.RACE,
    )
    assert availability.status == "PRESENT"
    assert availability.model_admissible is True


def test_production_seed_rejects_empty_or_superseded_normalizer_history(tmp_path):
    source = tmp_path / "source"
    _save_source(source, normalizer="slipstream-pirelli-v5-adapted.3")

    with pytest.raises(ValueError, match="at least one useful meeting/release"):
        build_pirelli_seed(
            source,
            from_year=2024,
            through_year=2024,
            output=tmp_path / "production.json.gz",
            require_nonempty=True,
        )

    diagnostic = tmp_path / "diagnostic.json.gz"
    report = build_pirelli_seed(
        source,
        from_year=2024,
        through_year=2024,
        output=diagnostic,
    )
    payload = validate_pirelli_seed(diagnostic)
    assert report.meetings == 0
    assert report.releases == 0
    assert payload["normalizerVersion"] == NORMALIZER_VERSION


def test_seed_import_preserves_better_local_release_and_hydrates_on_reacquire(
    tmp_path,
):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    body, artifact, _release = _save_source(source)
    seed = tmp_path / "seed.json.gz"
    build_pirelli_seed(source, from_year=2024, through_year=2024, output=seed)

    _, local_artifact, local_release = _save_source(
        destination,
        normalizer="slipstream-pirelli-v99",
        compounds=(Compound.SOFT, Compound.HARD),
    )
    result = import_pirelli_seed(seed, destination)
    current = list_normalized_releases(PirelliArchive(destination), "100")
    assert result.releases_preserved == 1
    assert current[0].normalizer_version == "slipstream-pirelli-v99"
    assert current[0].strategies[0].compounds == (Compound.SOFT, Compound.HARD)

    # A provenance-only import in a fresh store is safely enriched when the exact
    # official content is acquired later; facts/timestamps are not projected.
    hydrated_root = tmp_path / "hydrated"
    import_pirelli_seed(seed, hydrated_root)
    hydrated_archive = PirelliArchive(hydrated_root)
    assert hydrated_archive.load_asset_bytes("100", artifact.artifact_id) is None
    reacquired = hydrated_archive.archive_artifact(
        meeting_key="100",
        source_url=artifact.source_url,
        source_type=artifact.source_type,
        body=body,
        retrieved_at=artifact.retrieved_at + timedelta(days=365),
        published_at=artifact.published_at,
        modified_at=artifact.modified_at + timedelta(days=365),
        media_type=artifact.media_type,
        collector_version="runtime",
        extension="html",
    )
    assert reacquired.artifact_id == local_artifact.artifact_id
    assert reacquired.retrieved_at == artifact.retrieved_at
    assert reacquired.modified_at == artifact.modified_at
    assert hydrated_archive.load_asset_bytes("100", reacquired.artifact_id) == body
    assert local_release.release_id == reacquired.artifact_id


def test_seed_import_rejects_path_traversal_components(tmp_path):
    source = tmp_path / "source"
    _save_source(source)
    seed = tmp_path / "seed.json.gz"
    build_pirelli_seed(source, from_year=2024, through_year=2024, output=seed)
    payload = json.loads(gzip.decompress(seed.read_bytes()))
    payload["meetings"][0]["meetingKey"] = "../escape"
    base = {key: value for key, value in payload.items() if key != "integrity"}
    payload["integrity"]["digest"] = hashlib.sha256(
        json.dumps(base, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    crafted = gzip.compress(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() + b"\n",
        mtime=0,
    )

    with pytest.raises(ValueError, match="canonical numeric"):
        import_pirelli_seed_bytes(crafted, tmp_path / "destination")
    assert not (tmp_path / "escape").exists()
