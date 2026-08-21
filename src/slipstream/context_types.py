"""Normalized context-artifact contracts (v2.1 §5.2 Historical, §5.3 OfficialPreRace).

Phase A: the stable data + serialization contract only.

- Target-session-owned (v2.1 §5.5 data-ownership contract; Milestone 4 enforces
  the actual deletion cascade — we define the contract, we do not build it).
- Replay-safe / no-hindsight: every value is as-of the evidence cutoff, never later.
- Attributed + provenance-carrying (invariant 8); acquisition is Phase F
  (manual structured path guaranteed; automated is a bounded discovery spike).
- No LLM inference in the deterministic path (v2.1 §5.7).

These dataclasses are the contract the model, UI, and M4 all depend on, so the
shape is fixed here in Phase A even though the acquisition wiring lands in Phase F.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# --- v2.1 contract vocabulary (single source of truth for enum strings) --------

# §5.2 — Historical Context comparability states.
HISTORICAL_COMPARABILITY_STATES = ("NORMAL", "LIMITED", "INCOMPATIBLE")

# §5.3 — Official pre-race source kinds.
OFFICIAL_PRERACE_SOURCE_KINDS = ("PIRELLI", "FIA", "OTHER")

# §15 — dry-tyre requirement per-driver states (computed in Phase C).
DRY_TYRE_REQUIREMENT_STATES = ("UNSATISFIED", "SATISFIED", "NOT_APPLICABLE", "UNKNOWN")

# §12 — driver disposition + window states (computed in Phase C).
DISPOSITION_STATES = ("PIT_EXPECTED", "TO_FINISH", "UNKNOWN")
WINDOW_STATES = ("ACTIVE", "WINDOW_PASSED_EXTENDING", "TO_FINISH", "RESETTING", "UNKNOWN")

# §11 — strategy validity states (computed in Phase C).
STRATEGY_VALIDITY_STATES = ("VALID", "RESETTING", "RECALCULATING", "UNAVAILABLE", "FINAL")

# §17.1 — the derived pit-economics metric that blocks free-stop/rejoin/quantified undercut.
NET_PIT_LOSS_BLOCKED_BY = (
    "freeStopMargin",
    "projectedRejoinPosition",
    "undercutQuantified",
)


@dataclass(frozen=True)
class HistoricalContext:
    """Prior-season, same-circuit, no-hindsight evidence (v2.1 §5.2).

    Target-session-owned persistent artifact, cached locally so replay never
    needs the network. ``comparability`` degrades to LIMITED/INCOMPATIBLE when
    the regulation era differs (v2.1 §25-24, e.g. 2025 -> 2026).
    """

    season: int
    circuit_id: str
    comparability: str = "UNKNOWN"
    stop_distribution: dict[str, int] = field(default_factory=dict)
    compound_sequences: tuple[str, ...] = ()
    stint_lengths: dict[str, Any] = field(default_factory=dict)
    source_note: str = ""
    evidence_cutoff: str | None = None
    target_session_key: str | None = None  # §5.5 ownership (M4 enforces)

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": "PRESENT",
            "season": self.season,
            "circuitId": self.circuit_id,
            "comparability": self.comparability,
            "stopDistribution": dict(self.stop_distribution),
            "compoundSequences": list(self.compound_sequences),
            "stintLengths": dict(self.stint_lengths),
            "sourceNote": self.source_note,
            "evidenceCutoff": self.evidence_cutoff,
            "targetSessionKey": self.target_session_key,
        }


@dataclass(frozen=True)
class OfficialPreRaceContext:
    """Attributed official pre-race context, e.g. Pirelli (v2.1 §5.3 / §6).

    A separate artifact class (not the generic external-intelligence bucket).
    Published values are explicit statements only (no LLM inference), fully
    attributed, and rejected if published after the evidence cutoff (§25-14).
    """

    source: str
    published_at: str | None
    retrieved_at: str | None
    source_url: str | None = None
    expected_stop_count: int | None = None
    primary_sequence: str | None = None
    alternate_sequence: str | None = None
    stated_pit_windows: tuple[dict[str, Any], ...] = ()
    caveats: tuple[str, ...] = ()
    provider_version: str | None = None
    acquisition: str = "MANUAL"  # MANUAL | AUTOMATED (bounded spike)
    target_session_key: str | None = None  # §5.5 ownership (M4 enforces)

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": "PRESENT",
            "source": self.source,
            "publishedAt": self.published_at,
            "retrievedAt": self.retrieved_at,
            "sourceUrl": self.source_url,
            "expectedStopCount": self.expected_stop_count,
            "primarySequence": self.primary_sequence,
            "alternateSequence": self.alternate_sequence,
            "statedPitWindows": [dict(window) for window in self.stated_pit_windows],
            "caveats": list(self.caveats),
            "providerVersion": self.provider_version,
            "acquisition": self.acquisition,
            "targetSessionKey": self.target_session_key,
        }


# --- Absent placeholders (contract present, no data yet) ----------------------


def absent_official_pre_race(reason: str = "not_provided") -> dict[str, Any]:
    """Payload for the contract when no OfficialPreRace context exists."""
    return {"status": "ABSENT", "source": None, "reason": reason}


def absent_historical(reason: str = "not_provided") -> dict[str, Any]:
    """Payload for the contract when no Historical context exists."""
    return {"status": "ABSENT", "season": None, "reason": reason}


def official_pre_race_is_rejected_after_cutoff(
    context: OfficialPreRaceContext, evidence_cutoff: str | None
) -> bool:
    """v2.1 Scenario 14: an official pre-race context published after the
    session's evidence cutoff is **rejected** (not admitted, and not silently
    degraded to a lower-confidence value).

    Returns True when the context must be rejected, False when it may be
    admitted. A missing ``published_at`` or ``evidence_cutoff`` is *not* a
    rejection — those are provenance gaps handled by the usual UNKNOWN path.
    """
    if not context.published_at or not evidence_cutoff:
        return False
    try:
        from datetime import datetime

        published = datetime.fromisoformat(context.published_at)
        cutoff = datetime.fromisoformat(evidence_cutoff)
    except (ValueError, TypeError):
        return False
    return published > cutoff
