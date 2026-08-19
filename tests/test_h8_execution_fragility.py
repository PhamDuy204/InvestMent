from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.run_v8_h8_execution_fragility import (
    _forecast_admission,
    _prepare_registry,
    _rmse,
)


def test_prepare_registry_copies_v7_history_and_requires_tail_868(tmp_path: Path) -> None:
    source = tmp_path / "v7.csv"
    target = tmp_path / "v8.csv"
    pd.DataFrame(
        {
            "trial_number": list(range(858, 869)),
            "trial_id": [f"v7-{n}" for n in range(858, 869)],
            "phase": ["x"] * 11,
            "stage": ["x"] * 11,
            "hypothesis": ["x"] * 11,
            "status": ["x"] * 11,
            "config_hash": ["x"] * 11,
            "metrics_json": ["{}"] * 11,
            "timestamp_utc": ["2026-01-01T00:00:00Z"] * 11,
        }
    ).to_csv(source, index=False)

    _prepare_registry(source, target)

    copied = pd.read_csv(target)
    assert copied["trial_number"].tolist() == list(range(858, 869))


def test_prepare_registry_refuses_wrong_inherited_tail(tmp_path: Path) -> None:
    source = tmp_path / "v7.csv"
    pd.DataFrame({"trial_number": [867]}).to_csv(source, index=False)

    with pytest.raises(ValueError, match="868"):
        _prepare_registry(source, tmp_path / "v8.csv")


def test_forecast_admission_requires_two_rmse_wins_and_two_positive_slopes() -> None:
    folds = [
        {"baseline_rmse": 2.0, "augmented_rmse": 1.0, "impact_slope": 0.1},
        {"baseline_rmse": 2.0, "augmented_rmse": 1.5, "impact_slope": 0.2},
        {"baseline_rmse": 1.0, "augmented_rmse": 1.2, "impact_slope": -0.1},
    ]
    assert _forecast_admission(folds)
    folds[1]["impact_slope"] = -0.2
    assert not _forecast_admission(folds)


def test_rmse_is_zero_for_exact_predictions() -> None:
    assert _rmse([1.0, 2.0], [1.0, 2.0]) == 0.0
