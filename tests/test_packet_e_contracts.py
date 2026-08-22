from pathlib import Path

from slipstream.backtest import BacktestHarness
from slipstream.context_types import historical_comparability
from slipstream.historical import generate_historical_context_spike
from slipstream.pirelli import acquire_pirelli_context_spike


def test_legacy_context_spikes_fail_closed_without_source_evidence(tmp_path: Path) -> None:
    historical = generate_historical_context_spike(2026, "hungaroring", str(tmp_path))
    official = acquire_pirelli_context_spike("https://example.invalid/not-fetched")

    assert historical == {
        "status": "ABSENT",
        "season": None,
        "reason": "no_compatible_context_ingested",
    }
    assert official is None


def test_regulation_discontinuity_is_explicitly_limited() -> None:
    assert historical_comparability(2025, 2026) == "LIMITED"
    assert historical_comparability(2026, 2026) == "NORMAL"
    assert historical_comparability(2024, 2026) == "INCOMPATIBLE"


def test_backtest_never_publishes_canned_quality_metrics() -> None:
    result = BacktestHarness(["development"], ["holdout"]).evaluate_session("missing.json")

    assert result.to_payload() == {
        "status": "NOT_IMPLEMENTED",
        "metrics": None,
        "reason": (
            "No deterministic archived-session evaluator is implemented; "
            "quality metrics are unavailable."
        ),
    }
