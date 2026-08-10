import json

import pandas as pd

from crypto_research.multi_asset_v3 import cost_aware_cross_sectional_backtest


def _panel(*, funding_a: float = 0.0) -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-01", periods=20, freq="h", tz="UTC")
    rows = []
    for timestamp in timestamps:
        rows.extend([
            {"timestamp": timestamp, "symbol": "A", "open": 100.0, "close": 100.0, "ret_1": 0.0, "model_score": 0.02, "funding_rate": funding_a, "funding_event_rate": 0.0, "in_universe": True},
            {"timestamp": timestamp, "symbol": "B", "open": 100.0, "close": 100.0, "ret_1": 0.0, "model_score": -0.02, "funding_rate": 0.0, "funding_event_rate": 0.0, "in_universe": True},
        ])
    return pd.DataFrame(rows)


def _run(panel, **overrides):
    kwargs = dict(score_col="model_score", horizon=4, round_trip_cost_bps=10.0, risk_aversion=1.0, movement_penalty=0.0, covariance_lookback=0, gross_cap=1.0, net_cap=1.0, single_cap=0.5)
    kwargs.update(overrides)
    return cost_aware_cross_sectional_backtest(panel, **kwargs)[0]


def test_zero_no_trade_band_reproduces_default_weights():
    baseline = _run(_panel())
    explicit = _run(_panel(), min_abs_weight_change=0.0)
    assert baseline["weights_json"].tolist() == explicit["weights_json"].tolist()
    assert baseline["transaction_cost"].tolist() == explicit["transaction_cost"].tolist()


def test_no_trade_band_suppresses_small_target_change():
    periods = _run(_panel(), min_abs_weight_change=0.03)
    assert json.loads(periods.iloc[0]["weights_json"]) == {"A": 0.0, "B": 0.0}
    assert periods.iloc[0]["turnover"] == 0.0


def test_adverse_funding_filter_blocks_paying_side():
    first = json.loads(_run(_panel(funding_a=0.001), adverse_funding_threshold=0.0002).iloc[0]["weights_json"])
    assert first["A"] == 0.0
    assert first["B"] < 0.0
