from __future__ import annotations

HORIZON = 12
BASE_COST_BPS = 10.0
MIN_INNER_TRADES = 200


def select_inner_trial(trials: list[dict[str, object]], *, min_trades: int = 200) -> dict[str, object]:
    if min_trades <= 0:
        raise ValueError("min_trades must be positive")
    eligible = [trial for trial in trials if int(trial.get("trade_count", 0)) >= min_trades]
    if not eligible:
        raise ValueError("no inner trial meets minimum trade count")
    return max(
        eligible,
        key=lambda trial: (
            float(trial.get("expectancy", float("-inf"))),
            float(trial.get("sharpe", float("-inf"))),
            float(trial.get("net_return", float("-inf"))),
        ),
    )


def v3_cost_configs() -> list[dict[str, object]]:
    return [
        {
            "name": f"g{gamma}_k{kappa}_c{lookback}",
            "risk_aversion": gamma,
            "movement_penalty": kappa,
            "covariance_lookback": lookback,
            "gross_cap": 1.0,
            "net_cap": 0.05,
            "single_cap": 0.25,
        }
        for gamma in (30.0, 100.0, 300.0, 1000.0)
        for kappa in (0.0, 0.001, 0.003, 0.01)
        for lookback in (168, 720)
    ]


def stateful_summary(periods):
    from crypto_research.multi_asset_v2 import _portfolio_summary

    metrics = _portfolio_summary(periods, horizon=HORIZON)
    if periods.empty:
        return metrics
    metrics["turnover"] = float(periods["turnover"].sum() + periods["final_unwind_turnover"].sum())
    metrics["transaction_cost"] = float(periods["transaction_cost"].sum())
    metrics["trade_count"] = int(periods["rebalance_trade_count"].sum())
    return metrics


def inner_split(outer_train, *, fraction: float = 0.25):
    import pandas as pd

    times = pd.Index(sorted(pd.to_datetime(outer_train["timestamp"], utc=True).dropna().unique()))
    validation_size = max(HORIZON + 2, int(len(times) * fraction))
    validation_start_pos = len(times) - validation_size
    inner_train_end_pos = validation_start_pos - HORIZON - 1
    if inner_train_end_pos < 0:
        raise ValueError("not enough inner history after purge")
    validation_start = times[validation_start_pos]
    inner_train_end = times[inner_train_end_pos]
    return (
        outer_train.loc[pd.to_datetime(outer_train["timestamp"], utc=True) <= inner_train_end].copy(),
        outer_train.loc[pd.to_datetime(outer_train["timestamp"], utc=True) >= validation_start].copy(),
    )


def score_ridge(train, test):
    from crypto_research.multi_asset_v2 import _fit_predict_regression_scores
    from crypto_research.run_v2 import PRICE_FEATURES

    config = {"name": "ridge_a1.0", "model": "ridge", "alpha": 1.0, "top_k": 2, "weighting": "equal"}
    return _fit_predict_regression_scores(
        train,
        test,
        config=config,
        feature_columns=PRICE_FEATURES,
        target_col=f"future_residual_return_{HORIZON}",
    )


def run_nested_cost_aware(
    panel,
    *,
    configs: list[dict[str, object]] | None = None,
    round_trip_cost_bps: float = BASE_COST_BPS,
    delay_bars: int = 0,
    min_inner_trades: int = MIN_INNER_TRADES,
):
    import pandas as pd

    from crypto_research.multi_asset_v2 import purged_time_folds
    from crypto_research.multi_asset_v3 import cost_aware_cross_sectional_backtest

    configs = v3_cost_configs() if configs is None else configs
    fold_rows = []
    period_parts = []
    for fold_id, (train_idx, test_idx) in enumerate(purged_time_folds(panel, horizon=HORIZON, n_splits=3)):
        outer_train = panel.loc[train_idx].copy()
        outer_test = panel.loc[test_idx].copy()
        inner_train, inner_validation = inner_split(outer_train)
        scored_validation = score_ridge(inner_train, inner_validation)
        trials = []
        for config in configs:
            _, metrics = cost_aware_cross_sectional_backtest(
                scored_validation,
                score_col="model_score",
                horizon=HORIZON,
                round_trip_cost_bps=round_trip_cost_bps,
                risk_aversion=float(config["risk_aversion"]),
                movement_penalty=float(config["movement_penalty"]),
                covariance_lookback=int(config["covariance_lookback"]),
                gross_cap=float(config["gross_cap"]),
                net_cap=float(config["net_cap"]),
                single_cap=float(config["single_cap"]),
                delay_bars=delay_bars,
                covariance_history=inner_train[["timestamp", "symbol", "ret_1"]],
            )
            trials.append(
                {
                    "config": config,
                    "net_return": float(metrics["net_return"]),
                    "expectancy": float(metrics["expectancy"]),
                    "sharpe": float(metrics["sharpe"]),
                    "profit_factor": metrics["profit_factor"],
                    "trade_count": int(metrics["trade_count"]),
                    "turnover": float(metrics["turnover"]),
                    "transaction_cost": float(metrics["transaction_cost"]),
                }
            )
        selected = select_inner_trial(trials, min_trades=min_inner_trades)
        config = selected["config"]
        scored_test = score_ridge(outer_train, outer_test)
        periods, metrics = cost_aware_cross_sectional_backtest(
            scored_test,
            score_col="model_score",
            horizon=HORIZON,
            round_trip_cost_bps=round_trip_cost_bps,
            risk_aversion=float(config["risk_aversion"]),
            movement_penalty=float(config["movement_penalty"]),
            covariance_lookback=int(config["covariance_lookback"]),
            gross_cap=float(config["gross_cap"]),
            net_cap=float(config["net_cap"]),
            single_cap=float(config["single_cap"]),
            delay_bars=delay_bars,
            covariance_history=outer_train[["timestamp", "symbol", "ret_1"]],
        )
        if not periods.empty:
            periods = periods.copy()
            periods["fold"] = fold_id
            period_parts.append(periods)
        fold_rows.append(
            {
                "fold": fold_id,
                "selected_config": config,
                "selected_inner_metrics": {k: v for k, v in selected.items() if k != "config"},
                "inner_trials": trials,
                "outer_metrics": metrics,
            }
        )
    periods = pd.concat(period_parts, ignore_index=True) if period_parts else pd.DataFrame()
    return {"folds": fold_rows, "periods": periods, "metrics": stateful_summary(periods)}
