from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

FACTOR_COLUMNS = [
    "ret_1",
    "ret_4",
    "ret_12",
    "ret_24",
    "ret_72",
    "ret_168",
    "reversal_1",
    "realized_vol_24",
    "range_pct",
    "quote_volume_z24",
    "trade_count_z24",
    "taker_buy_ratio",
    "taker_imbalance",
    "taker_imbalance_4",
    "avg_trade_size",
    "price_impact_proxy",
    "funding_rate",
    "funding_z168",
    "funding_accel",
    "market_ret_1",
    "market_ret_4",
    "relative_ret_1",
    "relative_ret_4",
    "btc_ret_1_lag1",
    "btc_ret_4_lag1",
    "eth_ret_1_lag1",
    "eth_ret_4_lag1",
    "cross_sectional_dispersion",
    "market_breadth_positive",
    "momentum_rank_4",
    "momentum_rank_24",
    "reversal_rank_1",
    "taker_rank",
    "funding_rank",
    "liquidity_rank",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
    "is_weekend",
    "is_asia_session",
    "is_london_session",
    "is_us_session",
    "is_funding_hour",
]

_REQUIRED_MARKET_COLUMNS = {
    "timestamp",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "trade_count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
}


def _rolling_z(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window, min_periods=max(4, window // 4)).mean()
    std = series.rolling(window, min_periods=max(4, window // 4)).std()
    return (series - mean) / std.replace(0.0, np.nan)


def build_factor_panel(
    raw: pd.DataFrame,
    funding: pd.DataFrame | None = None,
    *,
    horizons: Iterable[int] = (4, 8, 12),
) -> pd.DataFrame:
    missing = _REQUIRED_MARKET_COLUMNS.difference(raw.columns)
    if missing:
        raise ValueError(f"missing market columns: {sorted(missing)}")
    horizons = tuple(int(h) for h in horizons)
    if not horizons or any(h <= 0 for h in horizons):
        raise ValueError("horizons must contain positive integers")

    out = raw.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    out = out.sort_values(["symbol", "timestamp"]).drop_duplicates(["symbol", "timestamp"], keep="last").reset_index(drop=True)
    numeric = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "taker_buy_volume",
        "taker_buy_quote_volume",
    ]
    for column in numeric:
        out[column] = pd.to_numeric(out[column], errors="raise").astype(float)

    grouped = out.groupby("symbol", sort=False, group_keys=False)
    for lag in (1, 4, 12, 24, 72, 168):
        out[f"ret_{lag}"] = grouped["close"].pct_change(lag, fill_method=None)
    out["reversal_1"] = -out["ret_1"]
    out["realized_vol_24"] = out["ret_1"].groupby(out["symbol"]).transform(
        lambda s: s.rolling(24, min_periods=8).std()
    )
    out["range_pct"] = (out["high"] - out["low"]) / out["close"].replace(0.0, np.nan)
    out["quote_volume_z24"] = out["quote_volume"].groupby(out["symbol"]).transform(lambda s: _rolling_z(s, 24))
    out["trade_count_z24"] = out["trade_count"].groupby(out["symbol"]).transform(lambda s: _rolling_z(s, 24))
    out["taker_buy_ratio"] = out["taker_buy_quote_volume"] / out["quote_volume"].replace(0.0, np.nan)
    out["taker_imbalance"] = 2.0 * out["taker_buy_ratio"] - 1.0
    out["taker_imbalance_4"] = out["taker_imbalance"].groupby(out["symbol"]).transform(
        lambda s: s.rolling(4, min_periods=1).mean()
    )
    out["avg_trade_size"] = out["quote_volume"] / out["trade_count"].replace(0.0, np.nan)
    out["price_impact_proxy"] = out["ret_1"].abs() / np.log1p(out["quote_volume"].clip(lower=0.0))

    if funding is not None and not funding.empty:
        funding_frame = funding[["timestamp", "symbol", "funding_rate"]].copy()
        funding_frame["timestamp"] = pd.to_datetime(funding_frame["timestamp"], utc=True, format="mixed").dt.floor("h")
        funding_frame["funding_rate"] = pd.to_numeric(funding_frame["funding_rate"], errors="raise").astype(float)
        funding_frame = funding_frame.groupby(["timestamp", "symbol"], as_index=False, sort=False)["funding_rate"].sum().rename(columns={"funding_rate": "funding_event_rate"})
        out = out.merge(funding_frame, on=["timestamp", "symbol"], how="left")
        out["funding_event_rate"] = out["funding_event_rate"].fillna(0.0)
        out["funding_rate"] = out["funding_event_rate"].replace(0.0, np.nan)
        out["funding_rate"] = out.groupby("symbol", sort=False)["funding_rate"].ffill().fillna(0.0)
    else:
        out["funding_event_rate"] = 0.0
        out["funding_rate"] = 0.0
    out["funding_z168"] = out["funding_rate"].groupby(out["symbol"]).transform(lambda s: _rolling_z(s, 168))
    out["funding_accel"] = out["funding_rate"].groupby(out["symbol"]).diff()

    by_time = out.groupby("timestamp", sort=False)
    out["market_ret_1"] = by_time["ret_1"].transform("mean")
    out["market_ret_4"] = by_time["ret_4"].transform("mean")
    out["relative_ret_1"] = out["ret_1"] - out["market_ret_1"]
    out["relative_ret_4"] = out["ret_4"] - out["market_ret_4"]
    out["cross_sectional_dispersion"] = by_time["ret_1"].transform("std")
    out["market_breadth_positive"] = by_time["ret_1"].transform(lambda s: float((s > 0).mean()))

    for source, destination, ascending in (
        ("ret_4", "momentum_rank_4", True),
        ("ret_24", "momentum_rank_24", True),
        ("reversal_1", "reversal_rank_1", True),
        ("taker_imbalance_4", "taker_rank", True),
        ("funding_rate", "funding_rank", True),
        ("quote_volume", "liquidity_rank", True),
    ):
        out[destination] = out.groupby("timestamp", sort=False)[source].rank(pct=True, ascending=ascending)

    for symbol, prefix in (("BTCUSDT", "btc"), ("ETHUSDT", "eth")):
        lead = out.loc[out["symbol"] == symbol, ["timestamp", "ret_1", "ret_4"]].copy()
        lead["ret_1"] = lead["ret_1"].shift(1)
        lead["ret_4"] = lead["ret_4"].shift(1)
        lead = lead.rename(columns={"ret_1": f"{prefix}_ret_1_lag1", "ret_4": f"{prefix}_ret_4_lag1"})
        out = out.merge(lead, on="timestamp", how="left")

    hour = out["timestamp"].dt.hour.astype(float)
    dow = out["timestamp"].dt.dayofweek.astype(float)
    out["hour_sin"] = np.sin(2.0 * np.pi * hour / 24.0)
    out["hour_cos"] = np.cos(2.0 * np.pi * hour / 24.0)
    out["dow_sin"] = np.sin(2.0 * np.pi * dow / 7.0)
    out["dow_cos"] = np.cos(2.0 * np.pi * dow / 7.0)
    out["is_weekend"] = (dow >= 5).astype(float)
    out["is_asia_session"] = ((hour >= 0) & (hour < 8)).astype(float)
    out["is_london_session"] = ((hour >= 7) & (hour < 16)).astype(float)
    out["is_us_session"] = ((hour >= 13) & (hour < 22)).astype(float)
    out["is_funding_hour"] = out["timestamp"].dt.hour.isin([0, 8, 16]).astype(float)

    grouped = out.groupby("symbol", sort=False, group_keys=False)
    entry_open = grouped["open"].shift(-1)
    for horizon in horizons:
        exit_close = grouped["close"].shift(-horizon)
        out[f"future_return_{horizon}"] = exit_close / entry_open - 1.0
        out[f"future_residual_return_{horizon}"] = out[f"future_return_{horizon}"] - out.groupby("timestamp", sort=False)[f"future_return_{horizon}"].transform("mean")
        out[f"future_rank_{horizon}"] = out.groupby("timestamp", sort=False)[f"future_return_{horizon}"].rank(pct=True)

    out[FACTOR_COLUMNS] = out[FACTOR_COLUMNS].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return out.sort_values(["timestamp", "symbol"]).reset_index(drop=True)


def rolling_universe(panel: pd.DataFrame, *, top_n: int, lookback_hours: int = 24 * 30, min_history_hours: int = 24 * 90) -> pd.Series:
    if top_n <= 0 or lookback_hours <= 0 or min_history_hours <= 0:
        raise ValueError("universe parameters must be positive")
    work = panel[["timestamp", "symbol", "quote_volume"]].copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    work["_original_index"] = np.arange(len(work))
    work = work.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    work["history_count"] = work.groupby("symbol", sort=False).cumcount() + 1
    min_periods = min(lookback_hours, min_history_hours)
    work["trailing_liquidity"] = work.groupby("symbol", sort=False)["quote_volume"].transform(lambda s: s.rolling(lookback_hours, min_periods=min_periods).mean())
    work["liquidity_position"] = work.groupby("timestamp", sort=False)["trailing_liquidity"].rank(method="first", ascending=False)
    work["in_universe"] = (work["history_count"] >= min_history_hours) & work["trailing_liquidity"].notna() & (work["liquidity_position"] <= top_n)
    return work.sort_values("_original_index")["in_universe"].reset_index(drop=True)


def _safe_profit_factor(returns: pd.Series) -> float | None:
    wins = float(returns[returns > 0].sum())
    losses = abs(float(returns[returns < 0].sum()))
    return wins / losses if losses > 0 else None


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    return float(((peak - equity) / peak.replace(0.0, np.nan)).max())


def _portfolio_summary(periods: pd.DataFrame, *, horizon: int) -> dict[str, float | int | None]:
    if periods.empty:
        return {"net_return": 0.0, "annualized_return": 0.0, "volatility": 0.0, "sharpe": 0.0, "sortino": 0.0, "max_drawdown": 0.0, "calmar": 0.0, "profit_factor": None, "win_rate": 0.0, "expectancy": 0.0, "trade_count": 0, "long_trades": 0, "short_trades": 0, "turnover": 0.0, "funding_return": 0.0, "transaction_cost": 0.0, "worst_period": 0.0, "var_95": 0.0, "cvar_95": 0.0}
    returns = periods["net_return"].astype(float)
    equity = (1.0 + returns).cumprod()
    net_return = float(equity.iloc[-1] - 1.0)
    periods_per_year = 24.0 * 365.0 / horizon
    years = len(returns) / periods_per_year
    annualized = float(equity.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 and equity.iloc[-1] > 0 else -1.0
    std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    volatility = std * math.sqrt(periods_per_year)
    sharpe = float(returns.mean() / std * math.sqrt(periods_per_year)) if std > 0 else 0.0
    downside = returns[returns < 0]
    downside_std = float(np.sqrt(np.mean(np.square(downside)))) if len(downside) else 0.0
    sortino = float(returns.mean() / downside_std * math.sqrt(periods_per_year)) if downside_std > 0 else 0.0
    max_dd = _max_drawdown(equity)
    var_95 = float(returns.quantile(0.05))
    cvar_tail = returns.loc[returns <= var_95]
    return {"net_return": net_return, "annualized_return": annualized, "volatility": volatility, "sharpe": sharpe, "sortino": sortino, "max_drawdown": max_dd, "calmar": annualized / max_dd if max_dd > 0 else 0.0, "profit_factor": _safe_profit_factor(returns), "win_rate": float((returns > 0).mean()), "expectancy": float(returns.mean()), "trade_count": int(periods["long_count"].sum() + periods["short_count"].sum()), "long_trades": int(periods["long_count"].sum()), "short_trades": int(periods["short_count"].sum()), "turnover": float(periods["gross_exposure"].sum()), "funding_return": float(periods["funding_return"].sum()), "transaction_cost": float(periods["transaction_cost"].sum()), "worst_period": float(returns.min()), "var_95": var_95, "cvar_95": float(cvar_tail.mean()) if len(cvar_tail) else var_95}


def purged_time_folds(frame: pd.DataFrame, *, horizon: int, n_splits: int = 3, initial_train_fraction: float = 0.5) -> list[tuple[pd.Index, pd.Index]]:
    if horizon <= 0 or n_splits <= 0:
        raise ValueError("horizon and n_splits must be positive")
    times = pd.Index(sorted(pd.to_datetime(frame["timestamp"], utc=True).dropna().unique()))
    first_test_pos = max(horizon + 1, int(len(times) * initial_train_fraction))
    remaining = len(times) - first_test_pos
    test_size = remaining // n_splits
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    folds = []
    for fold in range(n_splits):
        test_start_pos = first_test_pos + fold * test_size
        test_end_pos = len(times) - 1 if fold == n_splits - 1 else test_start_pos + test_size - 1
        train_end_pos = test_start_pos - horizon - 1
        if train_end_pos < 0:
            continue
        train_idx = frame.index[timestamps <= times[train_end_pos]]
        test_idx = frame.index[(timestamps >= times[test_start_pos]) & (timestamps <= times[test_end_pos])]
        if len(train_idx) and len(test_idx):
            folds.append((train_idx, test_idx))
    return folds


def _make_regressor(config: dict[str, object]):
    name = str(config["model"])
    if name == "ridge":
        return Pipeline([("scale", StandardScaler()), ("model", Ridge(alpha=float(config.get("alpha", 1.0))))])
    if name == "hist_gb":
        return HistGradientBoostingRegressor(max_depth=int(config.get("max_depth", 3)), learning_rate=float(config.get("learning_rate", 0.05)), max_iter=int(config.get("max_iter", 150)), l2_regularization=float(config.get("l2_regularization", 1.0)), random_state=42)
    if name == "extra_trees":
        return ExtraTreesRegressor(n_estimators=int(config.get("n_estimators", 120)), max_depth=config.get("max_depth"), min_samples_leaf=int(config.get("min_samples_leaf", 5)), random_state=42, n_jobs=-1)
    raise ValueError(f"unknown regression model: {name}")


def _fit_predict_regression_scores(train: pd.DataFrame, test: pd.DataFrame, *, config: dict[str, object], feature_columns: list[str], target_col: str, eligible_col: str = "in_universe") -> pd.DataFrame:
    fit = train.loc[train[target_col].notna()].copy()
    if eligible_col in fit.columns:
        fit = fit.loc[fit[eligible_col].astype(bool)]
    if len(fit) < 20:
        raise ValueError("not enough eligible training rows")
    model = _make_regressor(config)
    model.fit(fit[feature_columns], fit[target_col].astype(float))
    scored = test.copy()
    scored["model_score"] = model.predict(scored[feature_columns])
    return scored
