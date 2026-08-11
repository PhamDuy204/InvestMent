import numpy as np
import pandas as pd
import pytest

from crypto_research.features_v7 import (
    build_cross_sectional_dispersion,
    build_qh_opening_imbalance,
    previous_completed_quarter_open,
    signed_aggressor_volume,
)


def test_aggressor_sign_mapping():
    assert signed_aggressor_volume(3.0, True) == -3.0
    assert signed_aggressor_volume(3.0, False) == 3.0


def test_previous_quarter_boundary_uses_previous_completed_quarter():
    decision = pd.Timestamp("2026-01-01T04:00:00Z")
    assert previous_completed_quarter_open(decision) == pd.Timestamp("2026-01-01T03:45:00Z")


def test_qh_feature_never_uses_current_quarter():
    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T03:45:00Z",
                    "2026-01-01T03:45:09Z",
                    "2026-01-01T04:00:00Z",
                    "2026-01-01T04:00:09Z",
                ]
            ),
            "symbol": ["BTCUSDT"] * 4,
            "quantity": [1.0, 3.0, 1000.0, 1000.0],
            "isBuyerMaker": [False, True, False, False],
        }
    )
    decisions = pd.DataFrame(
        {"decision_timestamp": pd.to_datetime(["2026-01-01T04:00:00Z"]), "symbol": ["BTCUSDT"]}
    )
    out = build_qh_opening_imbalance(trades, decisions, opening_seconds=10)
    assert out.loc[0, "qh_window_start"] == pd.Timestamp("2026-01-01T03:45:00Z")
    assert out.loc[0, "qh_window_end"] == pd.Timestamp("2026-01-01T03:45:10Z")
    assert out.loc[0, "qh_trade_count"] == 2
    assert out.loc[0, "qh_order_imbalance"] == pytest.approx(-0.5)
    assert out.loc[0, "qh_abs_order_imbalance"] == pytest.approx(0.5)


def test_future_trade_mutation_does_not_change_qh_feature():
    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-01T03:45:00Z", "2026-01-01T04:00:00Z"]),
            "symbol": ["BTCUSDT", "BTCUSDT"],
            "quantity": [2.0, 1.0],
            "isBuyerMaker": [False, False],
        }
    )
    decisions = pd.DataFrame(
        {"decision_timestamp": pd.to_datetime(["2026-01-01T04:00:00Z"]), "symbol": ["BTCUSDT"]}
    )
    before = build_qh_opening_imbalance(trades, decisions)
    changed = trades.copy()
    changed.loc[changed["timestamp"] >= decisions.loc[0, "decision_timestamp"], "quantity"] = 999999.0
    after = build_qh_opening_imbalance(changed, decisions)
    pd.testing.assert_frame_equal(before, after)


def test_dispersion_uses_only_current_eligible_universe():
    panel = pd.DataFrame(
        {
            "decision_timestamp": pd.to_datetime(["2026-01-01T00:00Z"] * 4),
            "symbol": ["A", "B", "C", "D"],
            "ret_12": [0.01, 0.02, 0.05, 0.90],
            "in_universe": [True, True, True, False],
        }
    )
    out = build_cross_sectional_dispersion(panel)
    expected = np.quantile([0.01, 0.02, 0.05], 0.75) - np.quantile([0.01, 0.02, 0.05], 0.25)
    assert out.loc[0, "dispersion_iqr"] == pytest.approx(expected)
    assert out.loc[0, "eligible_symbol_count"] == 3


def test_future_dispersion_mutation_does_not_change_prior_state():
    panel = pd.DataFrame(
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
            "ret_12": [0.01, 0.03, 0.02, 0.04],
            "in_universe": [True, True, True, True],
        }
    )
    before = build_cross_sectional_dispersion(panel)
    changed = panel.copy()
    changed.loc[changed["decision_timestamp"] == pd.Timestamp("2026-01-01T12:00Z"), "ret_12"] = [10.0, -10.0]
    after = build_cross_sectional_dispersion(changed)
    pd.testing.assert_frame_equal(before.iloc[:1].reset_index(drop=True), after.iloc[:1].reset_index(drop=True))
