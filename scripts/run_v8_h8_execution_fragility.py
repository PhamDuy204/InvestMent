"""Run predeclared V8 H8 as an offline historical research trial only."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from crypto_research.basis_v7 import wrong_side_damage
from crypto_research.diagnostics_v7 import (
    append_failure_ledger,
    build_failure_record,
    write_do_not_repeat,
)
from crypto_research.execution_v8 import (
    DelayDamageFit,
    apply_execution_fragility_scale,
    fit_delay_damage_models,
    gross_exposure_stats,
)
from crypto_research.reliability_v7 import ReliabilityGateConfig
from crypto_research.run_v3 import stateful_summary
from crypto_research.run_v7 import (
    _wrong_side_count,
    replay_v7_reliability,
    split_selection_evaluation,
)
from crypto_research.trials_v7 import V7TrialRegistry

ART_V7 = Path("artifacts/multi_asset_v7")
ART_V8 = Path("artifacts/multi_asset_v8")
HYPOTHESIS = "H8_lagged_impact_execution_fragility"
FEATURES = ["lag_rv12", "log_impact_1h"]


def _rmse(actual: Iterable[float], predicted: Iterable[float]) -> float:
    y = np.asarray(list(actual), dtype=float)
    p = np.asarray(list(predicted), dtype=float)
    if not len(y) or len(y) != len(p):
        raise ValueError("RMSE requires equally sized non-empty arrays")
    return float(np.sqrt(np.mean(np.square(y - p))))


def _forecast_admission(folds: list[dict[str, object]]) -> bool:
    rmse_wins = sum(float(row["augmented_rmse"]) < float(row["baseline_rmse"]) for row in folds)
    positive_slopes = sum(float(row["impact_slope"]) > 0.0 for row in folds)
    return rmse_wins >= 2 and positive_slopes >= 2


def _prepare_registry(source: Path, target: Path) -> Path:
    source_frame = pd.read_csv(source)
    if source_frame.empty or int(source_frame["trial_number"].max()) != 868:
        raise ValueError("V8 must inherit V7 registry with tail 868")
    if target.exists():
        target_frame = pd.read_csv(target)
        if target_frame.empty or int(target_frame["trial_number"].max()) != 868:
            raise ValueError("existing V8 registry must still have tail 868 before H8")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def _copy_audit_memory() -> None:
    ART_V8.mkdir(parents=True, exist_ok=True)
    for name in (
        "failure_ledger.csv.gz",
        "do_not_repeat.json",
        "hypothesis_registry.jsonl",
        "agent_research_log.jsonl",
        "factor_observatory.json",
    ):
        source = ART_V7 / name
        target = ART_V8 / name
        if source.exists() and not target.exists():
            shutil.copy2(source, target)


def _predict(frame: pd.DataFrame, fit: DelayDamageFit) -> tuple[np.ndarray, np.ndarray]:
    rv = pd.to_numeric(frame["lag_rv12"], errors="coerce").to_numpy(dtype=float)
    impact = pd.to_numeric(frame["log_impact_1h"], errors="coerce").to_numpy(dtype=float)
    base = fit.baseline_intercept + fit.baseline_lag_rv_slope * rv
    aug = fit.augmented_intercept + fit.augmented_lag_rv_slope * rv + fit.impact_slope * impact
    return base, aug


def _forecast_row(evaluation: pd.DataFrame, fit: DelayDamageFit, fold: int) -> dict[str, object]:
    work = evaluation.loc[evaluation["exposure_increase"].astype(bool)].dropna(
        subset=FEATURES + ["delay_damage_per_unit"]
    )
    base, aug = _predict(work, fit)
    actual = pd.to_numeric(work["delay_damage_per_unit"], errors="coerce").to_numpy(dtype=float)
    return {
        "fold": int(fold),
        "rows": int(len(work)),
        "baseline_rmse": _rmse(actual, base),
        "augmented_rmse": _rmse(actual, aug),
        "impact_slope": float(fit.impact_slope),
        "anchor_damage": float(fit.anchor_damage),
    }


def _summary(parts: list[pd.DataFrame]) -> dict[str, object]:
    return stateful_summary(pd.concat(parts, ignore_index=True))


def _new_exposure_amount(previous: pd.Series, target: pd.Series) -> pd.Series:
    previous = pd.to_numeric(previous, errors="coerce").fillna(0.0)
    target = pd.to_numeric(target, errors="coerce").fillna(0.0)
    sign_flip = previous.mul(target) < 0.0
    same_side_add = (target.abs() - previous.abs()).clip(lower=0.0)
    return same_side_add.where(~sign_flip, target.abs())


def _delay_damage_total(frame: pd.DataFrame) -> float:
    amount = _new_exposure_amount(frame["previous_weight"], frame["target_weight"])
    damage = pd.to_numeric(frame["delay_damage_per_unit"], errors="coerce").fillna(0.0)
    return float((amount * damage).sum())


def _append_jsonl(path: Path, row: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _record_factor_observatory(
    forecast_rows: list[dict[str, object]],
    admitted: bool,
    candidate: dict[str, object],
    baseline: dict[str, object],
) -> None:
    path = ART_V8 / "factor_observatory.json"
    payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"factors": []}
    rmse_wins = sum(float(row["augmented_rmse"]) < float(row["baseline_rmse"]) for row in forecast_rows)
    positive_slopes = sum(float(row["impact_slope"]) > 0.0 for row in forecast_rows)
    payload.setdefault("factors", []).append(
        {
            "feature_name": "lagged_amihud_style_impact_after_lag_rv_control",
            "factor_family": "execution_risk",
            "status": "EVALUATED",
            "admitted": admitted,
            "causal_available": True,
            "coverage_fraction": 1.0,
            "evaluation_fold_count": len(forecast_rows),
            "forecast_rmse_win_folds": rmse_wins,
            "positive_coefficient_folds": positive_slopes,
            "stability_score": positive_slopes / max(1, len(forecast_rows)),
            "incremental_net_bps": (
                float(candidate["net_return"]) - float(baseline["net_return"])
            )
            * 10_000.0,
            "incremental_sharpe_delta": float(candidate["sharpe"]) - float(baseline["sharpe"]),
            "source_quality": "peer_reviewed",
            "source_ids": ["jbf-2025-liquidity-provision-returns", "binance-public-usdm-1h"],
            "target_error": "ONE_HOUR_DELAY_IMPLEMENTATION_DAMAGE",
            "note": "Amihud-style lagged price-impact proxy; not order-book depth or exact L2 liquidity.",
        }
    )
    payload["status"] = "EVALUATED"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> None:
    output = ART_V8 / "h8_execution_fragility_results.json"
    if output.exists():
        raise SystemExit("H8 result exists; refusing rerun")

    registry_path = _prepare_registry(ART_V7 / "experiment_registry.csv", ART_V8 / "experiment_registry.csv")
    _copy_audit_memory()
    inherited = pd.read_csv(registry_path)
    if int(inherited["trial_number"].max()) != 868:
        raise SystemExit("H8 must run exactly as trial 869")

    panel = pd.read_csv(ART_V8 / "execution_factor_panel.csv.gz")
    delayed = pd.read_csv(ART_V7 / "delay_1h_decision_log.csv.gz")
    for frame in (panel, delayed):
        frame["decision_timestamp"] = pd.to_datetime(frame["decision_timestamp"], utc=True)
    delayed = delayed.merge(
        panel[["decision_timestamp", "symbol", "lag_rv12", "log_impact_1h"]],
        on=["decision_timestamp", "symbol"],
        how="left",
        validate="one_to_one",
    )

    baseline_parts: list[pd.DataFrame] = []
    candidate_parts: list[pd.DataFrame] = []
    selection_parts: list[pd.DataFrame] = []
    cost20_parts: list[pd.DataFrame] = []
    delay_parts: list[pd.DataFrame] = []
    baseline_decisions: list[pd.DataFrame] = []
    candidate_decisions: list[pd.DataFrame] = []
    fold_rows: list[dict[str, object]] = []
    forecast_rows: list[dict[str, object]] = []
    baseline_wrong = candidate_wrong = 0
    baseline_wrong_damage = candidate_wrong_damage = 0.0
    baseline_delay_damage = candidate_delay_damage = 0.0
    fold_positive = 0
    scaled_count = row_count = 0

    for fold in sorted(panel["fold"].dropna().unique()):
        fold_panel = panel.loc[panel["fold"] == fold].copy()
        selection, evaluation = split_selection_evaluation(fold_panel, selection_fraction=0.70)
        delay_fold = delayed.loc[delayed["fold"] == fold].copy()
        _, delay_eval = split_selection_evaluation(delay_fold, selection_fraction=0.70)
        fit = fit_delay_damage_models(selection)
        forecast = _forecast_row(evaluation, fit, int(fold))
        forecast_rows.append(forecast)

        base_periods, base_decisions, base_metrics = replay_v7_reliability(
            evaluation, ReliabilityGateConfig(None, None, None, False), round_trip_cost_bps=10.0
        )
        scaled_selection = apply_execution_fragility_scale(selection, fit)
        select_periods, _, select_metrics = replay_v7_reliability(
            scaled_selection,
            ReliabilityGateConfig(None, None, None, False),
            round_trip_cost_bps=10.0,
        )
        scaled_eval = apply_execution_fragility_scale(evaluation, fit)
        cand_periods, cand_decisions, cand_metrics = replay_v7_reliability(
            scaled_eval, ReliabilityGateConfig(None, None, None, False), round_trip_cost_bps=10.0
        )
        cost_periods, _, cost_metrics = replay_v7_reliability(
            scaled_eval, ReliabilityGateConfig(None, None, None, False), round_trip_cost_bps=20.0
        )
        scaled_delay = apply_execution_fragility_scale(delay_eval, fit)
        delay_periods, _, delay_metrics = replay_v7_reliability(
            scaled_delay, ReliabilityGateConfig(None, None, None, False), round_trip_cost_bps=10.0
        )

        labels = evaluation[["decision_timestamp", "symbol", "holding_return_label", "funding_sum_label"]]
        baseline_wrong += _wrong_side_count(evaluation, base_decisions, round_trip_cost_bps=10.0)
        candidate_wrong += _wrong_side_count(scaled_eval, cand_decisions, round_trip_cost_bps=10.0)
        baseline_wrong_damage += wrong_side_damage(base_decisions, labels, round_trip_cost_bps=10.0)
        candidate_wrong_damage += wrong_side_damage(cand_decisions, labels, round_trip_cost_bps=10.0)
        baseline_delay_damage += _delay_damage_total(evaluation)
        scaled_damage_frame = scaled_eval[
            ["previous_weight", "target_weight", "delay_damage_per_unit"]
        ]
        candidate_delay_damage += _delay_damage_total(scaled_damage_frame)
        fold_positive += int(float(cand_metrics["net_return"]) > float(base_metrics["net_return"]))
        scaled_count += int((scaled_eval["execution_fragility_scale"] < 1.0).sum())
        row_count += len(scaled_eval)

        baseline_parts.append(base_periods)
        candidate_parts.append(cand_periods)
        selection_parts.append(select_periods)
        cost20_parts.append(cost_periods)
        delay_parts.append(delay_periods)
        baseline_decisions.append(base_decisions)
        candidate_decisions.append(cand_decisions)
        fold_rows.append(
            {
                **forecast,
                "selection_rows": int(len(selection)),
                "evaluation_rows": int(len(evaluation)),
                "selection_metrics": select_metrics,
                "baseline_evaluation_metrics": base_metrics,
                "candidate_evaluation_metrics": cand_metrics,
                "cost20_metrics": cost_metrics,
                "delay1h_metrics": delay_metrics,
            }
        )

    baseline = _summary(baseline_parts)
    candidate = _summary(candidate_parts)
    selection_metrics = _summary(selection_parts)
    cost20 = _summary(cost20_parts)
    delay1h = _summary(delay_parts)
    admitted = _forecast_admission(forecast_rows)
    exposure = gross_exposure_stats(pd.concat(candidate_decisions, ignore_index=True))
    baseline_exposure = gross_exposure_stats(pd.concat(baseline_decisions, ignore_index=True))

    failures: list[str] = []
    if not admitted:
        failures.append("execution_fragility_forecast_admission_failed")
    if float(candidate["net_return"]) <= float(baseline["net_return"]):
        failures.append("evaluation_net_not_improved")
    if float(candidate["net_return"]) <= 0.0:
        failures.append("evaluation_net_not_positive")
    if float(candidate["sharpe"]) < float(baseline["sharpe"]):
        failures.append("evaluation_sharpe_worse")
    if float(candidate["max_drawdown"]) > float(baseline["max_drawdown"]) + 0.01:
        failures.append("material_drawdown_damage")
    if fold_positive < 2:
        failures.append("insufficient_multi_fold_economic_support")
    if candidate_delay_damage >= baseline_delay_damage:
        failures.append("delay_implementation_damage_not_reduced")
    if float(cost20["net_return"]) < 0.0:
        failures.append("negative_at_20bps")
    if float(delay1h["net_return"]) < 0.0:
        failures.append("negative_with_1h_delay")
    if float(exposure["mean_gross_exposure"]) < 0.20:
        failures.append("economic_exposure_too_small")
    status = "PROMOTED_INNER" if not failures else "REJECTED_INNER"

    registry = V7TrialRegistry(registry_path, prior_count=857)
    row = registry.record(
        "H8",
        HYPOTHESIS,
        status,
        phase="v8_execution",
        config={
            "feature": "log10(abs(lag_return_1h)/lag_quote_volume)",
            "baseline_damage_model": "delay_damage ~ 1 + lag_rv12",
            "augmented_damage_model": "delay_damage ~ 1 + lag_rv12 + log_impact_1h",
            "mapping": "scale=anchor/(anchor+max(0,pred_aug-pred_base)) on exposure increases only",
            "direction": "H12 unchanged",
            "execution": "MARKET",
            "max_effective_exposure": "1x baseline; no boost",
            "grid": None,
        },
        metrics={
            "baseline_evaluation": baseline,
            "candidate_evaluation": candidate,
            "candidate_selection": selection_metrics,
            "cost20": cost20,
            "delay1h": delay1h,
            "factor_admitted": admitted,
            "fold_positive_count": fold_positive,
            "baseline_delay_damage": baseline_delay_damage,
            "candidate_delay_damage": candidate_delay_damage,
            "wrong_side_count_delta": candidate_wrong - baseline_wrong,
            "wrong_side_damage_delta_bps": (candidate_wrong_damage - baseline_wrong_damage) * 10_000.0,
            "promotion_failures": failures,
        },
    )
    row["trial_id"] = str(row["trial_id"]).replace("v7-", "v8-", 1)
    registry.to_csv()
    if registry.total_count != 869:
        raise RuntimeError(f"unexpected V8 trial number {registry.total_count}")

    _record_factor_observatory(forecast_rows, admitted, candidate, baseline)
    _append_jsonl(
        ART_V8 / "hypothesis_registry.jsonl",
        {
            "hypothesis_id": HYPOTHESIS,
            "status": status,
            "trial_number": 869,
            "factor_family": "execution_risk",
            "causal_inputs": FEATURES,
            "outcome_only": ["delay_damage_per_unit"],
            "single_change": "add lagged price-impact proxy after lag-RV control and scale only new/increased exposure",
            "approved_by": "predeclared V8 design",
        },
    )
    _append_jsonl(
        ART_V8 / "agent_research_log.jsonl",
        {
            "status": "V8_H8_COMPLETED",
            "trial_number": 869,
            "hypothesis_id": HYPOTHESIS,
            "trial_status": status,
            "factor_admitted": admitted,
        },
    )

    payload = {
        "hypothesis": HYPOTHESIS,
        "trial_number": 869,
        "status": status,
        "factor_admitted": admitted,
        "forecast_folds": forecast_rows,
        "folds": fold_rows,
        "baseline_evaluation": baseline,
        "candidate_selection": selection_metrics,
        "candidate_evaluation": candidate,
        "cost20": cost20,
        "delay1h": delay1h,
        "baseline_gross_exposure": baseline_exposure,
        "candidate_gross_exposure": exposure,
        "scaled_fraction": scaled_count / row_count if row_count else 0.0,
        "fold_positive_count": fold_positive,
        "baseline_delay_damage": baseline_delay_damage,
        "candidate_delay_damage": candidate_delay_damage,
        "delay_damage_delta_bps": (candidate_delay_damage - baseline_delay_damage) * 10_000.0,
        "wrong_side_count_baseline": baseline_wrong,
        "wrong_side_count_candidate": candidate_wrong,
        "wrong_side_count_delta": candidate_wrong - baseline_wrong,
        "wrong_side_damage_baseline": baseline_wrong_damage,
        "wrong_side_damage_candidate": candidate_wrong_damage,
        "wrong_side_damage_delta_bps": (candidate_wrong_damage - baseline_wrong_damage) * 10_000.0,
        "promotion_failures": failures,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")

    if status == "REJECTED_INNER":
        failure = build_failure_record(
            trial_number=869,
            hypothesis=HYPOTHESIS,
            target_error="ONE_HOUR_DELAY_IMPLEMENTATION_DAMAGE",
            expected_mechanism="lagged price movement per quote-notional identifies fragile H12 exposure increases after controlling lagged RV",
            causal_inputs=FEATURES,
            action="offline no-boost scaling of new/increased H12 exposure by factor-attributable predicted delay damage",
            actual_error_delta=candidate_wrong - baseline_wrong,
            net_effect_bps=(float(candidate["net_return"]) - float(baseline["net_return"])) * 10_000.0,
            turnover_effect=float(candidate["turnover"]) - float(baseline["turnover"]),
            drawdown_effect=float(candidate["max_drawdown"]) - float(baseline["max_drawdown"]),
            damaged_regime="mandatory promotion stress and any folds without positive incremental support",
            helped_regime="held-out rows where delay implementation damage was reduced",
            assumption_status="EXECUTION_FRAGILITY_POLICY_NOT_PROMOTABLE",
            failure_reason=";".join(failures),
            next_allowed_question="Require a materially new execution/liquidity mechanism or forward L2 evidence; do not grid lagged-impact transforms or thresholds around H8.",
            timestamp_utc=str(row["timestamp_utc"]),
        )
        ledger = ART_V8 / "failure_ledger.csv.gz"
        append_failure_ledger([failure], ledger)
        write_do_not_repeat(pd.read_csv(ledger).to_dict("records"), ART_V8 / "do_not_repeat.json")

    print(json.dumps({
        "trial": 869,
        "status": status,
        "factor_admitted": admitted,
        "baseline_eval_net": baseline["net_return"],
        "candidate_eval_net": candidate["net_return"],
        "cost20_net": cost20["net_return"],
        "delay1h_net": delay1h["net_return"],
        "fold_positive_count": fold_positive,
        "scaled_fraction": payload["scaled_fraction"],
        "delay_damage_delta_bps": payload["delay_damage_delta_bps"],
        "wrong_side_damage_delta_bps": payload["wrong_side_damage_delta_bps"],
        "failures": failures,
    }, indent=2))


if __name__ == "__main__":
    main()
