import json

import numpy as np
import pandas as pd

from crypto_research.run_v6 import replay_weight_overlay, select_incremental_module


def _toy_log():
    return pd.DataFrame(
        {
            "decision_timestamp": pd.to_datetime(
                ["2026-01-01T00:00Z", "2026-01-01T00:00Z", "2026-01-01T12:00Z", "2026-01-01T12:00Z"]
            ),
            "symbol": ["A", "B", "A", "B"],
            "previous_weight": [0.0, 0.0, 0.2, -0.2],
            "target_weight": [0.2, -0.2, 0.2, -0.2],
            "holding_return_label": [0.02, -0.01, -0.03, 0.01],
            "funding_sum_label": [0.0, 0.0, 0.0, 0.0],
            "effective_score": [0.01, -0.01, 0.01, -0.01],
            "vol_state": ["low", "low", "high", "high"],
            "burst_probability": [0.0, 0.0, 0.0, 0.0],
            "flow_state": ["neutral"] * 4,
        }
    )


def test_module_is_rejected_when_return_gain_is_only_complexity_cost():
    baseline = {"net_return": 0.10, "sharpe": 1.0, "max_drawdown": 0.10}
    candidate = {"net_return": 0.101, "sharpe": 1.0, "max_drawdown": 0.10}
    assert not select_incremental_module(baseline, candidate, penalty=0.002)


def test_module_can_survive_when_return_and_sharpe_improve_without_dd_damage():
    baseline = {"net_return": 0.10, "sharpe": 1.0, "max_drawdown": 0.10}
    candidate = {"net_return": 0.12, "sharpe": 1.1, "max_drawdown": 0.09}
    assert select_incremental_module(baseline, candidate, penalty=0.002)


def test_overlay_never_flips_baseline_direction_and_recomputes_cost():
    log = _toy_log()
    periods, decisions, metrics = replay_weight_overlay(
        log,
        scale_fn=lambda row: 0.5 if row.vol_state == "high" else 1.0,
        round_trip_cost_bps=10.0,
    )
    merged = decisions.merge(log[["decision_timestamp", "symbol", "target_weight"]], on=["decision_timestamp", "symbol"])
    signs_match = np.sign(merged["proposed_target_weight"]) * np.sign(merged["target_weight"]) >= 0
    assert signs_match.all()
    assert (periods["transaction_cost"] >= 0).all()
    assert metrics["turnover"] > 0
    assert all(isinstance(json.loads(text), dict) for text in periods["weights_json"])
