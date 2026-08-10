from __future__ import annotations

import numpy as np
import pandas as pd


def _rolling_z(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window, min_periods=max(5, window // 5)).mean()
    std = series.rolling(window, min_periods=max(5, window // 5)).std(ddof=0).replace(0.0, np.nan)
    return (series - mean) / std


def _single_symbol_features(group: pd.DataFrame) -> pd.DataFrame:
    frame = group.sort_values("timestamp").copy()
    close = pd.to_numeric(frame["close"], errors="coerce")
    high = pd.to_numeric(frame["high"], errors="coerce")
    low = pd.to_numeric(frame["low"], errors="coerce")
    quote = pd.to_numeric(frame["quote_volume"], errors="coerce")
    trades = pd.to_numeric(frame["trade_count"], errors="coerce")
    taker_buy_quote = pd.to_numeric(frame["taker_buy_quote_volume"], errors="coerce")
    frame["ret_1m"] = close.pct_change(1, fill_method=None)
    for horizon in (5, 15, 60):
        frame[f"ret_{horizon}m"] = close.pct_change(horizon, fill_method=None)
    frame["rv_15m"] = frame["ret_1m"].rolling(15, min_periods=5).std(ddof=0) * np.sqrt(15)
    frame["rv_60m"] = frame["ret_1m"].rolling(60, min_periods=15).std(ddof=0) * np.sqrt(60)
    frame["range_pct_1m"] = high / low.replace(0.0, np.nan) - 1.0
    frame["quote_volume_z60"] = _rolling_z(quote, 60)
    frame["trade_count_z60"] = _rolling_z(trades, 60)
    frame["quote_volume_z1440"] = _rolling_z(quote, 1440)
    frame["trade_count_z1440"] = _rolling_z(trades, 1440)
    buy_share = (taker_buy_quote / quote.replace(0.0, np.nan)).clip(0.0, 1.0)
    frame["taker_buy_share"] = buy_share
    frame["taker_sell_share"] = 1.0 - buy_share
    frame["taker_imbalance"] = 2.0 * buy_share - 1.0
    frame["taker_imbalance_5m"] = frame["taker_imbalance"].rolling(5, min_periods=1).mean()
    frame["taker_imbalance_accel"] = frame["taker_imbalance_5m"].diff()
    frame["avg_trade_quote"] = quote / trades.replace(0.0, np.nan)
    frame["volume_accel_15m"] = quote / quote.rolling(15, min_periods=5).mean().replace(0.0, np.nan) - 1.0
    timestamp = pd.to_datetime(frame["timestamp"], utc=True)
    minute_of_day = timestamp.dt.hour * 60 + timestamp.dt.minute
    frame["clock_sin"] = np.sin(2.0 * np.pi * minute_of_day / 1440.0)
    frame["clock_cos"] = np.cos(2.0 * np.pi * minute_of_day / 1440.0)
    quarter_phase = timestamp.dt.minute % 15
    frame["quarter_phase_sin"] = np.sin(2.0 * np.pi * quarter_phase / 15.0)
    frame["quarter_phase_cos"] = np.cos(2.0 * np.pi * quarter_phase / 15.0)
    frame["is_quarter_open"] = (quarter_phase == 0).astype(int)
    return frame


def build_burst_features(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "symbol", "open", "high", "low", "close", "quote_volume", "trade_count", "taker_buy_quote_volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing burst feature columns: {sorted(missing)}")
    work = frame.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    parts = [_single_symbol_features(group) for _, group in work.groupby("symbol", sort=False)]
    result = pd.concat(parts, ignore_index=True).sort_values(["timestamp", "symbol"]).reset_index(drop=True)
    by_time = result.groupby("timestamp", sort=False)["ret_1m"]
    result["market_ret_1m"] = by_time.transform("mean")
    result["cross_asset_dispersion_1m"] = by_time.transform("std").fillna(0.0)
    result["breadth_positive_1m"] = result["ret_1m"].gt(0).groupby(result["timestamp"]).transform("mean")
    keep = ["timestamp", "symbol", "ret_1m", "ret_5m", "ret_15m", "ret_60m", "rv_15m", "rv_60m", "range_pct_1m", "quote_volume_z60", "trade_count_z60", "quote_volume_z1440", "trade_count_z1440", "taker_buy_share", "taker_sell_share", "taker_imbalance", "taker_imbalance_5m", "taker_imbalance_accel", "avg_trade_quote", "volume_accel_15m", "clock_sin", "clock_cos", "quarter_phase_sin", "quarter_phase_cos", "is_quarter_open", "market_ret_1m", "cross_asset_dispersion_1m", "breadth_positive_1m"]
    return result[keep]


def _future_extreme(series: pd.Series, horizon: int, operation: str) -> pd.Series:
    shifted = series.shift(-1)
    rolling = getattr(shifted.rolling(horizon, min_periods=horizon), operation)()
    return rolling.shift(-(horizon - 1))


def _single_symbol_labels(group: pd.DataFrame, horizon: int) -> pd.DataFrame:
    frame = group.sort_values("timestamp").copy()
    close = pd.to_numeric(frame["close"], errors="coerce")
    high = pd.to_numeric(frame["high"], errors="coerce")
    low = pd.to_numeric(frame["low"], errors="coerce")
    future_close = close.shift(-horizon)
    future_high = _future_extreme(high, horizon, "max")
    future_low = _future_extreme(low, horizon, "min")
    future_return = future_close / close - 1.0
    future_range = future_high / future_low.replace(0.0, np.nan) - 1.0
    past_20m_return = close / close.shift(horizon) - 1.0
    return_scale = past_20m_return.rolling(1440, min_periods=1440).std(ddof=0)
    past_high = high.rolling(horizon, min_periods=horizon).max()
    past_low = low.rolling(horizon, min_periods=horizon).min()
    past_range = past_high / past_low.replace(0.0, np.nan) - 1.0
    range_scale = past_range.rolling(1440, min_periods=1440).median()
    return_threshold = pd.Series(np.maximum(0.01, 3.0 * return_scale), index=frame.index)
    range_threshold = pd.Series(np.maximum(0.015, 4.0 * range_scale), index=frame.index)
    jackpot = future_return.abs().ge(return_threshold) & future_range.ge(range_threshold)
    direction = np.sign(future_return).where(jackpot, 0).fillna(0).astype(int)
    return pd.DataFrame({"timestamp": frame["timestamp"], "symbol": frame["symbol"], f"future_return_{horizon}m": future_return, f"future_range_{horizon}m": future_range, "jackpot": jackpot.fillna(False), "jackpot_direction": direction, "jackpot_return_threshold": return_threshold, "jackpot_range_threshold": range_threshold})


def make_burst_labels(frame: pd.DataFrame, *, horizon_minutes: int = 20) -> pd.DataFrame:
    if horizon_minutes <= 0:
        raise ValueError("horizon_minutes must be positive")
    required = {"timestamp", "symbol", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing burst label columns: {sorted(missing)}")
    work = frame.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    parts = [_single_symbol_labels(group, horizon_minutes) for _, group in work.groupby("symbol", sort=False)]
    return pd.concat(parts, ignore_index=True).sort_values(["timestamp", "symbol"]).reset_index(drop=True)
