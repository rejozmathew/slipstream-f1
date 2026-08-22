"""Structured/low-risk extraction from article text and semantic tables."""

from __future__ import annotations

import re
from collections.abc import Mapping

from ..contracts import (
    CompoundSelection,
    ContextFact,
    EvidenceKind,
    ExtractionCompleteness,
    ExtractionIssue,
    ExtractionMethod,
    ExtractionResult,
    ExtractionStatus,
    FactApplicability,
    SessionScope,
    SourceEvidence,
)

_NOMINATION_LANGUAGE = (
    "compounds selected",
    "compounds selected for",
    "chosen",
    "three middle options",
    "softest trio",
    "selection",
)


def _codes(value: str) -> tuple[str, ...]:
    values: list[str] = []
    for match in re.finditer(r"\bC([1-5])\b", value, re.I):
        code = f"C{match.group(1)}"
        if code not in values:
            values.append(code)
    return tuple(values)


def _selection(
    codes: tuple[str, ...],
    *,
    evidence: SourceEvidence,
    applicability: FactApplicability,
) -> CompoundSelection | None:
    if len(codes) != 3:
        return None
    numeric = [int(code[1]) for code in codes]
    if numeric != sorted(numeric):
        return None
    return CompoundSelection(codes[0], codes[1], codes[2], (evidence,), applicability)


def extract_compound_nominations(
    text: str,
    *,
    source_url: str,
    artifact_id: str,
    meeting_aliases: Mapping[str, str] | None = None,
    default_applicability: FactApplicability = FactApplicability(session_scope=SessionScope.WEEKEND),
) -> ExtractionResult:
    """Extract one or more meeting-scoped nominations.

    Multi-event releases are accepted only when each three-code selection can be bound to
    an explicit supplied meeting alias in the same local clause/sentence.
    """

    aliases = meeting_aliases or {}
    facts: list[CompoundSelection] = []
    issues: list[ExtractionIssue] = []
    relevant = False

    # Split additionally on semicolons; multi-event Pirelli nomination releases often
    # place one event selection per sentence/clause.
    clauses = [part.strip() for part in re.split(r"(?<=[.!?;])\s+", text) if part.strip()]
    for clause in clauses:
        lower = clause.casefold()
        if not any(language in lower for language in _NOMINATION_LANGUAGE) and len(_codes(clause)) < 3:
            continue
        codes = _codes(clause)
        if len(codes) < 3:
            continue
        relevant = True

        matched_aliases = [
            (alias, meeting_key)
            for alias, meeting_key in aliases.items()
            if alias.casefold() in lower
        ]
        if aliases:
            if len(matched_aliases) != 1:
                issues.append(
                    ExtractionIssue(
                        "compound_nomination_meeting_ambiguous",
                        f"cannot uniquely bind nomination clause to meeting: {clause}",
                        artifact_id,
                    )
                )
                continue
            alias, meeting_key = matched_aliases[0]
            applicability = FactApplicability(
                meeting_key=meeting_key,
                source_meeting_name=alias,
                session_scope=SessionScope.WEEKEND,
            )
        else:
            applicability = default_applicability

        # One local clause must identify exactly one triplet. Six codes without local
        # event separation are ambiguous and fail closed.
        if len(codes) != 3:
            issues.append(
                ExtractionIssue(
                    "compound_nomination_multiple_triplets",
                    f"expected one three-code selection in local clause, found {len(codes)} codes",
                    artifact_id,
                )
            )
            continue

        evidence = SourceEvidence(
            artifact_id=artifact_id,
            source_url=source_url,
            kind=EvidenceKind.TEXT,
            extraction_method=ExtractionMethod.STRUCTURED_HTML,
            text=clause,
            confidence=1.0,
        )
        selection = _selection(codes, evidence=evidence, applicability=applicability)
        if selection is None:
            issues.append(
                ExtractionIssue(
                    "compound_nomination_order_invalid",
                    f"selection was not an ordered C-code trio: {codes}",
                    artifact_id,
                )
            )
            continue
        facts.append(selection)

    if facts and not issues:
        return ExtractionResult(
            status=ExtractionStatus.ACCEPTED,
            facts=tuple(facts),
            methods_attempted=(ExtractionMethod.STRUCTURED_HTML,),
            completeness=ExtractionCompleteness.COMPLETE,
        )
    if facts or issues or relevant:
        return ExtractionResult(
            status=ExtractionStatus.NEEDS_REVIEW,
            facts=tuple(facts),
            issues=tuple(issues)
            or (
                ExtractionIssue(
                    "compound_nomination_unresolved",
                    "nomination language exists but meeting-scoped selection is unresolved",
                    artifact_id,
                ),
            ),
            methods_attempted=(ExtractionMethod.STRUCTURED_HTML,),
            completeness=(
                ExtractionCompleteness.PARTIAL if facts else ExtractionCompleteness.UNKNOWN
            ),
        )
    return ExtractionResult(
        status=ExtractionStatus.UNKNOWN,
        methods_attempted=(ExtractionMethod.STRUCTURED_HTML,),
        completeness=ExtractionCompleteness.COMPLETE,
    )


def extract_compound_nomination(
    text: str,
    *,
    source_url: str,
    artifact_id: str,
    applicability: FactApplicability = FactApplicability(session_scope=SessionScope.WEEKEND),
) -> CompoundSelection | None:
    """Compatibility helper for a single unambiguous nomination."""

    result = extract_compound_nominations(
        text,
        source_url=source_url,
        artifact_id=artifact_id,
        default_applicability=applicability,
    )
    facts = [fact for fact in result.facts if isinstance(fact, CompoundSelection)]
    return facts[0] if result.status == ExtractionStatus.ACCEPTED and len(facts) == 1 else None


def extract_context_facts(
    text: str,
    *,
    source_url: str,
    artifact_id: str,
    applicability: FactApplicability = FactApplicability(),
) -> tuple[ContextFact, ...]:
    categories = {
        "DEGRADATION": ("degradation",),
        "GRIP": ("grip",),
        "TRACK_EVOLUTION": ("track evolution", "track has evolved", "track evolved"),
        "WEATHER": ("rain", "wet race", "weather forecast", "wind"),
        "TYRE_STRESS": ("tyre stress", "tire stress"),
    }
    out: list[ContextFact] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        lower = sentence.casefold()
        for category, words in categories.items():
            if any(word in lower for word in words):
                ev = SourceEvidence(
                    artifact_id=artifact_id,
                    source_url=source_url,
                    kind=EvidenceKind.TEXT,
                    extraction_method=ExtractionMethod.STRUCTURED_HTML,
                    text=sentence,
                    confidence=1.0,
                )
                out.append(ContextFact(category, sentence.strip(), (ev,), applicability))
                break
    return tuple(out)
