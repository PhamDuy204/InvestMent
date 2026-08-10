import pandas as pd

from crypto_research.aggtrades_v3 import build_quarter_hour_features


def test_quarter_hour_features_only_use_early_window():
    q = pd.Timestamp("2026-07-01T00:00:00Z")
    frame = pd.DataFrame({"timestamp": [q + pd.Timedelta(seconds=5), q + pd.Timedelta(seconds=20)], "price": [100.0, 101.0], "notional": [100.0, 200.0], "signed_notional": [100.0, -200.0]})
    out = build_quarter_hour_features(frame)
    assert out.loc[0, "trade_count_10s"] == 1
    assert out.loc[0, "trade_count_30s"] == 2
    assert out.loc[0, "notional_10s"] == 100.0


def test_feature_rows_are_quarter_aligned():
    q = pd.Timestamp("2026-07-01T00:15:00Z")
    frame = pd.DataFrame({"timestamp": [q + pd.Timedelta(seconds=1)], "price": [1.0], "notional": [2.0], "signed_notional": [2.0]})
    out = build_quarter_hour_features(frame)
    assert out.loc[0, "timestamp"] == q
