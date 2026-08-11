from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd

REQUIRED_V6_ARTIFACTS = {
    "experiment_registry.csv",
    "integrated_controller_config.json",
    "session_state_analysis.json",
    "session_horizon_results.json",
    "trade_frequency_results.json",
    "decision_log.csv.gz",
    "decision_error_summary.json",
    "burst_interaction_results.json",
    "flow_interaction_results.json",
    "horizon_policy_results.json",
    "execution_policy_results.json",
    "allocation_policy_results.json",
    "leverage_results.json",
    "liquidation_stress.json",
    "incremental_ablation.json",
    "groq_research_log.json",
    "groq_trial_registry.json",
    "forward_freeze.json",
    "forward_results.json",
    "dsr_results.json",
    "pbo_results.json",
    "final_candidate.json",
    "final_report.md",
}


def default_candidate_specs() -> list[dict[str, Any]]:
    return [
        {"stage": "B", "name": "high_vol_scale_050", "high_vol_scale": 0.50},
        {"stage": "B", "name": "high_vol_scale_075", "high_vol_scale": 0.75},
        {"stage": "C", "name": "burst_high_scale_050", "burst_high_scale": 0.50, "burst_threshold": 0.65},
        {"stage": "C", "name": "burst_high_scale_075", "burst_high_scale": 0.75, "burst_threshold": 0.65},
        {"stage": "D", "name": "flow_conflict_scale_050", "flow_conflict_scale": 0.50},
        {"stage": "D", "name": "flow_conflict_scale_075", "flow_conflict_scale": 0.75},
        {"stage": "E", "name": "trend_conflict_scale_050", "trend_conflict_scale": 0.50},
        {"stage": "E", "name": "trend_conflict_scale_075", "trend_conflict_scale": 0.75},
        {"stage": "G", "name": "reserve_10", "reserve_fraction": 0.10},
        {"stage": "G", "name": "reserve_20", "reserve_fraction": 0.20},
        {"stage": "G", "name": "reserve_30", "reserve_fraction": 0.30},
    ]


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def merge_frozen_burst_event_state(
    decisions: pd.DataFrame,
    events: pd.DataFrame,
    *,
    tolerance_minutes: int = 60,
) -> pd.DataFrame:
    if tolerance_minutes <= 0:
        raise ValueError("tolerance_minutes must be positive")
    required_decisions = {"decision_timestamp", "symbol"}
    required_events = {"timestamp", "symbol", "burst_score"}
    if required_decisions.difference(decisions.columns) or required_events.difference(events.columns):
        raise ValueError("missing decision or burst-event columns")
    left = decisions.copy()
    left["decision_timestamp"] = pd.to_datetime(left["decision_timestamp"], utc=True)
    right = events.loc[:, ["timestamp", "symbol", "burst_score"]].copy()
    right["timestamp"] = pd.to_datetime(right["timestamp"], utc=True)
    parts: list[pd.DataFrame] = []
    tolerance = pd.Timedelta(minutes=tolerance_minutes)
    for symbol, group in left.groupby("symbol", sort=False):
        event_group = right.loc[right["symbol"] == symbol].sort_values("timestamp")
        ordered = group.sort_values("decision_timestamp")
        if event_group.empty:
            merged = ordered.copy()
            merged["burst_event_timestamp"] = pd.NaT
            merged["burst_score_proxy"] = float("nan")
        else:
            merged = pd.merge_asof(
                ordered,
                event_group.rename(columns={"timestamp": "burst_event_timestamp", "burst_score": "burst_score_proxy"}).drop(columns="symbol"),
                left_on="decision_timestamp",
                right_on="burst_event_timestamp",
                direction="backward",
                tolerance=tolerance,
            )
        parts.append(merged)
    out = pd.concat(parts, ignore_index=False).sort_index()
    out["burst_probability"] = out["burst_score_proxy"].map(
        lambda value: _sigmoid(float(value)) if pd.notna(value) else 0.0
    )
    out["burst_probability_semantics"] = "sigmoid_proxy_of_frozen_v5_high_event_score_not_calibrated_probability"
    return out


def ensure_artifact_contract(root: str | Path) -> list[str]:
    base = Path(root)
    return sorted(name for name in REQUIRED_V6_ARTIFACTS if not (base / name).exists())
