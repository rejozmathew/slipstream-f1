"""Strict normalized contracts for Pirelli evidence ingestion v5.

This package is an acquisition/extraction subsystem, not a race prediction engine.
Every authoritative fact must be source-backed, scoped, completeness-aware and
replay-admissible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TypeAlias


class ExtractionStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    UNKNOWN = "UNKNOWN"
    UNPARSED = "UNPARSED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REJECTED = "REJECTED"


class ExtractionCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class ExtractionMethod(StrEnum):
    STRUCTURED_HTML = "STRUCTURED_HTML"
    DETERMINISTIC_PROSE = "DETERMINISTIC_PROSE"
    PDF_TEXT = "PDF_TEXT"
    HYBRID = "HYBRID"
    OTHER = "OTHER"


class SourceType(StrEnum):
    NEWSROOM_HTML = "NEWSROOM_HTML"
    PDF = "PDF"
    IMAGE = "IMAGE"
    RSS = "RSS"
    OTHER = "OTHER"


class StrategyRank(StrEnum):
    FASTEST_PUBLISHED = "FASTEST_PUBLISHED"
    EQUIVALENT_FASTEST = "EQUIVALENT_FASTEST"
    ALTERNATIVE = "ALTERNATIVE"
    CONDITIONAL = "CONDITIONAL"
    UNRANKED = "UNRANKED"


class StrategyOrder(StrEnum):
    ORDERED = "ORDERED"
    ANY_ORDER = "ANY_ORDER"
    PARTIALLY_ORDERED = "PARTIALLY_ORDERED"
    UNKNOWN = "UNKNOWN"


class Compound(StrEnum):
    HARD = "HARD"
    MEDIUM = "MEDIUM"
    SOFT = "SOFT"
    INTERMEDIATE = "INTERMEDIATE"
    WET = "WET"


class EvidenceKind(StrEnum):
    TEXT = "TEXT"
    TABLE = "TABLE"
    REGION = "REGION"
    METADATA = "METADATA"


class SessionScope(StrEnum):
    WEEKEND = "WEEKEND"
    PRACTICE = "PRACTICE"
    SPRINT_QUALIFYING = "SPRINT_QUALIFYING"
    SPRINT = "SPRINT"
    QUALIFYING = "QUALIFYING"
    RACE = "RACE"
    UNKNOWN = "UNKNOWN"


class TyreBankCoverage(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class FactApplicability:
    """Where a fact applies. Unknown scope is explicit and never guessed."""

    meeting_key: str | None = None
    source_meeting_name: str | None = None
    session_scope: SessionScope = SessionScope.UNKNOWN
    target_session_key: str | None = None


@dataclass(frozen=True)
class SourceEvidence:
    artifact_id: str
    source_url: str
    kind: EvidenceKind
    extraction_method: ExtractionMethod
    page: int | None = None
    text: str | None = None
    text_start: int | None = None
    text_end: int | None = None
    region: tuple[int, int, int, int] | None = None
    model_id: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class StrategyFieldEvidence:
    sequence: tuple[SourceEvidence, ...]
    rank: tuple[SourceEvidence, ...] = ()
    pit_windows: tuple[tuple[SourceEvidence, ...], ...] = ()
    delta: tuple[SourceEvidence, ...] = ()
    conditions: tuple[SourceEvidence, ...] = ()


@dataclass(frozen=True)
class CompoundSelection:
    hard: str
    medium: str
    soft: str
    source_evidence: tuple[SourceEvidence, ...]
    applicability: FactApplicability = FactApplicability()

    def code_map(self) -> dict[str, Compound]:
        return {
            self.hard.upper(): Compound.HARD,
            self.medium.upper(): Compound.MEDIUM,
            self.soft.upper(): Compound.SOFT,
        }


@dataclass(frozen=True)
class PitWindow:
    start_lap: int
    end_lap: int


@dataclass(frozen=True)
class StrategyOption:
    id: str
    rank: StrategyRank
    stop_count: int
    compounds: tuple[Compound, ...]
    pit_windows: tuple[PitWindow | None, ...]
    order: StrategyOrder = StrategyOrder.ORDERED
    published_delta_seconds: float | None = None
    published_delta_seconds_range: tuple[float, float] | None = None
    conditions: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()
    source_evidence: tuple[SourceEvidence, ...] = ()
    field_evidence: StrategyFieldEvidence | None = None
    applicability: FactApplicability = FactApplicability()

    def __post_init__(self) -> None:
        if len(self.compounds) < 2:
            raise ValueError("strategy requires at least two compounds")
        if self.stop_count != len(self.compounds) - 1:
            raise ValueError("stop_count must equal len(compounds)-1")
        if len(self.pit_windows) != self.stop_count:
            raise ValueError("pit_windows must have one entry per stop")
        if (
            self.published_delta_seconds is not None
            and self.published_delta_seconds_range is not None
        ):
            raise ValueError("publish either exact delta or delta range, not both")
        if self.published_delta_seconds_range is not None:
            low, high = self.published_delta_seconds_range
            if low < 0 or high < low:
                raise ValueError("published delta range must be non-negative and ordered")
        if self.order != StrategyOrder.ORDERED and any(
            window is not None for window in self.pit_windows
        ):
            raise ValueError("unordered strategies cannot carry transition pit windows")

    @property
    def sequence(self) -> str | None:
        if self.order != StrategyOrder.ORDERED:
            return None
        return "-".join(item.value[0] for item in self.compounds)


@dataclass(frozen=True)
class CompoundCount:
    new: int
    used: int


@dataclass(frozen=True)
class DriverTyreBank:
    source_driver_name: str
    hard: CompoundCount
    medium: CompoundCount
    soft: CompoundCount
    confidence: float
    source_evidence: tuple[SourceEvidence, ...]
    driver_number: str | None = None
    driver_code: str | None = None


@dataclass(frozen=True)
class TyreBankSnapshot:
    as_of: datetime | None
    target_session: str | None
    drivers: tuple[DriverTyreBank, ...]
    source_evidence: tuple[SourceEvidence, ...]
    coverage: TyreBankCoverage = TyreBankCoverage.UNKNOWN
    expected_driver_count: int | None = None
    applicability: FactApplicability = FactApplicability(session_scope=SessionScope.RACE)


@dataclass(frozen=True)
class ContextFact:
    category: str
    statement: str
    source_evidence: tuple[SourceEvidence, ...]
    applicability: FactApplicability = FactApplicability()


@dataclass(frozen=True)
class EvidenceArtifact:
    artifact_id: str
    text: str | None = None
    page_texts: tuple[str, ...] = ()
    image_dimensions: tuple[int, int] | None = None


@dataclass(frozen=True)
class ArtifactVersion:
    artifact_id: str
    source_url: str
    source_type: SourceType
    published_at: datetime | None
    modified_at: datetime | None
    retrieved_at: datetime
    content_hash: str
    media_type: str | None
    local_relpath: str | None
    collector_version: str


@dataclass(frozen=True)
class PirelliRelease:
    release_id: str
    source_url: str
    published_at: datetime | None
    modified_at: datetime | None
    retrieved_at: datetime
    content_hash: str
    source_type: SourceType
    extraction_method: ExtractionMethod
    normalizer_version: str
    artifact_ids: tuple[str, ...]
    applicability: FactApplicability = FactApplicability()
    compound_selections: tuple[CompoundSelection, ...] = ()
    strategies: tuple[StrategyOption, ...] = ()
    tyre_bank_snapshots: tuple[TyreBankSnapshot, ...] = ()
    context_facts: tuple[ContextFact, ...] = ()


@dataclass(frozen=True)
class ExtractionIssue:
    code: str
    message: str
    artifact_id: str | None = None


@dataclass(frozen=True)
class UnresolvedClaim:
    claim_id: str
    reason: str
    source_evidence: tuple[SourceEvidence, ...] = ()


NormalizedFact: TypeAlias = CompoundSelection | StrategyOption | TyreBankSnapshot | ContextFact


@dataclass(frozen=True)
class ExtractionResult:
    status: ExtractionStatus
    facts: tuple[NormalizedFact, ...] = ()
    issues: tuple[ExtractionIssue, ...] = ()
    methods_attempted: tuple[ExtractionMethod, ...] = ()
    completeness: ExtractionCompleteness = ExtractionCompleteness.UNKNOWN
    unresolved_claims: tuple[UnresolvedClaim, ...] = ()
    resolved_claim_ids: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        return (
            self.status == ExtractionStatus.ACCEPTED
            and self.completeness == ExtractionCompleteness.COMPLETE
            and not self.unresolved_claims
        )


@dataclass(frozen=True)
class WeekendDriverIdentity:
    driver_number: str
    driver_code: str
    full_name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class DriverResolution:
    status: ExtractionStatus
    source_name: str
    driver_number: str | None = None
    driver_code: str | None = None
    issue: ExtractionIssue | None = None


