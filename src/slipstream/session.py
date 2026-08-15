"""Source-neutral session taxonomy and layout-family classification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SessionKind(StrEnum):
    PRACTICE_1 = "practice_1"
    PRACTICE_2 = "practice_2"
    PRACTICE_3 = "practice_3"
    QUALIFYING = "qualifying"
    SPRINT_QUALIFYING = "sprint_qualifying"
    SPRINT = "sprint"
    RACE = "race"
    UNKNOWN = "unknown"


class LayoutFamily(StrEnum):
    PRACTICE = "practice"
    QUALIFYING = "qualifying"
    RACE = "race"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class SessionClassification:
    kind: SessionKind
    layout_family: LayoutFamily


def classify_session(
    session_type: str | None,
    session_name: str | None,
) -> SessionClassification:
    """Classify provider labels without assuming a fixed weekend inventory."""

    value = f"{session_type or ''} {session_name or ''}".strip().casefold()
    if "sprint qualifying" in value or "sprint shootout" in value:
        return SessionClassification(
            SessionKind.SPRINT_QUALIFYING, LayoutFamily.QUALIFYING
        )
    if "qualifying" in value or "shootout" in value:
        return SessionClassification(SessionKind.QUALIFYING, LayoutFamily.QUALIFYING)
    if "sprint" in value:
        return SessionClassification(SessionKind.SPRINT, LayoutFamily.RACE)
    if "practice" in value or "testing" in value:
        for number, kind in (
            ("1", SessionKind.PRACTICE_1),
            ("2", SessionKind.PRACTICE_2),
            ("3", SessionKind.PRACTICE_3),
        ):
            if f"practice {number}" in value or f"fp{number}" in value:
                return SessionClassification(kind, LayoutFamily.PRACTICE)
        return SessionClassification(SessionKind.UNKNOWN, LayoutFamily.PRACTICE)
    if "race" in value or "grand prix" in value:
        return SessionClassification(SessionKind.RACE, LayoutFamily.RACE)
    return SessionClassification(SessionKind.UNKNOWN, LayoutFamily.UNSUPPORTED)
