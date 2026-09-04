"""Versioned sporting-rule facts used only when their scope is established."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyRuleProfile:
    profile_version: str
    mandatory_pit_stops: int | None
    dry_compound_obligation: str
    evidence: tuple[str, ...]
    # v2.1 §15: the per-driver dry-tyre requirement is a separate, rule-derived
    # state (NOT "MUST_STOP"). This field carries the season/session-specific
    # rule profile the per-driver evaluation uses.
    dry_requirement: str = "unknown"


def strategy_rule_profile(year: int, session_kind: str) -> StrategyRuleProfile:
    """Return narrow verified facts; historical/event overrides remain unknown."""

    if session_kind in {"practice_1", "practice_2", "practice_3", "qualifying", "sprint_qualifying"}:
        return StrategyRuleProfile(
            profile_version="non-race-session-scope-v1",
            mandatory_pit_stops=None,
            dry_compound_obligation="not_applicable",
            evidence=("Grand Prix dry-compound requirements do not apply to timed sessions",),
            dry_requirement="not_applicable",
        )
    if year == 2026 and session_kind == "sprint":
        return StrategyRuleProfile(
            profile_version="fia-2026-section-b-issue-08",
            mandatory_pit_stops=0,
            dry_compound_obligation="none",
            evidence=(
                "FIA 2026 Formula 1 Regulations, Section B Sporting, Issue 08",
                "Sprint does not inherit the Race two-dry-specification obligation",
            ),
        )
    if year == 2026 and session_kind == "race":
        return StrategyRuleProfile(
            profile_version="fia-2026-section-b-issue-08",
            mandatory_pit_stops=None,
            dry_compound_obligation="conditional_two_specifications",
            evidence=(
                "FIA 2026 Formula 1 Regulations, Section B Sporting, Issue 08 B6.3.6",
                "Wet/intermediate use and red-flag tyre changes prevent a universal pit-stop count",
            ),
        )
    return StrategyRuleProfile(
        profile_version="unverified-historical-event-profile",
        mandatory_pit_stops=None,
        dry_compound_obligation="unknown",
        evidence=("No verified season/event-specific rule profile is loaded",),
    )
