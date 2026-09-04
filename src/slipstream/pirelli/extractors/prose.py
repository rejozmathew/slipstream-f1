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
_WIN = (
    r"(?:between\s+laps?|laps?)\s+(\d+)"
    r"(?:\s+(?:and|to)\s+|\s*[-–]\s*)(\d+)"
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"'])")

_STRATEGY_CONTEXT = re.compile(
    r"\b(?:race\s+strategy|strategy|strategies|one[- ]stop|two[- ]stop|three[- ]stop|"
    r"one[- ]stopper|two[- ]stopper|three[- ]stopper|"
    r"pit\s+window|pit\s+stop|starting\s+on|start\s+on|opening\s+stint|final\s+stint|"
    r"possible\s+options?|fastest\s+tactic|quickest\s+(?:option|solution|strategy)|"
    r"strategy\s+solution|stopping\s+once|stopping\s+twice)\b",
    re.IGNORECASE,
)
_NEGATIVE_SCOPE = re.compile(
    r"\b(?:historical\s+examples?|not\s+(?:a\s+)?recommendation|not\s+recommendations|"
    r"during\s+(?:fp\d|free\s+practice|practice)|development|constructions?|"
    r"long\s+runs?|compared\s+[^.]{0,30}performance)\b",
    re.IGNORECASE,
)
_NUMBER_WORDS = {
    "zero": 0.0,
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
    "six": 6.0,
    "seven": 7.0,
    "eight": 8.0,
    "nine": 9.0,
    "ten": 10.0,
}
_DELTA_NUMBER = r"(?:\d+(?:\.\d+)?|zero|one|two|three|four|five|six|seven|eight|nine|ten)"
_ANNOTATION_SUBJECT = re.compile(
    r"(?P<strategy>\b(?:race\s+)?(?:strateg(?:y|ies)|options?|alternatives?|tactics?)\b)"
    r"|(?P<other>\b(?:pit[- ]stops?|pit\s+windows?|windows?|laps?|sectors?)\b)",
    re.IGNORECASE,
)


def _strategy_id(source_url: str, seq: tuple[Compound, ...], evidence_text: str) -> str:
    raw = f"{source_url}|{'-'.join(x.value for x in seq)}|{evidence_text}".encode()
    return hashlib.sha256(raw).hexdigest()[:20]


def _compound(
    value: str, code_map: dict[str, Compound] | None = None
) -> Compound | None:
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
        re.IGNORECASE,
    ):
        return False
    return not re.search(
        r"\bnot\s+(?:a\s+)?recommendation|\bnot\s+recommendations", local, re.IGNORECASE
    )


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
    if any(
        phrase in lower for phrase in ("conditional on", "only if", "provided that")
    ):
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
    if re.search(
        rf"\b(?:not|unlikely|isn['’]t|aren['’]t)\b[^.;]{{0,45}}\b{rank_word}\b", lower
    ):
        return StrategyRank.UNRANKED
    if re.search(rf"\b{rank_word}\b[^.;]{{0,45}}\b(?:not|unlikely)\b", lower):
        return StrategyRank.UNRANKED
    if " not " in f" {lower} ":
        return StrategyRank.UNRANKED

    if re.search(r"\bbest\s+way\s+would\s+be\s+to\b", lower):
        return StrategyRank.FASTEST_PUBLISHED

    affirmative = (
        rf"\b(?:the\s+)?{rank_word}\s+(?:strategy|tactic|option|solution|choice)\b",
        (
            rf"\b(?:is|are|would\s+be|remains?|appears?\s+to\s+be|looks?\s+like)\s+"
            rf"(?:the\s+)?{rank_word}\b"
        ),
        rf"\b{rank_word}\s+on\s+paper\b",
    )
    if any(re.search(pattern, lower) for pattern in affirmative):
        return StrategyRank.FASTEST_PUBLISHED
    return StrategyRank.UNRANKED


def _window(text: str) -> PitWindow | None:
    match = re.search(_WIN, text, flags=re.IGNORECASE)
    if not match:
        match = re.search(
            r"(?:window|stop)[^.;]{0,70}?(\d+)\s*(?:-|–|to)\s*(\d+)",
            text,
            re.IGNORECASE,
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


def _number(value: str) -> float:
    word = _NUMBER_WORDS.get(value.casefold())
    return word if word is not None else float(value)


def _strategy_attributed(text: str, position: int) -> bool:
    subjects = tuple(_ANNOTATION_SUBJECT.finditer(text[:position]))
    return bool(subjects and subjects[-1].lastgroup == "strategy")


def _strategy_annotations(
    text: str,
) -> tuple[float | None, tuple[float, float] | None, tuple[str, ...], tuple[str, ...]]:
    """Extract explicit source-local annotations without deriving strategy meaning."""

    delta: float | None = None
    delta_range: tuple[float, float] | None = None
    range_match = re.search(
        rf"\bbetween\s+({_DELTA_NUMBER})\s+and\s+({_DELTA_NUMBER})\s+seconds?\s+slower\b",
        text,
        re.IGNORECASE,
    )
    if range_match and _strategy_attributed(text, range_match.start()):
        low, high = _number(range_match.group(1)), _number(range_match.group(2))
        if 0 <= low <= high <= 120:
            delta_range = (low, high)
    elif range_match is None:
        exact_match = re.search(
            rf"\b(?:around|about|approximately|roughly)?\s*({_DELTA_NUMBER})\s+seconds?\s+slower\b",
            text,
            re.IGNORECASE,
        )
        if exact_match and _strategy_attributed(text, exact_match.start()):
            value = _number(exact_match.group(1))
            if 0 <= value <= 120:
                delta = value

    conditions: list[str] = []
    condition_patterns = (
        (r"\bin\s+clean\s+air\b", "In clean air"),
        (r"\bin\s+(?:heavy\s+)?traffic\b", "In traffic"),
        (r"\bwith\s+(?:heavy\s+)?traffic\b", "With traffic"),
        (
            r"\b(?:under|during)\s+(?:a\s+)?(?:virtual\s+safety\s+car|VSC)\b",
            "Under a VSC",
        ),
        (
            r"\bif\s+(?:there\s+(?:is|was)\s+)?(?:a\s+)?(?:virtual\s+safety\s+car|VSC)\b",
            "If there is a VSC",
        ),
    )
    for pattern, label in condition_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if (
            match
            and _strategy_attributed(text, match.start())
            and label not in conditions
        ):
            conditions.append(label)

    caveats: list[str] = []
    for pattern in (
        r"\b(?:only\s+if|provided\s+that|unless)\b[^.;!?]*",
        r"\btraffic\b[^.;!?]{0,80}\b(?:could|may|might|would)\b[^.;!?]*",
        (
            r"\b(?:but|although|albeit)\b[^.;!?]{0,100}"
            r"\b(?:traffic|clean\s+air|VSC|virtual\s+safety\s+car)\b[^.;!?]*"
        ),
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match and _strategy_attributed(text, match.end()):
            value = re.sub(r"\s+", " ", match.group(0)).strip(" ,")
            if value and value not in caveats:
                caveats.append(value[0].upper() + value[1:])

    caveats = [
        item
        for item in caveats
        if not any(
            other != item and other.casefold() in item.casefold()
            for other in caveats
        )
    ]

    return delta, delta_range, tuple(conditions), tuple(caveats)


def _make(
    *,
    source_url: str,
    artifact_id: str,
    compounds: tuple[Compound, ...],
    windows: tuple[PitWindow | None, ...],
    evidence_text: str,
    rank_text: str | None = None,
    conditions: tuple[str, ...] = (),
    caveats: tuple[str, ...] = (),
    annotate: bool = True,
    applicability: FactApplicability = FactApplicability(),  # noqa: B008
) -> StrategyOption:
    sequence_ev = _evidence(artifact_id, source_url, evidence_text)
    annotation_text = evidence_text
    extracted_delta, extracted_range, extracted_conditions, extracted_caveats = (
        _strategy_annotations(annotation_text) if annotate else (None, None, (), ())
    )
    all_conditions = tuple(dict.fromkeys((*conditions, *extracted_conditions)))
    all_caveats = tuple(dict.fromkeys((*caveats, *extracted_caveats)))
    rank_value = _rank(rank_text or evidence_text)
    rank_ev = (
        (_evidence(artifact_id, source_url, rank_text or evidence_text),)
        if rank_value != StrategyRank.UNRANKED
        else ()
    )
    window_evidence = tuple(
        (sequence_ev,) if window is not None else () for window in windows
    )
    field_evidence = StrategyFieldEvidence(
        sequence=(sequence_ev,),
        rank=rank_ev,
        pit_windows=window_evidence,
        delta=(sequence_ev,)
        if extracted_delta is not None or extracted_range is not None
        else (),
        conditions=(sequence_ev,) if all_conditions or all_caveats else (),
    )
    return StrategyOption(
        id=_strategy_id(source_url, compounds, evidence_text),
        rank=rank_value,
        stop_count=len(compounds) - 1,
        compounds=compounds,
        pit_windows=windows,
        published_delta_seconds=extracted_delta,
        published_delta_seconds_range=extracted_range,
        conditions=all_conditions,
        caveats=all_caveats,
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
    applicability: FactApplicability = FactApplicability(),  # noqa: B008
) -> ExtractionResult:
    """Extract only strategy options supported by explicit local syntax."""

    options: list[StrategyOption] = []
    review: list[ExtractionIssue] = []
    unresolved: list[UnresolvedClaim] = []
    sentences = _SENTENCE.split(text)

    # 1) Explicit hyphenated sequences, but only inside a proven strategy context.
    direct_pattern = re.compile(
        rf"\b({_COMPOUND}(?:\s*[-–]\s*{_COMPOUND}){{1,3}})\b", re.IGNORECASE
    )
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
                    annotate=len(all_direct) == 1,
                    applicability=applicability,
                )
            )

    # 2) Explicit ordered language.
    ordered = re.compile(
        rf"(?:running|using)\s+the\s+({_COMPOUND})\s+and\s+then\s+the\s+({_COMPOUND})",
        re.IGNORECASE,
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

    # 3) Explicit start, run-until window, then switch. Recent Pirelli prose puts
    # the window before the transition verb rather than after the destination.
    until_switch = re.compile(
        rf"(?:start|starting)\s+on\s+(?:the\s+)?({_CODE}|{_COMPOUND})"
        rf"[^.]{{0,160}}?\buntil\s+{_WIN}\s+before\s+switch(?:ing)?\s+to\s+"
        rf"(?:the\s+)?({_CODE}|{_COMPOUND})",
        re.IGNORECASE,
    )
    for match in until_switch.finditer(text):
        first = _compound(match.group(1), compound_code_map)
        second = _compound(match.group(4), compound_code_map)
        if first is None or second is None:
            review.append(
                ExtractionIssue("compound_code_unresolved", match.group(0), artifact_id)
            )
            continue
        local = text[max(0, match.start() - 100) : match.end()]
        options.append(
            _make(
                source_url=source_url,
                artifact_id=artifact_id,
                compounds=(first, second),
                windows=(PitWindow(int(match.group(2)), int(match.group(3))),),
                evidence_text=match.group(0),
                rank_text=local,
                applicability=applicability,
            )
        )

    # 4) Explicit Cx/compound start -> switch, but don't truncate longer clauses.
    coded = re.compile(
        rf"(?:start|starting)\s+on\s+(?:the\s+)?({_CODE}|{_COMPOUND})"
        rf".{{0,100}}?(?:switching|switch)\s+to\s+(?:the\s+)?({_CODE}|{_COMPOUND})"
        rf"(?:\s+{_WIN})?",
        re.IGNORECASE,
    )
    for match in coded.finditer(text):
        first = _compound(match.group(1), compound_code_map)
        second = _compound(match.group(2), compound_code_map)
        if first is None or second is None:
            review.append(
                ExtractionIssue("compound_code_unresolved", match.group(0), artifact_id)
            )
            continue
        tail = text[match.end() : match.end() + 120]
        if re.search(
            r"^\s*,?\s*(?:and\s+then\s+(?:go\s+onto|switch\s+to)|before\s+finishing\s+on)",
            tail,
            re.IGNORECASE,
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

    # 5) Natural-language three-leg strategy with two explicit windows.
    natural_three = re.compile(
        rf"(?:start|starting)\s+on\s+(?:the\s+)?({_COMPOUND})[^.]*?"
        rf"(?:change|switch)\s+to\s+(?:the\s+)?({_COMPOUND})\s+{_WIN}[^.]*?"
        rf"(?:and\s+then\s+(?:go\s+onto|switch\s+to)|before\s+finishing\s+on)\s+"
        rf"(?:the\s+)?({_COMPOUND})\s+{_WIN}",
        re.IGNORECASE,
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

    # 6) Natural-language two-leg strategy with explicit start and transition window.
    natural_two = re.compile(
        rf"(?:start|starting)\s+on\s+(?:the\s+)?"
        rf"(?:P\s+Zero\s+(?:White|Yellow|Red)\s+)?({_COMPOUND})"
        rf"[^.]*?(?:change|switch(?:ing)?)\s+to\s+"
        rf"(?:P\s+Zero\s+(?:White|Yellow|Red)\s+)?({_COMPOUND})\s+{_WIN}",
        re.IGNORECASE,
    )
    for match in natural_two.finditer(text):
        tail = text[match.end() : match.end() + 90]
        if re.search(
            r"^\s*,?\s*and\s+then\s+(?:go\s+onto|switch\s+to)", tail, re.IGNORECASE
        ):
            continue
        first = _compound(match.group(1))
        second = _compound(match.group(2))
        if first is None or second is None:
            continue
        before = text[: match.start()]
        previous = (
            sentences[max(0, len(_SENTENCE.split(before)) - 1)]
            if before.strip()
            else ""
        )
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

    # 7) Modern Pirelli prose often states the start choices first and then pairs
    # their Hard transition windows in the same sentence. The ordering of both
    # lists is explicit, so no semantic guess is required.
    paired_starts = re.compile(
        rf"start\s+on\s+(?:the\s+)?({_COMPOUND})s?\s+or\s+(?:the\s+)?"
        rf"({_COMPOUND})s?.{{0,500}}?on\s+(?:the\s+)?({_COMPOUND})\s+tyres?.{{0,200}}?"
        rf"{_WIN}\s*,?\s+or\s+between\s+(\d+)\s+and\s+(\d+)",
        re.IGNORECASE | re.DOTALL,
    )
    for match in paired_starts.finditer(text):
        finish = _compound(match.group(3))
        starts = (_compound(match.group(1)), _compound(match.group(2)))
        windows = (
            PitWindow(int(match.group(4)), int(match.group(5))),
            PitWindow(int(match.group(6)), int(match.group(7))),
        )
        if finish is None or any(start is None for start in starts):
            continue
        local = text[max(0, match.start() - 180) : match.end()]
        for start, window in zip(starts, windows, strict=True):
            if start is not None:
                options.append(
                    _make(
                        source_url=source_url,
                        artifact_id=artifact_id,
                        compounds=(start, finish),
                        windows=(window,),
                        evidence_text=match.group(0),
                        rank_text=local,
                        annotate=False,
                        applicability=applicability,
                    )
                )

    # A preferred start in one sentence followed immediately by an explicit
    # one-stop finish/window is also source-explicit, despite the sentence break.
    preferred_start = re.compile(
        rf"({_COMPOUND})\s+(?:tyre\s+)?is[^.]*?preferred\s+compound\s+for\s+the\s+start\.\s*"
        rf"Those\s+opting\s+for\s+a\s+one[- ]stop\s+strategy[^.]*?"
        rf"(?:on\s+the|to\s+the)\s+({_COMPOUND})\s+compound[^.]*?{_WIN}",
        re.IGNORECASE,
    )
    for match in preferred_start.finditer(text):
        first = _compound(match.group(1))
        second = _compound(match.group(2))
        if first is not None and second is not None:
            local = text[max(0, match.start() - 180) : match.end()]
            options.append(
                _make(
                    source_url=source_url,
                    artifact_id=artifact_id,
                    compounds=(first, second),
                    windows=(PitWindow(int(match.group(3)), int(match.group(4))),),
                    evidence_text=match.group(0),
                    rank_text=local,
                    applicability=applicability,
                )
            )

    # Explicit alternative start/finish wording can put the stop verb after the
    # second compound rather than between the two compounds.
    alternative_finish = re.compile(
        rf"(?:alternative\s+is\s+to\s+)?start\s+on\s+(?:the\s+)?({_COMPOUND})"
        rf"[^.]*?(?:the\s+)?({_COMPOUND})['’]s[^.]*?stopping\s+{_WIN}",
        re.IGNORECASE,
    )
    for match in alternative_finish.finditer(text):
        first = _compound(match.group(1))
        second = _compound(match.group(2))
        if first is not None and second is not None:
            local = text[max(0, match.start() - 100) : match.end()]
            options.append(
                _make(
                    source_url=source_url,
                    artifact_id=artifact_id,
                    compounds=(first, second),
                    windows=(PitWindow(int(match.group(3)), int(match.group(4))),),
                    evidence_text=match.group(0),
                    rank_text=local,
                    applicability=applicability,
                )
            )

    # Some official guidance states an explicitly valid compound pairing without
    # using a transition verb. The route is deterministic even when a following
    # coded-start sentence does not provide enough local evidence to bind its window.
    valid_combination = re.compile(
        rf"\b({_COMPOUND})\s+could\s+be\s+a\s+valid\s+option[^.]*?"
        rf"(?:used\s+)?in\s+combination\s+with\s+(?:the\s+)?({_COMPOUND})\b",
        re.IGNORECASE,
    )
    for match in valid_combination.finditer(text):
        first = _compound(match.group(1))
        second = _compound(match.group(2))
        if first is not None and second is not None:
            options.append(
                _make(
                    source_url=source_url,
                    artifact_id=artifact_id,
                    compounds=(first, second),
                    windows=(None,),
                    evidence_text=match.group(0),
                    rank_text=match.group(0),
                    applicability=applicability,
                )
            )

    # Some releases state an alternative as a complete start/window/finish
    # sentence rather than using "switch" or "stop". All four facts are
    # explicit, so this remains deterministic and does not infer a chain.
    alternative_window_finish = re.compile(
        rf"\balternative\b[^.]*?start(?:ing)?\s+on\s+(?:the\s+)?({_COMPOUND})"
        rf"[^.]*?(?:window\s+)?between\s+laps?\s+(\d+)\s+and\s+(\d+)"
        rf"[^.]*?finish(?:ing)?(?:\s+the\s+race)?\s+on\s+(?:the\s+)?({_COMPOUND})",
        re.IGNORECASE,
    )
    for match in alternative_window_finish.finditer(text):
        first = _compound(match.group(1))
        second = _compound(match.group(4))
        if first is not None and second is not None:
            local = text[max(0, match.start() - 100) : match.end()]
            options.append(
                _make(
                    source_url=source_url,
                    artifact_id=artifact_id,
                    compounds=(first, second),
                    windows=(PitWindow(int(match.group(2)), int(match.group(3))),),
                    evidence_text=match.group(0),
                    rank_text=local,
                    applicability=applicability,
                )
            )

    # The three-leg form used by recent releases gives the first window before
    # naming the second and third compounds; the absent second window stays None.
    first_window_three = re.compile(
        rf"start(?:ing)?\s+on\s+(?:the\s+)?({_COMPOUND})[^.]*?"
        rf"(?:replacement|stop)[^.]*?{_WIN}[^.]*?switching\s+to\s+(?:the\s+)?"
        rf"({_COMPOUND})\s+before\s+finishing\s+on\s+(?:the\s+)?({_COMPOUND})",
        re.IGNORECASE,
    )
    for match in first_window_three.finditer(text):
        compounds = tuple(
            item
            for item in (
                _compound(match.group(1)),
                _compound(match.group(4)),
                _compound(match.group(5)),
            )
            if item is not None
        )
        if len(compounds) == 3:
            local = text[max(0, match.start() - 180) : match.end()]
            options.append(
                _make(
                    source_url=source_url,
                    artifact_id=artifact_id,
                    compounds=compounds,
                    windows=(PitWindow(int(match.group(2)), int(match.group(3))), None),
                    evidence_text=match.group(0),
                    rank_text=local,
                    applicability=applicability,
                )
            )

    # 8) Explicit 'respectively' paired alternatives.
    paired = re.compile(
        rf"final\s+stint\s+on\s+(?:the\s+)?({_COMPOUND}).{{0,100}}?"
        rf"starting\s+on\s+either\s+({_COMPOUND})\s+or\s+({_COMPOUND}).{{0,120}}?"
        rf"respectively\s+between\s+laps\s+(\d+)\s+and\s+(\d+)\s+or\s+"
        rf"between\s+laps\s+(\d+)\s+and\s+(\d+)",
        re.IGNORECASE,
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
                    annotate=False,
                    applicability=applicability,
                )
            )

    # 9) Coded start + two same-compound sets explicitly completing race.
    same_finish = re.compile(
        rf"Starting\s+on\s+(?:the\s+)?({_CODE}|{_COMPOUND}),[^.]*?"
        rf"two\s+sets\s+of\s+({_CODE}|{_COMPOUND})\s+available[^.]*?"
        rf"complete\s+the\s+race\s+using\s+both",
        re.IGNORECASE,
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
            "ALTERNATIVE_MIDDLE_STINT",
            r"Alternatively,[^.]*middle\s+stint[^.]*towards\s+the\s+end",
        ),
        (
            "WINDOW_ASSOCIATION",
            r"final\s+stints?\s+will\s+be\s+run[^.]*pit\s+stop\s+windows",
        ),
        (
            "LEGACY_STINT_MULTISET",
            r"(?:fastest|second-quickest|slowest|good)\s+two-stopper[^.]*\bstints?\b",
        ),
        (
            "UNORDERED_STINTS",
            r"all\s+of\s+the\s+above\s+stints\s+can\s+be\s+run\s+in\s+any\s+order",
        ),
    )
    for claim_id, pattern in unresolved_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
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

    # Prefer a windowed extraction over a windowless shorthand for the exact
    # same sequence and order. Pirelli prose commonly summarizes a plan as
    # ``medium-hard`` before stating the same plan with its pit window; keeping
    # both would publish a duplicate option with weaker evidence.
    specific_sequences = {
        (option.compounds, option.order)
        for option in options
        if any(window is not None for window in option.pit_windows)
    }

    # Dedupe exact facts.
    deduped: list[StrategyOption] = []
    seen: set[tuple[object, ...]] = set()
    for option in options:
        if (
            not any(window is not None for window in option.pit_windows)
            and (option.compounds, option.order) in specific_sequences
        ):
            continue
        key = (
            option.compounds,
            option.rank,
            option.order,
            tuple((w.start_lap, w.end_lap) if w else None for w in option.pit_windows),
            option.published_delta_seconds,
            option.published_delta_seconds_range,
            option.conditions,
            option.caveats,
        )
        if key not in seen:
            seen.add(key)
            deduped.append(option)

    if deduped:
        needs_review = bool(review or unresolved)
        return ExtractionResult(
            status=ExtractionStatus.NEEDS_REVIEW
            if needs_review
            else ExtractionStatus.ACCEPTED,
            facts=tuple(deduped),
            issues=tuple(review),
            methods_attempted=(ExtractionMethod.DETERMINISTIC_PROSE,),
            completeness=(
                ExtractionCompleteness.PARTIAL
                if needs_review
                else ExtractionCompleteness.COMPLETE
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
