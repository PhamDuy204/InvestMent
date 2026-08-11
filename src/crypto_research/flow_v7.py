from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from crypto_research.multi_asset_v3 import drift_futures_weights, rebalance_cost


@dataclass(frozen=True)
class FlowControlFit:
    log_buy_mean_by_symbol: dict[str, float]
    log_buy_std_by_symbol: dict[str, float]
    flow_on_return_intercept: float
    flow_on_return_slope: float
    next_return_flow_slope: float
    next_return_flow_t_stat: float


def _design(*columns: np.ndarray) -> np.ndarray:
    return np.column_stack((np.ones(len(columns[0])), *columns))


def fit_flow_control(train: pd.DataFrame) -> FlowControlFit:
    required = {"symbol", "lag_return_1h", "lag_taker_buy_quote_volume", "next_return_1h"}
    if missing := required.difference(train.columns):
        raise ValueError(f"flow training data missing columns: {sorted(missing)}")
    work = train.copy()
    work["lag_return_1h"] = pd.to_numeric(work["lag_return_1h"], errors="coerce")
    work["next_return_1h"] = pd.to_numeric(work["next_return_1h"], errors="coerce")
    buy = pd.to_numeric(work["lag_taker_buy_quote_volume"], errors="coerce").clip(lower=0)
    work["log_buy"] = np.log1p(buy)
    work = work.dropna(subset=["symbol", "lag_return_1h", "next_return_1h", "log_buy"])
    if len(work) < 4:
        raise ValueError("flow training data requires at least four complete rows")

    grouped = work.groupby("symbol", sort=True)["log_buy"]
    means = {str(key): float(value) for key, value in grouped.mean().items()}
    stds = {
        str(key): float(value) if np.isfinite(value) and float(value) > 1e-12 else 1.0
        for key, value in grouped.std(ddof=0).items()
    }
    work["z_flow"] = [
        (float(value) - means[str(symbol)]) / stds[str(symbol)]
        for symbol, value in zip(work["symbol"], work["log_buy"], strict=True)
    ]
    lag = work["lag_return_1h"].to_numpy(dtype=float)
    z_flow = work["z_flow"].to_numpy(dtype=float)
    target = work["next_return_1h"].to_numpy(dtype=float)

    flow_design = _design(lag)
    flow_coef, *_ = np.linalg.lstsq(flow_design, z_flow, rcond=None)
    return_design = _design(lag, z_flow)
    return_coef, *_ = np.linalg.lstsq(return_design, target, rcond=None)
    residual = target - return_design @ return_coef
    degrees = max(1, len(target) - return_design.shape[1])
    sigma2 = float(np.dot(residual, residual) / degrees)
    covariance = sigma2 * np.linalg.pinv(return_design.T @ return_design)
    flow_se = float(np.sqrt(max(0.0, covariance[2, 2])))
    t_stat = float(return_coef[2] / flow_se) if flow_se > 0 else float("inf") * float(np.sign(return_coef[2]))
    return FlowControlFit(
        log_buy_mean_by_symbol=means,
        log_buy_std_by_symbol=stds,
        flow_on_return_intercept=float(flow_coef[0]),
        flow_on_return_slope=float(flow_coef[1]),
        next_return_flow_slope=float(return_coef[2]),
        next_return_flow_t_stat=t_stat,
    )


def flow_component(row: pd.Series, fit: FlowControlFit) -> float:
    symbol = str(row["symbol"])
    if symbol not in fit.log_buy_mean_by_symbol:
        return float("nan")
    lag_return = float(row["lag_return_1h"])
    buy_volume = max(0.0, float(row["lag_taker_buy_quote_volume"]))
    z_flow = (
        np.log1p(buy_volume) - fit.log_buy_mean_by_symbol[symbol]
    ) / fit.log_buy_std_by_symbol[symbol]
    residual_flow = z_flow - (
        fit.flow_on_return_intercept + fit.flow_on_return_slope * lag_return
    )
    return float(fit.next_return_flow_slope * residual_flow)


def _is_increase(previous: float, target: float) -> bool:
    if abs(target) <= 1e-12:
        return False
    if abs(previous) <= 1e-12 or previous * target < 0:
        return True
    return abs(target) > abs(previous) + 1e-12


def apply_flow_veto(
    *,
    previous_weight: float,
    base_target_weight: float,
    h12_score: float,
    incremental_flow_component: float,
) -> dict[str, object]:
    previous = float(previous_weight)
    target = float(base_target_weight)
    score = float(h12_score)
    component = float(incremental_flow_component)
    conflict = bool(
        _is_increase(previous, target)
        and np.isfinite(component)
        and np.isfinite(score)
        and np.sign(component) != 0
        and np.sign(score) != 0
        and np.sign(component) != np.sign(score)
    )
    if not conflict:
        return {"target_weight": target, "h4_veto": False}
    if abs(previous) <= 1e-12 or previous * target < 0:
        target = 0.0
    else:
        target = previous
    return {"target_weight": float(target), "h4_veto": True}


def _build_flow_targets_one_fold(
    frame: pd.DataFrame,
    *,
    round_trip_cost_bps: float,
) -> pd.DataFrame:
    work = frame.copy()
    work["decision_timestamp"] = pd.to_datetime(work["decision_timestamp"], utc=True)
    work = work.sort_values(["decision_timestamp", "symbol"])
    current: dict[str, float] = {}
    rows: list[dict[str, object]] = []
    for timestamp, group in work.groupby("decision_timestamp", sort=True):
        indexed = group.set_index("symbol", drop=False)
        symbols = sorted(set(indexed.index) | set(current))
        previous = np.array([current.get(symbol, 0.0) for symbol in symbols], dtype=float)
        target = np.zeros(len(symbols), dtype=float)
        holding = np.zeros(len(symbols), dtype=float)
        funding = np.zeros(len(symbols), dtype=float)
        for index, symbol in enumerate(symbols):
            if symbol not in indexed.index:
                continue
            row = indexed.loc[symbol]
            gate = apply_flow_veto(
                previous_weight=float(previous[index]),
                base_target_weight=float(row["target_weight"]),
                h12_score=float(row["effective_score"]),
                incremental_flow_component=float(row["h4_flow_component"]),
            )
            target[index] = float(gate["target_weight"])
            holding[index] = float(row["holding_return_label"])
            funding[index] = float(row["funding_sum_label"])
            rows.append(
                {
                    "decision_timestamp": pd.Timestamp(timestamp),
                    "symbol": str(symbol),
                    "h4_target_weight": float(gate["target_weight"]),
                    "h4_veto": bool(gate["h4_veto"]),
                }
            )
        cost = rebalance_cost(previous, target, round_trip_cost_bps=round_trip_cost_bps)
        gross = float(np.dot(target, holding))
        funding_return = float(np.dot(-target, funding))
        net_return = gross + funding_return - cost
        if 1.0 + net_return <= 0:
            drifted = target
        else:
            drifted = drift_futures_weights(target, holding, net_return=net_return)
        current = {
            symbol: float(weight)
            for symbol, weight in zip(symbols, drifted, strict=True)
            if abs(float(weight)) > 1e-15
        }
    return pd.DataFrame(rows)


def build_flow_overlay_targets(
    frame: pd.DataFrame,
    *,
    round_trip_cost_bps: float = 10.0,
) -> pd.DataFrame:
    required = {
        "decision_timestamp",
        "symbol",
        "target_weight",
        "effective_score",
        "h4_flow_component",
        "holding_return_label",
        "funding_sum_label",
    }
    if missing := required.difference(frame.columns):
        raise ValueError(f"flow overlay data missing columns: {sorted(missing)}")
    if "fold" in frame.columns and frame["fold"].notna().all() and frame["fold"].nunique() > 1:
        return pd.concat(
            [
                _build_flow_targets_one_fold(part, round_trip_cost_bps=round_trip_cost_bps)
                for _, part in frame.groupby("fold", sort=False)
            ],
            ignore_index=True,
        )
    return _build_flow_targets_one_fold(frame, round_trip_cost_bps=round_trip_cost_bps)
