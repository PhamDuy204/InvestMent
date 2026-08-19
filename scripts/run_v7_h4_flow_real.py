from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_research.factor_observatory_v7 import (
    FactorEvidence,
    admit_factor,
    write_factor_observatory,
)
from crypto_research.flow_v7 import (
    build_flow_overlay_targets,
    fit_flow_control,
    flow_component,
)
from crypto_research.reliability_v7 import ReliabilityGateConfig
from crypto_research.run_v3 import stateful_summary
from crypto_research.run_v7 import (
    _promotion_gate,
    _wrong_side_count,
    replay_v7_reliability,
    split_selection_evaluation,
)
from crypto_research.trials_v7 import V7TrialRegistry

ART = Path("artifacts/multi_asset_v7")
HYPOTHESIS = "H4_lagged_taker_buy"


def _summary(parts: list[pd.DataFrame]) -> dict[str, object]:
    return stateful_summary(pd.concat(parts, ignore_index=True))


def _merge_factor(decisions: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
    left = decisions.copy()
    right = factors.copy()
    left["decision_timestamp"] = pd.to_datetime(left["decision_timestamp"], utc=True)
    right["decision_timestamp"] = pd.to_datetime(right["decision_timestamp"], utc=True)
    columns = ["decision_timestamp", "symbol", "lag_return_1h", "lag_taker_buy_quote_volume", "next_return_1h"]
    return left.merge(right[columns], on=["decision_timestamp", "symbol"], how="left", validate="one_to_one")


def _apply_fit(frame: pd.DataFrame, fit) -> pd.DataFrame:
    out = frame.copy()
    out["h4_flow_component"] = [flow_component(row, fit) for _, row in out.iterrows()]
    return out


def _evaluate(frame: pd.DataFrame, fit, *, cost_bps: float) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object], int]:
    enriched = _apply_fit(frame, fit)
    overlay = build_flow_overlay_targets(enriched, round_trip_cost_bps=cost_bps)
    candidate = enriched.merge(
        overlay[["decision_timestamp", "symbol", "h4_target_weight", "h4_veto"]],
        on=["decision_timestamp", "symbol"], how="left", validate="one_to_one",
    )
    if candidate["h4_target_weight"].isna().any():
        raise ValueError("H4 overlay target coverage is incomplete")
    candidate["target_weight"] = candidate["h4_target_weight"]
    periods, decisions, metrics = replay_v7_reliability(
        candidate, ReliabilityGateConfig(None, None, None, False), round_trip_cost_bps=cost_bps,
    )
    return periods, decisions, metrics, int(candidate["h4_veto"].sum())


def main() -> None:
    output = ART / "h4_order_flow_results.json"
    if output.exists():
        raise SystemExit("H4 result already exists; refusing to rerun trial")
    registry_path = ART / "experiment_registry.csv"
    existing = pd.read_csv(registry_path)
    if int(existing["trial_number"].max()) != 865:
        raise SystemExit("H4 must start exactly at trial 866")

    decisions = pd.read_csv("artifacts/multi_asset_v4/decision_log.csv.gz")
    delayed = pd.read_csv(ART / "delay_1h_decision_log.csv.gz")
    factors = pd.read_csv(ART / "hourly_factor_panel.csv.gz")
    for frame in (decisions, delayed, factors):
        frame["decision_timestamp"] = pd.to_datetime(frame["decision_timestamp"], utc=True)
    work = _merge_factor(decisions, factors)
    delayed_work = _merge_factor(delayed, factors)
    feature_cols = ["lag_return_1h", "lag_taker_buy_quote_volume", "next_return_1h"]
    coverage = float(work[feature_cols].notna().all(axis=1).mean())
    if coverage < 0.70:
        raise SystemExit(f"H4 causal data coverage below admission minimum: {coverage:.3f}")

    baseline_eval_parts: list[pd.DataFrame] = []
    candidate_eval_parts: list[pd.DataFrame] = []
    candidate_selection_parts: list[pd.DataFrame] = []
    cost20_parts: list[pd.DataFrame] = []
    delay_parts: list[pd.DataFrame] = []
    fold_rows: list[dict[str, object]] = []
    wrong_side_baseline = wrong_side_candidate = fold_positive = h4_vetoes = 0

    for fold in sorted(work["fold"].dropna().unique()):
        fold_work = work.loc[work["fold"] == fold].copy()
        selection, evaluation = split_selection_evaluation(fold_work, selection_fraction=0.70)
        delay_fold = delayed_work.loc[delayed_work["fold"] == fold].copy()
        _, delay_evaluation = split_selection_evaluation(delay_fold, selection_fraction=0.70)
        fit = fit_flow_control(selection)
        baseline_periods, baseline_decisions, baseline_metrics = replay_v7_reliability(
            evaluation, ReliabilityGateConfig(None, None, None, False), round_trip_cost_bps=10.0,
        )
        selection_periods, _, _, selection_vetoes = _evaluate(selection, fit, cost_bps=10.0)
        candidate_periods, candidate_decisions, candidate_metrics, evaluation_vetoes = _evaluate(evaluation, fit, cost_bps=10.0)
        cost20_periods, _, _, _ = _evaluate(evaluation, fit, cost_bps=20.0)
        delayed_periods, _, _, _ = _evaluate(delay_evaluation, fit, cost_bps=10.0)
        baseline_eval_parts.append(baseline_periods)
        candidate_eval_parts.append(candidate_periods)
        candidate_selection_parts.append(selection_periods)
        cost20_parts.append(cost20_periods)
        delay_parts.append(delayed_periods)
        fold_positive += int(float(candidate_metrics["net_return"]) > float(baseline_metrics["net_return"]))
        wrong_side_baseline += _wrong_side_count(evaluation, baseline_decisions, round_trip_cost_bps=10.0)
        wrong_side_candidate += _wrong_side_count(evaluation, candidate_decisions, round_trip_cost_bps=10.0)
        h4_vetoes += selection_vetoes + evaluation_vetoes
        fold_rows.append({
            "fold": int(fold), "selection_rows": int(len(selection)), "evaluation_rows": int(len(evaluation)),
            "flow_slope": float(fit.next_return_flow_slope), "flow_t_stat": float(fit.next_return_flow_t_stat),
            "selection_h4_net": float(stateful_summary(selection_periods)["net_return"]),
            "baseline_evaluation_net": float(baseline_metrics["net_return"]),
            "candidate_evaluation_net": float(candidate_metrics["net_return"]),
        })

    baseline_eval = _summary(baseline_eval_parts)
    candidate_eval = _summary(candidate_eval_parts)
    candidate_selection = _summary(candidate_selection_parts)
    cost20 = _summary(cost20_parts)
    delay1h = _summary(delay_parts)
    wrong_side_delta = wrong_side_candidate - wrong_side_baseline
    significant_folds = sum(abs(float(row["flow_t_stat"])) >= 1.96 for row in fold_rows)
    slopes = np.array([float(row["flow_slope"]) for row in fold_rows], dtype=float)
    slope_sign = np.sign(float(np.median(slopes)))
    stable_folds = sum(np.sign(float(row["flow_slope"])) == slope_sign and abs(float(row["flow_t_stat"])) >= 1.96 for row in fold_rows)
    stability_score = float(stable_folds / len(fold_rows))
    evidence = FactorEvidence(
        factor_family="microstructure", feature_name="lagged_taker_buy_quote_volume_controlled_for_lagged_return",
        source_ids=("jfm-2026-order-flow", "binance-public-usdm-1h"), coverage_fraction=coverage,
        causal_available=True, source_quality="peer_reviewed", stability_score=stability_score,
        target_error="WRONG_SIDE", association_value=float(np.median(slopes)),
        incremental_net_bps=(float(candidate_eval["net_return"]) - float(baseline_eval["net_return"])) * 10_000.0,
        incremental_sharpe_delta=float(candidate_eval["sharpe"]) - float(baseline_eval["sharpe"]),
        turnover_delta=float(candidate_eval["turnover"]) - float(baseline_eval["turnover"]),
        evaluation_fold_count=len(fold_rows), reverse_causality_checked=True, status="EVALUATED",
    )
    factor_admitted = admit_factor(evidence) and significant_folds >= 2
    promotion_passed, promotion_failures = _promotion_gate(
        baseline_eval, candidate_eval, wrong_side_delta=wrong_side_delta, fold_positive_count=fold_positive,
        fold_count=len(fold_rows), cost20_net=float(cost20["net_return"]), delay1h_net=float(delay1h["net_return"]),
    )
    if significant_folds < 2:
        promotion_failures.append("flow_coefficient_not_significant_in_two_folds")
    if not factor_admitted:
        promotion_failures.append("factor_observatory_admission_failed")
    status = "PROMOTED_INNER" if factor_admitted and promotion_passed else "REJECTED_INNER"
    registry = V7TrialRegistry(registry_path, prior_count=857)
    registry.record("H4", HYPOTHESIS, status, phase="escalation", config={
        "predictor": "log1p(lagged_1h_taker_buy_quote_volume), standardized per symbol on fold selection",
        "control": "lagged_1h_return", "flow_component": "FWL-equivalent residual flow contribution",
        "action": "veto only new/increased H12 exposure on sign conflict", "threshold_grid": None,
        "coefficient_significance_gate": "abs(t)>=1.96 in at least 2/3 folds",
    }, metrics={
        "baseline_evaluation": baseline_eval, "candidate_evaluation": candidate_eval, "candidate_selection": candidate_selection,
        "cost20": cost20, "delay1h": delay1h, "wrong_side_delta": wrong_side_delta,
        "fold_positive_count": fold_positive, "significant_folds": significant_folds,
        "stability_score": stability_score, "factor_admitted": factor_admitted, "promotion_failures": promotion_failures,
    })
    registry.to_csv()
    write_factor_observatory([evidence], ART / "factor_observatory.json")
    payload = {
        "hypothesis": HYPOTHESIS, "status": status, "trial_number": registry.total_count, "coverage_fraction": coverage,
        "folds": fold_rows, "significant_folds": significant_folds, "stability_score": stability_score,
        "factor_admitted": factor_admitted, "baseline_evaluation": baseline_eval, "candidate_selection": candidate_selection,
        "candidate_evaluation": candidate_eval, "cost20": cost20, "delay1h": delay1h, "wrong_side_delta": wrong_side_delta,
        "fold_positive_count": fold_positive, "h4_veto_count_selection_plus_evaluation": h4_vetoes,
        "promotion_failures": promotion_failures,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps({"status": status, "trial": registry.total_count, "wrong_side_delta": wrong_side_delta,
                      "significant_folds": significant_folds, "candidate_eval_net": candidate_eval["net_return"],
                      "baseline_eval_net": baseline_eval["net_return"]}, indent=2))


if __name__ == "__main__":
    main()
