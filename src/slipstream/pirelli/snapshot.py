"""Explicit snapshot semantics: complementary facts accumulate; ordering is internal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from .contracts import (
    CompoundSelection,
    ContextFact,
    PirelliRelease,
    SessionScope,
    StrategyOption,
    TyreBankSnapshot,
)


@dataclass(frozen=True)
class StrategyReleaseView:
    release_id: str
    source_url: str
    published_at: datetime | None
    retrieved_at: datetime
    strategies: tuple[StrategyOption, ...]


@dataclass(frozen=True)
class PirelliEvidenceSnapshot:
    release_ids: tuple[str, ...]
    compound_selections: tuple[CompoundSelection, ...]
    strategy_releases: tuple[StrategyReleaseView, ...]
    tyre_bank_snapshots: tuple[TyreBankSnapshot, ...]
    context_facts: tuple[ContextFact, ...]

    @property
    def latest_strategy_release(self) -> StrategyReleaseView | None:
        return self.strategy_releases[-1] if self.strategy_releases else None

    @property
    def latest_tyre_bank(self) -> TyreBankSnapshot | None:
        return self.tyre_bank_snapshots[-1] if self.tyre_bank_snapshots else None


def _applies(
    meeting_key: str | None,
    session_scope: SessionScope | None,
    fact_meeting: str | None,
    fact_scope: SessionScope,
) -> bool:
    # When a caller asks for a specific meeting, UNKNOWN is not a wildcard. Facts must
    # be explicitly bound to that meeting before they can enter a replay/session view.
    if meeting_key is not None and fact_meeting != meeting_key:
        return False
    if session_scope is None:
        return True
    # WEEKEND facts are deliberately reusable by sessions in that same meeting. Unknown
    # session applicability fails closed rather than silently applying everywhere.
    if fact_scope == SessionScope.WEEKEND:
        return True
    if fact_scope == SessionScope.UNKNOWN:
        return False
    return fact_scope == session_scope


def aggregate_releases(
    releases: tuple[PirelliRelease, ...],
    *,
    meeting_key: str | None = None,
    session_scope: SessionScope | None = None,
) -> PirelliEvidenceSnapshot:
    """Aggregate in explicit chronology and retain release/snapshot identity.

    Caller ordering is ignored. No category-wide latest-non-empty overwrite occurs.
    """
    floor = datetime.min.replace(tzinfo=UTC)
    ordered = tuple(
        sorted(
            releases,
            key=lambda release: (
                release.published_at or release.retrieved_at or floor,
                release.release_id,
            ),
        )
    )
    selections: list[CompoundSelection] = []
    strategy_releases: list[StrategyReleaseView] = []
    banks: list[TyreBankSnapshot] = []
    facts: list[ContextFact] = []
    seen_facts: set[tuple[str, str, str]] = set()

    for release in ordered:
        scoped_strategies = tuple(
            strategy
            for strategy in release.strategies
            if _applies(
                meeting_key,
                session_scope,
                strategy.applicability.meeting_key,
                strategy.applicability.session_scope,
            )
        )
        if scoped_strategies:
            strategy_releases.append(
                StrategyReleaseView(
                    release.release_id,
                    release.source_url,
                    release.published_at,
                    release.retrieved_at,
                    scoped_strategies,
                )
            )
        selections.extend(
            selection
            for selection in release.compound_selections
            if _applies(
                meeting_key,
                session_scope,
                selection.applicability.meeting_key,
                selection.applicability.session_scope,
            )
        )
        banks.extend(
            bank
            for bank in release.tyre_bank_snapshots
            if _applies(
                meeting_key,
                session_scope,
                bank.applicability.meeting_key,
                bank.applicability.session_scope,
            )
        )
        for fact in release.context_facts:
            if not _applies(
                meeting_key,
                session_scope,
                fact.applicability.meeting_key,
                fact.applicability.session_scope,
            ):
                continue
            source = (
                fact.source_evidence[0].source_url
                if fact.source_evidence
                else release.source_url
            )
            key = (fact.category, fact.statement, source)
            if key not in seen_facts:
                seen_facts.add(key)
                facts.append(fact)

    banks.sort(key=lambda bank: bank.as_of or floor)
    return PirelliEvidenceSnapshot(
        release_ids=tuple(release.release_id for release in ordered),
        compound_selections=tuple(selections),
        strategy_releases=tuple(strategy_releases),
        tyre_bank_snapshots=tuple(banks),
        context_facts=tuple(facts),
    )
