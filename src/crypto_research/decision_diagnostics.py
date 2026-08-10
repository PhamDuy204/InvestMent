from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

_EPS = 1e-12


def classify_decision(previous_weight: float, target_weight: float) -> str:
    previous = float(previous_weight)
    target = float(target_weight)
    previous_flat = abs(previous) <= _EPS
    target_flat = abs(target) <= _EPS
    if previous_flat and target_flat:
        return "NO_POSITION"
    if previous_flat:
        return "ENTER"
    if target_flat:
        return "EXIT"
    if np.sign(previous) != np.sign(target):
        return "FLIP"
    if abs(previous - target) <= _EPS:
        return "HOLD"
    return "REBALANCE"


def _full_round_trip_rate(round_trip_cost_bps: float) -> float:
    if round_trip_cost_bps < 0:
        raise ValueError("round_trip_cost_bps must be non-negative")
    return float(round_trip_cost_bps) / 10_000.0


def _directional_period_return(weight: float, holding_return: float, funding_sum: float) -> float:
    return float(weight) * (float(holding_return) - float(funding_sum))


def oracle_action(previous_weight: float, holding_return: float, funding_sum: float, *, round_trip_cost_bps: float) -> str:
    rate = _full_round_trip_rate(round_trip_cost_bps)
    previous = float(previous_weight)
    net_long = float(holding_return) - float(funding_sum) - rate
    net_short = -float(holding_return) + float(funding_sum) - rate
    if abs(previous) > _EPS:
        continued = _directional_period_return(previous, holding_return, funding_sum)
        if continued > abs(previous) * rate:
            return "HOLD"
        if max(net_long, net_short) <= 0:
            return "EXIT"
    if net_long > max(0.0, net_short):
        return "ENTER_LONG"
    if net_short > max(0.0, net_long):
        return "ENTER_SHORT"
    return "FLAT"


def classify_error(previous_weight: float, target_weight: float, *, holding_return: float, funding_sum: float, round_trip_cost_bps: float) -> str:
    action = classify_decision(previous_weight, target_weight)
    previous = float(previous_weight)
    target = float(target_weight)
    rate = _full_round_trip_rate(round_trip_cost_bps)
    target_contribution = _directional_period_return(target, holding_return, funding_sum)
    if action == "ENTER":
        return "FALSE_ENTER" if target_contribution - abs(target) * rate < 0 else "CORRECT"
    if action == "FLIP":
        return "WRONG_SIDE" if target_contribution - abs(target) * rate < 0 else "CORRECT"
    if action == "NO_POSITION":
        best_flat_entry = max(float(holding_return) - float(funding_sum), -float(holding_return) + float(funding_sum))
        return "MISSED_ENTER" if best_flat_entry > rate else "CORRECT"
    if action == "EXIT":
        continued = _directional_period_return(previous, holding_return, funding_sum)
        return "PREMATURE_EXIT" if continued > abs(previous) * rate else "CORRECT"
    if action == "HOLD":
        return "LATE_EXIT" if target_contribution < -abs(target) * rate else "CORRECT"
    keep_previous = _directional_period_return(previous, holding_return, funding_sum)
    incremental_cost = abs(target - previous) * rate
    if target_contribution < -abs(target) * rate:
        return "WRONG_SIDE"
    if target_contribution - incremental_cost <= keep_previous + _EPS:
        return "UNNECESSARY_REBALANCE"
    return "CORRECT"


def build_decision_log(periods: pd.DataFrame, *, round_trip_cost_bps: float) -> pd.DataFrame:
    required = {"decision_timestamp", "decision_details_json"}
    missing = required.difference(periods.columns)
    if missing:
        raise ValueError(f"missing decision diagnostic columns: {sorted(missing)}")
    rows: list[dict[str, Any]] = []
    for period in periods.itertuples(index=False):
        details = json.loads(period.decision_details_json)
        for symbol, detail in details.items():
            previous = float(detail["previous_weight"])
            target = float(detail["target_weight"])
            holding_return = float(detail["holding_return"])
            funding_sum = float(detail["funding_sum"])
            rows.append({
                "decision_timestamp": pd.Timestamp(period.decision_timestamp),
                "fold": getattr(period, "fold", None),
                "symbol": symbol,
                "action": classify_decision(previous, target),
                "error_class": classify_error(previous, target, holding_return=holding_return, funding_sum=funding_sum, round_trip_cost_bps=round_trip_cost_bps),
                "oracle_action": oracle_action(previous, holding_return, funding_sum, round_trip_cost_bps=round_trip_cost_bps),
                "previous_weight": previous,
                "target_weight": target,
                "delta_weight": float(detail["delta_weight"]),
                "raw_score": float(detail["raw_score"]),
                "effective_score": float(detail["effective_score"]),
                "funding_rate_feature": float(detail["funding_rate_feature"]),
                "holding_return_label": holding_return,
                "funding_sum_label": funding_sum,
                "gross_contribution_label": float(detail["gross_contribution"]),
                "funding_contribution_label": float(detail["funding_contribution"]),
                "realized_position_contribution_label": float(detail["gross_contribution"]) + float(detail["funding_contribution"]),
                "oracle_edge_per_unit_label": max(0.0, holding_return - funding_sum - _full_round_trip_rate(round_trip_cost_bps), -holding_return + funding_sum - _full_round_trip_rate(round_trip_cost_bps)),
            })
    return pd.DataFrame(rows)
