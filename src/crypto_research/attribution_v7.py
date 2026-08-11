from __future__ import annotations

from typing import Any

import pandas as pd

from crypto_research.decision_diagnostics import classify_error

_ERROR_CLASSES = (
    "CORRECT",
    "WRONG_SIDE",
    "FALSE_ENTER",
    "MISSED_ENTER",
    "PREMATURE_EXIT",
    "LATE_EXIT",
    "UNNECESSARY_REBALANCE",
)


def _row_net_contribution(
    previous_weight: float,
    target_weight: float,
    holding_return: float,
    funding_sum: float,
    *,
    round_trip_cost_bps: float,
) -> float:
    rate = float(round_trip_cost_bps) / 10_000.0
    directional = float(target_weight) * (float(holding_return) - float(funding_sum))
    rebalance_proxy = abs(float(target_weight) - float(previous_weight)) * rate
    return directional - rebalance_proxy


def attribute_candidate_errors(
    base_log: pd.DataFrame,
    candidate_decisions: pd.DataFrame,
    *,
    round_trip_cost_bps: float,
) -> dict[str, Any]:
    keys = ["decision_timestamp", "symbol"]
    required_base = {
        *keys,
        "previous_weight",
        "target_weight",
        "holding_return_label",
        "funding_sum_label",
    }
    required_candidate = {*keys, "current_weight", "proposed_target_weight"}
    if missing := required_base.difference(base_log.columns):
        raise ValueError(f"base_log missing columns: {sorted(missing)}")
    if missing := required_candidate.difference(candidate_decisions.columns):
        raise ValueError(f"candidate_decisions missing columns: {sorted(missing)}")
    if round_trip_cost_bps < 0:
        raise ValueError("round_trip_cost_bps must be non-negative")

    base = base_log.copy()
    candidate = candidate_decisions.copy()
    for frame in (base, candidate):
        frame["decision_timestamp"] = pd.to_datetime(frame["decision_timestamp"], utc=True)
    merged = base.merge(candidate, on=keys, how="inner", validate="one_to_one")
    if len(merged) != len(base) or len(merged) != len(candidate):
        raise ValueError("base/candidate attribution keys do not match one-to-one")

    rows: list[dict[str, Any]] = []
    for row in merged.itertuples(index=False):
        holding = float(row.holding_return_label)
        funding = float(row.funding_sum_label)
        base_error = classify_error(
            float(row.previous_weight),
            float(row.target_weight),
            holding_return=holding,
            funding_sum=funding,
            round_trip_cost_bps=round_trip_cost_bps,
        )
        candidate_error = classify_error(
            float(row.current_weight),
            float(row.proposed_target_weight),
            holding_return=holding,
            funding_sum=funding,
            round_trip_cost_bps=round_trip_cost_bps,
        )
        base_net = _row_net_contribution(
            float(row.previous_weight),
            float(row.target_weight),
            holding,
            funding,
            round_trip_cost_bps=round_trip_cost_bps,
        )
        candidate_net = _row_net_contribution(
            float(row.current_weight),
            float(row.proposed_target_weight),
            holding,
            funding,
            round_trip_cost_bps=round_trip_cost_bps,
        )
        rows.append(
            {
                "base_error": base_error,
                "candidate_error": candidate_error,
                "base_net": base_net,
                "candidate_net": candidate_net,
                "delta": candidate_net - base_net,
            }
        )

    frame = pd.DataFrame(rows)
    by_error: dict[str, dict[str, float | int]] = {}
    for error_class in _ERROR_CLASSES:
        base_mask = frame["base_error"].eq(error_class)
        candidate_count = int(frame["candidate_error"].eq(error_class).sum())
        deltas = frame.loc[base_mask, "delta"]
        positive = deltas.clip(lower=0.0)
        negative = (-deltas.clip(upper=0.0))
        avoided_loss_bps = float(positive.sum() * 10_000.0) if error_class != "CORRECT" else 0.0
        lost_correct_trade_bps = float(negative.sum() * 10_000.0) if error_class == "CORRECT" else 0.0
        net_effect_bps = float(deltas.sum() * 10_000.0)
        by_error[error_class] = {
            "baseline_count": int(base_mask.sum()),
            "candidate_count": candidate_count,
            "count_delta": candidate_count - int(base_mask.sum()),
            "avoided_loss_bps": avoided_loss_bps,
            "lost_correct_trade_bps": lost_correct_trade_bps,
            "net_bps_effect": net_effect_bps,
        }

    return {
        "rows": int(len(frame)),
        "round_trip_cost_bps": float(round_trip_cost_bps),
        "by_error": by_error,
        "net_bps_effect": float(sum(item["net_bps_effect"] for item in by_error.values())),
    }
