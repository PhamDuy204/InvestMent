from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from crypto_research.multi_asset_v2 import purged_time_folds
from crypto_research.multi_asset_v3 import cost_aware_cross_sectional_backtest
from crypto_research.run_v3 import HORIZON, inner_split, run_nested_cost_aware, score_ridge, select_inner_trial, stateful_summary


def v4_overlay_configs() -> list[dict[str, Any]]:
    return [{"name": f"band{band:g}_funding{threshold if threshold is not None else 'off'}", "min_abs_weight_change": band, "adverse_funding_threshold": threshold} for band in (0.0, 0.0025, 0.005, 0.01, 0.02) for threshold in (None, 0.0002)]


def liquidity_ablation_status() -> dict[str, str]:
    from crypto_research.run_v2 import PRICE_FEATURES
    liquidity_features = {name for name in PRICE_FEATURES if "liquid" in name or "volume" in name}
    if liquidity_features:
        return {"status": "REQUIRES_EXPLICIT_ABLATION", "features": ",".join(sorted(liquidity_features))}
    return {"status": "NOT_APPLICABLE", "reason": "V3 price-only Ridge contains no liquidity or volume predictor to ablate."}


def _run_overlay(scored: pd.DataFrame, *, history: pd.DataFrame, optimizer: dict[str, Any], overlay: dict[str, Any], round_trip_cost_bps: float, delay_bars: int):
    return cost_aware_cross_sectional_backtest(scored, score_col="model_score", horizon=HORIZON, round_trip_cost_bps=round_trip_cost_bps, risk_aversion=float(optimizer["risk_aversion"]), movement_penalty=float(optimizer["movement_penalty"]), covariance_lookback=int(optimizer["covariance_lookback"]), gross_cap=float(optimizer["gross_cap"]), net_cap=float(optimizer["net_cap"]), single_cap=float(optimizer["single_cap"]), delay_bars=delay_bars, covariance_history=history[["timestamp", "symbol", "ret_1"]], min_abs_weight_change=float(overlay["min_abs_weight_change"]), adverse_funding_threshold=overlay["adverse_funding_threshold"])


def run_nested_v4(panel: pd.DataFrame, *, round_trip_cost_bps: float = 10.0, delay_bars: int = 0, min_inner_trades: int = 200, overlays: list[dict[str, Any]] | None = None, v3_result: dict[str, Any] | None = None) -> dict[str, Any]:
    overlays = v4_overlay_configs() if overlays is None else overlays
    v3_result = run_nested_cost_aware(panel) if v3_result is None else v3_result
    if len(v3_result["folds"]) != 3:
        raise ValueError("V4 expects the same three V3 outer folds")
    fold_rows, period_parts = [], []
    for fold_id, (train_idx, test_idx) in enumerate(purged_time_folds(panel, horizon=HORIZON, n_splits=3)):
        outer_train, outer_test = panel.loc[train_idx].copy(), panel.loc[test_idx].copy()
        optimizer = dict(v3_result["folds"][fold_id]["selected_config"])
        inner_train, inner_validation = inner_split(outer_train)
        scored_validation = score_ridge(inner_train, inner_validation)
        trials = []
        for overlay in overlays:
            _, metrics = _run_overlay(scored_validation, history=inner_train, optimizer=optimizer, overlay=overlay, round_trip_cost_bps=round_trip_cost_bps, delay_bars=delay_bars)
            trials.append({"config": overlay, "net_return": float(metrics["net_return"]), "expectancy": float(metrics["expectancy"]), "sharpe": float(metrics["sharpe"]), "profit_factor": metrics["profit_factor"], "trade_count": int(metrics["trade_count"]), "turnover": float(metrics["turnover"]), "transaction_cost": float(metrics["transaction_cost"])})
        selected = select_inner_trial(trials, min_trades=min_inner_trades)
        selected_overlay = dict(selected["config"])
        scored_test = score_ridge(outer_train, outer_test)
        periods, metrics = _run_overlay(scored_test, history=outer_train, optimizer=optimizer, overlay=selected_overlay, round_trip_cost_bps=round_trip_cost_bps, delay_bars=delay_bars)
        if not periods.empty:
            periods = periods.copy(); periods["fold"] = fold_id; periods["optimizer_config"] = optimizer["name"]; periods["overlay_config"] = selected_overlay["name"]; period_parts.append(periods)
        fold_rows.append({"fold": fold_id, "optimizer_config": optimizer, "selected_overlay": selected_overlay, "selected_inner_metrics": {k: v for k, v in selected.items() if k != "config"}, "inner_overlay_trials": trials, "outer_metrics": metrics})
    periods = pd.concat(period_parts, ignore_index=True) if period_parts else pd.DataFrame()
    return {"folds": fold_rows, "periods": periods, "metrics": stateful_summary(periods), "overlay_trial_count": len(overlays) * len(fold_rows), "liquidity_ablation": liquidity_ablation_status()}


def evaluate_frozen_v4(panel: pd.DataFrame, selections: list[dict[str, Any]], *, round_trip_cost_bps: float, delay_bars: int) -> dict[str, Any]:
    if len(selections) != 3:
        raise ValueError("expected one frozen selection per outer fold")
    parts, fold_rows = [], []
    for fold_id, (train_idx, test_idx) in enumerate(purged_time_folds(panel, horizon=HORIZON, n_splits=3)):
        outer_train, outer_test = panel.loc[train_idx].copy(), panel.loc[test_idx].copy()
        scored_test = score_ridge(outer_train, outer_test); selection = selections[fold_id]
        periods, metrics = _run_overlay(scored_test, history=outer_train, optimizer=selection["optimizer_config"], overlay=selection["selected_overlay"], round_trip_cost_bps=round_trip_cost_bps, delay_bars=delay_bars)
        if not periods.empty:
            periods = periods.copy(); periods["fold"] = fold_id; parts.append(periods)
        fold_rows.append({"fold": fold_id, "metrics": metrics})
    periods = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    return {"metrics": stateful_summary(periods), "folds": fold_rows, "periods": periods}


def write_v4_artifacts(result: dict[str, Any], *, root: str | Path) -> None:
    import json
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    result["periods"].to_csv(root / "v4_periods.csv.gz", index=False, compression="gzip")
    (root / "v4_results.json").write_text(json.dumps({key: value for key, value in result.items() if key != "periods"}, indent=2, default=str))
