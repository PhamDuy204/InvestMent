from __future__ import annotations

import numpy as np


def turnover(previous_weights: np.ndarray, new_weights: np.ndarray) -> float:
    previous = np.asarray(previous_weights, dtype=float)
    new = np.asarray(new_weights, dtype=float)
    if previous.shape != new.shape:
        raise ValueError("weight vectors must have the same shape")
    return float(np.abs(new - previous).sum())


def drift_futures_weights(weights: np.ndarray, returns: np.ndarray, *, net_return: float) -> np.ndarray:
    current = np.asarray(weights, dtype=float)
    realized = np.asarray(returns, dtype=float)
    if current.shape != realized.shape:
        raise ValueError("weights and returns must have the same shape")
    equity_factor = 1.0 + float(net_return)
    if equity_factor <= 0:
        raise ValueError("equity must remain positive to drift futures weights")
    return current * (1.0 + realized) / equity_factor


def _project_exposure_caps(weights: np.ndarray, *, gross_cap: float, net_cap: float, single_cap: float) -> np.ndarray:
    if gross_cap <= 0 or net_cap < 0 or single_cap <= 0:
        raise ValueError("exposure caps must be positive, except net_cap may be zero")
    result = np.clip(np.asarray(weights, dtype=float), -single_cap, single_cap)
    for _ in range(12):
        gross = float(np.abs(result).sum())
        if gross > gross_cap:
            result *= gross_cap / gross
        net = float(result.sum())
        if abs(net) <= net_cap + 1e-12:
            break
        target_net = np.sign(net) * net_cap
        result -= (net - target_net) / len(result)
        result = np.clip(result, -single_cap, single_cap)
    gross = float(np.abs(result).sum())
    if gross > gross_cap:
        result *= gross_cap / gross
    return result


def cost_aware_target(*, mu: np.ndarray, covariance: np.ndarray, previous_weights: np.ndarray, cost_penalty: np.ndarray, risk_aversion: float, movement_penalty: float, gross_cap: float, net_cap: float, single_cap: float) -> np.ndarray:
    expected = np.asarray(mu, dtype=float)
    previous = np.asarray(previous_weights, dtype=float)
    liquidity_penalty = np.asarray(cost_penalty, dtype=float)
    covariance = np.asarray(covariance, dtype=float)
    n_assets = len(expected)
    if expected.ndim != 1 or previous.shape != expected.shape or liquidity_penalty.shape != expected.shape:
        raise ValueError("mu, previous_weights, and cost_penalty must be same-length vectors")
    if covariance.shape != (n_assets, n_assets):
        raise ValueError("covariance must be square and match mu")
    if risk_aversion < 0 or movement_penalty < 0 or np.any(liquidity_penalty < 0):
        raise ValueError("penalties must be non-negative")
    if risk_aversion == 0 and movement_penalty == 0:
        raise ValueError("at least one penalty must be positive")
    diagonal = np.diag(liquidity_penalty)
    system = risk_aversion * covariance + movement_penalty * diagonal
    rhs = expected + movement_penalty * diagonal @ previous
    try:
        raw = np.linalg.solve(system, rhs)
    except np.linalg.LinAlgError:
        raw = np.linalg.lstsq(system, rhs, rcond=None)[0]
    return _project_exposure_caps(raw, gross_cap=gross_cap, net_cap=net_cap, single_cap=single_cap)


def rebalance_cost(previous_weights: np.ndarray, new_weights: np.ndarray, *, round_trip_cost_bps: float) -> float:
    if round_trip_cost_bps < 0:
        raise ValueError("round_trip_cost_bps must be non-negative")
    one_way_bps = round_trip_cost_bps / 2.0
    return turnover(previous_weights, new_weights) * one_way_bps / 10_000.0


def _rolling_covariance(returns_wide, *, timestamp, symbols: list[str], lookback: int) -> np.ndarray:
    if lookback == 0:
        return np.eye(len(symbols), dtype=float)
    history = returns_wide.loc[returns_wide.index <= timestamp, symbols].tail(lookback)
    matrix = history.cov(min_periods=2).reindex(index=symbols, columns=symbols).fillna(0.0).to_numpy(dtype=float)
    diagonal = np.diag(matrix)
    positive = diagonal[diagonal > 0]
    floor = max(float(np.median(positive)) * 0.01 if len(positive) else 0.0, 1e-8)
    matrix = matrix.copy()
    matrix.flat[:: len(symbols) + 1] += floor
    return matrix


def cost_aware_cross_sectional_backtest(panel, *, score_col: str, horizon: int, round_trip_cost_bps: float, risk_aversion: float, movement_penalty: float, covariance_lookback: int = 24 * 30, gross_cap: float = 1.0, net_cap: float = 0.05, single_cap: float = 0.25, eligible_col: str = "in_universe", delay_bars: int = 0, covariance_history=None, uncertainty_quantile: float | None = None, uncertainty_window: int = 20, uncertainty_min_history: int = 10, uncertainty_safety_margin: float = 0.0, initial_residuals: dict[str, list[float]] | None = None, min_abs_weight_change: float = 0.0, adverse_funding_threshold: float | None = None):
    import json
    import pandas as pd
    from crypto_research.multi_asset_v2 import _portfolio_summary
    if horizon <= 0 or covariance_lookback < 0 or delay_bars < 0:
        raise ValueError("invalid horizon, covariance lookback, or delay")
    if min_abs_weight_change < 0:
        raise ValueError("min_abs_weight_change must be non-negative")
    if adverse_funding_threshold is not None and adverse_funding_threshold < 0:
        raise ValueError("adverse_funding_threshold must be non-negative")
    if uncertainty_quantile is not None:
        if not 0.0 <= uncertainty_quantile <= 1.0:
            raise ValueError("uncertainty_quantile must be between zero and one")
        if uncertainty_window <= 0 or uncertainty_min_history <= 0 or uncertainty_min_history > uncertainty_window:
            raise ValueError("invalid uncertainty history parameters")
        if uncertainty_safety_margin < 0:
            raise ValueError("uncertainty_safety_margin must be non-negative")
    required = {"timestamp", "symbol", "open", "close", score_col}
    missing = required.difference(panel.columns)
    if missing:
        raise ValueError(f"missing backtest columns: {sorted(missing)}")
    work = panel.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    work = work.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    grouped = work.groupby("symbol", sort=False, group_keys=False)
    if "ret_1" not in work.columns:
        work["ret_1"] = grouped["close"].pct_change(fill_method=None).fillna(0.0)
    entry_shift = 1 + delay_bars
    exit_shift = entry_shift + horizon
    work["_entry_open"] = grouped["open"].shift(-entry_shift)
    work["_exit_close"] = grouped["open"].shift(-exit_shift)
    work["_entry_timestamp"] = grouped["timestamp"].shift(-entry_shift)
    work["_exit_timestamp"] = grouped["timestamp"].shift(-exit_shift)
    work["_target_exit_timestamp"] = grouped["timestamp"].shift(-horizon)
    work["_holding_return"] = work["_exit_close"] / work["_entry_open"] - 1.0
    funding = pd.to_numeric(work.get("funding_event_rate", 0.0), errors="coerce").fillna(0.0)
    work["_funding_sum"] = 0.0
    for offset in range(entry_shift, exit_shift):
        work["_funding_sum"] += funding.groupby(work["symbol"], sort=False).shift(-offset).fillna(0.0)
    times = pd.Index(sorted(work["timestamp"].dropna().unique()))
    decision_times = set(times[::horizon])
    returns_source = work[["timestamp", "symbol", "ret_1"]]
    if covariance_history is not None:
        history = covariance_history[["timestamp", "symbol", "ret_1"]].copy()
        history["timestamp"] = pd.to_datetime(history["timestamp"], utc=True)
        if not history.empty and history["timestamp"].max() >= work["timestamp"].min():
            raise ValueError("covariance_history must be strictly earlier than backtest panel")
        returns_source = pd.concat([history, returns_source], ignore_index=True)
    returns_wide = returns_source.pivot(index="timestamp", columns="symbol", values="ret_1").sort_index()
    previous_by_symbol: dict[str, float] = {}
    rows: list[dict[str, object]] = []
    residual_history = {symbol: list(values) for symbol, values in (initial_residuals or {}).items()}
    pending_residuals: list[tuple[pd.Timestamp, str, float]] = []
    target_column = f"future_residual_return_{horizon}"
    for timestamp, cross_section in work.loc[work["timestamp"].isin(decision_times)].groupby("timestamp", sort=True):
        cross_section = cross_section.set_index("symbol", drop=False)
        still_pending = []
        for available_at, residual_symbol, residual_value in pending_residuals:
            if available_at <= pd.Timestamp(timestamp):
                residual_history.setdefault(residual_symbol, []).append(residual_value)
            else:
                still_pending.append((available_at, residual_symbol, residual_value))
        pending_residuals = still_pending
        if not cross_section["_holding_return"].notna().any():
            break
        valid = cross_section["_holding_return"].notna() & pd.to_numeric(cross_section[score_col], errors="coerce").notna()
        if eligible_col in cross_section.columns:
            valid &= cross_section[eligible_col].astype(bool)
        eligible_symbols = set(cross_section.index[valid])
        held_symbols = {symbol for symbol, weight in previous_by_symbol.items() if abs(weight) > 1e-12}
        symbols = sorted((eligible_symbols | held_symbols).intersection(cross_section.index))
        if not symbols:
            continue
        previous = np.array([previous_by_symbol.get(symbol, 0.0) for symbol in symbols], dtype=float)
        expected = np.array([float(cross_section.at[symbol, score_col]) if symbol in eligible_symbols else 0.0 for symbol in symbols], dtype=float)
        raw_expected = expected.copy()
        if "funding_rate" in cross_section.columns:
            funding_feature = pd.to_numeric(cross_section["funding_rate"], errors="coerce").fillna(0.0)
            funding_rates = np.array([float(funding_feature.at[symbol]) for symbol in symbols])
        else:
            funding_rates = np.zeros(len(symbols), dtype=float)
        if adverse_funding_threshold is not None:
            adverse = ((expected > 0.0) & (funding_rates > adverse_funding_threshold)) | ((expected < 0.0) & (funding_rates < -adverse_funding_threshold))
            expected = np.where(adverse, 0.0, expected)
        if uncertainty_quantile is not None:
            adjusted = np.zeros_like(expected)
            per_unit_cost = (round_trip_cost_bps / 2.0) / 10_000.0
            for score_index, symbol in enumerate(symbols):
                if symbol not in eligible_symbols:
                    continue
                history_values = residual_history.get(symbol, [])
                if len(history_values) < uncertainty_min_history:
                    continue
                sample = history_values[-uncertainty_window:]
                radius = float(np.quantile(sample, uncertainty_quantile))
                magnitude = max(abs(raw_expected[score_index]) - radius - per_unit_cost - uncertainty_safety_margin, 0.0)
                adjusted[score_index] = np.sign(raw_expected[score_index]) * magnitude
            expected = adjusted
        covariance = _rolling_covariance(returns_wide, timestamp=pd.Timestamp(timestamp), symbols=symbols, lookback=covariance_lookback)
        target = cost_aware_target(mu=expected, covariance=covariance, previous_weights=previous, cost_penalty=np.ones(len(symbols), dtype=float), risk_aversion=risk_aversion, movement_penalty=movement_penalty, gross_cap=gross_cap, net_cap=net_cap, single_cap=single_cap)
        if min_abs_weight_change > 0.0:
            for index, symbol in enumerate(symbols):
                if symbol in eligible_symbols and abs(target[index] - previous[index]) < min_abs_weight_change:
                    target[index] = previous[index]
        for index, symbol in enumerate(symbols):
            if symbol not in eligible_symbols:
                target[index] = 0.0
        target = _project_exposure_caps(target, gross_cap=gross_cap, net_cap=net_cap, single_cap=single_cap)
        delta = target - previous
        period_turnover = turnover(previous, target)
        transaction_cost = rebalance_cost(previous, target, round_trip_cost_bps=round_trip_cost_bps)
        holding_returns = np.array([float(cross_section.at[symbol, "_holding_return"]) for symbol in symbols])
        funding_sums = np.array([float(cross_section.at[symbol, "_funding_sum"]) for symbol in symbols])
        weighted = target * holding_returns
        long_mask = target > 1e-12
        short_mask = target < -1e-12
        gross_return = float(weighted.sum())
        funding_return = float((-target * funding_sums).sum())
        rows.append({
            "decision_timestamp": timestamp,
            "entry_timestamp": cross_section.loc[symbols, "_entry_timestamp"].min(),
            "exit_timestamp": cross_section.loc[symbols, "_exit_timestamp"].max(),
            "long_gross_return": float(weighted[long_mask].sum()),
            "short_gross_return": float(weighted[short_mask].sum()),
            "gross_return": gross_return,
            "raw_predicted_edge": float(np.dot(target, raw_expected)),
            "adjusted_predicted_edge": float(np.dot(target, expected)),
            "funding_return": funding_return,
            "transaction_cost": transaction_cost,
            "net_return": gross_return + funding_return - transaction_cost,
            "turnover": period_turnover,
            "final_unwind_turnover": 0.0,
            "gross_exposure": float(np.abs(target).sum()),
            "net_exposure": float(target.sum()),
            "long_count": int(long_mask.sum()),
            "short_count": int(short_mask.sum()),
            "rebalance_trade_count": int((np.abs(delta) > 1e-12).sum()),
            "long_symbols": ",".join(np.array(symbols)[long_mask]),
            "weights_json": json.dumps({symbol: float(weight) for symbol, weight in zip(symbols, target, strict=True)}),
            "decision_details_json": json.dumps({symbol: {"eligible": symbol in eligible_symbols, "previous_weight": float(previous[index]), "target_weight": float(target[index]), "delta_weight": float(delta[index]), "raw_score": float(raw_expected[index]), "effective_score": float(expected[index]), "funding_rate_feature": float(funding_rates[index]), "holding_return": float(holding_returns[index]), "funding_sum": float(funding_sums[index]), "gross_contribution": float(weighted[index]), "funding_contribution": float(-target[index] * funding_sums[index])} for index, symbol in enumerate(symbols)}),
            "short_symbols": ",".join(np.array(symbols)[short_mask]),
        })
        if target_column in cross_section.columns:
            for residual_symbol in eligible_symbols:
                actual = cross_section.at[residual_symbol, target_column]
                available_at = cross_section.at[residual_symbol, "_target_exit_timestamp"]
                if pd.notna(actual) and pd.notna(available_at):
                    residual_value = abs(float(actual) - float(cross_section.at[residual_symbol, score_col]))
                    pending_residuals.append((pd.Timestamp(available_at), residual_symbol, residual_value))
        period_net_return = gross_return + funding_return - transaction_cost
        drifted = drift_futures_weights(target, holding_returns, net_return=period_net_return)
        previous_by_symbol = {symbol: float(weight) for symbol, weight in zip(symbols, drifted, strict=True)}
    periods = pd.DataFrame(rows)
    if periods.empty:
        return periods, _portfolio_summary(periods, horizon=horizon)
    final_symbols = sorted(previous_by_symbol)
    final_weights = np.array([previous_by_symbol[symbol] for symbol in final_symbols], dtype=float)
    flat = np.zeros_like(final_weights)
    final_unwind = turnover(final_weights, flat)
    final_cost = rebalance_cost(final_weights, flat, round_trip_cost_bps=round_trip_cost_bps)
    periods.loc[periods.index[-1], "final_unwind_turnover"] = final_unwind
    periods.loc[periods.index[-1], "transaction_cost"] += final_cost
    periods.loc[periods.index[-1], "net_return"] -= final_cost
    periods.loc[periods.index[-1], "rebalance_trade_count"] += int((np.abs(final_weights) > 1e-12).sum())
    metrics = _portfolio_summary(periods, horizon=horizon)
    metrics["turnover"] = float(periods["turnover"].sum() + periods["final_unwind_turnover"].sum())
    metrics["transaction_cost"] = float(periods["transaction_cost"].sum())
    metrics["trade_count"] = int(periods["rebalance_trade_count"].sum())
    return periods, metrics


def rolling_lower_bound(prediction, realized, *, window: int, quantile: float, min_history: int):
    import pandas as pd
    if window <= 0 or min_history <= 0 or min_history > window:
        raise ValueError("window/min_history must be positive and min_history <= window")
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between zero and one")
    predicted = pd.Series(prediction, copy=False).astype(float)
    actual = pd.Series(realized, copy=False).astype(float)
    if len(predicted) != len(actual):
        raise ValueError("prediction and realized must have equal length")
    past_error = (actual - predicted).abs().shift(1)
    uncertainty = past_error.rolling(window, min_periods=min_history).quantile(quantile)
    return predicted - uncertainty


def uncertainty_eligibility(lower_bound, *, expected_cost: float, safety_margin: float = 0.0):
    import pandas as pd
    if expected_cost < 0 or safety_margin < 0:
        raise ValueError("cost and safety margin must be non-negative")
    lower = pd.Series(lower_bound, copy=False).astype(float)
    return (lower > expected_cost + safety_margin).fillna(False)
