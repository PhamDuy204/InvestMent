from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PortfolioCaps:
    gross: float = 1.0
    net: float = 0.05
    single_asset: float = 0.25


def turnover(previous: np.ndarray, target: np.ndarray) -> float:
    """One-way turnover: sum of absolute weight changes."""
    previous = np.asarray(previous, dtype=float)
    target = np.asarray(target, dtype=float)
    if previous.shape != target.shape:
        raise ValueError("previous and target must have identical shapes")
    return float(np.abs(target - previous).sum())


def _project_exposure_caps(weights: np.ndarray, caps: PortfolioCaps) -> np.ndarray:
    w = np.asarray(weights, dtype=float).copy()
    w = np.clip(w, -caps.single_asset, caps.single_asset)

    gross = np.abs(w).sum()
    if gross > caps.gross and gross > 0:
        w *= caps.gross / gross

    net = float(w.sum())
    if abs(net) > caps.net and len(w):
        target_sum = float(np.sign(net) * caps.net)
        lo = float(w.min() - caps.single_asset - abs(net) - 1.0)
        hi = float(w.max() + caps.single_asset + abs(net) + 1.0)
        for _ in range(100):
            mid = (lo + hi) / 2.0
            candidate = np.clip(w - mid, -caps.single_asset, caps.single_asset)
            if candidate.sum() > target_sum:
                lo = mid
            else:
                hi = mid
        w = np.clip(w - (lo + hi) / 2.0, -caps.single_asset, caps.single_asset)

    gross = np.abs(w).sum()
    if gross > caps.gross and gross > 0:
        w *= caps.gross / gross
    return w


def cost_aware_target(
    mu: np.ndarray,
    covariance: np.ndarray,
    previous: np.ndarray,
    gamma: float,
    kappa: float,
    turnover_scale: np.ndarray | None = None,
    caps: PortfolioCaps = PortfolioCaps(),
) -> np.ndarray:
    """Closed-form quadratic approximation to a cost-aware target portfolio."""
    mu = np.asarray(mu, dtype=float)
    covariance = np.asarray(covariance, dtype=float)
    previous = np.asarray(previous, dtype=float)
    n = len(mu)
    if covariance.shape != (n, n) or previous.shape != (n,):
        raise ValueError("shape mismatch")
    if gamma <= 0 or kappa < 0:
        raise ValueError("gamma must be positive and kappa non-negative")

    if turnover_scale is None:
        turnover_scale = np.ones(n, dtype=float)
    turnover_scale = np.asarray(turnover_scale, dtype=float)
    if turnover_scale.shape != (n,):
        raise ValueError("turnover_scale shape mismatch")

    d = np.diag(np.maximum(turnover_scale, 1e-12))
    lhs = gamma * covariance + kappa * d
    rhs = mu + kappa * d @ previous
    try:
        raw = np.linalg.solve(lhs, rhs)
    except np.linalg.LinAlgError:
        raw = np.linalg.lstsq(lhs, rhs, rcond=None)[0]
    return _project_exposure_caps(raw, caps)


def rebalance_cost(
    previous: np.ndarray,
    target: np.ndarray,
    round_trip_bps: float,
    include_final_unwind: bool = False,
) -> float:
    """Execution cost as fraction of equity; quoted round-trip bps are split per leg."""
    if round_trip_bps < 0:
        raise ValueError("round_trip_bps must be non-negative")
    one_way = round_trip_bps * 1e-4 / 2.0
    cost = turnover(previous, target) * one_way
    if include_final_unwind:
        cost += np.abs(np.asarray(target, dtype=float)).sum() * one_way
    return float(cost)


def _rolling_covariance(history: pd.DataFrame, symbols: list[str], lookback: int) -> np.ndarray:
    if lookback < 2:
        raise ValueError("lookback must be >= 2")
    tail = history[symbols].tail(lookback).dropna(how="any")
    if len(tail) < 2:
        return np.eye(len(symbols)) * 1e-4
    cov = tail.cov().to_numpy(dtype=float)
    cov = np.nan_to_num(cov, nan=0.0, posinf=0.0, neginf=0.0)
    cov += np.eye(len(symbols)) * 1e-8
    return cov


def rolling_lower_bound(
    prediction: pd.Series,
    realized: pd.Series,
    window: int = 60,
    quantile: float = 0.8,
    min_history: int = 10,
) -> pd.Series:
    """Causal conservative magnitude bound based on strictly prior residuals."""
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between 0 and 1")
    residual = (prediction - realized).abs()
    penalty = residual.shift(1).rolling(window, min_periods=min_history).quantile(quantile)
    return (prediction.abs() - penalty).clip(lower=0.0) * np.sign(prediction)


def uncertainty_eligible(history_count: int, min_history: int) -> bool:
    return history_count >= min_history


def cost_aware_cross_sectional_backtest(
    frame: pd.DataFrame,
    symbols: Iterable[str],
    *,
    prediction_col: str = "prediction",
    return_col: str = "holding_return",
    timestamp_col: str = "timestamp",
    symbol_col: str = "symbol",
    gamma: float = 100.0,
    kappa: float = 0.01,
    covariance_lookback: int = 168,
    round_trip_bps: float = 10.0,
    caps: PortfolioCaps = PortfolioCaps(),
    covariance_history: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Stateful cross-sectional backtest over already causally-built holding returns."""
    symbols = list(symbols)
    data = frame.copy().sort_values([timestamp_col, symbol_col])
    if data.empty:
        return pd.DataFrame()

    first_ts = pd.Timestamp(data[timestamp_col].min())
    if covariance_history is not None and not covariance_history.empty:
        hist_max = pd.Timestamp(covariance_history[timestamp_col].max())
        if hist_max >= first_ts:
            raise ValueError("covariance_history must be strictly earlier than OOS start")

    previous = np.zeros(len(symbols), dtype=float)
    rows: list[dict[str, object]] = []
    return_history: list[pd.Series] = []

    if covariance_history is not None and not covariance_history.empty:
        pivot = covariance_history.pivot(index=timestamp_col, columns=symbol_col, values=return_col)
        for _, row in pivot.reindex(columns=symbols).iterrows():
            return_history.append(row)

    for ts, grp in data.groupby(timestamp_col, sort=True):
        g = grp.set_index(symbol_col).reindex(symbols)
        mu = g[prediction_col].fillna(0.0).to_numpy(float)
        if return_history:
            hist = pd.DataFrame(return_history, columns=symbols)
            covariance = _rolling_covariance(hist, symbols, covariance_lookback)
        else:
            covariance = np.eye(len(symbols)) * 1e-4

        target = cost_aware_target(mu, covariance, previous, gamma, kappa, caps=caps)
        one_way_turnover = turnover(previous, target)
        cost = rebalance_cost(previous, target, round_trip_bps)
        realized = g[return_col].fillna(0.0).to_numpy(float)
        gross_pnl = float(np.dot(target, realized))
        net_pnl = gross_pnl - cost
        rows.append({
            "timestamp": pd.Timestamp(ts),
            "gross_pnl": gross_pnl,
            "transaction_cost": cost,
            "net_pnl": net_pnl,
            "turnover": one_way_turnover,
            "gross_exposure": float(np.abs(target).sum()),
            "net_exposure": float(target.sum()),
            "weights_json": json.dumps(dict(zip(symbols, map(float, target)))),
        })
        previous = target
        return_history.append(pd.Series(realized, index=symbols))

    if rows:
        final_unwind = rebalance_cost(previous, np.zeros_like(previous), round_trip_bps)
        rows[-1]["transaction_cost"] = float(rows[-1]["transaction_cost"]) + final_unwind
        rows[-1]["net_pnl"] = float(rows[-1]["net_pnl"]) - final_unwind
    return pd.DataFrame(rows)
