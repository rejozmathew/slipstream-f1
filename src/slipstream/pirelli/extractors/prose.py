"""High-precision deterministic strategy prose extraction.

The parser is intentionally conservative. A compound chain is only considered inside a
formal strategy context, ranking is negation-safe, and unresolved article scopes are
carried explicitly so a fallback cannot falsely mark an incomplete article complete.
"""

from __future__ import annotations

import hashlib
import re

from ..contracts import (
    Compound,
    EvidenceKind,
    ExtractionCompleteness,
    ExtractionIssue,
    ExtractionMethod,
    ExtractionResult,
    ExtractionStatus,
    FactApplicability,
    PitWindow,
    SourceEvidence,
    StrategyFieldEvidence,
    StrategyOption,
    StrategyRank,
    UnresolvedClaim,
)

_COMPOUND = r"(?:Hard|Medium|Soft)"
_CODE = r"C[1-5]"
_WIN = r"(?:between\s+laps?|laps?)\s+(\d+)\s+(?:and|to|[-–])\s+(\d+)"
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"'])")

_STRATEGY_CONTEXT = re.compile(
    r"\b(?:race\s+strategy|strategy|strategies|one[- ]stop|two[- ]stop|three[- ]stop|"
    r"one[- ]stopper|two[- ]stopper|three[- ]stopper|"
    r"pit\s+window|pit\s+stop|starting\s+on|start\s+on|opening\s+stint|final\s+stint|"
    r"possible\s+options?|fastest\s+tactic|quickest\s+(?:option|solution|strategy)|"
    r"strategy\s+solution|stopping\s+once|stopping\s+twice)\b",
    re.I,
)
_NEGATIVE_SCOPE = re.compile(
    r"\b(?:historical\s+examples?|not\s+(?:a\s+)?recommendation|not\s+recommendations|"
    r"during\s+(?:fp\d|free\s+practice|practice)|development|constructions?|"
    r"long\s+runs?|compared\s+[^.]{0,30}performance)\b",
    re.I,
)


def _strategy_id(source_url: str, seq: tuple[Compound, ...], evidence_text: str) -> str:
    raw = f"{source_url}|{'-'.join(x.value for x in seq)}|{evidence_text}".encode()
    return hashlib.sha256(raw).hexdigest()[:20]


def _compound(value: str, code_map: dict[str, Compound] | None = None) -> Compound | None:
    upper = value.strip().upper()
    if upper in Compound.__members__:
        return Compound[upper]
    if code_map:
        return code_map.get(upper)
    return None


def _has_strategy_context(sentence: str, previous: str = "") -> bool:
    local = f"{previous} {sentence}".strip()
    if not _STRATEGY_CONTEXT.search(local):
        return False
    # Practice/development language blocks a direct chain unless the same local scope
    # explicitly calls it a strategy/stop option. This is intentionally conservative.
    if _NEGATIVE_SCOPE.search(local) and not re.search(
        r"\b(?:strategy|one[- ]stop|two[- ]stop|three[- ]stop|pit\s+window|pit\s+stop)\b",
        local,
        re.I,
    ):
        return False
    if re.search(r"\bnot\s+(?:a\s+)?recommendation|\bnot\s+recommendations", local, re.I):
        return False
    return True


def _rank(text: str) -> StrategyRank:
    lower = re.sub(r"\s+", " ", text.casefold()).strip()
    if any(
        phrase in lower
        for phrase in (
            "no difference in overall race time",
            "effectively equivalent",
            "equivalent fastest",
            "equally fast",
            "same overall race time",
        )
    ):
        return StrategyRank.EQUIVALENT_FASTEST
    if any(phrase in lower for phrase in ("conditional on", "only if", "provided that")):
        return StrategyRank.CONDITIONAL
    if any(
        phrase in lower
        for phrase in (
            "alternative",
            "less effective",
            "slower",
            "not as quick",
            "valid option",
            "albeit not as quick",
        )
    ):
        return StrategyRank.ALTERNATIVE

    # Never rank from the mere presence of 'fastest'. Negation/scope uncertainty wins.
    rank_word = r"(?:fastest|quickest|best)"
    if re.search(rf"\b(?:not|unlikely|isn['’]t|aren['’]t)\b[^.;]{{0,45}}\b{rank_word}\b", lower):
        return StrategyRank.UNRANKED
    if re.search(rf"\b{rank_word}\b[^.;]{{0,45}}\b(?:not|unlikely)\b", lower):
        return StrategyRank.UNRANKED
    if " not " in f" {lower} ":
        return StrategyRank.UNRANKED

    if re.search(r"\bbest\s+way\s+would\s+be\s+to\b", lower):
        return StrategyRank.FASTEST_PUBLISHED

    affirmative = (
        rf"\b(?:the\s+)?{rank_word}\s+(?:strategy|tactic|option|solution|choice)\b",
        rf"\b(?:is|are|would\s+be|remains?|appears?\s+to\s+be|looks?\s+like)\s+"
        rf"(?:the\s+)?{rank_word}\b",
        rf"\b{rank_word}\s+on\s+paper\b",
    )
    if any(re.search(pattern, lower) for pattern in affirmative):
        return StrategyRank.FASTEST_PUBLISHED
    return StrategyRank.UNRANKED


def _window(text: str) -> PitWindow | None:
    match = re.search(_WIN, text, flags=re.IGNORECASE)
    if not match:
        match = re.search(
            r"(?:window|stop)[^.;]{0,70}?(\d+)\s*(?:-|–|to)\s*(\d+)", text, re.I
        )
    if not match:
        return None
    start, end = int(match.group(1)), int(match.group(2))
    if 1 <= start <= end <= 100:
        return PitWindow(start, end)
    return None


def _evidence(
    artifact_id: str,
    source_url: str,
    text: str,
    *,
    start: int | None = None,
) -> SourceEvidence:
    return SourceEvidence(
        artifact_id=artifact_id,
        source_url=source_url,
        kind=EvidenceKind.TEXT,
        extraction_method=ExtractionMethod.DETERMINISTIC_PROSE,
        text=text,
        text_start=start,
        text_end=(start + len(text)) if start is not None else None,
        confidence=1.0,
    )


def _make(
    *,
    source_url: str,
    artifact_id: str,
    compounds: tuple[Compound, ...],
    windows: tuple[PitWindow | None, ...],
    evidence_text: str,
    rank_text: str | None = None,
    conditions: tuple[str, ...] = (),
    applicability: FactApplicability = FactApplicability(),
) -> StrategyOption:
    sequence_ev = _evidence(artifact_id, source_url, evidence_text)
    rank_value = _rank(rank_text or evidence_text)
    rank_ev = (
        (_evidence(artifact_id, source_url, rank_text or evidence_text),)
        if rank_value != StrategyRank.UNRANKED
        else ()
    )
    window_evidence = tuple((sequence_ev,) if window is not None else () for window in windows)
    field_evidence = StrategyFieldEvidence(
        sequence=(sequence_ev,),
        rank=rank_ev,
        pit_windows=window_evidence,
        conditions=(sequence_ev,) if conditions else (),
    )
    return StrategyOption(
        id=_strategy_id(source_url, compounds, evidence_text),
        rank=rank_value,
        stop_count=len(compounds) - 1,
        compounds=compounds,
        pit_windows=windows,
        conditions=conditions,
        source_evidence=(sequence_ev,),
        field_evidence=field_evidence,
        applicability=applicability,
    )


def extract_strategy_prose(
    text: str,
    *,
    source_url: str,
    artifact_id: str,
    compound_code_map: dict[str, Compound] | None = None,
    applicability: FactApplicability = FactApplicability(),
) -> ExtractionResult:
    """Extract only strategy options supported by explicit local syntax."""

    options: list[StrategyOption] = []
    review: list[ExtractionIssue] = []
    unresolved: list[UnresolvedClaim] = []
    sentences = _SENTENCE.split(text)

    # 1) Explicit hyphenated sequences, but only inside a proven strategy context.
    direct_pattern = re.compile(rf"\b({_COMPOUND}(?:\s*[-–]\s*{_COMPOUND}){{1,3}})\b", re.I)
    for sentence_index, sentence in enumerate(sentences):
        previous = sentences[sentence_index - 1] if sentence_index > 0 else ""
        if not _has_strategy_context(sentence, previous):
            continue
        all_direct = list(direct_pattern.finditer(sentence))
        for match in all_direct:
            names = re.split(r"\s*[-–]\s*", match.group(1))
            parsed = tuple(_compound(name) for name in names)
            if any(item is None for item in parsed):
                continue
            seq = tuple(item for item in parsed if item is not None)
            win = _window(sentence) if len(seq) == 2 and len(all_direct) == 1 else None
            options.append(
                _make(
                    source_url=source_url,
                    artifact_id=artifact_id,
                    compounds=seq,
                    windows=(win,) + (None,) * max(0, len(seq) - 2),
                    evidence_text=sentence.strip(),
                    rank_text=(previous + " " + sentence).strip(),
                    applicability=applicability,
                )
            )

    # 2) Explicit ordered language.
    ordered = re.compile(
        rf"(?:running|using)\s+the\s+({_COMPOUND})\s+and\s+then\s+the\s+({_COMPOUND})",
        re.I,
    )
    for match in ordered.finditer(text):
        sentence = next((s for s in sentences if match.group(0) in s), match.group(0))
        first = _compound(match.group(1))
        second = _compound(match.group(2))
        if first is not None and second is not None and _has_strategy_context(sentence):
            options.append(
                _make(
                    source_url=source_url,
                    artifact_id=artifact_id,
                    compounds=(first, second),
                    windows=(_window(sentence),),
                    evidence_text=sentence.strip(),
                    rank_text=sentence,
                    applicability=applicability,
                )
            )

    # 3) Explicit Cx/compound start -> switch, but don't truncate longer clauses.
    coded = re.compile(
        rf"(?:start|starting)\s+on\s+(?:the\s+)?({_CODE}|{_COMPOUND})"
        rf".{{0,100}}?(?:switching|switch)\s+to\s+(?:the\s+)?({_CODE}|{_COMPOUND})"
        rf"(?:\s+{_WIN})?",
        re.I,
    )
    for match in coded.finditer(text):
        first = _compound(match.group(1), compound_code_map)
        second = _compound(match.group(2), compound_code_map)
        if first is None or second is None:
            review.append(ExtractionIssue("compound_code_unresolved", match.group(0), artifact_id))
            continue
        tail = text[match.end() : match.end() + 120]
        if re.search(
            r"^\s*,?\s*(?:and\s+then\s+(?:go\s+onto|switch\s+to)|before\s+finishing\s+on)",
            tail,
            re.I,
        ):
            continue
        win = (
            PitWindow(int(match.group(3)), int(match.group(4)))
            if match.group(3) and match.group(4)
            else None
        )
        local = text[max(0, match.start() - 100) : match.end()]
        options.append(
            _make(
                source_url=source_url,
                artifact_id=artifact_id,
                compounds=(first, second),
                windows=(win,),
                evidence_text=match.group(0),
                rank_text=local,
                applicability=applicability,
            )
        )

    # 4) Natural-language three-leg strategy with two explicit windows.
    natural_three = re.compile(
        rf"(?:start|starting)\s+on\s+(?:the\s+)?({_COMPOUND})[^.]*?"
        rf"(?:change|switch)\s+to\s+(?:the\s+)?({_COMPOUND})\s+{_WIN}[^.]*?"
        rf"(?:and\s+then\s+(?:go\s+onto|switch\s+to)|before\s+finishing\s+on)\s+"
        rf"(?:the\s+)?({_COMPOUND})\s+{_WIN}",
        re.I,
    )
    for match in natural_three.finditer(text):
        first = _compound(match.group(1))
        second = _compound(match.group(2))
        third = _compound(match.group(5))
        if first is None or second is None or third is None:
            continue
        local = text[max(0, match.start() - 180) : match.end()]
        options.append(
            _make(
                source_url=source_url,
                artifact_id=artifact_id,
                compounds=(first, second, third),
                windows=(
                    PitWindow(int(match.group(3)), int(match.group(4))),
                    PitWindow(int(match.group(6)), int(match.group(7))),
                ),
                evidence_text=match.group(0),
                rank_text=local,
                applicability=applicability,
            )
        )

    # 5) Natural-language two-leg strategy with explicit start and transition window.
    natural_two = re.compile(
        rf"(?:start|starting)\s+on\s+(?:the\s+)?"
        rf"(?:P\s+Zero\s+(?:White|Yellow|Red)\s+)?({_COMPOUND})"
        rf"[^.]*?(?:change|switch(?:ing)?)\s+to\s+"
        rf"(?:P\s+Zero\s+(?:White|Yellow|Red)\s+)?({_COMPOUND})\s+{_WIN}",
        re.I,
    )
    for match in natural_two.finditer(text):
        tail = text[match.end() : match.end() + 90]
        if re.search(r"^\s*,?\s*and\s+then\s+(?:go\s+onto|switch\s+to)", tail, re.I):
            continue
        first = _compound(match.group(1))
        second = _compound(match.group(2))
        if first is None or second is None:
            continue
        before = text[: match.start()]
        previous = sentences[max(0, len(_SENTENCE.split(before)) - 1)] if before.strip() else ""
        options.append(
            _make(
                source_url=source_url,
                artifact_id=artifact_id,
                compounds=(first, second),
                windows=(PitWindow(int(match.group(3)), int(match.group(4))),),
                evidence_text=match.group(0),
                rank_text=(previous + " " + match.group(0)).strip(),
                applicability=applicability,
            )
        )

    # 6) Explicit 'respectively' paired alternatives.
    paired = re.compile(
        rf"final\s+stint\s+on\s+(?:the\s+)?({_COMPOUND}).{{0,100}}?"
        rf"starting\s+on\s+either\s+({_COMPOUND})\s+or\s+({_COMPOUND}).{{0,120}}?"
        rf"respectively\s+between\s+laps\s+(\d+)\s+and\s+(\d+)\s+or\s+"
        rf"between\s+laps\s+(\d+)\s+and\s+(\d+)",
        re.I,
    )
    for match in paired.finditer(text):
        finish = _compound(match.group(1))
        first_start = _compound(match.group(2))
        second_start = _compound(match.group(3))
        if finish is None or first_start is None or second_start is None:
            continue
        for start_compound, a, b in (
            (first_start, int(match.group(4)), int(match.group(5))),
            (second_start, int(match.group(6)), int(match.group(7))),
        ):
            options.append(
                _make(
                    source_url=source_url,
                    artifact_id=artifact_id,
                    compounds=(start_compound, finish),
                    windows=(PitWindow(a, b),),
                    evidence_text=match.group(0),
                    applicability=applicability,
                )
            )

    # 7) Coded start + two same-compound sets explicitly completing race.
    same_finish = re.compile(
        rf"Starting\s+on\s+(?:the\s+)?({_CODE}|{_COMPOUND}),[^.]*?"
        rf"two\s+sets\s+of\s+({_CODE}|{_COMPOUND})\s+available[^.]*?"
        rf"complete\s+the\s+race\s+using\s+both",
        re.I,
    )
    for match in same_finish.finditer(text):
        first = _compound(match.group(1), compound_code_map)
        finish = _compound(match.group(2), compound_code_map)
        if first is not None and finish is not None:
            options.append(
                _make(
                    source_url=source_url,
                    artifact_id=artifact_id,
                    compounds=(first, finish, finish),
                    windows=(None, None),
                    evidence_text=match.group(0),
                    applicability=applicability,
                )
            )

    # Explicit unresolved constructs: facts already extracted remain usable, but the
    # article is PARTIAL until these claim scopes are resolved or disproved.
    unresolved_patterns = (
        ("ANAPHORIC_OPTION", r"could\s+instead\s+use\s+it\s+at\s+the\s+start"),
        (
            "CROSS_SENTENCE_COMBINATION",
            rf"(?:{_COMPOUND})\s+could\s+be\s+a\s+valid\s+option[^.]*?combination\s+with\s+(?:the\s+)?(?:{_COMPOUND})",
        ),
        ("ALTERNATIVE_MIDDLE_STINT", r"Alternatively,[^.]*middle\s+stint[^.]*towards\s+the\s+end"),
        ("WINDOW_ASSOCIATION", r"final\s+stints?\s+will\s+be\s+run[^.]*pit\s+stop\s+windows"),
        ("LEGACY_STINT_MULTISET", r"(?:fastest|second-quickest|slowest|good)\s+two-stopper[^.]*\bstints?\b"),
        ("UNORDERED_STINTS", r"all\s+of\s+the\s+above\s+stints\s+can\s+be\s+run\s+in\s+any\s+order"),
    )
    for claim_id, pattern in unresolved_patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        ev = _evidence(artifact_id, source_url, match.group(0), start=match.start())
        unresolved.append(
            UnresolvedClaim(
                claim_id=claim_id,
                reason="strategy scope requires cross-sentence or semantic resolution",
                source_evidence=(ev,),
            )
        )
        review.append(
            ExtractionIssue(
                "strategy_scope_unresolved",
                f"unresolved strategy scope: {claim_id}",
                artifact_id,
            )
        )

    # Dedupe exact facts.
    deduped: list[StrategyOption] = []
    seen: set[tuple[object, ...]] = set()
    for option in options:
        key = (
            option.compounds,
            option.rank,
            option.order,
            tuple((w.start_lap, w.end_lap) if w else None for w in option.pit_windows),
        )
        if key not in seen:
            seen.add(key)
            deduped.append(option)

    if deduped:
        needs_review = bool(review or unresolved)
        return ExtractionResult(
            status=ExtractionStatus.NEEDS_REVIEW if needs_review else ExtractionStatus.ACCEPTED,
            facts=tuple(deduped),
            issues=tuple(review),
            methods_attempted=(ExtractionMethod.DETERMINISTIC_PROSE,),
            completeness=(
                ExtractionCompleteness.PARTIAL if needs_review else ExtractionCompleteness.COMPLETE
            ),
            unresolved_claims=tuple(unresolved),
        )

    if _STRATEGY_CONTEXT.search(text):
        issue = ExtractionIssue(
            "strategy_language_unparsed",
            "formal strategy language exists but no option had an unambiguous deterministic parse",
            artifact_id,
        )
        unresolved_claim = UnresolvedClaim(
            "FORMAL_STRATEGY_UNPARSED",
            issue.message,
        )
        return ExtractionResult(
            status=ExtractionStatus.NEEDS_REVIEW,
            issues=(issue,),
            methods_attempted=(ExtractionMethod.DETERMINISTIC_PROSE,),
            completeness=ExtractionCompleteness.UNKNOWN,
            unresolved_claims=(unresolved_claim,),
        )

    return ExtractionResult(
        status=ExtractionStatus.UNKNOWN,
        issues=(
            ExtractionIssue(
                "no_formal_strategy_language",
                "no formal strategy option detected",
                artifact_id,
            ),
        ),
        methods_attempted=(ExtractionMethod.DETERMINISTIC_PROSE,),
        completeness=ExtractionCompleteness.COMPLETE,
    )
