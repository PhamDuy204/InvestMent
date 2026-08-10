from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

BURST_FEATURES = ["ret_1m", "ret_5m", "ret_15m", "ret_60m", "rv_15m", "rv_60m", "range_pct_1m", "quote_volume_z60", "trade_count_z60", "quote_volume_z1440", "trade_count_z1440", "taker_buy_share", "taker_sell_share", "taker_imbalance", "taker_imbalance_5m", "taker_imbalance_accel", "volume_accel_15m", "clock_sin", "clock_cos", "quarter_phase_sin", "quarter_phase_cos", "is_quarter_open"]


def non_overlapping_mask(frame: pd.DataFrame, *, horizon_minutes: int) -> pd.Series:
    if horizon_minutes <= 0:
        raise ValueError("horizon_minutes must be positive")
    required = {"timestamp", "symbol", "eligible"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing event columns: {sorted(missing)}")
    work = frame.copy(); work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    result = pd.Series(False, index=work.index, dtype=bool); gap = pd.Timedelta(minutes=horizon_minutes)
    for _, group in work.groupby("symbol", sort=False):
        last = None
        for idx, row in group.sort_values("timestamp").iterrows():
            if not bool(row["eligible"]):
                continue
            ts = pd.Timestamp(row["timestamp"])
            if last is None or ts - last >= gap:
                result.at[idx] = True; last = ts
    return result


def economic_event_metrics(gross_returns: pd.Series, *, round_trip_cost_bps: float) -> dict[str, float | int | None]:
    if round_trip_cost_bps < 0:
        raise ValueError("round_trip_cost_bps must be non-negative")
    gross = pd.to_numeric(gross_returns, errors="coerce").dropna().astype(float); net = gross - round_trip_cost_bps / 10_000.0
    positives = float(net[net > 0].sum()); negatives = float(-net[net < 0].sum())
    return {"count": int(len(net)), "mean_gross_return": float(gross.mean()) if len(gross) else 0.0, "mean_net_return": float(net.mean()) if len(net) else 0.0, "win_rate": float((net > 0).mean()) if len(net) else 0.0, "profit_factor": positives / negatives if negatives > 0 else None, "net_compounded": float((1.0 + net).prod() - 1.0) if len(net) else 0.0}


def _model_frame(table_root: Path) -> pd.DataFrame:
    columns = ["timestamp", "symbol", *BURST_FEATURES, "jackpot", "tradable_return_20m", "future_taker_sell_share_5m"]
    parts = [pd.read_pickle(path).loc[:, columns].copy() for path in sorted(table_root.glob("*.pkl"))]
    if not parts:
        raise ValueError("no burst tables found")
    result = pd.concat(parts, ignore_index=True); result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True)
    return result.replace([np.inf, -np.inf], np.nan)


def _fit_models(train: pd.DataFrame, *, random_state: int):
    from sklearn.linear_model import LogisticRegression, Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    positives = train.loc[train["jackpot"]].copy(); negatives = train.loc[~train["jackpot"]].copy()
    max_negatives = min(len(negatives), max(50_000, 10 * len(positives)))
    negatives = negatives.sample(max_negatives, random_state=random_state) if len(negatives) > max_negatives else negatives
    classifier_train = pd.concat([positives, negatives], ignore_index=True).sample(frac=1.0, random_state=random_state)
    classifier = make_pipeline(StandardScaler(), LogisticRegression(max_iter=300, C=1.0)); classifier.fit(classifier_train[BURST_FEATURES], classifier_train["jackpot"].astype(int))
    regression_train = train.sample(800_000, random_state=random_state) if len(train) > 800_000 else train
    return_model = make_pipeline(StandardScaler(), Ridge(alpha=1.0)); return_model.fit(regression_train[BURST_FEATURES], regression_train["tradable_return_20m"])
    sell_model = make_pipeline(StandardScaler(), Ridge(alpha=1.0)); sell_model.fit(regression_train[BURST_FEATURES], regression_train["future_taker_sell_share_5m"])
    return classifier, return_model, sell_model


def _score(models, frame: pd.DataFrame) -> pd.DataFrame:
    classifier, return_model, sell_model = models; scored = frame.copy()
    scored["burst_score"] = classifier.decision_function(scored[BURST_FEATURES])
    scored["predicted_return_20m"] = return_model.predict(scored[BURST_FEATURES])
    scored["predicted_taker_sell_share_5m"] = sell_model.predict(scored[BURST_FEATURES]).clip(0.0, 1.0)
    return scored


def _prediction_metrics(scored: pd.DataFrame) -> dict[str, float]:
    from sklearn.metrics import average_precision_score, mean_absolute_error, roc_auc_score
    y = scored["jackpot"].astype(int); score = scored["burst_score"]
    actual_return = scored["tradable_return_20m"]; predicted_return = scored["predicted_return_20m"]
    actual_sell = scored["future_taker_sell_share_5m"]; predicted_sell = scored["predicted_taker_sell_share_5m"]; current_sell = scored["taker_sell_share"]
    return {"jackpot_rate": float(y.mean()), "roc_auc": float(roc_auc_score(y, score)), "average_precision": float(average_precision_score(y, score)), "return_correlation": float(np.corrcoef(actual_return, predicted_return)[0, 1]), "return_mae": float(mean_absolute_error(actual_return, predicted_return)), "sell_share_correlation": float(np.corrcoef(actual_sell, predicted_sell)[0, 1]), "sell_share_mae": float(mean_absolute_error(actual_sell, predicted_sell)), "sell_change_direction_accuracy": float((np.sign(predicted_sell - current_sell) == np.sign(actual_sell - current_sell)).mean())}


def _event_selection(scored: pd.DataFrame, *, score_threshold: float, min_predicted_edge: float, round_trip_cost_bps: float):
    work = scored.copy(); work["eligible"] = work["burst_score"].ge(score_threshold) & work["predicted_return_20m"].abs().ge(min_predicted_edge) & work["tradable_return_20m"].notna()
    events = work.loc[non_overlapping_mask(work[["timestamp", "symbol", "eligible"]], horizon_minutes=20)].copy()
    events["signal_side"] = np.sign(events["predicted_return_20m"]); events["gross_signal_return"] = events["signal_side"] * events["tradable_return_20m"]
    return events, economic_event_metrics(events["gross_signal_return"], round_trip_cost_bps=round_trip_cost_bps)


def run_burst_research(*, table_root: str | Path, artifact_root: str | Path, round_trip_cost_bps: float = 10.0, min_predicted_edge: float = 0.0015, random_state: int = 42) -> dict[str, object]:
    table_root = Path(table_root); artifact_root = Path(artifact_root); artifact_root.mkdir(parents=True, exist_ok=True)
    data = _model_frame(table_root).dropna(subset=[*BURST_FEATURES, "tradable_return_20m", "future_taker_sell_share_5m"])
    train = data.loc[data["timestamp"] < pd.Timestamp("2026-01-01", tz="UTC")].copy()
    validation = data.loc[(data["timestamp"] >= pd.Timestamp("2026-01-01", tz="UTC")) & (data["timestamp"] < pd.Timestamp("2026-05-01", tz="UTC"))].copy()
    test = data.loc[data["timestamp"] >= pd.Timestamp("2026-05-01", tz="UTC")].copy()
    if min(len(train), len(validation), len(test)) == 0:
        raise ValueError("burst train/validation/test split is empty")
    models = _fit_models(train, random_state=random_state); scored_validation = _score(models, validation); scored_test = _score(models, test)
    trials = []
    for quantile in (0.95, 0.975, 0.99, 0.995, 0.999):
        threshold = float(scored_validation["burst_score"].quantile(quantile)); _, metrics = _event_selection(scored_validation, score_threshold=threshold, min_predicted_edge=min_predicted_edge, round_trip_cost_bps=round_trip_cost_bps); trials.append({"quantile": quantile, "score_threshold": threshold, "metrics": metrics})
    eligible = [row for row in trials if int(row["metrics"]["count"]) >= 200]
    selected = max(eligible, key=lambda row: (float(row["metrics"]["mean_net_return"]), float(row["metrics"]["profit_factor"] or 0.0))) if eligible else None
    test_events = pd.DataFrame(); test_metrics = economic_event_metrics(pd.Series(dtype=float), round_trip_cost_bps=round_trip_cost_bps)
    if selected is not None:
        test_events, test_metrics = _event_selection(scored_test, score_threshold=float(selected["score_threshold"]), min_predicted_edge=min_predicted_edge, round_trip_cost_bps=round_trip_cost_bps); test_events.to_csv(artifact_root / "burst_test_events.csv.gz", index=False, compression="gzip")
    sell_low = float(scored_validation["predicted_taker_sell_share_5m"].quantile(0.1)); sell_high = float(scored_validation["predicted_taker_sell_share_5m"].quantile(0.9))
    payload = {"rows": {"train": len(train), "validation": len(validation), "test": len(test)}, "validation_prediction_metrics": _prediction_metrics(scored_validation), "test_prediction_metrics": _prediction_metrics(scored_test), "threshold_trials": trials, "selected_threshold": selected, "test_event_metrics": test_metrics, "sell_flow_effect": {"validation_low_threshold": sell_low, "validation_high_threshold": sell_high, "test_low_predicted_sell_mean_return": float(scored_test.loc[scored_test["predicted_taker_sell_share_5m"] <= sell_low, "tradable_return_20m"].mean()), "test_high_predicted_sell_mean_return": float(scored_test.loc[scored_test["predicted_taker_sell_share_5m"] >= sell_high, "tradable_return_20m"].mean())}, "feature_columns": BURST_FEATURES, "round_trip_cost_bps": round_trip_cost_bps, "min_predicted_edge": min_predicted_edge}
    (artifact_root / "burst_model_results.json").write_text(json.dumps(payload, indent=2, default=str)); return payload
