from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from crypto_research.multi_asset_v3 import drift_futures_weights, rebalance_cost, turnover
from crypto_research.reliability_v7 import ReliabilityGateConfig, apply_reliability_gates
from crypto_research.run_v3 import stateful_summary


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
