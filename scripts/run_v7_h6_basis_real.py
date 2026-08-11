from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_research.basis_v7 import (
    apply_basis_vol_scale,
    fit_basis_vol_model,
    predict_basis_vol,
    predict_lag_only_vol,
    wrong_side_damage,
)
from crypto_research.factor_observatory_v7 import (
    FactorEvidence,
    admit_factor,
    factor_rejection_reasons,
)
from crypto_research.reliability_v7 import ReliabilityGateConfig
from crypto_research.run_v3 import stateful_summary
from crypto_research.run_v7 import _wrong_side_count, replay_v7_reliability, split_selection_evaluation
from crypto_research.trials_v7 import V7TrialRegistry

ART = Path("artifacts/multi_asset_v7")
HYPOTHESIS = "H_basis_vol_reliability_1"


def _summary(parts: list[pd.DataFrame]) -> dict[str, object]:
    return stateful_summary(pd.concat(parts, ignore_index=True))


def _merge_basis(decisions: pd.DataFrame, basis: pd.DataFrame) -> pd.DataFrame:
    left = decisions.copy()
    right = basis.copy()
    left["decision_timestamp"] = pd.to_datetime(left["decision_timestamp"], utc=True)
    right["decision_timestamp"] = pd.to_datetime(right["decision_timestamp"], utc=True)
    columns = ["decision_timestamp", "symbol", "abs_basis", "lag_rv12", "future_rv12"]
    return left.merge(right[columns], on=["decision_timestamp", "symbol"], how="left", validate="one_to_one")


def _scale_targets(frame: pd.DataFrame, fit) -> tuple[pd.DataFrame, float]:
    out = frame.copy()
    scales: list[float] = []
    targets: list[float] = []
    predictions: list[float] = []
    for _, row in out.iterrows():
        predicted = predict_basis_vol(row, fit)
        scaled = apply_basis_vol_scale(
            base_target_weight=float(row["target_weight"]),
            predicted_vol=predicted,
            anchor_vol=fit.anchor_vol,
        )
        predictions.append(float(predicted))
        scales.append(float(scaled["basis_scale"]))
        targets.append(float(scaled["target_weight"]))
    out["predicted_rv12"] = predictions
    out["basis_scale"] = scales
    out["base_target_weight"] = out["target_weight"]
    out["target_weight"] = targets
    return out, float(np.mean(np.asarray(scales) < 1.0))


def _rmse(actual: pd.Series, predicted: np.ndarray) -> float:
    y = pd.to_numeric(actual, errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(y) & np.isfinite(predicted)
    if not mask.any():
        return float("nan")
    return float(np.sqrt(np.mean(np.square(y[mask] - predicted[mask]))))


def _write_observatory_append(evidence: FactorEvidence) -> None:
    path = ART / "factor_observatory.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = {"status": "EVALUATED", "factors": []}
    row = asdict(evidence)
    row["source_ids"] = list(evidence.source_ids)
    reasons = factor_rejection_reasons(evidence)
    row["admitted"] = not reasons
    row["rejection_reasons"] = reasons
    factors = [item for item in payload.get("factors", []) if item.get("feature_name") != evidence.feature_name]
    factors.append(row)
    payload["status"] = "EVALUATED"
    payload["factors"] = factors
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> None:
    output = ART / "h6_basis_vol_results.json"
    if output.exists():
        raise SystemExit("H6 basis result already exists; refusing to rerun trial")
    registry_path = ART / "experiment_registry.csv"
    existing = pd.read_csv(registry_path)
    if int(existing["trial_number"].max()) != 866:
        raise SystemExit("H6 must start exactly at trial 867")

    decisions = pd.read_csv("artifacts/multi_asset_v4/decision_log.csv.gz")
    delayed = pd.read_csv(ART / "delay_1h_decision_log.csv.gz")
    basis = pd.read_csv(ART / "basis_factor_panel.csv.gz")
    for frame in (decisions, delayed, basis):
        frame["decision_timestamp"] = pd.to_datetime(frame["decision_timestamp"], utc=True)
    work = _merge_basis(decisions, basis)
    delayed_work = _merge_basis(delayed, basis)
    coverage = float(work[["abs_basis", "lag_rv12", "future_rv12"]].notna().all(axis=1).mean())
    if coverage < 0.70:
        raise SystemExit(f"basis causal panel coverage below 0.70: {coverage:.3f}")

    baseline_eval_parts: list[pd.DataFrame] = []
    candidate_eval_parts: list[pd.DataFrame] = []
    candidate_selection_parts: list[pd.DataFrame] = []
    cost20_parts: list[pd.DataFrame] = []
    delay_parts: list[pd.DataFrame] = []
    fold_rows: list[dict[str, object]] = []
    baseline_wrong_side_count = 0
    candidate_wrong_side_count = 0
    baseline_damage = 0.0
    candidate_damage = 0.0
    fold_positive = 0
    scaled_fraction_weighted = 0.0
    scaled_rows = 0

    for fold in sorted(work["fold"].dropna().unique()):
        fold_work = work.loc[work["fold"] == fold].copy()
        selection, evaluation = split_selection_evaluation(fold_work, selection_fraction=0.70)
        delay_fold = delayed_work.loc[delayed_work["fold"] == fold].copy()
        _, delay_evaluation = split_selection_evaluation(delay_fold, selection_fraction=0.70)
        fit = fit_basis_vol_model(selection)

        baseline_pred = np.array([predict_lag_only_vol(row, fit) for _, row in evaluation.iterrows()])
        augmented_pred = np.array([predict_basis_vol(row, fit) for _, row in evaluation.iterrows()])
        baseline_rmse = _rmse(evaluation["future_rv12"], baseline_pred)
        augmented_rmse = _rmse(evaluation["future_rv12"], augmented_pred)
        forecast_pass = bool(fit.basis_coefficient > 0.0 and augmented_rmse < baseline_rmse)

        baseline_periods, baseline_decisions, baseline_metrics = replay_v7_reliability(
            evaluation,
            ReliabilityGateConfig(None, None, None, False),
            round_trip_cost_bps=10.0,
        )
        scaled_selection, selection_scaled_fraction = _scale_targets(selection, fit)
        selection_periods, _, selection_metrics = replay_v7_reliability(
            scaled_selection,
            ReliabilityGateConfig(None, None, None, False),
            round_trip_cost_bps=10.0,
        )
        scaled_evaluation, evaluation_scaled_fraction = _scale_targets(evaluation, fit)
        candidate_periods, candidate_decisions, candidate_metrics = replay_v7_reliability(
            scaled_evaluation,
            ReliabilityGateConfig(None, None, None, False),
            round_trip_cost_bps=10.0,
        )
        cost20_periods, _, _ = replay_v7_reliability(
            scaled_evaluation,
            ReliabilityGateConfig(None, None, None, False),
            round_trip_cost_bps=20.0,
        )
        scaled_delay, _ = _scale_targets(delay_evaluation, fit)
        delayed_periods, _, _ = replay_v7_reliability(
            scaled_delay,
            ReliabilityGateConfig(None, None, None, False),
            round_trip_cost_bps=10.0,
        )

        labels = evaluation[["decision_timestamp", "symbol", "holding_return_label", "funding_sum_label"]]
        baseline_damage += wrong_side_damage(baseline_decisions, labels, round_trip_cost_bps=10.0)
        candidate_damage += wrong_side_damage(candidate_decisions, labels, round_trip_cost_bps=10.0)
        baseline_wrong_side_count += _wrong_side_count(evaluation, baseline_decisions, round_trip_cost_bps=10.0)
        candidate_wrong_side_count += _wrong_side_count(evaluation, candidate_decisions, round_trip_cost_bps=10.0)
        fold_positive += int(float(candidate_metrics["net_return"]) > float(baseline_metrics["net_return"]))
        baseline_eval_parts.append(baseline_periods)
        candidate_eval_parts.append(candidate_periods)
        candidate_selection_parts.append(selection_periods)
        cost20_parts.append(cost20_periods)
        delay_parts.append(delayed_periods)
        scaled_fraction_weighted += evaluation_scaled_fraction * len(evaluation)
        scaled_rows += len(evaluation)
        fold_rows.append(
            {
                "fold": int(fold),
                "selection_rows": int(len(selection)),
                "evaluation_rows": int(len(evaluation)),
                "basis_coefficient": float(fit.basis_coefficient),
                "anchor_vol": float(fit.anchor_vol),
                "baseline_rmse": baseline_rmse,
                "augmented_rmse": augmented_rmse,
                "forecast_pass": forecast_pass,
                "selection_candidate_net": float(selection_metrics["net_return"]),
                "baseline_evaluation_net": float(baseline_metrics["net_return"]),
                "candidate_evaluation_net": float(candidate_metrics["net_return"]),
                "selection_scaled_fraction": selection_scaled_fraction,
                "evaluation_scaled_fraction": evaluation_scaled_fraction,
            }
        )

    baseline_eval = _summary(baseline_eval_parts)
    candidate_eval = _summary(candidate_eval_parts)
    candidate_selection = _summary(candidate_selection_parts)
    cost20 = _summary(cost20_parts)
    delay1h = _summary(delay_parts)
    forecast_pass_folds = sum(bool(row["forecast_pass"]) for row in fold_rows)
    stability_score = float(forecast_pass_folds / len(fold_rows))
    incremental_net_bps = (float(candidate_eval["net_return"]) - float(baseline_eval["net_return"])) * 10_000.0
    sharpe_delta = float(candidate_eval["sharpe"]) - float(baseline_eval["sharpe"])
    turnover_delta = float(candidate_eval["turnover"]) - float(baseline_eval["turnover"])
    damage_delta_bps = (candidate_damage - baseline_damage) * 10_000.0
    wrong_side_count_delta = candidate_wrong_side_count - baseline_wrong_side_count

    evidence = FactorEvidence(
        factor_family="derivatives",
        feature_name="absolute_binance_premium_index_for_rv12_forecast",
        source_ids=("ssrn-2026-perpetual-basis", "binance-public-premium-index-klines"),
        coverage_fraction=coverage,
        causal_available=True,
        source_quality="primary",
        stability_score=stability_score,
        target_error="WRONG_SIDE_ECONOMIC_DAMAGE",
        association_value=float(np.median([row["basis_coefficient"] for row in fold_rows])),
        incremental_net_bps=incremental_net_bps,
        incremental_sharpe_delta=sharpe_delta,
        turnover_delta=turnover_delta,
        evaluation_fold_count=len(fold_rows),
        reverse_causality_checked=True,
        status="EVALUATED",
    )
    factor_admitted = admit_factor(evidence) and forecast_pass_folds >= 2
    promotion_failures: list[str] = []
    if forecast_pass_folds < 2:
        promotion_failures.append("basis_forecast_not_better_in_two_folds")
    if float(candidate_eval["net_return"]) <= float(baseline_eval["net_return"]):
        promotion_failures.append("evaluation_net_not_improved")
    if float(candidate_eval["sharpe"]) < float(baseline_eval["sharpe"]):
        promotion_failures.append("evaluation_sharpe_not_improved")
    if float(candidate_eval["max_drawdown"]) > float(baseline_eval["max_drawdown"]) + 0.01:
        promotion_failures.append("material_drawdown_damage")
    if candidate_damage >= baseline_damage:
        promotion_failures.append("wrong_side_economic_damage_not_reduced")
    if fold_positive < 2:
        promotion_failures.append("insufficient_multi_fold_economic_support")
    if float(cost20["net_return"]) < 0.0:
        promotion_failures.append("negative_at_20bps")
    if float(delay1h["net_return"]) < 0.0:
        promotion_failures.append("negative_with_1h_delay")
    if not factor_admitted:
        promotion_failures.append("factor_observatory_admission_failed")
    status = "PROMOTED_INNER" if not promotion_failures else "REJECTED_INNER"

    registry = V7TrialRegistry(registry_path, prior_count=857)
    registry.record(
        "H6",
        HYPOTHESIS,
        status,
        phase="escalation",
        config={
            "basis_proxy": "abs(previous_completed_1h_Binance_premium_index_close)",
            "baseline_vol_model": "future_rv12 ~ 1 + lag_rv12",
            "augmented_vol_model": "future_rv12 ~ 1 + lag_rv12 + abs_basis",
            "forecast_gate": "positive basis coefficient and lower OOS RMSE in at least 2/3 outer folds",
            "risk_mapping": "scale=min(1, selection_median_future_rv12 / predicted_rv12); invalid/nonpositive prediction => scale=1",
            "direction": "H12 unchanged",
            "threshold_grid": None,
        },
        metrics={
            "baseline_evaluation": baseline_eval,
            "candidate_evaluation": candidate_eval,
            "candidate_selection": candidate_selection,
            "cost20": cost20,
            "delay1h": delay1h,
            "forecast_pass_folds": forecast_pass_folds,
            "stability_score": stability_score,
            "factor_admitted": factor_admitted,
            "wrong_side_damage_baseline": baseline_damage,
            "wrong_side_damage_candidate": candidate_damage,
            "wrong_side_damage_delta_bps": damage_delta_bps,
            "wrong_side_count_delta": wrong_side_count_delta,
            "fold_positive_count": fold_positive,
            "promotion_failures": promotion_failures,
        },
    )
    registry.to_csv()
    _write_observatory_append(evidence)
    payload = {
        "hypothesis": HYPOTHESIS,
        "status": status,
        "trial_number": registry.total_count,
        "coverage_fraction": coverage,
        "folds": fold_rows,
        "forecast_pass_folds": forecast_pass_folds,
        "stability_score": stability_score,
        "factor_admitted": factor_admitted,
        "baseline_evaluation": baseline_eval,
        "candidate_selection": candidate_selection,
        "candidate_evaluation": candidate_eval,
        "cost20": cost20,
        "delay1h": delay1h,
        "wrong_side_damage_baseline": baseline_damage,
        "wrong_side_damage_candidate": candidate_damage,
        "wrong_side_damage_delta_bps": damage_delta_bps,
        "wrong_side_count_delta": wrong_side_count_delta,
        "fold_positive_count": fold_positive,
        "evaluation_scaled_fraction": scaled_fraction_weighted / scaled_rows if scaled_rows else 0.0,
        "promotion_failures": promotion_failures,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps({
        "status": status,
        "trial": registry.total_count,
        "forecast_pass_folds": forecast_pass_folds,
        "factor_admitted": factor_admitted,
        "baseline_eval_net": baseline_eval["net_return"],
        "candidate_eval_net": candidate_eval["net_return"],
        "wrong_side_damage_delta_bps": damage_delta_bps,
    }, indent=2))


if __name__ == "__main__":
    main()
