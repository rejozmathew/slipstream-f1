"""Projection backtesting harness (v2.1 Phase G)."""

import json
from dataclasses import dataclass
from typing import Any

@dataclass
class BacktestMetrics:
    hit_rate: float
    event_censored_hit_rate: float
    false_stop_rate: float
    window_error_laps: float
    stability_score: float
    coverage: float
    hard_validity_violations: int

class BacktestHarness:
    """Harness to replay archived races and score strategy projections."""
    
    def __init__(self, development_set: list[str], holdout_set: list[str]):
        self.development_set = development_set
        self.holdout_set = holdout_set
        
    def evaluate_session(self, session_archive_path: str) -> BacktestMetrics:
        """Replay a single session at multiple cursors and compute metrics.
        
        Spike implementation: returns mocked metrics. A real implementation would:
        1. Load the replay resource.
        2. Advance the cursor lap by lap.
        3. Extract the projected strategy snapshot at each lap.
        4. Compare projected pit windows and stop counts against the final factual state.
        5. Compute stability over a rolling window.
        """
        # Mock metrics for the spike
        return BacktestMetrics(
            hit_rate=0.85,
            event_censored_hit_rate=0.92,
            false_stop_rate=0.04,
            window_error_laps=1.2,
            stability_score=0.95,
            coverage=1.0,
            hard_validity_violations=0,
        )

    def run_development_set(self) -> dict[str, BacktestMetrics]:
        """Run the harness against all sessions in the development set."""
        return {session: self.evaluate_session(session) for session in self.development_set}

    def run_holdout_set(self) -> dict[str, BacktestMetrics]:
        """Run the harness against the pre-registered holdout set.
        
        WARNING: This should only be executed once development is complete.
        """
        return {session: self.evaluate_session(session) for session in self.holdout_set}

if __name__ == "__main__":
    harness = BacktestHarness(
        development_set=["2025_bahrain", "2025_silverstone"],
        holdout_set=["2025_monza", "2025_suzuka"]
    )
    print("Running development set...")
    dev_results = harness.run_development_set()
    for session, metrics in dev_results.items():
        print(f"{session}: {metrics}")
