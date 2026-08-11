from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from crypto_research.core_artifacts_v7 import run_v7_first_line_with_artifacts
from crypto_research.forward_v7 import freeze_v7_candidate
from crypto_research.run_v7 import write_not_run_research_placeholders
from crypto_research.statistics_v7 import approximate_dsr, cscv_pbo
from crypto_research.stress_v7 import run_v7_stress_suite


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def _protocol_payload() -> dict[str, Any]:
    return {
        "research_version": "V7",
        "research_scope": "RESEARCH_BACKTEST_SIMULATION_ONLY",
        "starting_trial_count": 857,
        "first_line_trial_cap": 24,
        "total_v7_trial_cap": 60,
        "selection_fraction": 0.70,
        "execution_mode": "MARKET",
        "recommended_effective_leverage": 1.0,
        "direction_source": "retained_H12_Ridge_relative_return",
        "h1": {
            "name": "quarter_hour_conflict_veto",
            "threshold_fit": "training_fold_median_abs_qh_imbalance",
            "action": "veto_new_or_increased_exposure_only",
            "direction_flip_allowed": False,
        },
        "h2": {
            "name": "high_dispersion_gate",
            "threshold_fit": "training_fold_q80_cross_sectional_IQR",
            "high_dispersion_increment_scale": 0.5,
            "action": "scale_incremental_exposure_increase_only",
        },
        "h3": {
            "name": "weak_edge_veto",
            "threshold_fit": "training_fold_q20_abs_H12_score",
            "enable_condition": "training_weak_bucket_mean_net_contribution_le_0",
            "action": "veto_new_or_increased_exposure_only",
        },
        "locked_evidence": {
            "2021_2023": "OBSERVED_LOCKED_NOT_FOR_V7_SELECTION",
            "2026_08_01_to_10": "OBSERVED_LOCKED_NOT_FOR_V7_SELECTION",
        },
        "a1_readiness": {
            "minimum_untouched_calendar_days": 30,
            "minimum_eligible_h12_observations": 40,
            "ret_10bps": ">0",
            "profit_factor": ">1.10",
            "sharpe": ">0.50",
            "ret_20bps": ">=0",
            "delay_1h_return": ">=0",
            "liquidation_count": 0,
            "exposure_violation_count": 0,
            "margin_violation_count": 0,
            "candidate_hash_unchanged": True,
            "forward_driven_retuning": False,
        },
        "prohibited_capabilities": [
            "live_order_placement",
            "order_cancellation",
            "withdrawal",
            "transfer",
            "otp_flow",
            "exchange_side_leverage_mutation",
        ],
    }


def _write_empty_forward_observations(path: Path) -> None:
    pd.DataFrame(
        columns=[
            "decision_timestamp",
            "eligible_h12",
            "candidate_hash_sha256",
            "net_return",
        ]
    ).to_csv(path, index=False, compression="gzip")


def _candidate_sharpes(frame: pd.DataFrame) -> list[float]:
    sharpes: list[float] = []
    for column in frame.columns:
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        if len(values) <= 1:
            sharpes.append(0.0)
            continue
        std = float(values.std(ddof=1))
        sharpe = float(values.mean() / std * math.sqrt(730.0)) if std > 0 else 0.0
        sharpes.append(sharpe)
    return sharpes


def _write_multiple_testing(
    root: Path,
    aligned_candidate_returns: pd.DataFrame | None,
    *,
    total_trial_count: int,
    observed_sharpe: float,
) -> None:
    if aligned_candidate_returns is None:
        status = "NOT_EVALUATED_ALIGNED_CANDIDATE_RETURNS_NOT_SUPPLIED"
        _write_json(root / "dsr_results.json", {"status": status})
        _write_json(root / "pbo_results.json", {"status": status})
        return

    clean = aligned_candidate_returns.apply(pd.to_numeric, errors="coerce").dropna()
    if clean.empty or clean.shape[1] < 2:
        status = "NOT_EVALUATED_INSUFFICIENT_ALIGNED_CANDIDATE_RETURNS"
        _write_json(root / "dsr_results.json", {"status": status})
        _write_json(root / "pbo_results.json", {"status": status})
        return
    trial_sharpes = _candidate_sharpes(clean)
    dsr = approximate_dsr(
        observed_sharpe=observed_sharpe,
        trial_sharpes=trial_sharpes,
        observations=len(clean),
        total_trial_count=total_trial_count,
    )
    _write_json(root / "dsr_results.json", dsr)
    try:
        pbo = cscv_pbo(clean, segments=8)
    except ValueError as exc:
        pbo = {
            "status": "NOT_EVALUATED_INSUFFICIENT_CSCV_MATRIX",
            "reason": str(exc),
        }
    _write_json(root / "pbo_results.json", pbo)


def _select_simple_candidate(first_line: dict[str, Any]) -> dict[str, Any] | None:
    promoted = list(first_line.get("promoted", []))
    if not promoted:
        return None
    combination = first_line.get("combination", {})
    if combination.get("status") == "INSPECTED_COMBINATION":
        return {
            "name": "H1_H2_H3_promoted_combination",
            "config": combination["config"],
            "discovery_metrics": combination.get("evaluation", {}),
        }
    ranked = sorted(
        promoted,
        key=lambda name: float(
            first_line["results"][name]["evaluation"].get("net_return", float("-inf"))
        ),
        reverse=True,
    )
    name = ranked[0]
    return {
        "name": name,
        "config": first_line["results"][name]["config"],
        "discovery_metrics": first_line["results"][name]["evaluation"],
    }


def _final_report(
    *,
    escalation_required: bool,
    first_line: dict[str, Any],
    stress_status: str,
    freeze_status: str,
) -> str:
    promoted = list(first_line.get("promoted", []))
    return "\n".join(
        [
            "# V7 Factor Observatory — Core Research Report",
            "",
            "## Scope",
            "V7 is research/backtest/simulation only. No live trading or exchange credential path is introduced.",
            "",
            "## First-line reliability hypotheses",
            f"Inspected promoted modules: {promoted if promoted else 'none'}.",
            "H1/H2/H3 thresholds are fit on selection data only and cannot create opposite H12 direction.",
            "",
            "## Failure memory",
            f"Rejected first-line failure records: {int(first_line.get('failure_count', 0))}.",
            "Rejected mechanisms are persisted in the do-not-repeat registry.",
            "",
            "## Account stress",
            f"Stress status: {stress_status}.",
            "Missing account-path inputs are reported as not evaluated and are never synthesized from decision summaries.",
            "",
            "## Freeze and untouched forward evidence",
            f"Freeze status: {freeze_status}.",
            "Untouched forward evidence is separate from discovery/evaluation evidence. No synthetic forward observations are created.",
            "",
            "## Escalation",
            f"Research-council escalation required: {str(escalation_required).lower()}.",
            "Escalation, if required, must occur before a valid V7 freeze and remains subject to the shared 60-trial cap.",
            "",
            "## Readiness",
            "The core cycle cannot declare readiness without a valid frozen candidate and the full A1 untouched-forward gate.",
            "",
            "NEEDS_MORE_RESEARCH",
        ]
    )


def run_v7_core_cycle(
    decision_log: pd.DataFrame,
    qh_features: pd.DataFrame,
    dispersion: pd.DataFrame,
    *,
    artifact_root: str | Path,
    source_sha: str,
    freeze_timestamp: str,
    delay_decision_log: pd.DataFrame | None = None,
    account_periods: pd.DataFrame | None = None,
    market: pd.DataFrame | None = None,
    delay_account_periods: pd.DataFrame | None = None,
    aligned_candidate_returns: pd.DataFrame | None = None,
) -> dict[str, Any]:
    root = Path(artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    _write_json(root / "v7_protocol.json", _protocol_payload())
    write_not_run_research_placeholders(root)

    first_line = run_v7_first_line_with_artifacts(
        decision_log,
        qh_features,
        dispersion,
        artifact_root=root,
        delay_decision_log=delay_decision_log,
    )
    simple_candidate = _select_simple_candidate(first_line)
    escalation_required = simple_candidate is None

    if account_periods is not None and market is not None:
        stress = run_v7_stress_suite(
            account_periods,
            market,
            delay_periods=delay_account_periods,
        )
        stress_status = "EVALUATED"
        _write_json(root / "stress_results.json", {"status": stress_status, "scenarios": stress})
    else:
        stress_status = "NOT_EVALUATED_ACCOUNT_PATH_NOT_SUPPLIED"
        _write_json(root / "stress_results.json", {"status": stress_status})

    observed_sharpe = float(first_line["baseline"]["evaluation"].get("sharpe", 0.0))
    _write_multiple_testing(
        root,
        aligned_candidate_returns,
        total_trial_count=int(first_line["trial_count_after"]),
        observed_sharpe=observed_sharpe,
    )

    if escalation_required:
        final_candidate = {
            "status": "PRE_FREEZE_ESCALATION_REQUIRED",
            "direction_source": "retained_H12_Ridge_relative_return",
            "execution_mode": "MARKET",
            "recommended_effective_leverage": 1.0,
            "first_line_promoted": list(first_line.get("promoted", [])),
            "trial_count_after_first_line": int(first_line["trial_count_after"]),
        }
        freeze_payload: dict[str, Any] = {
            "status": "NOT_FROZEN_ESCALATION_PENDING",
            "source_sha": str(source_sha),
            "trial_count_after_first_line": int(first_line["trial_count_after"]),
        }
        freeze_status = str(freeze_payload["status"])
    else:
        assert simple_candidate is not None
        final_candidate = {
            "status": "SIMPLE_DISCOVERY_CANDIDATE_SELECTED_NOT_FORWARD_CONFIRMED",
            "name": simple_candidate["name"],
            "direction_source": "retained_H12_Ridge_relative_return",
            "execution_mode": "MARKET",
            "recommended_effective_leverage": 1.0,
            "reliability_config": simple_candidate["config"],
            "discovery_metrics": simple_candidate["discovery_metrics"],
            "trial_count_at_selection": int(first_line["trial_count_after"]),
        }
        freeze_payload = freeze_v7_candidate(
            final_candidate,
            artifact_root=root,
            timestamp=freeze_timestamp,
            total_trial_count=int(first_line["trial_count_after"]),
            source_sha=source_sha,
            causal_schema_version="v7-causal-1",
        )
        freeze_status = "FROZEN_AWAITING_UNTOUCHED_FORWARD"

    _write_json(root / "final_candidate.json", final_candidate)
    if escalation_required:
        _write_json(root / "forward_freeze.json", freeze_payload)
    _write_empty_forward_observations(root / "forward_observations.csv.gz")
    readiness = {
        "verdict": "NEEDS_MORE_RESEARCH",
        "failed_gates": (
            ["candidate_not_frozen", "minimum_calendar_days", "minimum_h12_observations"]
            if escalation_required
            else ["minimum_calendar_days", "minimum_h12_observations", "forward_metrics_not_available"]
        ),
        "eligible_h12_observations": 0,
        "calendar_days": 0,
        "forward_driven_retuning": False,
    }
    _write_json(root / "readiness_gate.json", readiness)
    (root / "final_report.md").write_text(
        _final_report(
            escalation_required=escalation_required,
            first_line=first_line,
            stress_status=stress_status,
            freeze_status=freeze_status,
        ),
        encoding="utf-8",
    )
    return {
        "status": "CORE_COMPLETE",
        "escalation_required": escalation_required,
        "first_line": first_line,
        "final_candidate": final_candidate,
        "freeze": freeze_payload,
        "readiness": readiness,
    }
