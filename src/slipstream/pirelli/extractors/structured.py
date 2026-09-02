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

_UNKNOWN_APPLICABILITY = FactApplicability()
_WEEKEND_APPLICABILITY = FactApplicability(session_scope=SessionScope.WEEKEND)


def _codes(value: str) -> tuple[str, ...]:
    values: list[str] = []
    for match in re.finditer(r"\bC([1-5])\b", value, re.IGNORECASE):
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
    default_applicability: FactApplicability = _WEEKEND_APPLICABILITY,
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
    clauses = [
        part.strip() for part in re.split(r"(?<=[.!?;])\s+", text) if part.strip()
    ]
    for clause in clauses:
        lower = clause.casefold()
        if (
            not any(language in lower for language in _NOMINATION_LANGUAGE)
            and len(_codes(clause)) < 3
        ):
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
            matched_meetings: dict[str, str] = {}
            for alias, meeting_key in sorted(
                matched_aliases,
                key=lambda item: (lower.find(item[0].casefold()), -len(item[0])),
            ):
                matched_meetings.setdefault(meeting_key, alias)
            if not matched_meetings:
                issues.append(
                    ExtractionIssue(
                        "compound_nomination_meeting_ambiguous",
                        f"cannot bind nomination clause to a named meeting: {clause}",
                        artifact_id,
                    )
                )
                continue
            applicabilities = tuple(
                FactApplicability(
                    meeting_key=meeting_key,
                    source_meeting_name=alias,
                    session_scope=SessionScope.WEEKEND,
                )
                for meeting_key, alias in matched_meetings.items()
            )
        else:
            applicabilities = (default_applicability,)

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
        selections = tuple(
            selection
            for applicability in applicabilities
            if (
                selection := _selection(
                    codes, evidence=evidence, applicability=applicability
                )
            )
            is not None
        )
        if not selections:
            issues.append(
                ExtractionIssue(
                    "compound_nomination_order_invalid",
                    f"selection was not an ordered C-code trio: {codes}",
                    artifact_id,
                )
            )
            continue
        facts.extend(selections)

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
                ExtractionCompleteness.PARTIAL
                if facts
                else ExtractionCompleteness.UNKNOWN
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
    applicability: FactApplicability = FactApplicability(  # noqa: B008
        session_scope=SessionScope.WEEKEND
    ),
) -> CompoundSelection | None:
    """Compatibility helper for a single unambiguous nomination."""

    result = extract_compound_nominations(
        text,
        source_url=source_url,
        artifact_id=artifact_id,
        default_applicability=applicability,
    )
    facts = [fact for fact in result.facts if isinstance(fact, CompoundSelection)]
    return (
        facts[0]
        if result.status == ExtractionStatus.ACCEPTED and len(facts) == 1
        else None
    )


def extract_context_facts(
    text: str,
    *,
    source_url: str,
    artifact_id: str,
    applicability: FactApplicability = _UNKNOWN_APPLICABILITY,
    meeting_aliases: Mapping[str, str] | None = None,
    sections: tuple[str, ...] = (),
) -> tuple[ContextFact, ...]:
    categories = (
        (
            "COMPOUND_OUTLOOK",
            (
                re.compile(
                    r"\ball\s+three\s+compounds?\b[^.!?]{0,60}"
                    r"\b(?:in\s+play|viable|valid\s+options?)\b",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"\b(?:hard\s+and\s+medium|medium\s+and\s+hard)\b"
                    r"[^.!?]{0,60}\b(?:common|usual|main)\s+race\s+choices?\b",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"\bsoft\b[^.!?]{0,45}\b(?:is|remains?|could\s+be|will\s+be)\b"
                    r"[^.!?]{0,25}\b(?:a\s+)?viable\s+(?:race\s+)?option\b",
                    re.IGNORECASE,
                ),
            ),
        ),
        ("DEGRADATION", (re.compile(r"\bdegradation\b", re.IGNORECASE),)),
        ("GRIP", (re.compile(r"\bgrip\b", re.IGNORECASE),)),
        (
            "TRACK_EVOLUTION",
            (
                re.compile(r"\btrack\s+evolution\b", re.IGNORECASE),
                re.compile(r"\btrack\s+(?:has\s+)?evolved\b", re.IGNORECASE),
            ),
        ),
        (
            "WEATHER",
            (
                re.compile(r"\brain\b", re.IGNORECASE),
                re.compile(r"\bwet\s+race\b", re.IGNORECASE),
                re.compile(r"\bweather\s+forecast\b", re.IGNORECASE),
                re.compile(r"\bwind\b", re.IGNORECASE),
            ),
        ),
        (
            "TYRE_STRESS",
            (re.compile(r"\b(?:tyre|tire)\s+stress\b", re.IGNORECASE),),
        ),
    )
    aliases = meeting_aliases or {}
    target_key = applicability.meeting_key
    scoped_sections = _meeting_scoped_sections(
        sections or _paragraphs(text), aliases=aliases, target_key=target_key
    )
    out: list[ContextFact] = []
    for section in scoped_sections:
        for sentence in re.split(r"(?<=[.!?])\s+", section):
            sentence = sentence.strip()
            if not sentence:
                continue
            for category, patterns in categories:
                if not any(pattern.search(sentence) for pattern in patterns):
                    continue
                if category == "COMPOUND_OUTLOOK" and re.search(
                    r"\b(?:not|no|neither|unlikely|cannot|can't|won't)\b",
                    sentence,
                    re.IGNORECASE,
                ):
                    continue
                ev = SourceEvidence(
                    artifact_id=artifact_id,
                    source_url=source_url,
                    kind=EvidenceKind.TEXT,
                    extraction_method=ExtractionMethod.STRUCTURED_HTML,
                    text=sentence,
                    confidence=1.0,
                )
                out.append(
                    ContextFact(category, sentence.strip(), (ev,), applicability)
                )
    return tuple(out)


_NAMED_GRAND_PRIX = re.compile(
    r"\b([A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’\-]*(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’\-]*){0,3}"
    r"\s+Grand\s+Prix)\b",
    re.IGNORECASE,
)


def _paragraphs(text: str) -> tuple[str, ...]:
    paragraphs = tuple(
        part.strip() for part in re.split(r"(?:\r?\n){2,}", text) if part.strip()
    )
    if len(paragraphs) > 1:
        return paragraphs
    return tuple(
        part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()
    )


def _meeting_scoped_sections(
    sections: tuple[str, ...], *, aliases: Mapping[str, str], target_key: str | None
) -> tuple[str, ...]:
    """Keep only the target meeting's local section when an article is multi-event.

    Named meetings outside the supplied alias map are treated as explicit foreign
    section markers. Unlabelled prose is accepted only for a single-event article or
    while an unambiguous target section is active.
    """

    if not aliases or target_key is None:
        return sections
    normalized_aliases = tuple(
        (alias.casefold(), str(meeting_key))
        for alias, meeting_key in aliases.items()
        if alias.strip()
    )

    markers: list[set[str]] = []
    has_foreign = False
    has_target = False
    for section in sections:
        lower = section.casefold()
        keys = {
            meeting_key
            for alias, meeting_key in normalized_aliases
            if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", lower)
        }
        for name in _NAMED_GRAND_PRIX.findall(section):
            folded = name.casefold()
            if not any(
                re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", folded)
                for alias, _meeting_key in normalized_aliases
            ):
                keys.add("__foreign__")
        has_foreign = has_foreign or any(key != target_key for key in keys)
        has_target = has_target or target_key in keys
        markers.append(keys)

    if not has_foreign:
        return sections
    if not has_target:
        return ()

    selected: list[str] = []
    active: str | None = None
    for section, keys in zip(sections, markers, strict=True):
        if keys:
            active = next(iter(keys)) if len(keys) == 1 else None
        if active == target_key:
            selected.append(section)
    return tuple(selected)
