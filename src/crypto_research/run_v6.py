from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from crypto_research.multi_asset_v3 import (
    drift_futures_weights,
    rebalance_cost,
    turnover,
)
from crypto_research.run_v3 import stateful_summary


def select_incremental_module(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    penalty: float,
) -> bool:
    if penalty < 0:
        raise ValueError("penalty must be non-negative")
    net_gain = float(candidate["net_return"]) - float(baseline["net_return"])
    sharpe_ok = float(candidate["sharpe"]) >= float(baseline["sharpe"])
    drawdown_ok = float(candidate["max_drawdown"]) <= float(baseline["max_drawdown"]) + 1e-12
    return net_gain > penalty and sharpe_ok and drawdown_ok


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


def replay_weight_overlay(
    decision_log: pd.DataFrame,
    *,
    scale_fn: Callable[[Any], float],
    round_trip_cost_bps: float = 10.0,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    required = {
        "decision_timestamp",
        "symbol",
        "target_weight",
        "holding_return_label",
        "funding_sum_label",
    }
    missing = required.difference(decision_log.columns)
    if missing:
        raise ValueError(f"missing decision columns: {sorted(missing)}")
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
        symbols = sorted(set(indexed.index) | set(current))
        previous = np.array([current.get(symbol, 0.0) for symbol in symbols], dtype=float)
        target = np.zeros(len(symbols), dtype=float)
        holding = np.zeros(len(symbols), dtype=float)
        funding = np.zeros(len(symbols), dtype=float)

        for index, symbol in enumerate(symbols):
            if symbol not in indexed.index:
                continue
            row = indexed.loc[symbol]
            if isinstance(row, pd.DataFrame):
                raise ValueError(f"duplicate decision row for {symbol} at {timestamp}")
            base_target = float(row["target_weight"])
            scale = float(scale_fn(row))
            if not np.isfinite(scale) or not 0.0 <= scale <= 1.0:
                raise ValueError("overlay scale must be finite and in [0, 1]")
            target[index] = base_target * scale
            holding[index] = float(row["holding_return_label"])
            funding[index] = float(row["funding_sum_label"])
            decision_rows.append(
                {
                    "decision_timestamp": timestamp,
                    "symbol": symbol,
                    "current_weight": float(previous[index]),
                    "base_target_weight": base_target,
                    "proposed_target_weight": float(target[index]),
                    "decision": _action(float(previous[index]), float(target[index])),
                    "scale": scale,
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
        long_mask = target > 1e-12
        short_mask = target < -1e-12
        period_rows.append(
            {
                "decision_timestamp": timestamp,
                "gross_return": gross_return,
                "funding_return": funding_return,
                "transaction_cost": transaction_cost,
                "net_return": net_return,
                "turnover": period_turnover,
                "final_unwind_turnover": 0.0,
                "gross_exposure": float(np.abs(target).sum()),
                "net_exposure": float(target.sum()),
                "long_count": int(long_mask.sum()),
                "short_count": int(short_mask.sum()),
                "rebalance_trade_count": int((np.abs(delta) > 1e-12).sum()),
                "weights_json": json.dumps(
                    {symbol: float(weight) for symbol, weight in zip(symbols, target, strict=True)}
                ),
            }
        )
        if 1.0 + net_return <= 0:
            current = {symbol: float(weight) for symbol, weight in zip(symbols, target, strict=True)}
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
        final_cost = rebalance_cost(final_weights, flat, round_trip_cost_bps=round_trip_cost_bps)
        periods.loc[periods.index[-1], "final_unwind_turnover"] = final_turnover
        periods.loc[periods.index[-1], "transaction_cost"] += final_cost
        periods.loc[periods.index[-1], "net_return"] -= final_cost
        periods.loc[periods.index[-1], "rebalance_trade_count"] += int((np.abs(final_weights) > 1e-12).sum())
    return periods, pd.DataFrame(decision_rows), stateful_summary(periods)


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def freeze_candidate(
    config: dict[str, Any],
    *,
    artifact_root: str | Path,
    timestamp: str,
    total_trial_count: int,
) -> dict[str, Any]:
    if total_trial_count < 779:
        raise ValueError("V6 trial count cannot reset below the locked V5 count")
    root = Path(artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    canonical = _canonical_json(config)
    payload = {
        "research_version": "V6",
        "freeze_timestamp_utc": str(timestamp),
        "candidate_config": config,
        "candidate_hash_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "total_trial_count_at_freeze": int(total_trial_count),
        "locked_evidence": {
            "historical_confirmation": "2021-2023_OBSERVED_NOT_TUNED",
            "aug_1_9_2026": "OBSERVED_CONTAMINATED_NOT_TUNED",
        },
    }
    (root / "forward_freeze.json").write_text(json.dumps(payload, indent=2, default=str))
    return payload


def verify_frozen_candidate(path: str | Path) -> bool:
    payload = json.loads(Path(path).read_text())
    expected = str(payload.get("candidate_hash_sha256", ""))
    actual = hashlib.sha256(_canonical_json(payload["candidate_config"]).encode()).hexdigest()
    return bool(expected) and expected == actual


def build_horizon_outcomes(
    signals: pd.DataFrame,
    minute_bars: pd.DataFrame,
    *,
    horizons: tuple[int, ...] = (15, 30, 60, 180, 240, 720),
    entry_delay_minutes: int = 60,
    round_trip_cost_bps: float = 10.0,
) -> pd.DataFrame:
    if entry_delay_minutes < 0 or round_trip_cost_bps < 0 or any(h <= 0 for h in horizons):
        raise ValueError("invalid horizon, delay, or cost")
    required_signals = {"decision_timestamp", "symbol", "target_weight"}
    required_bars = {"timestamp", "symbol", "open", "close"}
    if required_signals.difference(signals.columns) or required_bars.difference(minute_bars.columns):
        raise ValueError("missing signal or minute-bar columns")
    signal = signals.copy()
    signal["decision_timestamp"] = pd.to_datetime(signal["decision_timestamp"], utc=True)
    bars = minute_bars.copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars = bars.sort_values(["symbol", "timestamp"])
    cost = round_trip_cost_bps / 10_000.0
    rows: list[dict[str, Any]] = []
    by_symbol = {symbol: group.set_index("timestamp") for symbol, group in bars.groupby("symbol", sort=False)}
    for row in signal.itertuples(index=False):
        symbol = str(row.symbol)
        table = by_symbol.get(symbol)
        if table is None:
            continue
        entry_timestamp = pd.Timestamp(row.decision_timestamp) + pd.Timedelta(minutes=entry_delay_minutes)
        if entry_timestamp not in table.index:
            continue
        entry_open = float(table.at[entry_timestamp, "open"])
        if entry_open <= 0:
            continue
        side = int(np.sign(float(row.target_weight)))
        result: dict[str, Any] = {
            "decision_timestamp": pd.Timestamp(row.decision_timestamp),
            "symbol": symbol,
            "entry_timestamp": entry_timestamp,
            "signal_side": side,
            "target_weight": float(row.target_weight),
        }
        for horizon in horizons:
            exit_timestamp = entry_timestamp + pd.Timedelta(minutes=horizon - 1)
            if exit_timestamp not in table.index:
                result[f"return_{horizon}m"] = np.nan
                result[f"directional_net_{horizon}m"] = np.nan
                continue
            gross = float(table.at[exit_timestamp, "close"]) / entry_open - 1.0
            result[f"return_{horizon}m"] = gross
            result[f"directional_net_{horizon}m"] = side * gross - cost if side else -cost
        rows.append(result)
    return pd.DataFrame(rows)


def _max_losing_streak(values: pd.Series) -> int:
    longest = 0
    current = 0
    for value in pd.to_numeric(values, errors="coerce").fillna(0.0):
        if float(value) < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return int(longest)


def summarize_trade_frequency(decisions: pd.DataFrame) -> dict[str, Any]:
    required = {"decision_timestamp", "decision", "realized_net_contribution"}
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(f"missing frequency columns: {sorted(missing)}")
    work = decisions.copy()
    work["decision_timestamp"] = pd.to_datetime(work["decision_timestamp"], utc=True)
    trade_mask = ~work["decision"].isin(["NO_TRADE", "HOLD_LONG", "HOLD_SHORT"])
    trades = work.loc[trade_mask].sort_values("decision_timestamp").copy()
    net = pd.to_numeric(trades["realized_net_contribution"], errors="coerce").fillna(0.0)
    fees = pd.to_numeric(trades.get("transaction_cost_contribution", 0.0), errors="coerce")
    fees = fees.fillna(0.0) if isinstance(fees, pd.Series) else pd.Series(float(fees), index=trades.index)
    slippage = pd.to_numeric(trades.get("slippage_contribution", 0.0), errors="coerce")
    slippage = slippage.fillna(0.0) if isinstance(slippage, pd.Series) else pd.Series(float(slippage), index=trades.index)
    funding = pd.to_numeric(trades.get("funding_contribution", 0.0), errors="coerce")
    funding = funding.fillna(0.0) if isinstance(funding, pd.Series) else pd.Series(float(funding), index=trades.index)
    days = max(int(work["decision_timestamp"].dt.floor("D").nunique()), 1)
    session_counts = trades.groupby("vn_session").size().astype(int).to_dict() if "vn_session" in trades.columns else {}
    return {
        "trade_count": int(len(trades)),
        "trades_per_day": float(len(trades) / days),
        "trades_per_session": session_counts,
        "gross_edge_per_trade": float((net + fees + slippage - funding).mean()) if len(trades) else 0.0,
        "fees_per_trade": float(fees.mean()) if len(trades) else 0.0,
        "slippage_per_trade": float(slippage.mean()) if len(trades) else 0.0,
        "funding_per_trade": float(funding.mean()) if len(trades) else 0.0,
        "net_expectancy_per_trade": float(net.mean()) if len(trades) else 0.0,
        "daily_net_expectancy": float(net.sum() / days),
        "probability_of_loss": float((net < 0).mean()) if len(trades) else 0.0,
        "max_losing_streak": _max_losing_streak(net),
    }


def _scale_for_spec(row: Any, spec: dict[str, Any]) -> float:
    scale = 1.0
    if "high_vol_scale" in spec and str(getattr(row, "vol_state", "mid")) == "high":
        scale *= float(spec["high_vol_scale"])
    if "burst_high_scale" in spec and float(getattr(row, "burst_probability", 0.0) or 0.0) >= float(spec.get("burst_threshold", 0.65)):
        scale *= float(spec["burst_high_scale"])
    target = float(getattr(row, "target_weight", 0.0))
    flow = str(getattr(row, "flow_state", "neutral"))
    if "flow_conflict_scale" in spec and ((target > 0 and flow == "sell") or (target < 0 and flow == "buy")):
        scale *= float(spec["flow_conflict_scale"])
    trend = str(getattr(row, "trend_state", "unknown"))
    if "trend_conflict_scale" in spec and ((target > 0 and trend == "down") or (target < 0 and trend == "up")):
        scale *= float(spec["trend_conflict_scale"])
    if "reserve_fraction" in spec:
        reserve = float(spec["reserve_fraction"])
        if not 0.0 <= reserve < 1.0:
            raise ValueError("reserve_fraction must be in [0, 1)")
        scale *= 1.0 - reserve
    if not 0.0 <= scale <= 1.0:
        raise ValueError("combined overlay scale must remain in [0, 1]")
    return float(scale)


def _metric_delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float | None]:
    keys = ("net_return", "sharpe", "profit_factor", "max_drawdown", "turnover", "transaction_cost", "funding_return")
    result: dict[str, float | None] = {}
    for key in keys:
        left = candidate.get(key)
        right = baseline.get(key)
        result[key] = None if left is None or right is None else float(left) - float(right)
    return result


def run_hierarchical_replay(
    decision_log: pd.DataFrame,
    *,
    artifact_root: str | Path,
    candidate_specs: list[dict[str, Any]],
    selection_fraction: float = 0.7,
    complexity_penalty: float = 0.002,
    prior_trials: int = 779,
    round_trip_cost_bps: float = 10.0,
) -> dict[str, Any]:
    from crypto_research.trials_v6 import TrialRegistry

    if not 0.0 < selection_fraction < 1.0:
        raise ValueError("selection_fraction must be between zero and one")
    root = Path(artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    work = decision_log.copy()
    work["decision_timestamp"] = pd.to_datetime(work["decision_timestamp"], utc=True)
    times = pd.Index(sorted(work["decision_timestamp"].dropna().unique()))
    if len(times) < 4:
        raise ValueError("not enough decision timestamps for selection/evaluation split")
    split = max(1, min(len(times) - 1, int(len(times) * selection_fraction)))
    cutoff = times[split - 1]
    selection = work.loc[work["decision_timestamp"] <= cutoff].copy()
    evaluation = work.loc[work["decision_timestamp"] > cutoff].copy()

    base_fn = lambda row: 1.0
    base_sel_periods, _, base_sel = replay_weight_overlay(selection, scale_fn=base_fn, round_trip_cost_bps=round_trip_cost_bps)
    base_eval_periods, _, base_eval = replay_weight_overlay(evaluation, scale_fn=base_fn, round_trip_cost_bps=round_trip_cost_bps)
    registry = TrialRegistry(root / "experiment_registry.csv", prior_count=prior_trials)
    stages: dict[str, Any] = {
        "A": {
            "name": "retained_v4_core_replay",
            "selection_metrics": base_sel,
            "evaluation_metrics": base_eval,
            "selection_end": str(pd.Timestamp(cutoff)),
        }
    }
    promoted_by_stage: dict[str, dict[str, Any]] = {}
    stage_candidates: dict[str, list[dict[str, Any]]] = {}

    for spec in candidate_specs:
        stage = str(spec["stage"])
        name = str(spec["name"])
        scale_fn = lambda row, current=spec: _scale_for_spec(row, current)
        _, _, sel_metrics = replay_weight_overlay(selection, scale_fn=scale_fn, round_trip_cost_bps=round_trip_cost_bps)
        _, _, eval_metrics = replay_weight_overlay(evaluation, scale_fn=scale_fn, round_trip_cost_bps=round_trip_cost_bps)
        promoted = select_incremental_module(base_sel, sel_metrics, penalty=complexity_penalty)
        status = "PROMOTED_INNER" if promoted else "REJECTED_INNER"
        registry.record(stage, name, status, config=spec, metrics={"selection": sel_metrics, "evaluation": eval_metrics})
        row = {
            "name": name,
            "config": spec,
            "status": status,
            "selection_metrics": sel_metrics,
            "evaluation_metrics": eval_metrics,
            "selection_delta": _metric_delta(sel_metrics, base_sel),
            "evaluation_delta": _metric_delta(eval_metrics, base_eval),
        }
        stage_candidates.setdefault(stage, []).append(row)

    for stage, rows in stage_candidates.items():
        eligible = [row for row in rows if row["status"] == "PROMOTED_INNER"]
        if eligible:
            winner = max(eligible, key=lambda row: (float(row["selection_metrics"].get("sharpe", -1e99)), float(row["selection_metrics"].get("net_return", -1e99))))
            promoted_by_stage[stage] = dict(winner["config"])
        stages[stage] = {"candidates": rows, "selected_inner": promoted_by_stage.get(stage)}

    promoted_specs = [promoted_by_stage[key] for key in sorted(promoted_by_stage)]

    def full_scale(row: Any) -> float:
        value = 1.0
        for spec in promoted_specs:
            value *= _scale_for_spec(row, spec)
        return float(max(0.0, min(1.0, value)))

    h_sel_periods, h_sel_decisions, h_sel = replay_weight_overlay(
        selection, scale_fn=full_scale, round_trip_cost_bps=round_trip_cost_bps
    )
    h_eval_periods, h_eval_decisions, h_eval = replay_weight_overlay(
        evaluation, scale_fn=full_scale, round_trip_cost_bps=round_trip_cost_bps
    )
    h_config = {
        "promoted_stage_specs": promoted_specs,
        "direction_source": "retained_H12",
        "round_trip_cost_bps": round_trip_cost_bps,
    }
    registry.record(
        "H",
        "integrated_inner_selected_combination",
        "FROZEN_DISCOVERY_CANDIDATE",
        config=h_config,
        metrics={"selection": h_sel, "evaluation": h_eval},
    )
    registry.to_csv()
    stages["H"] = {
        "config": h_config,
        "selection_metrics": h_sel,
        "evaluation_metrics": h_eval,
        "selection_delta": _metric_delta(h_sel, base_sel),
        "evaluation_delta": _metric_delta(h_eval, base_eval),
    }
    payload = {
        "prior_trial_count": int(prior_trials),
        "trial_count_after": int(registry.total_count),
        "selection_fraction": float(selection_fraction),
        "complexity_penalty": float(complexity_penalty),
        "stages": stages,
        "final_discovery_config": h_config,
    }
    (root / "incremental_ablation.json").write_text(json.dumps(payload, indent=2, default=str))
    pd.concat([h_sel_periods, h_eval_periods], ignore_index=True).to_csv(
        root / "integrated_periods.csv.gz", index=False, compression="gzip"
    )
    pd.concat([h_sel_decisions, h_eval_decisions], ignore_index=True).to_csv(
        root / "controller_decisions.csv.gz", index=False, compression="gzip"
    )
    pd.concat([base_sel_periods, base_eval_periods], ignore_index=True).to_csv(
        root / "baseline_replay_periods.csv.gz", index=False, compression="gzip"
    )
    return payload
