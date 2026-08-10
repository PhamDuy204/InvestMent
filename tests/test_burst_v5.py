import pandas as pd

from crypto_research.binance_archive import _timeframe_ms
from crypto_research.burst_v5 import build_burst_features, make_burst_labels


def _bars(n=1600):
    ts = pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC")
    price = pd.Series([100.0 + i * 0.001 for i in range(n)])
    return pd.DataFrame({"timestamp": ts, "symbol": "BTCUSDT", "open": price, "high": price + 0.02, "low": price - 0.02, "close": price, "volume": 10.0, "quote_volume": 1000.0, "trade_count": 100, "taker_buy_volume": 5.0, "taker_buy_quote_volume": 500.0})


def test_one_minute_timeframe_supported():
    assert _timeframe_ms("1m") == 60_000


def test_burst_features_are_causal_to_future_mutations():
    bars = _bars()
    base = build_burst_features(bars)
    changed = bars.copy()
    changed.loc[1201:, ["open", "high", "low", "close", "volume", "quote_volume"]] *= 9.0
    mutated = build_burst_features(changed)
    cols = [c for c in base.columns if c not in {"timestamp", "symbol"}]
    pd.testing.assert_frame_equal(base.loc[:1200, cols], mutated.loc[:1200, cols])


def test_burst_labels_detect_large_future_move_without_entering_features():
    bars = _bars()
    bars.loc[1500:1520, "close"] = [100.0 + i * 0.2 for i in range(21)]
    bars.loc[1500:1520, "high"] = bars.loc[1500:1520, "close"] + 0.2
    labels = make_burst_labels(bars, horizon_minutes=20)
    assert labels.loc[1499, "jackpot"]
    assert labels.loc[1499, "jackpot_direction"] == 1
    features = build_burst_features(_bars())
    assert not any(c.startswith("future_") or c.startswith("jackpot") for c in features.columns)
