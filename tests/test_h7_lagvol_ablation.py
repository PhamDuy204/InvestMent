from pathlib import Path

import pandas as pd
import pytest

from scripts.run_v7_h7_lagvol_ablation import _fit, _gross_exposure_stats


def test_h7_fit_is_lag_rv_only_even_if_basis_changes() -> None:
    base = pd.DataFrame(
        {
            "lag_rv12": [0.01, 0.02, 0.03, 0.04],
            "future_rv12": [0.015, 0.021, 0.028, 0.034],
            "abs_basis": [0.0001, 0.0002, 0.0003, 0.0004],
        }
    )
    mutated = base.copy()
    mutated["abs_basis"] = [50.0, 0.0, 100.0, 1.0]

    assert _fit(base) == _fit(mutated)


def test_h7_gross_exposure_stats_aggregate_absolute_proposed_weights_by_timestamp() -> None:
    decisions = pd.DataFrame(
        {
            "decision_timestamp": [
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
                "2026-01-01T12:00:00Z",
                "2026-01-01T12:00:00Z",
            ],
            "proposed_target_weight": [0.20, -0.10, 0.05, -0.05],
        }
    )

    stats = _gross_exposure_stats(decisions)
    assert stats["mean_gross_exposure"] == pytest.approx(0.20)
    assert stats["median_gross_exposure"] == pytest.approx(0.20)
    assert stats["max_gross_exposure"] == pytest.approx(0.30)


def test_h7_runner_declares_required_fold_metrics_and_research_memory_outputs() -> None:
    source = Path("scripts/run_v7_h7_lagvol_ablation.py").read_text(encoding="utf-8")
    required_tokens = (
        '"candidate_selection_metrics"',
        '"baseline_evaluation_metrics"',
        '"candidate_evaluation_metrics"',
        '"cost20_metrics"',
        '"delay1h_metrics"',
        '"comparison_to_h6"',
        '"baseline_gross_exposure"',
        '"candidate_gross_exposure"',
        '"h7_decision_error_summary.json"',
        '"failure_ledger.csv.gz"',
        '"hypothesis_registry.jsonl"',
        '"agent_research_log.jsonl"',
    )
    for token in required_tokens:
        assert token in source
