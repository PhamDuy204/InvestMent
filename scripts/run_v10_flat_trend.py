from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from crypto_research.basis_v7 import wrong_side_damage
from crypto_research.diagnostics_v7 import (
    append_failure_ledger,
    build_failure_record,
    write_do_not_repeat,
)
from crypto_research.factor_observatory_v7 import (
    FactorEvidence,
    admit_factor,
    write_factor_observatory,
)
from crypto_research.governance_v9 import validate_trial_continuity
from crypto_research.reliability_v7 import ReliabilityGateConfig
from crypto_research.run_v3 import stateful_summary
from crypto_research.run_v7 import (
    _wrong_side_count,
    replay_v7_reliability,
    split_selection_evaluation,
)
from crypto_research.trials_v7 import V7TrialRegistry

ART = Path("artifacts/multi_asset_v10")
HYPOTHESIS = "V10_H1_flat_trend_incremental_reliability"
TRIAL = 870
CONFIG = {
    "direction": "H12 unchanged",
    "trigger": "trend_state == flat",
    "mapping": "scale only new/increased H12 exposure",
    "flat_trend_scale": 0.5,
    "selection_fraction": 0.70,
    "round_trip_cost_bps": 10.0,
    "cost_stress_bps": 20.0,
    "delay_stress": "+1h inherited replay",
}


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_config_hash() -> str:
    payload = {
        "config": CONFIG,
        "reliability_v7_sha256": _sha256("src/crypto_research/reliability_v7.py"),
        "runner_sha256": _sha256(__file__),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _load(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["decision_timestamp"] = pd.to_datetime(frame["decision_timestamp"], utc=True)
    required = {
        "decision_timestamp",
        "fold",
        "symbol",
        "target_weight",
        "effective_score",
        "trend_state",
        "holding_return_label",
        "funding_sum_label",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"input missing columns: {sorted(missing)}")
    return frame


def _summary(parts: list[pd.DataFrame]) -> dict[str, Any]:
    return stateful_summary(pd.concat(parts, ignore_index=True))


def _evaluate_partitions(
    frame: pd.DataFrame,
    delayed: pd.DataFrame,
    *,
    held_out: bool,
) -> dict[str, Any]:
    baseline_config = ReliabilityGateConfig(None, None, None, False)
    candidate_config = ReliabilityGateConfig(None, None, None, False, flat_trend_scale=0.5)
    baseline_parts: list[pd.DataFrame] = []
    candidate_parts: list[pd.DataFrame] = []
    cost20_parts: list[pd.DataFrame] = []
    delay_parts: list[pd.DataFrame] = []
    fold_rows: list[dict[str, Any]] = []
    baseline_damage = 0.0
    candidate_damage = 0.0
    baseline_wrong = 0
    candidate_wrong = 0
    fold_positive = 0

    for fold in sorted(frame["fold"].dropna().unique()):
        fold_frame = frame.loc[frame["fold"] == fold].copy()
        selection, evaluation = split_selection_evaluation(fold_frame, selection_fraction=0.70)
        part = evaluation if held_out else selection
        delay_fold = delayed.loc[delayed["fold"] == fold].copy()
        delay_selection, delay_evaluation = split_selection_evaluation(delay_fold, selection_fraction=0.70)
        delay_part = delay_evaluation if held_out else delay_selection

        base_periods, base_decisions, base_metrics = replay_v7_reliability(
            part, baseline_config, round_trip_cost_bps=10.0
        )
        cand_periods, cand_decisions, cand_metrics = replay_v7_reliability(
            part, candidate_config, round_trip_cost_bps=10.0
        )
        cost20_periods, _, cost20_metrics = replay_v7_reliability(
            part, candidate_config, round_trip_cost_bps=20.0
        )
        delay_periods, _, delay_metrics = replay_v7_reliability(
            delay_part, candidate_config, round_trip_cost_bps=10.0
        )
        labels = part[
            ["decision_timestamp", "symbol", "holding_return_label", "funding_sum_label"]
        ]
        baseline_damage += wrong_side_damage(base_decisions, labels, round_trip_cost_bps=10.0)
        candidate_damage += wrong_side_damage(cand_decisions, labels, round_trip_cost_bps=10.0)
        baseline_wrong += _wrong_side_count(part, base_decisions, round_trip_cost_bps=10.0)
        candidate_wrong += _wrong_side_count(part, cand_decisions, round_trip_cost_bps=10.0)
        fold_positive += int(float(cand_metrics["net_return"]) > float(base_metrics["net_return"]))
        baseline_parts.append(base_periods)
        candidate_parts.append(cand_periods)
        cost20_parts.append(cost20_periods)
        delay_parts.append(delay_periods)
        fold_rows.append(
            {
                "fold": int(fold),
                "rows": int(len(part)),
                "baseline": base_metrics,
                "candidate": cand_metrics,
                "cost20": cost20_metrics,
                "delay1h": delay_metrics,
            }
        )

    baseline = _summary(baseline_parts)
    candidate = _summary(candidate_parts)
    cost20 = _summary(cost20_parts)
    delay1h = _summary(delay_parts)
    return {
        "folds": fold_rows,
        "baseline": baseline,
        "candidate": candidate,
        "cost20": cost20,
        "delay1h": delay1h,
        "baseline_wrong": baseline_wrong,
        "candidate_wrong": candidate_wrong,
        "wrong_count_delta": candidate_wrong - baseline_wrong,
        "baseline_damage": baseline_damage,
        "candidate_damage": candidate_damage,
        "damage_delta_bps": (candidate_damage - baseline_damage) * 10_000.0,
        "fold_positive_count": fold_positive,
    }


def _promotion_failures(result: dict[str, Any]) -> list[str]:
    baseline = result["baseline"]
    candidate = result["candidate"]
    failures: list[str] = []
    if float(candidate["net_return"]) <= float(baseline["net_return"]):
        failures.append("evaluation_net_not_improved")
    if float(candidate["net_return"]) <= 0.0:
        failures.append("evaluation_net_not_positive")
    if float(candidate["sharpe"]) <= float(baseline["sharpe"]):
        failures.append("evaluation_sharpe_not_improved")
    if float(candidate["max_drawdown"]) > float(baseline["max_drawdown"]) + 0.01:
        failures.append("material_drawdown_damage")
    if float(result["candidate_damage"]) >= float(result["baseline_damage"]):
        failures.append("wrong_side_economic_damage_not_reduced")
    if int(result["fold_positive_count"]) < 2:
        failures.append("insufficient_multi_fold_economic_support")
    if float(result["cost20"]["net_return"]) < 0.0:
        failures.append("negative_at_20bps")
    if float(result["delay1h"]["net_return"]) < 0.0:
        failures.append("negative_with_1h_delay")
    return failures


def _verify_predeclaration(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if int(payload.get("trial_number", -1)) != TRIAL:
        raise ValueError("predeclaration does not lock trial 870")
    if payload.get("hypothesis_id") != HYPOTHESIS:
        raise ValueError("predeclaration hypothesis mismatch")
    if payload.get("code_config_hash") != code_config_hash():
        raise ValueError("predeclaration code/config hash mismatch")
    return payload


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _consume_and_evaluate(frame: pd.DataFrame, delayed: pd.DataFrame, predecl: Path) -> dict[str, Any]:
    ART.mkdir(parents=True, exist_ok=True)
    result_path = ART / "h1_flat_trend_results.json"
    marker = ART / "trial_870_access_started.json"
    registry_path = ART / "experiment_registry.csv"
    if result_path.exists() or marker.exists() or registry_path.exists():
        raise RuntimeError("trial 870 state already exists; refusing rerun")

    inherited_registry = Path("artifacts/multi_asset_v8/experiment_registry.csv")
    validate_trial_continuity(inherited_registry, expected_max=869, next_trial=870)
    declaration = _verify_predeclaration(predecl)
    marker_payload = {
        "trial_number": TRIAL,
        "hypothesis_id": HYPOTHESIS,
        "held_out_access_started_utc": datetime.now(timezone.utc).isoformat(),
        "code_config_hash": code_config_hash(),
        "predeclaration_sha256": _sha256(predecl),
        "live_authorization": "LIVE_NOT_AUTHORIZED",
    }
    with marker.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(marker_payload, indent=2, sort_keys=True) + "\n")

    result = _evaluate_partitions(frame, delayed, held_out=True)
    failures = _promotion_failures(result)
    status = "PROMOTED_INNER" if not failures else "REJECTED_INNER"
    baseline = result["baseline"]
    candidate = result["candidate"]

    shutil.copyfile(inherited_registry, registry_path)
    registry = V7TrialRegistry(registry_path, prior_count=857)
    if registry.total_count != 869:
        raise RuntimeError(f"expected inherited max 869, found {registry.total_count}")
    trial_row = registry.record(
        "V10_H1",
        HYPOTHESIS,
        status,
        phase="v10_scientific_candidate",
        config=CONFIG,
        metrics={
            "baseline_evaluation": baseline,
            "candidate_evaluation": candidate,
            "cost20": result["cost20"],
            "delay1h": result["delay1h"],
            "wrong_side_damage_delta_bps": result["damage_delta_bps"],
            "wrong_side_count_delta": result["wrong_count_delta"],
            "fold_positive_count": result["fold_positive_count"],
            "promotion_failures": failures,
        },
    )
    registry.to_csv()

    evidence = FactorEvidence(
        factor_family="cross_sectional",
        feature_name="flat_trend_incremental_reliability",
        source_ids=("doi:10.1016/j.najef.2022.101733", "doi:10.1016/j.frl.2025.108356"),
        coverage_fraction=float(frame["trend_state"].notna().mean()),
        causal_available=True,
        source_quality="peer_reviewed",
        stability_score=float(result["fold_positive_count"]) / 3.0,
        target_error="WRONG_SIDE_ECONOMIC_DAMAGE",
        association_value=-1.5164,
        incremental_net_bps=(float(candidate["net_return"]) - float(baseline["net_return"])) * 10_000.0,
        incremental_sharpe_delta=float(candidate["sharpe"]) - float(baseline["sharpe"]),
        turnover_delta=float(candidate["turnover"]) - float(baseline["turnover"]),
        evaluation_fold_count=3,
        reverse_causality_checked=True,
        status=status,
    )
    factor_admitted = bool(not failures and admit_factor(evidence))
    write_factor_observatory([evidence], ART / "factor_observatory.json")

    payload = {
        "schema_version": "v10-trial-result-1",
        "trial_number": TRIAL,
        "hypothesis_id": HYPOTHESIS,
        "status": status,
        "factor_admitted": factor_admitted,
        "config": CONFIG,
        "code_config_hash": code_config_hash(),
        "predeclaration": declaration,
        **result,
        "promotion_failures": failures,
        "live_authorization": "LIVE_NOT_AUTHORIZED",
    }
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    _append_jsonl(
        ART / "hypothesis_registry.jsonl",
        {
            "hypothesis_id": HYPOTHESIS,
            "trial_number": TRIAL,
            "status": status,
            "factor_admitted": factor_admitted,
            "causal_inputs": ["trend_state", "H12 target_weight"],
            "single_change": CONFIG["mapping"],
            "timestamp_utc": trial_row["timestamp_utc"],
        },
    )
    (ART / "multiple_testing.json").write_text(
        json.dumps(
            {
                "schema_version": "v10-multiple-testing-1",
                "performance_trial_count": 870,
                "v10_performance_trials_consumed": 1,
                "trial_870_present": True,
                "next_performance_trial": 871,
                "cpcv": "NOT_COMPUTABLE_WITH_CURRENT_PROVENANCE",
                "cscv": "NOT_COMPUTABLE_WITH_CURRENT_PROVENANCE",
                "pbo": "NOT_COMPUTABLE_WITH_CURRENT_PROVENANCE",
                "dsr": "NOT_COMPUTABLE_WITH_CURRENT_PROVENANCE",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    if not factor_admitted:
        ledger_path = ART / "failure_ledger.csv.gz"
        shutil.copyfile("artifacts/multi_asset_v8/failure_ledger.csv.gz", ledger_path)
        failure = build_failure_record(
            trial_number=TRIAL,
            hypothesis=HYPOTHESIS,
            target_error="WRONG_SIDE_ECONOMIC_DAMAGE",
            expected_mechanism="H12 continuation reliability is weaker when the causal trend state is flat",
            causal_inputs=["trend_state", "H12 target_weight"],
            action="scale only H12 exposure increases by 0.5 when trend_state is flat",
            actual_error_delta=int(result["wrong_count_delta"]),
            net_effect_bps=(float(candidate["net_return"]) - float(baseline["net_return"])) * 10_000.0,
            turnover_effect=float(candidate["turnover"]) - float(baseline["turnover"]),
            drawdown_effect=float(candidate["max_drawdown"]) - float(baseline["max_drawdown"]),
            damaged_regime="held-out folds or mandatory cost/delay gates that fail promotion",
            helped_regime="flat-trend exposure increases where economic wrong-side damage is reduced",
            assumption_status="FLAT_TREND_RELIABILITY_NOT_ADMITTED",
            failure_reason=";".join(failures) if failures else "factor_admission_failed",
            next_allowed_question="Require a materially distinct causal mechanism; do not grid flat-state scales around trial 870.",
            timestamp_utc=str(trial_row["timestamp_utc"]),
        )
        append_failure_ledger([failure], ledger_path)
        write_do_not_repeat(pd.read_csv(ledger_path).to_dict("records"), ART / "do_not_repeat.json")

    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--panel",
        default="/home/duypham/workspace/InvestMent-v8-local-data/multi_asset_v8/execution_factor_panel.csv.gz",
    )
    parser.add_argument(
        "--delay",
        default="/home/duypham/workspace/InvestMent-v6-local/.worktrees/v8-execution-liquidity-shadow/artifacts/multi_asset_v7/delay_1h_decision_log.csv.gz",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--selection-only", action="store_true")
    mode.add_argument("--evaluate", action="store_true")
    mode.add_argument("--print-lock-hash", action="store_true")
    parser.add_argument(
        "--predeclaration",
        default="artifacts/multi_asset_v10/hypothesis_predeclaration_870.json",
    )
    args = parser.parse_args()

    if args.print_lock_hash:
        print(code_config_hash())
        return
    frame = _load(args.panel)
    delayed = _load(args.delay)
    if args.selection_only:
        result = _evaluate_partitions(frame, delayed, held_out=False)
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return
    result = _consume_and_evaluate(frame, delayed, Path(args.predeclaration))
    print(
        json.dumps(
            {
                "trial": result["trial_number"],
                "status": result["status"],
                "factor_admitted": result["factor_admitted"],
                "candidate_net": result["candidate"]["net_return"],
                "candidate_sharpe": result["candidate"]["sharpe"],
                "promotion_failures": result["promotion_failures"],
                "live_authorization": result["live_authorization"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
