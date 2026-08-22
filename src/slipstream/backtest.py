"""Backtest contract for strategy projections.

Milestone 3.5 intentionally publishes no quality metrics until an archived-session
evaluator can replay real evidence at multiple cursors and score its projections.
Returning invented or canned numbers is forbidden.
"""

from dataclasses import asdict, dataclass
from typing import Literal


@dataclass(frozen=True)
class BacktestResult:
    status: Literal["NOT_IMPLEMENTED"] = "NOT_IMPLEMENTED"
    metrics: None = None
    reason: str = (
        "No deterministic archived-session evaluator is implemented; "
        "quality metrics are unavailable."
    )

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


class BacktestHarness:
    """Truthful placeholder for the future deterministic archive evaluator."""

    def __init__(self, development_set: list[str], holdout_set: list[str]):
        self.development_set = tuple(development_set)
        self.holdout_set = tuple(holdout_set)

    def evaluate_session(self, session_archive_path: str) -> BacktestResult:
        """Report unavailable; never synthesize metrics for an archive path."""
        _ = session_archive_path
        return BacktestResult()

    def run_development_set(self) -> dict[str, BacktestResult]:
        return {session: self.evaluate_session(session) for session in self.development_set}

    def run_holdout_set(self) -> dict[str, BacktestResult]:
        return {session: self.evaluate_session(session) for session in self.holdout_set}
