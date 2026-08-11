from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from crypto_research.decision_diagnostics import classify_error
from crypto_research.multi_asset_v3 import drift_futures_weights, rebalance_cost, turnover
from crypto_research.reliability_v7 import (
    ReliabilityGateConfig,
    apply_reliability_gates,
    fit_reliability_gates,
)
from crypto_research.run_v3 import stateful_summary
from crypto_research.trials_v7 import V7TrialRegistry


def _action(previous: float, target: float) -> str:
    eps = 1e-12
    if abs(previous) <= eps and abs(target) <= eps:
        return "NO_TRADE"
    if abs(previous) <= eps:
        return "ENTER_LONG" if target > 0 else "ENTER_SHORT"
    if abs(target) <= eps:
        return "EXIT"
    if previous * target < 0:
        return "FLIP"
    if abs(previous - target) <= eps:
        return "HOLD_LONG" if target > 0 else "HOLD_SHORT"
    if abs(target) < abs(previous):
        return "REDUCE"
    return "HOLD_LONG" if target > 0 else "HOLD_SHORT"


def replay_v7_reliability(
    decision_log: pd.DataFrame,
    config: ReliabilityGateConfig,
    *,
    round_trip_cost_bps: float = 10.0,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    required = {
        "decision_timestamp",
        "symbol",
        "target_weight",
        "holding_return_label",
        "funding_sum_label",
        "effective_score",
    }
    missing = required.difference(decision_log.columns)
    if missing:
        raise ValueError(f"missing V7 replay columns: {sorted(missing)}")
    if round_trip_cost_bps < 0:
        raise ValueError("round_trip_cost_bps must be non-negative")

    if (
        "fold" in decision_log.columns
        and decision_log["fold"].notna().all()
        and decision_log["fold"].nunique() > 1
    ):
        ordered = decision_log.copy()
        ordered["decision_timestamp"] = pd.to_datetime(ordered["decision_timestamp"], utc=True)
        ordered = ordered.sort_values(["decision_timestamp", "symbol"])
        period_parts: list[pd.DataFrame] = []
        decision_parts: list[pd.DataFrame] = []
        for _, part in ordered.groupby("fold", sort=False):
            periods, decisions, _ = replay_v7_reliability(
                part,
                config,
                round_trip_cost_bps=round_trip_cost_bps,
            )
            period_parts.append(periods)
            decision_parts.append(decisions)
        combined_periods = pd.concat(period_parts, ignore_index=True)
        combined_decisions = pd.concat(decision_parts, ignore_index=True)
        return combined_periods, combined_decisions, stateful_summary(combined_periods)

    work = decision_log.copy()
    work["decision_timestamp"] = pd.to_datetime(work["decision_timestamp"], utc=True)
    work = work.sort_values(["decision_timestamp", "symbol"])
    current: dict[str, float] = {}
    period_rows: list[dict[str, Any]] = []
    decision_rows: list[dict[str, Any]] = []

    for timestamp, group in work.groupby("decision_timestamp", sort=True):
        indexed = group.set_index("symbol", drop=False)
        if not indexed.index.is_unique:
            raise ValueError(f"duplicate V7 decision rows at {timestamp}")
        symbols = sorted(set(indexed.index) | set(current))
        previous = np.array([current.get(symbol, 0.0) for symbol in symbols], dtype=float)
        target = np.zeros(len(symbols), dtype=float)
        holding = np.zeros(len(symbols), dtype=float)
        funding = np.zeros(len(symbols), dtype=float)

        for index, symbol in enumerate(symbols):
            if symbol not in indexed.index:
                continue
            row = indexed.loc[symbol]
            base_target = float(row["target_weight"])
            gate = apply_reliability_gates(row, float(previous[index]), base_target, config)
            candidate_target = float(gate["target_weight"])
            if base_target != 0.0 and candidate_target != 0.0:
                if np.sign(candidate_target) != np.sign(base_target):
                    raise RuntimeError("V7 replay changed H12 direction")
            target[index] = candidate_target
            holding[index] = float(row["holding_return_label"])
            funding[index] = float(row["funding_sum_label"])
            decision_rows.append(
                {
                    "decision_timestamp": pd.Timestamp(timestamp),
                    "symbol": str(symbol),
                    "current_weight": float(previous[index]),
                    "base_target_weight": base_target,
                    "proposed_target_weight": candidate_target,
                    "decision": _action(float(previous[index]), candidate_target),
                    "h1_veto": bool(gate["h1_veto"]),
                    "h2_scaled": bool(gate["h2_scaled"]),
                    "h3_veto": bool(gate["h3_veto"]),
                }
            )

        delta = target - previous
        period_turnover = turnover(previous, target)
        transaction_cost = rebalance_cost(
            previous,
            target,
            round_trip_cost_bps=round_trip_cost_bps,
        )
        gross_return = float(np.dot(target, holding))
        funding_return = float(np.dot(-target, funding))
        net_return = gross_return + funding_return - transaction_cost
        period_rows.append(
            {
                "decision_timestamp": pd.Timestamp(timestamp),
                "gross_return": gross_return,
                "funding_return": funding_return,
                "transaction_cost": transaction_cost,
                "net_return": net_return,
                "turnover": period_turnover,
                "final_unwind_turnover": 0.0,
                "gross_exposure": float(np.abs(target).sum()),
                "net_exposure": float(target.sum()),
                "long_count": int((target > 1e-12).sum()),
                "short_count": int((target < -1e-12).sum()),
                "rebalance_trade_count": int((np.abs(delta) > 1e-12).sum()),
                "weights_json": json.dumps(
                    {symbol: float(weight) for symbol, weight in zip(symbols, target, strict=True)}
                ),
            }
        )
        if 1.0 + net_return <= 0:
            current = {
                symbol: float(weight)
                for symbol, weight in zip(symbols, target, strict=True)
                if abs(float(weight)) > 1e-15
            }
        else:
            drifted = drift_futures_weights(target, holding, net_return=net_return)
            current = {
                symbol: float(weight)
                for symbol, weight in zip(symbols, drifted, strict=True)
                if abs(float(weight)) > 1e-15
            }

    periods = pd.DataFrame(period_rows)
    if not periods.empty and current:
        final_weights = np.array(list(current.values()), dtype=float)
        flat = np.zeros_like(final_weights)
        final_turnover = turnover(final_weights, flat)
        final_cost = rebalance_cost(
            final_weights,
            flat,
            round_trip_cost_bps=round_trip_cost_bps,
        )
        periods.loc[periods.index[-1], "final_unwind_turnover"] = final_turnover
        periods.loc[periods.index[-1], "transaction_cost"] += final_cost
        periods.loc[periods.index[-1], "net_return"] -= final_cost
        periods.loc[periods.index[-1], "rebalance_trade_count"] += int(
            (np.abs(final_weights) > 1e-12).sum()
        )

    return periods, pd.DataFrame(decision_rows), stateful_summary(periods)


def split_selection_evaluation(
    decision_log: pd.DataFrame,
    *,
    selection_fraction: float = 0.70,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not 0.0 < selection_fraction < 1.0:
        raise ValueError("selection_fraction must be between zero and one")
    work = decision_log.copy()
    work["decision_timestamp"] = pd.to_datetime(work["decision_timestamp"], utc=True)
    if (
        "fold" in work.columns
        and work["fold"].notna().all()
        and work["fold"].nunique() > 1
    ):
        selection_parts: list[pd.DataFrame] = []
        evaluation_parts: list[pd.DataFrame] = []
        for _, part in work.groupby("fold", sort=False):
            times = pd.Index(sorted(part["decision_timestamp"].dropna().unique()))
            if len(times) < 4:
                raise ValueError("each fold requires at least four decision timestamps")
            split = max(1, min(len(times) - 1, int(len(times) * selection_fraction)))
            cutoff = times[split - 1]
            selection_parts.append(part.loc[part["decision_timestamp"] <= cutoff].copy())
            evaluation_parts.append(part.loc[part["decision_timestamp"] > cutoff].copy())
        return (
            pd.concat(selection_parts).sort_values(["decision_timestamp", "symbol"]),
            pd.concat(evaluation_parts).sort_values(["decision_timestamp", "symbol"]),
        )

    times = pd.Index(sorted(work["decision_timestamp"].dropna().unique()))
    if len(times) < 4:
        raise ValueError("at least four decision timestamps are required")
    split = max(1, min(len(times) - 1, int(len(times) * selection_fraction)))
    cutoff = times[split - 1]
    return (
        work.loc[work["decision_timestamp"] <= cutoff].copy(),
        work.loc[work["decision_timestamp"] > cutoff].copy(),
    )


def _merge_first_line_features(
    decision_log: pd.DataFrame,
    qh_features: pd.DataFrame,
    dispersion: pd.DataFrame,
) -> pd.DataFrame:
    keys = ["decision_timestamp", "symbol"]
    left = decision_log.copy()
    qh = qh_features.copy()
    disp = dispersion.copy()
    for frame, column in ((left, "decision_timestamp"), (qh, "decision_timestamp"), (disp, "decision_timestamp")):
        frame[column] = pd.to_datetime(frame[column], utc=True)
    qh_columns = [
        column
        for column in (
            "decision_timestamp",
            "symbol",
            "qh_order_imbalance",
            "qh_abs_order_imbalance",
            "qh_trade_count",
            "qh_window_start",
            "qh_window_end",
        )
        if column in qh.columns
    ]
    disp_columns = [
        column
        for column in ("decision_timestamp", "dispersion_iqr", "eligible_symbol_count")
        if column in disp.columns
    ]
    merged = left.merge(qh[qh_columns], on=keys, how="left", validate="one_to_one")
    merged = merged.merge(
        disp[disp_columns],
        on="decision_timestamp",
        how="left",
        validate="many_to_one",
    )
    return merged


def _variant_config(
    fitted: ReliabilityGateConfig,
    *,
    h1: bool = False,
    h2: bool = False,
    h3: bool = False,
) -> ReliabilityGateConfig:
    return ReliabilityGateConfig(
        qh_abs_threshold=fitted.qh_abs_threshold if h1 else None,
        dispersion_threshold=fitted.dispersion_threshold if h2 else None,
        weak_score_threshold=fitted.weak_score_threshold if h3 else None,
        weak_score_veto_enabled=fitted.weak_score_veto_enabled if h3 else False,
        high_dispersion_scale=fitted.high_dispersion_scale,
    )


def _wrong_side_count(
    source: pd.DataFrame,
    candidate_decisions: pd.DataFrame,
    *,
    round_trip_cost_bps: float,
) -> int:
    labels = source[
        ["decision_timestamp", "symbol", "holding_return_label", "funding_sum_label"]
    ].copy()
    labels["decision_timestamp"] = pd.to_datetime(labels["decision_timestamp"], utc=True)
    merged = candidate_decisions.merge(
        labels,
        on=["decision_timestamp", "symbol"],
        how="left",
        validate="one_to_one",
    )
    count = 0
    for row in merged.itertuples(index=False):
        error = classify_error(
            float(row.current_weight),
            float(row.proposed_target_weight),
            holding_return=float(row.holding_return_label),
            funding_sum=float(row.funding_sum_label),
            round_trip_cost_bps=round_trip_cost_bps,
        )
        count += int(error == "WRONG_SIDE")
    return count


def _fold_support(
    evaluation: pd.DataFrame,
    config: ReliabilityGateConfig,
    *,
    round_trip_cost_bps: float,
) -> tuple[int, int]:
    if "fold" not in evaluation.columns:
        return 0, 0
    folds = [value for value in evaluation["fold"].dropna().unique()]
    positive = 0
    for fold in folds:
        part = evaluation.loc[evaluation["fold"] == fold].copy()
        if part["decision_timestamp"].nunique() < 2:
            continue
        _, _, baseline = replay_v7_reliability(
            part,
            ReliabilityGateConfig(None, None, None, False),
            round_trip_cost_bps=round_trip_cost_bps,
        )
        _, _, candidate = replay_v7_reliability(
            part,
            config,
            round_trip_cost_bps=round_trip_cost_bps,
        )
        positive += int(float(candidate["net_return"]) > float(baseline["net_return"]))
    return positive, len(folds)


def _promotion_gate(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    wrong_side_delta: int,
    fold_positive_count: int,
    fold_count: int,
    cost20_net: float,
    delay1h_net: float | None,
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if float(candidate["net_return"]) <= float(baseline["net_return"]):
        failures.append("evaluation_net_not_improved")
    if float(candidate["sharpe"]) < float(baseline["sharpe"]) - 0.05:
        failures.append("material_sharpe_damage")
    if float(candidate["max_drawdown"]) > float(baseline["max_drawdown"]) + 0.01:
        failures.append("material_drawdown_damage")
    if wrong_side_delta >= 0:
        failures.append("wrong_side_not_reduced")
    if fold_count < 2 or fold_positive_count < 2:
        failures.append("insufficient_multi_fold_support")
    if cost20_net < 0.0:
        failures.append("negative_at_20bps")
    if delay1h_net is None:
        failures.append("delay_1h_not_evaluated")
    elif delay1h_net < 0.0:
        failures.append("negative_with_1h_delay")
    return not failures, failures


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def run_v7_first_line(
    decision_log: pd.DataFrame,
    qh_features: pd.DataFrame,
    dispersion: pd.DataFrame,
    *,
    artifact_root: str | Path,
    prior_trials: int = 857,
    round_trip_cost_bps: float = 10.0,
    selection_fraction: float = 0.70,
    delay_decision_log: pd.DataFrame | None = None,
) -> dict[str, Any]:
    if (
        "fold" in decision_log.columns
        and decision_log["fold"].notna().all()
        and decision_log["fold"].nunique() > 1
    ):
        from crypto_research.run_v7_foldwise import run_v7_first_line_foldwise

        return run_v7_first_line_foldwise(
            decision_log,
            qh_features,
            dispersion,
            artifact_root=artifact_root,
            prior_trials=prior_trials,
            round_trip_cost_bps=round_trip_cost_bps,
            selection_fraction=selection_fraction,
            delay_decision_log=delay_decision_log,
        )

    root = Path(artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    work = _merge_first_line_features(decision_log, qh_features, dispersion)
    selection, evaluation = split_selection_evaluation(work, selection_fraction=selection_fraction)
    fitted = fit_reliability_gates(selection)
    registry = V7TrialRegistry(root / "experiment_registry.csv", prior_count=prior_trials)

    baseline_config = ReliabilityGateConfig(None, None, None, False)
    _, baseline_sel_decisions, baseline_sel = replay_v7_reliability(
        selection,
        baseline_config,
        round_trip_cost_bps=round_trip_cost_bps,
    )
    _, baseline_eval_decisions, baseline_eval = replay_v7_reliability(
        evaluation,
        baseline_config,
        round_trip_cost_bps=round_trip_cost_bps,
    )
    registry.record(
        "A",
        "exact_v6_control",
        "CONTROL",
        phase="first_line",
        config={"direction": "H12", "execution": "MARKET", "leverage": 1.0},
        metrics={"selection": baseline_sel, "evaluation": baseline_eval},
    )

    candidates = [
        ("H1", "H1_qh_conflict_veto", "qh_imbalance_results.json", _variant_config(fitted, h1=True)),
        ("H2", "H2_high_dispersion_gate", "dispersion_results.json", _variant_config(fitted, h2=True)),
        ("H3", "H3_weak_edge_veto", "weak_edge_results.json", _variant_config(fitted, h3=True)),
    ]
    promoted: list[str] = []
    result_rows: dict[str, dict[str, Any]] = {}
    baseline_wrong_side = _wrong_side_count(
        evaluation,
        baseline_eval_decisions,
        round_trip_cost_bps=round_trip_cost_bps,
    )

    delayed_eval: pd.DataFrame | None = None
    if delay_decision_log is not None:
        delayed = _merge_first_line_features(delay_decision_log, qh_features, dispersion)
        _, delayed_eval = split_selection_evaluation(delayed, selection_fraction=selection_fraction)

    for stage, name, artifact_name, config in candidates:
        _, sel_decisions, sel_metrics = replay_v7_reliability(
            selection,
            config,
            round_trip_cost_bps=round_trip_cost_bps,
        )
        _, eval_decisions, eval_metrics = replay_v7_reliability(
            evaluation,
            config,
            round_trip_cost_bps=round_trip_cost_bps,
        )
        _, _, cost20_metrics = replay_v7_reliability(
            evaluation,
            config,
            round_trip_cost_bps=20.0,
        )
        candidate_wrong_side = _wrong_side_count(
            evaluation,
            eval_decisions,
            round_trip_cost_bps=round_trip_cost_bps,
        )
        fold_positive_count, fold_count = _fold_support(
            evaluation,
            config,
            round_trip_cost_bps=round_trip_cost_bps,
        )
        delay1h_net: float | None = None
        if delayed_eval is not None:
            _, _, delay_metrics = replay_v7_reliability(
                delayed_eval,
                config,
                round_trip_cost_bps=round_trip_cost_bps,
            )
            delay1h_net = float(delay_metrics["net_return"])
        passed, failures = _promotion_gate(
            baseline_eval,
            eval_metrics,
            wrong_side_delta=candidate_wrong_side - baseline_wrong_side,
            fold_positive_count=fold_positive_count,
            fold_count=fold_count,
            cost20_net=float(cost20_metrics["net_return"]),
            delay1h_net=delay1h_net,
        )
        status = "PROMOTED_INNER" if passed else "REJECTED_INNER"
        registry.record(
            stage,
            name,
            status,
            phase="first_line",
            config=config.__dict__,
            metrics={
                "selection": sel_metrics,
                "evaluation": eval_metrics,
                "wrong_side_delta": candidate_wrong_side - baseline_wrong_side,
                "fold_positive_count": fold_positive_count,
                "fold_count": fold_count,
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
            "config": config.__dict__,
            "selection": sel_metrics,
            "evaluation": eval_metrics,
            "wrong_side_delta": candidate_wrong_side - baseline_wrong_side,
            "fold_positive_count": fold_positive_count,
            "fold_count": fold_count,
            "cost20_net": float(cost20_metrics["net_return"]),
            "delay1h_net": delay1h_net,
            "promotion_failures": failures,
            "selection_decision_count": int(len(sel_decisions)),
        }
        _write_json(root / artifact_name, payload)
        result_rows[name] = payload

    if len(promoted) < 2:
        combination = {
            "status": "NOT_RUN_FEWER_THAN_TWO_PROMOTED",
            "promoted": promoted,
        }
    else:
        enable_h1 = "H1_qh_conflict_veto" in promoted
        enable_h2 = "H2_high_dispersion_gate" in promoted
        enable_h3 = "H3_weak_edge_veto" in promoted
        combo_config = _variant_config(fitted, h1=enable_h1, h2=enable_h2, h3=enable_h3)
        _, _, combo_sel = replay_v7_reliability(
            selection,
            combo_config,
            round_trip_cost_bps=round_trip_cost_bps,
        )
        _, combo_eval_decisions, combo_eval = replay_v7_reliability(
            evaluation,
            combo_config,
            round_trip_cost_bps=round_trip_cost_bps,
        )
        combo_wrong_side = _wrong_side_count(
            evaluation,
            combo_eval_decisions,
            round_trip_cost_bps=round_trip_cost_bps,
        )
        registry.record(
            "C",
            "H1_H2_H3_promoted_combination",
            "INSPECTED_COMBINATION",
            phase="first_line",
            config=combo_config.__dict__,
            metrics={"selection": combo_sel, "evaluation": combo_eval},
        )
        combination = {
            "status": "INSPECTED_COMBINATION",
            "promoted_inputs": promoted,
            "config": combo_config.__dict__,
            "selection": combo_sel,
            "evaluation": combo_eval,
            "wrong_side_delta": combo_wrong_side - baseline_wrong_side,
        }
    _write_json(root / "combination_results.json", combination)
    registry.to_csv()
    return {
        "fitted_gate_config": fitted.__dict__,
        "baseline": {"selection": baseline_sel, "evaluation": baseline_eval},
        "results": result_rows,
        "promoted": promoted,
        "combination": combination,
        "trial_count_after": registry.total_count,
        "baseline_selection_decision_count": int(len(baseline_sel_decisions)),
    }


def write_not_run_research_placeholders(artifact_root: str | Path) -> None:
    root = Path(artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "literature_registry.json").write_text(
        json.dumps({"status": "NOT_RUN_CORE_ONLY", "sources": []}, indent=2),
        encoding="utf-8",
    )
    (root / "factor_observatory.json").write_text(
        json.dumps({"status": "NOT_RUN_CORE_ONLY", "factors": []}, indent=2),
        encoding="utf-8",
    )
    for name in ("hypothesis_registry.jsonl", "agent_research_log.jsonl", "research_blackboard.jsonl"):
        (root / name).write_text(
            json.dumps({"status": "NOT_RUN_CORE_ONLY"}) + "\n",
            encoding="utf-8",
        )
