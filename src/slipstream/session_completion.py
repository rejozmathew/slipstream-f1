"""Whole-session completion, distinct from scheduled end and segment flags."""

from collections.abc import Iterable
from dataclasses import dataclass

from .events import NormalizedEvent


@dataclass(frozen=True)
class SessionCompletion:
    complete: bool = False
    at: str | None = None
    reason: str | None = None


def session_completion(
    events: Iterable[NormalizedEvent], *, session_kind: str = "unknown"
) -> SessionCompletion:
    """Reconcile chronological canonical history, never receipt order.

    FINISHED is provisional for Race/Practice, and only a final-segment
    boundary for Qualifying. Explicit source-authored whole-session completion
    also supports sessions legitimately shortened before Q3. Neither schedule
    expiry, transport silence, nor file existence is evidence here.
    """
    phase = "UNKNOWN"
    result = SessionCompletion()
    explicit = False
    for event in events:
        if event.kind != "session":
            continue
        payload = event.payload
        session_kind = payload.get("session_kind", session_kind)
        phase = payload.get("qualifying_phase", phase)
        status = str(payload.get("status") or "").upper()
        if payload.get("session_complete") is True or status in {
            "CANCELLED",
            "COMPLETE",
            "FINAL",
            "FINALIZED",
            "FINALISED",
            "ENDED",
        }:
            if not explicit:
                result = SessionCompletion(
                    True, event.occurred_at, "source_session_complete"
                )
            explicit = True
        elif not explicit and status in {"RUNNING", "SCHEDULED", "SUSPENDED"}:
            result = SessionCompletion()
        elif not explicit and status == "FINISHED":
            qualifying = session_kind in {"qualifying", "sprint_qualifying"}
            final_phase = "SQ3" if session_kind == "sprint_qualifying" else "Q3"
            if (not qualifying or phase == final_phase) and not result.complete:
                result = SessionCompletion(
                    True,
                    event.occurred_at,
                    "final_qualifying_segment" if qualifying else "session_finished",
                )
    return result
