"""Deterministic tyre-bank table normalization.

Native PDF text is accepted automatically only for a benchmarked Pirelli table template
whose H/M/S and New/Used semantics are explicitly proven. Generic six-number rows are not
interpreted.
"""

from __future__ import annotations

import re
from datetime import datetime

from ..contracts import (
    CompoundCount,
    DriverTyreBank,
    EvidenceKind,
    ExtractionCompleteness,
    ExtractionIssue,
    ExtractionMethod,
    ExtractionResult,
    ExtractionStatus,
    FactApplicability,
    SessionScope,
    SourceEvidence,
    TyreBankCoverage,
    TyreBankSnapshot,
    WeekendDriverIdentity,
)
from ..driver_resolution import resolve_driver
from ..validation import validate_tyre_bank

_ROW = re.compile(
    r"^\s*(?:#(?P<number>\d{1,3})\s+)?"
    r"(?P<name>[A-Za-zÀ-ÿ' .-]+?)\s+"
    r"(?P<hnew>\d+)\s+(?P<hused>\d+)\s+"
    r"(?P<mnew>\d+)\s+(?P<mused>\d+)\s+"
    r"(?P<snew>\d+)\s+(?P<sused>\d+)\s*$"
)

_TEMPLATE_ID = "PIRELLI_RACE_TYRE_TABLE_TEXT_V1"
_SUBHEADER = "new used new used new used"
_COMPOUND_HEADER = "hard medium soft"


def _normalized_lines(text: str) -> tuple[str, ...]:
    return tuple(re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip())


def detect_benchmarked_text_template(text: str) -> str | None:
    """Recognize the exact native-text layout benchmarked against the Pirelli race PDF.

    The PDF text extractor may emit the compound header after the rows, so physical order
    is not inferred from line order. Instead, acceptance is limited to this explicitly
    versioned layout: exact repeated New/Used subheader, exact Hard/Medium/Soft group
    header, Driver label, and the Pirelli race-availability title.
    """

    lines = _normalized_lines(text)
    lowered = tuple(line.casefold() for line in lines)
    if _SUBHEADER not in lowered or _COMPOUND_HEADER not in lowered:
        return None
    if "driver" not in lowered:
        return None
    if not any("tyre sets available for the race" in line for line in lowered):
        return None
    # Reject competing/reordered compound/subcolumn header lines rather than deciding
    # which one to trust.
    compound_header_like = [
        line
        for line in lowered
        if all(word in line.split() for word in ("hard", "medium", "soft"))
    ]
    if any(line != _COMPOUND_HEADER for line in compound_header_like):
        return None
    new_used_like = [
        line for line in lowered if line.count("new") >= 1 and line.count("used") >= 1
    ]
    if any(line != _SUBHEADER for line in new_used_like):
        return None
    return _TEMPLATE_ID


def parse_tyre_bank_text(
    text: str,
    *,
    artifact_id: str,
    source_url: str,
    method: ExtractionMethod,
    as_of: datetime | None = None,
    target_session: str | None = None,
    weekend_drivers: tuple[WeekendDriverIdentity, ...] = (),
    minimum_rows: int = 10,
    applicability: FactApplicability | None = None,
    template_proof: str | None = None,
) -> ExtractionResult:
    template_id = template_proof or detect_benchmarked_text_template(text)
    if template_id != _TEMPLATE_ID:
        return ExtractionResult(
            status=ExtractionStatus.NEEDS_REVIEW,
            issues=(
                ExtractionIssue(
                    "tyre_bank_header_semantics_unproven",
                    "native text does not match a benchmarked Pirelli H/M/S × New/Used template",
                    artifact_id,
                ),
            ),
            methods_attempted=(method,),
            completeness=ExtractionCompleteness.UNKNOWN,
        )

    lines = _normalized_lines(text)
    rows: list[DriverTyreBank] = []
    issues: list[ExtractionIssue] = []
    for line in lines:
        match = _ROW.match(line)
        if not match:
            continue
        values = match.groupdict()
        number = values.get("number")
        name = values["name"].strip()
        evidence = SourceEvidence(
            artifact_id=artifact_id,
            source_url=source_url,
            kind=EvidenceKind.TABLE,
            extraction_method=method,
            page=0,
            text=line,
            confidence=1.0 if method == ExtractionMethod.PDF_TEXT else 0.9,
        )

        driver_number: str | None = None
        driver_code: str | None = None
        confidence = evidence.confidence or 0.0
        if weekend_drivers:
            resolved = resolve_driver(name, weekend_drivers, source_number=number)
            if resolved.status != ExtractionStatus.ACCEPTED:
                issues.append(
                    resolved.issue
                    or ExtractionIssue("driver_resolution_failed", name, artifact_id)
                )
                confidence = min(confidence, 0.5)
            else:
                driver_number = resolved.driver_number
                driver_code = resolved.driver_code
        else:
            driver_number = number

        rows.append(
            DriverTyreBank(
                source_driver_name=name,
                driver_number=driver_number,
                driver_code=driver_code,
                hard=CompoundCount(int(values["hnew"]), int(values["hused"])),
                medium=CompoundCount(int(values["mnew"]), int(values["mused"])),
                soft=CompoundCount(int(values["snew"]), int(values["sused"])),
                confidence=confidence,
                source_evidence=(evidence,),
            )
        )

    if not rows:
        return ExtractionResult(
            status=ExtractionStatus.UNPARSED,
            issues=(
                ExtractionIssue(
                    "tyre_bank_no_rows", "no driver rows matched the benchmarked table", artifact_id
                ),
            ),
            methods_attempted=(method,),
            completeness=ExtractionCompleteness.UNKNOWN,
        )

    expected_numbers = {driver.driver_number for driver in weekend_drivers} if weekend_drivers else None
    parsed_numbers = {row.driver_number for row in rows if row.driver_number}
    fully_resolved = bool(
        expected_numbers is not None
        and parsed_numbers == expected_numbers
        and all(row.driver_number is not None for row in rows)
        and len(rows) == len(expected_numbers)
    )
    coverage = TyreBankCoverage.COMPLETE if fully_resolved else (
        TyreBankCoverage.PARTIAL if expected_numbers is not None else TyreBankCoverage.UNKNOWN
    )

    header_lines = [
        line for line in lines
        if line.casefold() in {_SUBHEADER, _COMPOUND_HEADER}

    ]
    header_evidence = tuple(
        SourceEvidence(
            artifact_id=artifact_id,
            source_url=source_url,
            kind=EvidenceKind.TABLE,
            extraction_method=method,
            page=0,
            text=line,
            confidence=1.0 if method == ExtractionMethod.PDF_TEXT else 0.9,
        )
        for line in header_lines
    )
    app = applicability or FactApplicability(
        session_scope=SessionScope.RACE,
        target_session_key=target_session,
    )
    snapshot = TyreBankSnapshot(
        as_of=as_of,
        target_session=target_session,
        drivers=tuple(rows),
        source_evidence=header_evidence,
        coverage=coverage,
        expected_driver_count=(len(expected_numbers) if expected_numbers is not None else None),
        applicability=app,
    )

    validation = validate_tyre_bank(
        snapshot,
        expected_driver_numbers=expected_numbers,
        min_driver_rows=minimum_rows,
    )
    issues.extend(validation)
    if not weekend_drivers:
        issues.append(
            ExtractionIssue(
                "tyre_bank_canonical_roster_required",
                "per-driver tyre bank cannot be authoritative without the weekend canonical roster",
                artifact_id,
            )
        )

    return ExtractionResult(
        status=ExtractionStatus.NEEDS_REVIEW if issues else ExtractionStatus.ACCEPTED,
        facts=(snapshot,),
        issues=tuple(issues),
        methods_attempted=(method,),
        completeness=(
            ExtractionCompleteness.COMPLETE
            if not issues and coverage == TyreBankCoverage.COMPLETE
            else ExtractionCompleteness.PARTIAL
        ),
    )


