from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_research.basis_v7 import apply_basis_vol_scale, wrong_side_damage
from crypto_research.diagnostics_v7 import (
    append_failure_ledger,
    build_failure_record,
    write_do_not_repeat,
)
from crypto_research.reliability_v7 import ReliabilityGateConfig
from crypto_research.run_v3 import stateful_summary
from crypto_research.run_v7 import (
    _wrong_side_count,
    replay_v7_reliability,
    split_selection_evaluation,
)
from crypto_research.trials_v7 import V7TrialRegistry

ART = Path("artifacts/multi_asset_v7")
HYPOTHESIS = "H7_lagged_rv_inverse_vol_ablation"


@dataclass(frozen=True)
class LagVolFit:
    intercept: float
    slope: float
    anchor_vol: float


def _fit(train: pd.DataFrame) -> LagVolFit:
    work = train[["lag_rv12", "future_rv12"]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(work) < 3:
        raise ValueError("lag-vol training data insufficient")
    x = work["lag_rv12"].to_numpy(dtype=float)
    y = work["future_rv12"].to_numpy(dtype=float)
    design = np.column_stack((np.ones(len(x)), x))
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    anchor = float(np.median(y))
    if anchor <= 0 or not np.isfinite(anchor):
        raise ValueError("lag-vol anchor invalid")
    return LagVolFit(float(coef[0]), float(coef[1]), anchor)


def _predict(row: pd.Series, fit: LagVolFit) -> float:
    return float(fit.intercept + fit.slope * float(row["lag_rv12"]))


def _scale(frame: pd.DataFrame, fit: LagVolFit) -> tuple[pd.DataFrame, float]:
    out = frame.copy()
    targets: list[float] = []
    scales: list[float] = []
    for _, row in out.iterrows():
        scaled = apply_basis_vol_scale(
            base_target_weight=float(row["target_weight"]),
            predicted_vol=_predict(row, fit),
            anchor_vol=fit.anchor_vol,
        )
        targets.append(float(scaled["target_weight"]))
        scales.append(float(scaled["basis_scale"]))
    out["base_target_weight"] = out["target_weight"]
    out["target_weight"] = targets
    out["lagvol_scale"] = scales
    return out, float(np.mean(np.asarray(scales) < 1.0))


def _summary(parts: list[pd.DataFrame]) -> dict[str, object]:
    return stateful_summary(pd.concat(parts, ignore_index=True))


def _gross_exposure_stats(decisions: pd.DataFrame) -> dict[str, float]:
    if decisions.empty:
        return {
            "mean_gross_exposure": 0.0,
            "median_gross_exposure": 0.0,
            "max_gross_exposure": 0.0,
        }
    work = decisions[["decision_timestamp", "proposed_target_weight"]].copy()
    work["decision_timestamp"] = pd.to_datetime(work["decision_timestamp"], utc=True)
    work["proposed_target_weight"] = pd.to_numeric(work["proposed_target_weight"], errors="coerce").fillna(0.0)
    gross = work.assign(abs_weight=work["proposed_target_weight"].abs()).groupby("decision_timestamp")["abs_weight"].sum()
    return {
        "mean_gross_exposure": float(gross.mean()),
        "median_gross_exposure": float(gross.median()),
        "max_gross_exposure": float(gross.max()),
    }


def _append_jsonl(path: Path, row: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def main() -> None:
    output = ART / "h7_lagvol_ablation_results.json"
    if output.exists():
        raise SystemExit("H7 result exists; refusing rerun")
    registry_path = ART / "experiment_registry.csv"
    existing = pd.read_csv(registry_path)
    if int(existing["trial_number"].max()) != 867:
        raise SystemExit("H7 must run exactly as trial 868")

    decisions = pd.read_csv("artifacts/multi_asset_v4/decision_log.csv.gz")
    delayed = pd.read_csv(ART / "delay_1h_decision_log.csv.gz")
    panel = pd.read_csv(ART / "basis_factor_panel.csv.gz")
    for frame in (decisions, delayed, panel):
        frame["decision_timestamp"] = pd.to_datetime(frame["decision_timestamp"], utc=True)
    features = panel[["decision_timestamp", "symbol", "lag_rv12", "future_rv12"]]
    work = decisions.merge(features, on=["decision_timestamp", "symbol"], how="left", validate="one_to_one")
    delayed_work = delayed.merge(features, on=["decision_timestamp", "symbol"], how="left", validate="one_to_one")
    coverage = float(work[["lag_rv12", "future_rv12"]].notna().all(axis=1).mean())
    if coverage < 0.70:
        raise SystemExit(f"H7 coverage below 0.70: {coverage:.3f}")

    baseline_parts: list[pd.DataFrame] = []
    candidate_parts: list[pd.DataFrame] = []
    selection_parts: list[pd.DataFrame] = []
    cost20_parts: list[pd.DataFrame] = []
    delay_parts: list[pd.DataFrame] = []
    baseline_decision_parts: list[pd.DataFrame] = []
    candidate_decision_parts: list[pd.DataFrame] = []
    fold_rows: list[dict[str, object]] = []
    baseline_damage = 0.0
    candidate_damage = 0.0
    baseline_wrong = 0
    candidate_wrong = 0
    fold_positive = 0
    scaled_rows = 0
    scaled_weighted = 0.0

    for fold in sorted(work["fold"].dropna().unique()):
        fold_work = work.loc[work["fold"] == fold].copy()
        selection, evaluation = split_selection_evaluation(fold_work, selection_fraction=0.70)
        delay_fold = delayed_work.loc[delayed_work["fold"] == fold].copy()
        _, delay_eval = split_selection_evaluation(delay_fold, selection_fraction=0.70)
        fit = _fit(selection)

        base_periods, base_decisions, base_metrics = replay_v7_reliability(
            evaluation, ReliabilityGateConfig(None, None, None, False), round_trip_cost_bps=10.0
        )
        scaled_selection, selection_scaled = _scale(selection, fit)
        selection_periods, _, selection_metrics = replay_v7_reliability(
            scaled_selection, ReliabilityGateConfig(None, None, None, False), round_trip_cost_bps=10.0
        )
        scaled_eval, evaluation_scaled = _scale(evaluation, fit)
        cand_periods, cand_decisions, cand_metrics = replay_v7_reliability(
            scaled_eval, ReliabilityGateConfig(None, None, None, False), round_trip_cost_bps=10.0
        )
        cost20_periods, _, cost20_metrics = replay_v7_reliability(
            scaled_eval, ReliabilityGateConfig(None, None, None, False), round_trip_cost_bps=20.0
        )
        scaled_delay, _ = _scale(delay_eval, fit)
        delayed_periods, _, delay1h_metrics = replay_v7_reliability(
            scaled_delay, ReliabilityGateConfig(None, None, None, False), round_trip_cost_bps=10.0
        )

        labels = evaluation[["decision_timestamp", "symbol", "holding_return_label", "funding_sum_label"]]
        baseline_damage += wrong_side_damage(base_decisions, labels, round_trip_cost_bps=10.0)
        candidate_damage += wrong_side_damage(cand_decisions, labels, round_trip_cost_bps=10.0)
        baseline_wrong += _wrong_side_count(evaluation, base_decisions, round_trip_cost_bps=10.0)
        candidate_wrong += _wrong_side_count(evaluation, cand_decisions, round_trip_cost_bps=10.0)
        fold_positive += int(float(cand_metrics["net_return"]) > float(base_metrics["net_return"]))
        baseline_parts.append(base_periods)
        candidate_parts.append(cand_periods)
        selection_parts.append(selection_periods)
        cost20_parts.append(cost20_periods)
        delay_parts.append(delayed_periods)
        baseline_decision_parts.append(base_decisions)
        candidate_decision_parts.append(cand_decisions)
        scaled_weighted += evaluation_scaled * len(evaluation)
        scaled_rows += len(evaluation)
        fold_rows.append(
            {
                "fold": int(fold),
                "selection_rows": int(len(selection)),
                "evaluation_rows": int(len(evaluation)),
                "intercept": fit.intercept,
                "slope": fit.slope,
                "anchor_vol": fit.anchor_vol,
                "selection_scaled_fraction": selection_scaled,
                "evaluation_scaled_fraction": evaluation_scaled,
                "candidate_selection_metrics": selection_metrics,
                "baseline_evaluation_metrics": base_metrics,
                "candidate_evaluation_metrics": cand_metrics,
                "cost20_metrics": cost20_metrics,
                "delay1h_metrics": delay1h_metrics,
            }
        )

    baseline = _summary(baseline_parts)
    candidate = _summary(candidate_parts)
    selection = _summary(selection_parts)
    cost20 = _summary(cost20_parts)
    delay1h = _summary(delay_parts)
    baseline_gross_exposure = _gross_exposure_stats(pd.concat(baseline_decision_parts, ignore_index=True))
    candidate_gross_exposure = _gross_exposure_stats(pd.concat(candidate_decision_parts, ignore_index=True))
    damage_delta_bps = (candidate_damage - baseline_damage) * 10_000.0
    wrong_count_delta = candidate_wrong - baseline_wrong
    failures: list[str] = []
    if float(candidate["net_return"]) <= float(baseline["net_return"]):
        failures.append("evaluation_net_not_improved")
    if float(candidate["sharpe"]) <= float(baseline["sharpe"]):
        failures.append("evaluation_sharpe_not_improved")
    if float(candidate["max_drawdown"]) > float(baseline["max_drawdown"]) + 0.01:
        failures.append("material_drawdown_damage")
    if candidate_damage >= baseline_damage:
        failures.append("wrong_side_economic_damage_not_reduced")
    if fold_positive < 2:
        failures.append("insufficient_multi_fold_economic_support")
    if float(cost20["net_return"]) < 0.0:
        failures.append("negative_at_20bps")
    if float(delay1h["net_return"]) < 0.0:
        failures.append("negative_with_1h_delay")
    status = "PROMOTED_INNER" if not failures else "REJECTED_INNER"

    h6 = json.loads((ART / "h6_basis_vol_results.json").read_text(encoding="utf-8"))
    h6_eval = h6["candidate_evaluation"]
    comparison_to_h6 = {
        "evaluation_net_delta": float(candidate["net_return"]) - float(h6_eval["net_return"]),
        "evaluation_sharpe_delta": float(candidate["sharpe"]) - float(h6_eval["sharpe"]),
        "evaluation_max_drawdown_delta": float(candidate["max_drawdown"]) - float(h6_eval["max_drawdown"]),
        "evaluation_turnover_delta": float(candidate["turnover"]) - float(h6_eval["turnover"]),
        "evaluation_trade_count_delta": int(candidate["trade_count"]) - int(h6_eval["trade_count"]),
        "evaluation_transaction_cost_delta": float(candidate["transaction_cost"]) - float(h6_eval["transaction_cost"]),
        "cost20_net_delta": float(cost20["net_return"]) - float(h6["cost20"]["net_return"]),
        "delay1h_net_delta": float(delay1h["net_return"]) - float(h6["delay1h"]["net_return"]),
        "evaluation_scaled_fraction_delta": (
            scaled_weighted / scaled_rows if scaled_rows else 0.0
        )
        - float(h6["evaluation_scaled_fraction"]),
    }

    registry = V7TrialRegistry(registry_path, prior_count=857)
    trial_row = registry.record(
        "H7",
        HYPOTHESIS,
        status,
        phase="escalation",
        config={
            "purpose": "H6 attribution ablation; remove basis and retain the same no-boost inverse-vol mapping",
            "vol_model": "future_rv12 ~ 1 + lag_rv12, fit only on fold selection",
            "anchor": "selection median future_rv12",
            "risk_mapping": "scale=min(1, anchor/predicted_rv12); invalid/nonpositive prediction => scale=1",
            "direction": "H12 unchanged",
            "execution": "MARKET",
            "max_effective_exposure": "1x baseline; no leverage boost",
            "threshold_grid": None,
        },
        metrics={
            "baseline_evaluation": baseline,
            "candidate_evaluation": candidate,
            "candidate_selection": selection,
            "cost20": cost20,
            "delay1h": delay1h,
            "baseline_gross_exposure": baseline_gross_exposure,
            "candidate_gross_exposure": candidate_gross_exposure,
            "wrong_side_damage_baseline": baseline_damage,
            "wrong_side_damage_candidate": candidate_damage,
            "wrong_side_damage_delta_bps": damage_delta_bps,
            "wrong_side_count_delta": wrong_count_delta,
            "fold_positive_count": fold_positive,
            "comparison_to_h6": comparison_to_h6,
            "promotion_failures": failures,
        },
    )
    registry.to_csv()

    evaluation_scaled_fraction = scaled_weighted / scaled_rows if scaled_rows else 0.0
    payload = {
        "hypothesis": HYPOTHESIS,
        "status": status,
        "trial_number": registry.total_count,
        "coverage_fraction": coverage,
        "folds": fold_rows,
        "baseline_evaluation": baseline,
        "candidate_selection": selection,
        "candidate_evaluation": candidate,
        "cost20": cost20,
        "delay1h": delay1h,
        "baseline_gross_exposure": baseline_gross_exposure,
        "candidate_gross_exposure": candidate_gross_exposure,
        "wrong_side_count_baseline": baseline_wrong,
        "wrong_side_count_candidate": candidate_wrong,
        "wrong_side_damage_baseline": baseline_damage,
        "wrong_side_damage_candidate": candidate_damage,
        "wrong_side_damage_delta_bps": damage_delta_bps,
        "wrong_side_count_delta": wrong_count_delta,
        "fold_positive_count": fold_positive,
        "evaluation_scaled_fraction": evaluation_scaled_fraction,
        "comparison_to_h6": comparison_to_h6,
        "promotion_failures": failures,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")

    error_summary = {
        "baseline": {
            "WRONG_SIDE": baseline_wrong,
            "wrong_side_economic_damage": baseline_damage,
        },
        "candidate": {
            "WRONG_SIDE": candidate_wrong,
            "wrong_side_economic_damage": candidate_damage,
        },
        "delta": {
            "WRONG_SIDE": wrong_count_delta,
            "wrong_side_economic_damage_bps": damage_delta_bps,
        },
        "note": "H7 is a sizing-only controller; wrong-side economic damage is the primary error target while raw WRONG_SIDE count is reported diagnostically.",
    }
    (ART / "h7_decision_error_summary.json").write_text(
        json.dumps(error_summary, indent=2, sort_keys=True), encoding="utf-8"
    )

    _append_jsonl(
        ART / "hypothesis_registry.jsonl",
        {
            "hypothesis_id": HYPOTHESIS,
            "status": status,
            "trial_number": registry.total_count,
            "target_error": "WRONG_SIDE_ECONOMIC_DAMAGE",
            "factor_family": "risk_controller_ablation",
            "causal_inputs": ["lag_rv12"],
            "outcome_only": ["future_rv12"],
            "expected_mechanism": "generic continuous lag-RV-only volatility targeting may explain H6 de-risking without basis information",
            "single_change": "remove abs_basis from the H6 volatility forecast and preserve all other sizing/replay semantics",
            "required_test": "fold-local selection fit, >=2 positive evaluation folds, economic/error gates, non-negative 20bps and +1h stress for serious promotion",
            "approved_by": "predeclared H6 attribution ablation",
        },
    )
    _append_jsonl(
        ART / "agent_research_log.jsonl",
        {
            "status": "LOCAL_PREDECLARED_ABLATION_COMPLETED",
            "research_step": "H7",
            "hypothesis_id": HYPOTHESIS,
            "trial_number": registry.total_count,
            "trial_status": status,
            "performance_trial_count_after": registry.total_count,
            "basis_incremental_attribution": "compare H7 directly with H6; no basis transform or threshold rescue",
        },
    )

    if status == "REJECTED_INNER":
        failure = build_failure_record(
            trial_number=registry.total_count,
            hypothesis=HYPOTHESIS,
            target_error="WRONG_SIDE_ECONOMIC_DAMAGE",
            expected_mechanism="generic continuous lag-RV-only volatility targeting reduces H12 wrong-side economic damage while retaining after-cost economic edge",
            causal_inputs=["lag_rv12"],
            action="scale H12 target by min(1, selection median RV12 / lag-RV-only predicted RV12)",
            actual_error_delta=wrong_count_delta,
            net_effect_bps=(float(candidate["net_return"]) - float(baseline["net_return"])) * 10_000.0,
            turnover_effect=float(candidate["turnover"]) - float(baseline["turnover"]),
            drawdown_effect=float(candidate["max_drawdown"]) - float(baseline["max_drawdown"]),
            damaged_regime="mandatory promotion stress and any evaluation folds without positive incremental support",
            helped_regime="held-out risk suppression where wrong-side economic damage is reduced",
            assumption_status="GENERIC_CONTINUOUS_VOL_CONTROL_NOT_PROMOTABLE",
            failure_reason=";".join(failures),
            next_allowed_question="Require a materially new causal reliability mechanism; do not grid lag-vol thresholds, anchors, or scale floors around H7.",
            timestamp_utc=str(trial_row["timestamp_utc"]),
        )
        ledger_path = ART / "failure_ledger.csv.gz"
        append_failure_ledger([failure], ledger_path)
        write_do_not_repeat(pd.read_csv(ledger_path).to_dict("records"), ART / "do_not_repeat.json")

    print(
        json.dumps(
            {
                "status": status,
                "trial": registry.total_count,
                "baseline_eval_net": baseline["net_return"],
                "candidate_eval_net": candidate["net_return"],
                "cost20_net": cost20["net_return"],
                "delay1h_net": delay1h["net_return"],
                "evaluation_scaled_fraction": evaluation_scaled_fraction,
                "wrong_side_damage_delta_bps": damage_delta_bps,
                "comparison_to_h6": comparison_to_h6,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
