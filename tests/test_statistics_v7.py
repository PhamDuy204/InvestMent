import numpy as np
import pandas as pd

from crypto_research.statistics_v7 import (
    approximate_dsr,
    block_bootstrap_equity,
    cscv_pbo,
)


def test_block_bootstrap_is_reproducible():
    returns = pd.Series([0.01, -0.005, 0.002, 0.004] * 20)
    left = block_bootstrap_equity(returns, samples=100, block_length=4, seed=42)
    right = block_bootstrap_equity(returns, samples=100, block_length=4, seed=42)
    assert left == right
    assert 0.0 <= left["probability_final_equity_below_one"] <= 1.0


def test_pbo_is_bounded_and_not_labeled_cpcv():
    matrix = pd.DataFrame(
        {
            "a": np.linspace(-0.01, 0.02, 80),
            "b": np.linspace(0.01, -0.01, 80),
            "c": np.sin(np.arange(80)) / 100.0,
        }
    )
    result = cscv_pbo(matrix, segments=8)
    assert 0.0 <= result["pbo"] <= 1.0
    assert result["segments"] == 8
    assert result["status"] == "CSCV_PBO_NOT_CPCV"


def test_approximate_dsr_marks_incomplete_trial_history():
    result = approximate_dsr(
        observed_sharpe=1.0,
        trial_sharpes=[0.5, 0.8, 1.0],
        observations=200,
        total_trial_count=860,
    )
    assert "INCOMPLETE" in result["status"]
    assert result["total_trial_count"] == 860
    assert result["available_trial_sharpes"] == 3
    assert 0.0 <= result["probability"] <= 1.0
