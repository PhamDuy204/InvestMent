from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from crypto_research.reliability_v7 import ReliabilityGateConfig, fit_reliability_gates
from crypto_research.run_v3 import stateful_summary
from crypto_research.trials_v7 import V7TrialRegistry


def _summary(parts: list[pd.DataFrame]) -> dict[str, Any]:
    return stateful_summary(pd.concat(parts, ignore_index=True))


def run_v7_first_line_foldwise(
    decision_log: pd.DataFrame,
    qh_features: pd.DataFrame,
    dispersion: pd.DataFrame,
    *,
    artifact_root: str | Path,
    prior_trials: int,
    round_trip_cost_bps: float,
    selection_fraction: float,
    delay_decision_log: pd.DataFrame | None,
) -> dict[str, Any]:
    from crypto_research.run_v7 import (
        _merge_first_line_features,
        _promotion_gate,
        _variant_config,
        _write_json,
        _wrong_side_count,
        replay_v7_reliability,
        split_selection_evaluation,
    )

    root = Path(artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    work = _merge_first_line_features(decision_log, qh_features, dispersion)
    folds = list(
        work[["fold", "decision_timestamp"]]
        .drop_duplicates()
        .sort_values("decision_timestamp")["fold"]
        .drop_duplicates()
    )
    partitions: dict[object, tuple[pd.DataFrame, pd.DataFrame]] = {}
    fitted: dict[object, ReliabilityGateConfig] = {}
    for fold in folds:
        part = work.loc[work["fold"] == fold].copy()
        selection, evaluation = split_selection_evaluation(part, selection_fraction=selection_fraction)
        partitions[fold] = (selection, evaluation)
        fitted[fold] = fit_reliability_gates(selection)

    delayed_partitions: dict[object, pd.DataFrame] = {}
    if delay_decision_log is not None:
        delayed = _merge_first_line_features(delay_decision_log, qh_features, dispersion)
        for fold in folds:
            part = delayed.loc[delayed["fold"] == fold].copy()
            _, evaluation = split_selection_evaluation(part, selection_fraction=selection_fraction)
            delayed_partitions[fold] = evaluation

    registry = V7TrialRegistry(root / "experiment_registry.csv", prior_count=prior_trials)
    baseline_config = ReliabilityGateConfig(None, None, None, False)
    baseline_sel_periods: list[pd.DataFrame] = []
    baseline_eval_periods: list[pd.DataFrame] = []
    baseline_eval_decisions: dict[object, pd.DataFrame] = {}
    baseline_eval_metrics: dict[object, dict[str, Any]] = {}
    baseline_selection_decisions = 0
    for fold in folds:
        selection, evaluation = partitions[fold]
        sel_periods, sel_decisions, _ = replay_v7_reliability(
            selection, baseline_config, round_trip_cost_bps=round_trip_cost_bps
        )
        eval_periods, eval_decisions, eval_metrics = replay_v7_reliability(
            evaluation, baseline_config, round_trip_cost_bps=round_trip_cost_bps
        )
        baseline_sel_periods.append(sel_periods)
        baseline_eval_periods.append(eval_periods)
        baseline_eval_decisions[fold] = eval_decisions
        baseline_eval_metrics[fold] = eval_metrics
        baseline_selection_decisions += len(sel_decisions)
    baseline_sel = _summary(baseline_sel_periods)
    baseline_eval = _summary(baseline_eval_periods)
    registry.record(
        "A",
        "exact_v6_control_foldwise",
        "CONTROL_CORRECTED_METHODOLOGY",
        phase="first_line",
        config={"direction": "H12", "execution": "MARKET", "leverage": 1.0, "validation": "70_30_within_outer_fold"},
        metrics={"selection": baseline_sel, "evaluation": baseline_eval},
    )

    baseline_wrong_side = 0
    for fold in folds:
        baseline_wrong_side += _wrong_side_count(
            partitions[fold][1],
            baseline_eval_decisions[fold],
            round_trip_cost_bps=round_trip_cost_bps,
        )

    candidate_defs = [
        ("H1", "H1_qh_conflict_veto", "qh_imbalance_results.json", dict(h1=True)),
        ("H2", "H2_high_dispersion_gate", "dispersion_results.json", dict(h2=True)),
        ("H3", "H3_weak_edge_veto", "weak_edge_results.json", dict(h3=True)),
    ]
    promoted: list[str] = []
    result_rows: dict[str, dict[str, Any]] = {}

    for stage, name, artifact_name, flags in candidate_defs:
        configs = {fold: _variant_config(fitted[fold], **flags) for fold in folds}
        if stage == "H1" and any(config.qh_abs_threshold is None for config in configs.values()):
            coverage = {
                str(fold): float(partitions[fold][0]["qh_order_imbalance"].notna().mean())
                for fold in folds
            }
            metrics = {
                "selection_qh_coverage": float(sum(coverage.values()) / len(coverage)),
                "selection_qh_coverage_by_fold": coverage,
                "failure": "insufficient_qh_selection_coverage",
            }
            registry.record(
                stage,
                name,
                "REJECTED_PRECHECK_DATA_LIMITATION",
                phase="first_line",
                config={"per_fold": {str(fold): configs[fold].__dict__ for fold in folds}},
                metrics=metrics,
            )
            payload = {
                "name": name,
                "status": "REJECTED_PRECHECK_DATA_LIMITATION",
                "config": {"per_fold": {str(fold): configs[fold].__dict__ for fold in folds}},
                **metrics,
                "promotion_failures": ["insufficient_qh_selection_coverage"],
            }
            _write_json(root / artifact_name, payload)
            result_rows[name] = payload
            continue

        sel_period_parts: list[pd.DataFrame] = []
        eval_period_parts: list[pd.DataFrame] = []
        cost20_parts: list[pd.DataFrame] = []
        delay_parts: list[pd.DataFrame] = []
        candidate_wrong_side = 0
        fold_positive_count = 0
        for fold in folds:
            selection, evaluation = partitions[fold]
            config = configs[fold]
            sel_periods, _, _ = replay_v7_reliability(
                selection, config, round_trip_cost_bps=round_trip_cost_bps
            )
            eval_periods, eval_decisions, eval_metrics = replay_v7_reliability(
                evaluation, config, round_trip_cost_bps=round_trip_cost_bps
            )
            cost20_periods, _, _ = replay_v7_reliability(
                evaluation, config, round_trip_cost_bps=20.0
            )
            sel_period_parts.append(sel_periods)
            eval_period_parts.append(eval_periods)
            cost20_parts.append(cost20_periods)
            candidate_wrong_side += _wrong_side_count(
                evaluation, eval_decisions, round_trip_cost_bps=round_trip_cost_bps
            )
            fold_positive_count += int(
                float(eval_metrics["net_return"])
                > float(baseline_eval_metrics[fold]["net_return"])
            )
            if fold in delayed_partitions:
                delay_periods, _, _ = replay_v7_reliability(
                    delayed_partitions[fold], config, round_trip_cost_bps=round_trip_cost_bps
                )
                delay_parts.append(delay_periods)

        sel_metrics = _summary(sel_period_parts)
        eval_metrics = _summary(eval_period_parts)
        cost20_metrics = _summary(cost20_parts)
        delay_metrics = _summary(delay_parts) if len(delay_parts) == len(folds) else None
        delay1h_net = None if delay_metrics is None else float(delay_metrics["net_return"])
        wrong_side_delta = candidate_wrong_side - baseline_wrong_side
        passed, failures = _promotion_gate(
            baseline_eval,
            eval_metrics,
            wrong_side_delta=wrong_side_delta,
            fold_positive_count=fold_positive_count,
            fold_count=len(folds),
            cost20_net=float(cost20_metrics["net_return"]),
            delay1h_net=delay1h_net,
        )
        status = "PROMOTED_INNER" if passed else "REJECTED_INNER"
        config_payload = {"per_fold": {str(fold): configs[fold].__dict__ for fold in folds}}
        registry.record(
            stage,
            name,
            status,
            phase="first_line",
            config=config_payload,
            metrics={
                "selection": sel_metrics,
                "evaluation": eval_metrics,
                "wrong_side_delta": wrong_side_delta,
                "fold_positive_count": fold_positive_count,
                "fold_count": len(folds),
                "cost20_net": float(cost20_metrics["net_return"]),
                "delay1h_net": delay1h_net,
                "failures": failures,
            },
        )
        if passed:
            promoted.append(name)
        payload = {
            "name": name,
            "status": status,
            "config": config_payload,
            "selection": sel_metrics,
            "evaluation": eval_metrics,
            "wrong_side_delta": wrong_side_delta,
            "fold_positive_count": fold_positive_count,
            "fold_count": len(folds),
            "cost20_net": float(cost20_metrics["net_return"]),
            "delay1h_net": delay1h_net,
            "promotion_failures": failures,
        }
        _write_json(root / artifact_name, payload)
        result_rows[name] = payload

    if len(promoted) < 2:
        combination = {"status": "NOT_RUN_FEWER_THAN_TWO_PROMOTED", "promoted": promoted}
    else:
        combo_configs: dict[object, ReliabilityGateConfig] = {}
        for fold in folds:
            combo_configs[fold] = _variant_config(
                fitted[fold],
                h1="H1_qh_conflict_veto" in promoted,
                h2="H2_high_dispersion_gate" in promoted,
                h3="H3_weak_edge_veto" in promoted,
            )
        sel_parts: list[pd.DataFrame] = []
        eval_parts: list[pd.DataFrame] = []
        combo_wrong_side = 0
        for fold in folds:
            selection, evaluation = partitions[fold]
            sel_periods, _, _ = replay_v7_reliability(
                selection, combo_configs[fold], round_trip_cost_bps=round_trip_cost_bps
            )
            eval_periods, eval_decisions, _ = replay_v7_reliability(
                evaluation, combo_configs[fold], round_trip_cost_bps=round_trip_cost_bps
            )
            sel_parts.append(sel_periods)
            eval_parts.append(eval_periods)
            combo_wrong_side += _wrong_side_count(
                evaluation, eval_decisions, round_trip_cost_bps=round_trip_cost_bps
            )
        combo_sel = _summary(sel_parts)
        combo_eval = _summary(eval_parts)
        registry.record(
            "C",
            "H1_H2_H3_promoted_combination",
            "INSPECTED_COMBINATION",
            phase="first_line",
            config={"per_fold": {str(fold): combo_configs[fold].__dict__ for fold in folds}},
            metrics={"selection": combo_sel, "evaluation": combo_eval},
        )
        combination = {
            "status": "INSPECTED_COMBINATION",
            "promoted_inputs": promoted,
            "config": {"per_fold": {str(fold): combo_configs[fold].__dict__ for fold in folds}},
            "selection": combo_sel,
            "evaluation": combo_eval,
            "wrong_side_delta": combo_wrong_side - baseline_wrong_side,
        }
    (root / "combination_results.json").write_text(
        json.dumps(combination, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    registry.to_csv()
    return {
        "fitted_gate_config": {"per_fold": {str(fold): fitted[fold].__dict__ for fold in folds}},
        "baseline": {"selection": baseline_sel, "evaluation": baseline_eval},
        "results": result_rows,
        "promoted": promoted,
        "combination": combination,
        "trial_count_after": registry.total_count,
        "baseline_selection_decision_count": int(baseline_selection_decisions),
        "validation": "70_30_chronological_within_each_outer_fold",
    }
