import numpy as np
import pandas as pd
import pytest

from crypto_research.multi_asset_v3 import (
    PortfolioCaps,
    cost_aware_target,
    rebalance_cost,
    rolling_lower_bound,
    turnover,
)
from crypto_research.run_v3 import select_inner_trial, v3_cost_configs


def test_round_trip_cost_split_across_one_way_legs():
    prev = np.array([0.0, 0.0])
    target = np.array([0.5, -0.5])
    assert turnover(prev, target) == pytest.approx(1.0)
    assert rebalance_cost(prev, target, 10.0) == pytest.approx(0.0005)
    assert rebalance_cost(prev, target, 10.0, include_final_unwind=True) == pytest.approx(0.001)


def test_unchanged_position_has_no_rebalance_cost():
    w = np.array([0.25, -0.25])
    assert rebalance_cost(w, w, 10.0) == 0.0


def test_target_respects_caps():
    mu = np.array([0.2, -0.1, 0.3])
    cov = np.eye(3) * 0.01
    w = cost_aware_target(mu, cov, np.zeros(3), 30.0, 0.01, caps=PortfolioCaps())
    assert np.abs(w).sum() <= 1.0 + 1e-12
    assert abs(w.sum()) <= 0.05 + 1e-12
    assert np.abs(w).max() <= 0.25 + 1e-12


def test_uncertainty_bound_is_strictly_causal():
    pred = pd.Series([1.0, 1.0, 1.0, 1.0])
    realized = pd.Series([0.0, 0.0, 100.0, 0.0])
    bound = rolling_lower_bound(pred, realized, window=2, quantile=0.5, min_history=1)
    assert np.isnan(bound.iloc[0])
    assert bound.iloc[2] == pytest.approx(0.0)


def test_v3_grid_has_32_configs():
    assert len(v3_cost_configs()) == 32


def test_inner_selector_rejects_sparse_winner():
    trials = pd.DataFrame({"net_return": [10.0, 2.0], "trade_count": [10, 250]})
    chosen = select_inner_trial(trials, min_trades=200)
    assert chosen["net_return"] == 2.0
