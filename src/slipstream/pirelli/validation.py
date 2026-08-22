"""Deterministic validators. Validation never repairs source values."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

from .contracts import (
    CompoundSelection,
    ContextFact,
    EvidenceArtifact,
    EvidenceKind,
    ExtractionCompleteness,
    ExtractionIssue,
    ExtractionMethod,
    ExtractionResult,
    ExtractionStatus,
    NormalizedFact,
    SourceEvidence,
    StrategyOption,
    StrategyOrder,
    TyreBankCoverage,
    TyreBankSnapshot,
)


def validate_strategy(option: StrategyOption) -> tuple[ExtractionIssue, ...]:
    issues: list[ExtractionIssue] = []
    if option.stop_count < 1 or option.stop_count > 6:
        issues.append(
            ExtractionIssue("strategy_stop_count_implausible", "stop count outside 1..6")
        )
    if option.order != StrategyOrder.ORDERED and any(
        window is not None for window in option.pit_windows
    ):
        issues.append(
            ExtractionIssue(
                "unordered_strategy_has_window",
                "pit window cannot be mapped to unordered transitions",
            )
        )
    for window in option.pit_windows:
        if window is None:
            continue
        if window.start_lap < 1 or window.end_lap < window.start_lap or window.end_lap > 100:
            issues.append(ExtractionIssue("pit_window_invalid", f"invalid lap window {window}"))
    if option.published_delta_seconds is not None and option.published_delta_seconds < 0:
        issues.append(ExtractionIssue("strategy_delta_invalid", "published delta must be non-negative"))
    if option.published_delta_seconds_range is not None:
        low, high = option.published_delta_seconds_range
        if low < 0 or high < low:
            issues.append(
                ExtractionIssue("strategy_delta_range_invalid", "published delta range invalid")
            )
    if not option.source_evidence:
        issues.append(ExtractionIssue("strategy_missing_evidence", "strategy has no source evidence"))
    if option.field_evidence is None or not option.field_evidence.sequence:
        issues.append(
            ExtractionIssue("strategy_missing_sequence_evidence", "sequence lacks field evidence")
        )
    elif option.field_evidence is not None:
        if option.rank.value != "UNRANKED" and not option.field_evidence.rank:
            issues.append(ExtractionIssue("strategy_missing_rank_evidence", "rank lacks field evidence"))
        if len(option.field_evidence.pit_windows) != len(option.pit_windows):
            issues.append(
                ExtractionIssue(
                    "strategy_window_evidence_shape",
                    "pit-window evidence length does not match transition count",
                )
            )
        else:
            for index, window in enumerate(option.pit_windows):
                if window is not None and not option.field_evidence.pit_windows[index]:
                    issues.append(
                        ExtractionIssue(
                            "strategy_missing_window_evidence",
                            f"pit window {index} lacks field evidence",
                        )
                    )
        if (
            option.published_delta_seconds is not None
            or option.published_delta_seconds_range is not None
        ) and not option.field_evidence.delta:
            issues.append(ExtractionIssue("strategy_missing_delta_evidence", "delta lacks field evidence"))
        if option.conditions and not option.field_evidence.conditions:
            issues.append(
                ExtractionIssue("strategy_missing_condition_evidence", "conditions lack field evidence")
            )
    return tuple(issues)


def validate_tyre_bank(
    snapshot: TyreBankSnapshot,
    *,
    expected_driver_numbers: set[str] | None = None,
    min_driver_rows: int = 10,
) -> tuple[ExtractionIssue, ...]:
    issues: list[ExtractionIssue] = []
    if len(snapshot.drivers) < min_driver_rows:
        issues.append(
            ExtractionIssue("tyre_bank_too_few_rows", f"only {len(snapshot.drivers)} rows parsed")
        )

    source_names = [row.source_driver_name.casefold() for row in snapshot.drivers]
    duplicates = [name for name, count in Counter(source_names).items() if count > 1]
    if duplicates:
        issues.append(
            ExtractionIssue("tyre_bank_duplicate_source_driver", ", ".join(duplicates))
        )

    numbers = [row.driver_number for row in snapshot.drivers if row.driver_number]
    if len(numbers) != len(set(numbers)):
        issues.append(
            ExtractionIssue("tyre_bank_duplicate_driver_number", "canonical driver number duplicated")
        )

    for row in snapshot.drivers:
        for label, count in (("hard", row.hard), ("medium", row.medium), ("soft", row.soft)):
            if count.new < 0 or count.used < 0:
                issues.append(
                    ExtractionIssue("tyre_bank_negative_count", f"{row.source_driver_name} {label}")
                )
            if count.new + count.used > 13:
                issues.append(
                    ExtractionIssue(
                        "tyre_bank_total_implausible", f"{row.source_driver_name} {label} > 13"
                    )
                )
        if not 0.0 <= row.confidence <= 1.0:
            issues.append(
                ExtractionIssue("tyre_bank_confidence_invalid", row.source_driver_name)
            )

    if expected_driver_numbers is not None:
        unresolved = [row.source_driver_name for row in snapshot.drivers if not row.driver_number]
        if unresolved:
            issues.append(
                ExtractionIssue("tyre_bank_unresolved_driver", ", ".join(unresolved))
            )
        parsed_numbers = {row.driver_number for row in snapshot.drivers if row.driver_number}
        unknown = parsed_numbers - expected_driver_numbers
        missing = expected_driver_numbers - parsed_numbers
        if unknown:
            issues.append(
                ExtractionIssue(
                    "tyre_bank_unknown_driver_number", ", ".join(sorted(unknown))
                )
            )
        if missing:
            issues.append(
                ExtractionIssue(
                    "tyre_bank_partial_roster",
                    f"missing {len(missing)} of {len(expected_driver_numbers)} expected drivers: "
                    + ", ".join(sorted(missing)),
                )
            )
        if not missing and not unknown and not unresolved:
            if snapshot.coverage != TyreBankCoverage.COMPLETE:
                issues.append(
                    ExtractionIssue(
                        "tyre_bank_coverage_mismatch",
                        "full roster parsed but snapshot is not marked COMPLETE",
                    )
                )
        elif snapshot.coverage == TyreBankCoverage.COMPLETE:
            issues.append(
                ExtractionIssue(
                    "tyre_bank_false_complete",
                    "snapshot marked COMPLETE without full resolved roster",
                )
            )
    elif snapshot.coverage == TyreBankCoverage.COMPLETE:
        issues.append(
            ExtractionIssue(
                "tyre_bank_complete_without_roster",
                "COMPLETE coverage requires a known canonical weekend roster",
            )
        )

    return tuple(issues)


def verify_source_evidence(
    evidence: SourceEvidence,
    artifacts: Mapping[str, EvidenceArtifact],
) -> tuple[ExtractionIssue, ...]:
    artifact = artifacts.get(evidence.artifact_id)
    if artifact is None:
        return (
            ExtractionIssue(
                "evidence_artifact_missing",
                f"artifact {evidence.artifact_id} unavailable to verifier",
                evidence.artifact_id,
            ),
        )

    if evidence.kind in {EvidenceKind.TEXT, EvidenceKind.TABLE}:
        if not evidence.text:
            return (
                ExtractionIssue(
                    "evidence_text_missing",
                    "text/table evidence must include exact source text",
                    evidence.artifact_id,
                ),
            )
        texts = tuple(x for x in (artifact.text, *artifact.page_texts) if x is not None)
        if not texts:
            return (
                ExtractionIssue(
                    "evidence_text_artifact_unavailable",
                    "archived artifact has no verifier text representation",
                    evidence.artifact_id,
                ),
            )
        if not any(evidence.text in source for source in texts):
            return (
                ExtractionIssue(
                    "evidence_text_not_in_artifact",
                    "quoted evidence does not occur in immutable artifact",
                    evidence.artifact_id,
                ),
            )
        if (
            evidence.text_start is not None
            and evidence.text_end is not None
            and artifact.text is not None
        ):
            if artifact.text[evidence.text_start : evidence.text_end] != evidence.text:
                return (
                    ExtractionIssue(
                        "evidence_span_mismatch",
                        "declared text span does not resolve to quoted evidence",
                        evidence.artifact_id,
                    ),
                )

    elif evidence.kind == EvidenceKind.REGION:
        if evidence.region is None:
            return (
                ExtractionIssue(
                    "evidence_region_missing",
                    "image evidence requires a region",
                    evidence.artifact_id,
                ),
            )
        if artifact.image_dimensions is None:
            return (
                ExtractionIssue(
                    "evidence_image_dimensions_unknown",
                    "cannot validate image region without archived dimensions",
                    evidence.artifact_id,
                ),
            )
        width, height = artifact.image_dimensions
        left, top, region_width, region_height = evidence.region
        if (
            left < 0
            or top < 0
            or region_width <= 0
            or region_height <= 0
            or left + region_width > width
            or top + region_height > height
        ):
            return (
                ExtractionIssue(
                    "evidence_region_out_of_bounds",
                    f"region {evidence.region} outside {width}x{height}",
                    evidence.artifact_id,
                ),
            )
    return ()


def _fact_evidence(fact: NormalizedFact) -> tuple[SourceEvidence, ...]:
    evidence: list[SourceEvidence] = []
    if isinstance(fact, StrategyOption):
        evidence.extend(fact.source_evidence)
        if fact.field_evidence is not None:
            evidence.extend(fact.field_evidence.sequence)
            evidence.extend(fact.field_evidence.rank)
            for group in fact.field_evidence.pit_windows:
                evidence.extend(group)
            evidence.extend(fact.field_evidence.delta)
            evidence.extend(fact.field_evidence.conditions)
    elif isinstance(fact, TyreBankSnapshot):
        evidence.extend(fact.source_evidence)
        for row in fact.drivers:
            evidence.extend(row.source_evidence)
    elif isinstance(fact, (CompoundSelection, ContextFact)):
        evidence.extend(fact.source_evidence)
    # Preserve order while de-duplicating immutable objects.
    return tuple(dict.fromkeys(evidence))


def verify_fact_evidence(
    fact: NormalizedFact,
    artifacts: Mapping[str, EvidenceArtifact],
) -> tuple[ExtractionIssue, ...]:
    issues: list[ExtractionIssue] = []
    for evidence in _fact_evidence(fact):
        issues.extend(verify_source_evidence(evidence, artifacts))
    if not _fact_evidence(fact):
        issues.append(ExtractionIssue("fact_missing_evidence", type(fact).__name__))
    return tuple(issues)


def validate_result_against_artifacts(
    result: ExtractionResult,
    artifacts: Mapping[str, EvidenceArtifact],
) -> ExtractionResult:
    issues = list(result.issues)
    for fact in result.facts:
        issues.extend(verify_fact_evidence(fact, artifacts))
    if len(issues) == len(result.issues):
        return result
    return ExtractionResult(
        status=ExtractionStatus.NEEDS_REVIEW,
        facts=result.facts,
        issues=tuple(issues),
        methods_attempted=result.methods_attempted,
        completeness=(
            ExtractionCompleteness.PARTIAL
            if result.facts
            else ExtractionCompleteness.UNKNOWN
        ),
        unresolved_claims=result.unresolved_claims,
    )


def result_from_validation(
    facts: tuple[NormalizedFact, ...],
    issues: tuple[ExtractionIssue, ...],
    *,
    method: ExtractionMethod,
) -> ExtractionResult:
    return ExtractionResult(
        status=ExtractionStatus.NEEDS_REVIEW if issues else ExtractionStatus.ACCEPTED,
        facts=facts,
        issues=issues,
        methods_attempted=(method,),
        completeness=(
            ExtractionCompleteness.PARTIAL if issues else ExtractionCompleteness.COMPLETE
        ),
    )
