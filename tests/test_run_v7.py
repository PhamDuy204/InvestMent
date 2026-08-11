import numpy as np
import pandas as pd
import pytest

from crypto_research.reliability_v7 import ReliabilityGateConfig
from crypto_research.run_v6 import replay_weight_overlay
from crypto_research.run_v7 import replay_v7_reliability


def _toy_log():
    return pd.DataFrame(
        {
            "decision_timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00Z",
                    "2026-01-01T00:00Z",
                    "2026-01-01T12:00Z",
                    "2026-01-01T12:00Z",
                ]
            ),
            "symbol": ["A", "B", "A", "B"],
            "previous_weight": [0.0, 0.0, 0.0, 0.0],
            "target_weight": [0.2, -0.2, 0.2, -0.2],
            "holding_return_label": [0.02, -0.01, -0.03, 0.01],
            "funding_sum_label": [0.0, 0.0, 0.0, 0.0],
            "effective_score": [0.01, -0.01, 0.01, -0.01],
            "qh_order_imbalance": [0.0, 0.0, 0.0, 0.0],
            "dispersion_iqr": [0.01, 0.01, 0.01, 0.01],
        }
    )


def test_disabled_v7_gates_match_v6_control_replay():
    log = _toy_log()
    v6_periods, _, v6_metrics = replay_weight_overlay(
        log,
        scale_fn=lambda row: 1.0,
        round_trip_cost_bps=10.0,
    )
    v7_periods, _, v7_metrics = replay_v7_reliability(
        log,
        ReliabilityGateConfig(None, None, None, False),
        round_trip_cost_bps=10.0,
    )
    for column in (
        "gross_return",
        "funding_return",
        "transaction_cost",
        "net_return",
        "turnover",
        "gross_exposure",
        "net_exposure",
    ):
        np.testing.assert_allclose(v7_periods[column], v6_periods[column], atol=1e-14, rtol=0.0)
    for key in ("net_return", "sharpe", "max_drawdown", "turnover", "transaction_cost"):
        assert v7_metrics[key] == pytest.approx(v6_metrics[key], abs=1e-14)


def test_v7_replay_uses_candidate_drifted_state_not_baseline_previous_column():
    log = pd.DataFrame(
        {
            "decision_timestamp": pd.to_datetime(["2026-01-01T00:00Z", "2026-01-01T12:00Z"]),
            "symbol": ["A", "A"],
            "previous_weight": [0.0, 0.0],
            "target_weight": [0.2, 0.3],
            "holding_return_label": [0.10, 0.0],
            "funding_sum_label": [0.0, 0.0],
            "effective_score": [0.05, 0.05],
            "qh_order_imbalance": [0.0, 0.0],
            "dispersion_iqr": [0.0, 0.05],
        }
    )
    cfg = ReliabilityGateConfig(None, 0.01, None, False, high_dispersion_scale=0.5)
    _, decisions, _ = replay_v7_reliability(log, cfg, round_trip_cost_bps=0.0)
    second = decisions.iloc[1]
    expected_drift = 0.2 * 1.10 / 1.02
    expected_target = expected_drift + 0.5 * (0.3 - expected_drift)
    assert second["current_weight"] == pytest.approx(expected_drift)
    assert second["current_weight"] != log.iloc[1]["previous_weight"]
    assert second["proposed_target_weight"] == pytest.approx(expected_target)
