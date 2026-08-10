from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from .aggtrades_v3 import build_quarter_hour_features, load_daily_aggtrades


def build_pilot(symbols: Iterable[str], dates: Iterable[str], cache_dir=None) -> pd.DataFrame:
    """Download and aggregate a small Binance aggTrades pilot, never live orders."""
    rows = []
    for symbol in symbols:
        for date in dates:
            trades = load_daily_aggtrades(symbol, date, cache_dir=cache_dir)
            features = build_quarter_hour_features(trades)
            features["symbol"] = symbol
            features["date"] = date
            rows.append(features)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
