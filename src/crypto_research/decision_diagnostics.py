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


def oracle_action(
    previous_weight: float,
    holding_return: float,
    funding_sum: float,
    *,
    round_trip_cost_bps: float,
) -> str:
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


def classify_error(
    previous_weight: float,
    target_weight: float,
    *,
    holding_return: float,
    funding_sum: float,
    round_trip_cost_bps: float,
) -> str:
    action = classify_decision(previous_weight, target_weight)
    previous = float(previous_weight)
    target = float(target_weight)
    rate = _full_round_trip_rate(round_trip_cost_bps)
    target_contribution = _directional_period_return(target, holding_return, funding_sum)

    if action == "ENTER":
        if target_contribution - abs(target) * rate < 0:
            return "FALSE_ENTER"
        return "CORRECT"
    if action == "FLIP":
        if target_contribution - abs(target) * rate < 0:
            return "WRONG_SIDE"
        return "CORRECT"
    if action == "NO_POSITION":
        best_flat_entry = max(
            float(holding_return) - float(funding_sum),
            -float(holding_return) + float(funding_sum),
        )
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
            rows.append(
                {
                    "decision_timestamp": pd.Timestamp(period.decision_timestamp),
                    "fold": getattr(period, "fold", None),
                    "symbol": symbol,
                    "action": classify_decision(previous, target),
                    "error_class": classify_error(
                        previous,
                        target,
                        holding_return=holding_return,
                        funding_sum=funding_sum,
                        round_trip_cost_bps=round_trip_cost_bps,
                    ),
                    "oracle_action": oracle_action(
                        previous,
                        holding_return,
                        funding_sum,
                        round_trip_cost_bps=round_trip_cost_bps,
                    ),
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
                    "oracle_edge_per_unit_label": max(
                        0.0,
                        holding_return - funding_sum - _full_round_trip_rate(round_trip_cost_bps),
                        -holding_return + funding_sum - _full_round_trip_rate(round_trip_cost_bps),
                    ),
                }
            )
    return pd.DataFrame(rows)

V6_CAUSAL_COLUMNS = (
    "decision_timestamp",
    "symbol",
    "effective_score",
    "previous_weight",
    "proposed_target_weight",
    "decision",
    "chosen_horizon",
    "effective_leverage",
    "execution_mode",
    "burst_probability",
    "vol_state",
    "vn_session",
    "flow_state",
    "funding",
    "trend_state",
    "correlation_state",
    "account_equity",
    "drawdown",
    "margin_buffer",
)

V6_LABEL_COLUMNS = (
    "realized_return",
    "oracle_direction",
    "oracle_exit",
    "WRONG_SIDE",
    "FALSE_ENTER",
    "MISSED_ENTER",
    "PREMATURE_EXIT",
    "LATE_EXIT",
    "UNNECESSARY_REBALANCE",
    "EXECUTION_MISS",
    "SLIPPAGE_DAMAGE",
    "LEVERAGE_DAMAGE",
    "LIQUIDATION",
)


def enrich_v6_decision_log(
    base_log: pd.DataFrame,
    controller_rows: pd.DataFrame,
    outcomes: pd.DataFrame | None = None,
) -> pd.DataFrame:
    keys = ["decision_timestamp", "symbol"]
    for frame, name in ((base_log, "base_log"), (controller_rows, "controller_rows")):
        missing = set(keys).difference(frame.columns)
        if missing:
            raise ValueError(f"{name} missing keys: {sorted(missing)}")
    base = base_log.copy()
    controller = controller_rows.copy()
    for frame in (base, controller):
        frame["decision_timestamp"] = pd.to_datetime(frame["decision_timestamp"], utc=True)
    out = base.merge(controller, on=keys, how="left", suffixes=("", "_controller"), validate="one_to_one")

    if outcomes is not None:
        outcome = outcomes.copy()
        missing = set(keys).difference(outcome.columns)
        if missing:
            raise ValueError(f"outcomes missing keys: {sorted(missing)}")
        outcome["decision_timestamp"] = pd.to_datetime(outcome["decision_timestamp"], utc=True)
        out = out.merge(outcome, on=keys, how="left", validate="one_to_one")

    for label in ("WRONG_SIDE", "FALSE_ENTER", "MISSED_ENTER", "PREMATURE_EXIT", "LATE_EXIT", "UNNECESSARY_REBALANCE"):
        out[label] = out.get("error_class", pd.Series("CORRECT", index=out.index)).eq(label)
    for target, source in (
        ("EXECUTION_MISS", "execution_miss"),
        ("SLIPPAGE_DAMAGE", "slippage_damage"),
        ("LEVERAGE_DAMAGE", "leverage_damage"),
        ("LIQUIDATION", "liquidation"),
    ):
        out[target] = out[source].fillna(False).astype(bool) if source in out.columns else False
    for label in ("realized_return", "oracle_direction", "oracle_exit"):
        if label not in out.columns:
            out[label] = np.nan
    return out


def summarize_v6_errors(frame: pd.DataFrame) -> dict[str, object]:
    before = frame.get("error_class", pd.Series(dtype="object")).value_counts().to_dict()
    after = frame.get("v6_error_class", frame.get("error_class", pd.Series(dtype="object"))).value_counts().to_dict()
    groups: dict[str, object] = {}
    for key in ("symbol", "vn_session", "vol_state"):
        if key not in frame.columns:
            continue
        grouped: dict[str, object] = {}
        for value, part in frame.groupby(key, dropna=False):
            grouped[str(value)] = {
                "before": part.get("error_class", pd.Series(dtype="object")).value_counts().to_dict(),
                "after": part.get("v6_error_class", part.get("error_class", pd.Series(dtype="object"))).value_counts().to_dict(),
            }
        groups[key] = grouped
    return {"before": before, "after": after, "groups": groups}
