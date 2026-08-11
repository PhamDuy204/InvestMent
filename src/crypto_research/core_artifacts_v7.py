from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from crypto_research.attribution_v7 import attribute_candidate_errors
from crypto_research.diagnostics_v7 import (
    append_failure_ledger,
    build_failure_record,
    write_do_not_repeat,
)
from crypto_research.reliability_v7 import ReliabilityGateConfig
from crypto_research.run_v7 import (
    _merge_first_line_features,
    replay_v7_reliability,
    run_v7_first_line,
    split_selection_evaluation,
)

_HYPOTHESIS_META: dict[str, dict[str, object]] = {
    "H1_qh_conflict_veto": {
        "target_error": "WRONG_SIDE",
        "expected_mechanism": "quarter-hour order-imbalance conflict reduces H12 reliability",
        "causal_inputs": ["qh_order_imbalance", "effective_score"],
        "action": "veto_increase",
        "next_allowed_question": "does quarter-hour conflict matter only in a distinct admitted state?",
    },
    "H2_high_dispersion_gate": {
        "target_error": "WRONG_SIDE",
        "expected_mechanism": "high cross-sectional dispersion increases H12 allocation uncertainty",
        "causal_inputs": ["dispersion_iqr"],
        "action": "scale_increase",
        "next_allowed_question": "does dispersion add value jointly with an independently admitted factor?",
    },
    "H3_weak_edge_veto": {
        "target_error": "FALSE_ENTER",
        "expected_mechanism": "weak absolute H12 score lacks after-cost reliability",
        "causal_inputs": ["effective_score"],
        "action": "veto_increase",
        "next_allowed_question": "is weak-edge failure conditional on a new causal factor family?",
    },
}


def _json_write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def _baseline_attribution_log(
    evaluation: pd.DataFrame,
    *,
    round_trip_cost_bps: float,
) -> pd.DataFrame:
    _, baseline_decisions, _ = replay_v7_reliability(
        evaluation,
        ReliabilityGateConfig(None, None, None, False),
        round_trip_cost_bps=round_trip_cost_bps,
    )
    labels = evaluation[
        ["decision_timestamp", "symbol", "holding_return_label", "funding_sum_label"]
    ].copy()
    labels["decision_timestamp"] = pd.to_datetime(labels["decision_timestamp"], utc=True)
    baseline = baseline_decisions.rename(
        columns={
            "current_weight": "previous_weight",
            "proposed_target_weight": "target_weight",
        }
    )
    return baseline[
        ["decision_timestamp", "symbol", "previous_weight", "target_weight"]
    ].merge(
        labels,
        on=["decision_timestamp", "symbol"],
        how="left",
        validate="one_to_one",
    )


def run_v7_first_line_with_artifacts(
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
    root = Path(artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    result = run_v7_first_line(
        decision_log,
        qh_features,
        dispersion,
        artifact_root=root,
        prior_trials=prior_trials,
        round_trip_cost_bps=round_trip_cost_bps,
        selection_fraction=selection_fraction,
        delay_decision_log=delay_decision_log,
    )

    work = _merge_first_line_features(decision_log, qh_features, dispersion)
    _, evaluation = split_selection_evaluation(work, selection_fraction=selection_fraction)
    baseline_eval = result["baseline"]["evaluation"]
    baseline_attribution_log = _baseline_attribution_log(
        evaluation,
        round_trip_cost_bps=round_trip_cost_bps,
    )
    registry = pd.read_csv(root / "experiment_registry.csv")

    attribution_rows: dict[str, Any] = {}
    failure_records: list[dict[str, object]] = []
    for name, payload in result["results"].items():
        config = ReliabilityGateConfig(**payload["config"])
        _, candidate_decisions, candidate_metrics = replay_v7_reliability(
            evaluation,
            config,
            round_trip_cost_bps=round_trip_cost_bps,
        )
        attribution = attribute_candidate_errors(
            baseline_attribution_log,
            candidate_decisions,
            round_trip_cost_bps=round_trip_cost_bps,
        )
        attribution_rows[name] = attribution

        if payload["status"] != "REJECTED_INNER":
            continue
        meta = _HYPOTHESIS_META[name]
        matched = registry.loc[registry["hypothesis"] == name, "trial_number"]
        if len(matched) != 1:
            raise RuntimeError(f"expected one registry row for {name}")
        target_error = str(meta["target_error"])
        actual_error_delta = int(
            attribution["by_error"].get(target_error, {}).get("count_delta", 0)
        )
        failures = list(payload.get("promotion_failures", []))
        failure_records.append(
            build_failure_record(
                trial_number=int(matched.iloc[0]),
                hypothesis=name,
                target_error=target_error,
                expected_mechanism=str(meta["expected_mechanism"]),
                causal_inputs=list(meta["causal_inputs"]),
                action=str(meta["action"]),
                actual_error_delta=actual_error_delta,
                net_effect_bps=float(attribution["net_bps_effect"]),
                turnover_effect=float(candidate_metrics.get("turnover", 0.0))
                - float(baseline_eval.get("turnover", 0.0)),
                drawdown_effect=float(candidate_metrics.get("max_drawdown", 0.0))
                - float(baseline_eval.get("max_drawdown", 0.0)),
                damaged_regime="NOT_ATTRIBUTED_FIRST_LINE",
                helped_regime="NOT_ATTRIBUTED_FIRST_LINE",
                assumption_status="not_supported",
                failure_reason=", ".join(failures) if failures else "promotion gate failed",
                next_allowed_question=str(meta["next_allowed_question"]),
                timestamp_utc=pd.Timestamp.now(tz="UTC").isoformat(),
            )
        )

    _json_write(
        root / "error_attribution.json",
        {
            "status": "DISCOVERY_EVALUATION_ONLY_NOT_FORWARD_CONFIRMATION",
            "candidates": attribution_rows,
        },
    )
    ledger_path = root / "failure_ledger.csv.gz"
    ledger_path.unlink(missing_ok=True)
    append_failure_ledger(failure_records, ledger_path)
    write_do_not_repeat(failure_records, root / "do_not_repeat.json")
    result["error_attribution"] = attribution_rows
    result["failure_count"] = len(failure_records)
    return result
