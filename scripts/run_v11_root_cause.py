from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from crypto_research.multi_asset_v3 import drift_futures_weights
from crypto_research.reliability_v7 import ReliabilityGateConfig
from crypto_research.run_v3 import stateful_summary
from crypto_research.run_v7 import (
    _wrong_side_count,
    replay_v7_reliability,
    split_selection_evaluation,
)
from crypto_research.state_v6 import add_session_state

ART = Path("artifacts/multi_asset_v11")
BASELINE = ReliabilityGateConfig(None, None, None, False)
V10_CANDIDATE = ReliabilityGateConfig(None, None, None, False, flat_trend_scale=0.5)
ONE_WAY_COST = lambda round_trip_bps: float(round_trip_bps) / 2.0 / 10_000.0


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def _write_json(name: str, payload: dict[str, Any]) -> None:
    ART.mkdir(parents=True, exist_ok=True)
    (ART / name).write_text(json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["decision_timestamp"] = pd.to_datetime(frame["decision_timestamp"], utc=True)
    required = {
        "decision_timestamp",
        "fold",
        "symbol",
        "action",
        "target_weight",
        "effective_score",
        "holding_return_label",
        "funding_sum_label",
        "trend_state",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"diagnostic input missing columns: {sorted(missing)}")
    frame = frame.sort_values(["fold", "decision_timestamp", "symbol"]).reset_index(drop=True)
    return add_session_state(frame)


def _side(weight: pd.Series) -> pd.Series:
    return pd.Series(np.select([weight > 1e-12, weight < -1e-12], ["LONG", "SHORT"], default="FLAT"), index=weight.index)


def attribute_replay_components(
    source: pd.DataFrame,
    decisions: pd.DataFrame,
    periods: pd.DataFrame,
    *,
    round_trip_cost_bps: float,
) -> pd.DataFrame:
    """Attribute the shared replay's additive P&L/cost exactly to symbols.

    This does not recreate strategy decisions: it consumes the decision rows produced by
    ``replay_v7_reliability``. The only extra accounting is the replay's final unwind.
    """
    if source["fold"].nunique() != 1:
        raise ValueError("attribute_replay_components expects one fold")
    if round_trip_cost_bps < 0:
        raise ValueError("round_trip_cost_bps must be non-negative")

    keys = ["decision_timestamp", "symbol"]
    causal_columns = {"vol_state", "activity_state", "global_session"}
    causal = source.copy() if causal_columns.issubset(source.columns) else add_session_state(source)
    keep = [
        "decision_timestamp",
        "fold",
        "symbol",
        "action",
        "holding_return_label",
        "funding_sum_label",
        "effective_score",
        "trend_state",
        "vol_state",
        "activity_state",
        "funding_state",
        "global_session",
    ]
    keep += [c for c in ("cross_sectional_dispersion", "exposure_increase") if c in causal.columns]
    merged = decisions.merge(causal[keep], on=keys, how="left", validate="one_to_one")
    if merged[["fold", "holding_return_label", "funding_sum_label"]].isna().any().any():
        raise ValueError("replay decisions could not be matched to diagnostic source")

    rate = ONE_WAY_COST(round_trip_cost_bps)
    merged["turnover"] = (merged["proposed_target_weight"] - merged["current_weight"]).abs()
    merged["transaction_cost"] = merged["turnover"] * rate
    merged["gross_holding_return"] = merged["proposed_target_weight"] * merged["holding_return_label"]
    merged["funding_contribution"] = -merged["proposed_target_weight"] * merged["funding_sum_label"]
    merged["net_component"] = (
        merged["gross_holding_return"] + merged["funding_contribution"] - merged["transaction_cost"]
    )
    merged["side"] = _side(merged["proposed_target_weight"])
    merged["source_action"] = merged["action"].astype(str)
    merged["action_type"] = merged["source_action"]
    merged["replay_action"] = merged["decision"].astype(str)
    merged["is_final_unwind"] = False

    # The shared replay charges a final liquidation after drifting the final target by
    # the final holding return. Attribute that exact linear cost to the final symbols.
    last_time = merged["decision_timestamp"].max()
    last = merged.loc[merged["decision_timestamp"] == last_time].sort_values("symbol").copy()
    pre_unwind_net = float(
        last["gross_holding_return"].sum()
        + last["funding_contribution"].sum()
        - last["transaction_cost"].sum()
    )
    final_weights = drift_futures_weights(
        last["proposed_target_weight"].to_numpy(dtype=float),
        last["holding_return_label"].to_numpy(dtype=float),
        net_return=pre_unwind_net,
    )
    unwind = last.copy()
    unwind["current_weight"] = final_weights
    unwind["base_target_weight"] = 0.0
    unwind["proposed_target_weight"] = 0.0
    unwind["turnover"] = np.abs(final_weights)
    unwind["transaction_cost"] = unwind["turnover"] * rate
    unwind["gross_holding_return"] = 0.0
    unwind["funding_contribution"] = 0.0
    unwind["net_component"] = -unwind["transaction_cost"]
    unwind["side"] = _side(pd.Series(final_weights, index=unwind.index))
    unwind["source_action"] = "FINAL_UNWIND"
    unwind["action_type"] = "FINAL_UNWIND"
    unwind["replay_action"] = "FINAL_UNWIND"
    unwind["is_final_unwind"] = True
    for column in ("trend_state", "vol_state", "activity_state", "funding_state", "global_session"):
        unwind[column] = "FINAL_UNWIND"
    unwind = unwind.loc[unwind["turnover"] > 1e-15]

    rows = pd.concat([merged, unwind], ignore_index=True, sort=False)
    expected_turnover = float(periods["turnover"].sum() + periods["final_unwind_turnover"].sum())
    checks = {
        "gross": (float(rows["gross_holding_return"].sum()), float(periods["gross_return"].sum())),
        "funding": (float(rows["funding_contribution"].sum()), float(periods["funding_return"].sum())),
        "cost": (float(rows["transaction_cost"].sum()), float(periods["transaction_cost"].sum())),
        "turnover": (float(rows["turnover"].sum()), expected_turnover),
        "net": (float(rows["net_component"].sum()), float(periods["net_return"].sum())),
    }
    for name, (actual, expected) in checks.items():
        if not np.isclose(actual, expected, rtol=1e-9, atol=1e-12):
            raise RuntimeError(f"{name} attribution mismatch: {actual} != {expected}")
    return rows


def _component_totals(rows: pd.DataFrame) -> dict[str, float | int]:
    return {
        "rows": int((~rows["is_final_unwind"]).sum()),
        "gross_holding_return_sum": float(rows["gross_holding_return"].sum()),
        "funding_contribution_sum": float(rows["funding_contribution"].sum()),
        "transaction_cost_sum": float(rows["transaction_cost"].sum()),
        "turnover_sum": float(rows["turnover"].sum()),
        "net_component_sum": float(rows["net_component"].sum()),
    }


def _group_components(rows: pd.DataFrame, keys: list[str]) -> list[dict[str, Any]]:
    work = rows.loc[~rows["is_final_unwind"]].copy()
    grouped = (
        work.groupby(keys, dropna=False, sort=True)
        .agg(
            rows=("symbol", "size"),
            gross_holding_return_sum=("gross_holding_return", "sum"),
            funding_contribution_sum=("funding_contribution", "sum"),
            transaction_cost_sum=("transaction_cost", "sum"),
            turnover_sum=("turnover", "sum"),
            net_component_sum=("net_component", "sum"),
        )
        .reset_index()
    )
    grouped["gross_per_row"] = grouped["gross_holding_return_sum"] / grouped["rows"]
    grouped["net_per_row"] = grouped["net_component_sum"] / grouped["rows"]
    return grouped.sort_values("net_component_sum").to_dict("records")


def _partition(frame: pd.DataFrame, fold: int, *, held_out: bool) -> pd.DataFrame:
    part = frame.loc[frame["fold"] == fold].copy()
    selection, evaluation = split_selection_evaluation(part, selection_fraction=0.70)
    return evaluation if held_out else selection


def _replay_fold(
    part: pd.DataFrame,
    config: ReliabilityGateConfig,
    *,
    round_trip_cost_bps: float,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    periods, decisions, metrics = replay_v7_reliability(
        part, config, round_trip_cost_bps=round_trip_cost_bps
    )
    return periods, decisions, metrics


def _replay_scope(
    frame: pd.DataFrame,
    config: ReliabilityGateConfig,
    *,
    held_out: bool,
    round_trip_cost_bps: float,
    attribute: bool = False,
) -> dict[str, Any]:
    period_parts: list[pd.DataFrame] = []
    component_parts: list[pd.DataFrame] = []
    folds: list[dict[str, Any]] = []
    for fold in sorted(int(v) for v in frame["fold"].dropna().unique()):
        part = _partition(frame, fold, held_out=held_out)
        periods, decisions, metrics = _replay_fold(
            part, config, round_trip_cost_bps=round_trip_cost_bps
        )
        period_parts.append(periods)
        row = {"fold": fold, "rows": int(len(part)), "metrics": metrics}
        if attribute:
            components = attribute_replay_components(
                part, decisions, periods, round_trip_cost_bps=round_trip_cost_bps
            )
            component_parts.append(components)
            row["components"] = _component_totals(components)
        folds.append(row)
    all_periods = pd.concat(period_parts, ignore_index=True)
    result: dict[str, Any] = {
        "metrics": stateful_summary(all_periods),
        "period_component_sums": {
            "gross_holding_return_sum": float(all_periods["gross_return"].sum()),
            "funding_contribution_sum": float(all_periods["funding_return"].sum()),
            "transaction_cost_sum": float(all_periods["transaction_cost"].sum()),
            "turnover_sum": float(
                all_periods["turnover"].sum() + all_periods["final_unwind_turnover"].sum()
            ),
            "net_return_sum": float(all_periods["net_return"].sum()),
        },
        "folds": folds,
        "periods": all_periods,
    }
    if attribute:
        result["components"] = pd.concat(component_parts, ignore_index=True)
    return result


def _failure_decomposition(frame: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame]:
    baseline: dict[int, dict[str, Any]] = {}
    for cost in (0, 10, 20):
        baseline[cost] = _replay_scope(
            frame, BASELINE, held_out=True, round_trip_cost_bps=float(cost), attribute=(cost == 10)
        )
    selection0 = _replay_scope(
        frame, BASELINE, held_out=False, round_trip_cost_bps=0.0, attribute=False
    )
    selection10 = _replay_scope(
        frame, BASELINE, held_out=False, round_trip_cost_bps=10.0, attribute=False
    )
    candidate10 = _replay_scope(
        frame, V10_CANDIDATE, held_out=True, round_trip_cost_bps=10.0, attribute=False
    )
    candidate20 = _replay_scope(
        frame, V10_CANDIDATE, held_out=True, round_trip_cost_bps=20.0, attribute=False
    )
    components = baseline[10]["components"]

    fold_rows = []
    for index, fold_row in enumerate(baseline[10]["folds"]):
        fold = int(fold_row["fold"])
        fold_rows.append(
            {
                "fold": fold,
                "rows": fold_row["rows"],
                "net_0bps": baseline[0]["folds"][index]["metrics"]["net_return"],
                "net_10bps": fold_row["metrics"]["net_return"],
                "net_20bps": baseline[20]["folds"][index]["metrics"]["net_return"],
                "sharpe_10bps": fold_row["metrics"]["sharpe"],
                "components_10bps": fold_row["components"],
                "gross_edge_before_cost_positive": bool(
                    baseline[0]["folds"][index]["metrics"]["net_return"] > 0.0
                ),
            }
        )

    grouped = {
        "by_fold_symbol": _group_components(components, ["fold", "symbol"]),
        "by_fold_side": _group_components(components, ["fold", "side"]),
        "by_fold_action": _group_components(components, ["fold", "action_type"]),
        "by_fold_trend": _group_components(components, ["fold", "trend_state"]),
        "by_fold_side_trend": _group_components(components, ["fold", "side", "trend_state"]),
    }
    payload = {
        "schema_version": "v11-failure-decomposition-1",
        "evidence_class": "OBSERVED_V10_HELDOUT_DIAGNOSTIC_ONLY",
        "performance_trial_count_after_diagnostic": 870,
        "trial_871_consumed": False,
        "baseline_h12": {
            "aggregate": {
                "net_0bps": baseline[0]["metrics"]["net_return"],
                "net_10bps": baseline[10]["metrics"]["net_return"],
                "net_20bps": baseline[20]["metrics"]["net_return"],
                "sharpe_10bps": baseline[10]["metrics"]["sharpe"],
                "components_10bps": baseline[10]["period_component_sums"],
            },
            "folds": fold_rows,
            "selection_reference": {
                "aggregate_net_0bps": selection0["metrics"]["net_return"],
                "aggregate_net_10bps": selection10["metrics"]["net_return"],
                "folds": [
                    {
                        "fold": int(row0["fold"]),
                        "net_0bps": row0["metrics"]["net_return"],
                        "net_10bps": row10["metrics"]["net_return"],
                    }
                    for row0, row10 in zip(
                        selection0["folds"], selection10["folds"], strict=True
                    )
                ],
            },
            "grouped_components_10bps": grouped,
        },
        "trial_870_candidate_reference": {
            "net_10bps": candidate10["metrics"]["net_return"],
            "net_20bps": candidate20["metrics"]["net_return"],
            "sharpe_10bps": candidate10["metrics"]["sharpe"],
        },
        "interpretation_rule": {
            "alpha_failure": "H12 0bps held-out economics are non-positive before transaction costs.",
            "cost_failure": "H12 0bps economics are positive but become non-positive after realistic transaction costs.",
            "regime_instability": "Temporal folds materially disagree on pre-cost economic sign/magnitude.",
            "timing_failure": "Diagnosed separately in signal_decay.json; no unsupported delay is fabricated.",
        },
        "live_authorization": "LIVE_NOT_AUTHORIZED",
    }
    return payload, components


def _regime_localization(components: pd.DataFrame) -> dict[str, Any]:
    dimensions = [
        "side",
        "trend_state",
        "vol_state",
        "activity_state",
        "funding_state",
        "global_session",
        "action_type",
    ]
    summaries = {dimension: _group_components(components, ["fold", dimension]) for dimension in dimensions}
    for dimension in (
        "trend_state",
        "vol_state",
        "activity_state",
        "funding_state",
        "global_session",
        "action_type",
    ):
        summaries[f"side_x_{dimension}"] = _group_components(
            components, ["fold", "side", dimension]
        )

    contrasts: list[dict[str, Any]] = []
    for dimension in dimensions + ["side_x_trend_state"]:
        keys = ["side", "trend_state"] if dimension == "side_x_trend_state" else [dimension]
        table = pd.DataFrame(summaries[dimension])
        if table.empty:
            continue
        for values, group in table.groupby(keys, dropna=False):
            values = values if isinstance(values, tuple) else (values,)
            by_fold = {int(row.fold): row for row in group.itertuples(index=False)}
            if 1 not in by_fold or not ({0, 2} & set(by_fold)):
                continue
            others = [by_fold[f] for f in (0, 2) if f in by_fold]
            fold1 = by_fold[1]
            contrasts.append(
                {
                    "dimension": dimension,
                    "regime": {key: value for key, value in zip(keys, values, strict=True)},
                    "fold1_rows": int(fold1.rows),
                    "fold1_gross_sum": float(fold1.gross_holding_return_sum),
                    "fold1_net_sum": float(fold1.net_component_sum),
                    "fold1_gross_per_row": float(fold1.gross_per_row),
                    "fold1_net_per_row": float(fold1.net_per_row),
                    "other_folds_mean_gross_per_row": float(
                        np.mean([row.gross_per_row for row in others])
                    ),
                    "other_folds_mean_net_per_row": float(np.mean([row.net_per_row for row in others])),
                    "fold1_minus_others_gross_per_row": float(
                        fold1.gross_per_row - np.mean([row.gross_per_row for row in others])
                    ),
                    "fold1_minus_others_net_per_row": float(
                        fold1.net_per_row - np.mean([row.net_per_row for row in others])
                    ),
                    "other_fold_net_signs": [int(np.sign(row.net_component_sum)) for row in others],
                }
            )
    contrasts.sort(key=lambda row: row["fold1_minus_others_gross_per_row"])

    side_trend = pd.DataFrame(summaries["side_x_trend_state"])
    fold1 = side_trend.loc[side_trend["fold"] == 1].copy()
    fold1 = fold1.sort_values("gross_holding_return_sum")
    broadness = {}
    for dimension in (
        "trend_state", "vol_state", "activity_state", "global_session"
    ):
        table = pd.DataFrame(summaries[f"side_x_{dimension}"])
        long1 = table.loc[(table["fold"] == 1) & (table["side"] == "LONG")].copy()
        broadness[dimension] = {
            "states": int(len(long1)),
            "negative_gross_states": int((long1["gross_holding_return_sum"] < 0).sum()),
            "all_long_states_negative_gross": bool(
                len(long1) and (long1["gross_holding_return_sum"] < 0).all()
            ),
        }
    return {
        "schema_version": "v11-regime-localization-1",
        "evidence_class": "OBSERVED_V10_HELDOUT_DIAGNOSTIC_ONLY",
        "causal_state_note": "vol_state/activity_state/global_session are rebuilt with the existing causal add_session_state helper; legacy completed-log tercile convenience labels are not used.",
        "summaries": summaries,
        "fold1_contrasts_ranked_by_gross_per_row": contrasts,
        "fold1_side_trend_ranked": fold1.to_dict("records"),
        "fold1_long_failure_broadness": broadness,
        "performance_trial_count_after_diagnostic": 870,
        "trial_871_consumed": False,
        "live_authorization": "LIVE_NOT_AUTHORIZED",
    }


def _delay_scope(frame: pd.DataFrame, *, label: str) -> dict[str, Any]:
    period0_parts: list[pd.DataFrame] = []
    period10_parts: list[pd.DataFrame] = []
    folds: list[dict[str, Any]] = []
    wrong_total = 0
    decision_total = 0
    for fold in sorted(int(v) for v in frame["fold"].dropna().unique()):
        part = _partition(frame, fold, held_out=True)
        p0, _, m0 = _replay_fold(part, BASELINE, round_trip_cost_bps=0.0)
        p10, decisions, m10 = _replay_fold(part, BASELINE, round_trip_cost_bps=10.0)
        wrong = _wrong_side_count(part, decisions, round_trip_cost_bps=10.0)
        wrong_total += wrong
        decision_total += len(decisions)
        period0_parts.append(p0)
        period10_parts.append(p10)
        folds.append(
            {
                "fold": fold,
                "net_0bps": m0["net_return"],
                "net_10bps": m10["net_return"],
                "gross_holding_return_sum": float(p10["gross_return"].sum()),
                "funding_contribution_sum": float(p10["funding_return"].sum()),
                "wrong_side_count": int(wrong),
                "decision_rows": int(len(decisions)),
                "wrong_side_rate": float(wrong / len(decisions)) if len(decisions) else None,
            }
        )
    p0all = pd.concat(period0_parts, ignore_index=True)
    p10all = pd.concat(period10_parts, ignore_index=True)
    return {
        "label": label,
        "aggregate": {
            "net_0bps": stateful_summary(p0all)["net_return"],
            "net_10bps": stateful_summary(p10all)["net_return"],
            "gross_holding_return_sum": float(p10all["gross_return"].sum()),
            "funding_contribution_sum": float(p10all["funding_return"].sum()),
            "wrong_side_count": int(wrong_total),
            "decision_rows": int(decision_total),
            "wrong_side_rate": float(wrong_total / decision_total) if decision_total else None,
        },
        "folds": folds,
    }


def _signal_decay(frame: pd.DataFrame, delayed: pd.DataFrame) -> dict[str, Any]:
    instant = _delay_scope(frame, label="0m")
    delay60 = _delay_scope(delayed, label="60m")
    instant0 = float(instant["aggregate"]["net_0bps"])
    delay0 = float(delay60["aggregate"]["net_0bps"])
    instant_fold_signs = [int(np.sign(row["net_0bps"])) for row in instant["folds"]]
    delayed_fold_signs = [int(np.sign(row["net_0bps"])) for row in delay60["folds"]]
    if instant0 <= 0.0 and delay0 <= 0.0:
        classification = "NO_MEANINGFUL_EDGE"
    elif len(set(instant_fold_signs + delayed_fold_signs)) > 1:
        classification = "REGIME_DEPENDENT_HALF_LIFE"
    elif instant0 > 0.0 and delay0 <= 0.0:
        classification = "SHORT_HALF_LIFE"
    else:
        classification = "LONG_HALF_LIFE"
    return {
        "schema_version": "v11-signal-decay-1",
        "evidence_class": "OBSERVED_V10_HELDOUT_DIAGNOSTIC_ONLY",
        "supported_delays_minutes": [0, 60],
        "unsupported_requested_delays_minutes": [15, 30, 120, 240],
        "unsupported_delay_note": "Only the inherited 0m panel and +1h causal delayed decision log exist; no synthetic intermediate/longer delay is fabricated.",
        "instant": instant,
        "delay_60m": delay60,
        "classification": classification,
        "aggregate_delta_60m_minus_0m": {
            "net_0bps": delay0 - instant0,
            "net_10bps": float(delay60["aggregate"]["net_10bps"])
            - float(instant["aggregate"]["net_10bps"]),
            "gross_holding_return_sum": float(delay60["aggregate"]["gross_holding_return_sum"])
            - float(instant["aggregate"]["gross_holding_return_sum"]),
        },
        "performance_trial_count_after_diagnostic": 870,
        "trial_871_consumed": False,
        "live_authorization": "LIVE_NOT_AUTHORIZED",
    }


def _root_cause_verdict(
    failure: dict[str, Any], regime: dict[str, Any], decay: dict[str, Any]
) -> dict[str, Any]:
    aggregate = failure["baseline_h12"]["aggregate"]
    folds = failure["baseline_h12"]["folds"]
    net0 = float(aggregate["net_0bps"])
    net10 = float(aggregate["net_10bps"])
    fold0 = {int(row["fold"]): row for row in folds}
    positive_pre_cost_folds = sum(float(row["net_0bps"]) > 0.0 for row in folds)

    if net0 <= 0.0:
        dominant = "ALPHA_FAILURE"
        shortest = "Do not add another H12 filter. The directional core needs materially new causal evidence/replacement before another performance trial."
    elif net10 <= 0.0:
        dominant = "COST_FAILURE"
        shortest = "Reuse existing no-trade-band machinery to test whether small rebalances are uneconomic."
    elif decay["classification"] == "SHORT_HALF_LIFE":
        dominant = "TIMING_FAILURE"
        shortest = "Test one causal horizon/action policy change; do not add a forecasting family."
    else:
        dominant = "REGIME_INSTABILITY"
        shortest = "Test one economically interpretable causal regime interaction only if development evidence is stable."

    secondary: list[str] = []
    if 0 < positive_pre_cost_folds < len(folds):
        secondary.append("REGIME_INSTABILITY")
    if net10 < net0:
        secondary.append("COST_FAILURE")
    if decay["classification"] in {"SHORT_HALF_LIFE", "REGIME_DEPENDENT_HALF_LIFE"}:
        secondary.append("TIMING_FAILURE")
    secondary = [item for item in dict.fromkeys(secondary) if item != dominant]

    fold1 = fold0.get(1, {})
    fold1_contrasts = regime["fold1_contrasts_ranked_by_gross_per_row"][:10]
    return {
        "schema_version": "v11-root-cause-verdict-1",
        "dominant_failure": dominant,
        "secondary_failures": secondary,
        "evidence": {
            "aggregate_h12_net_0bps": net0,
            "aggregate_h12_net_10bps": net10,
            "aggregate_h12_net_20bps": aggregate["net_20bps"],
            "aggregate_gross_holding_return_sum": aggregate["components_10bps"][
                "gross_holding_return_sum"
            ],
            "positive_pre_cost_temporal_folds": int(positive_pre_cost_folds),
            "fold_count": int(len(folds)),
            "fold1_net_0bps": fold1.get("net_0bps"),
            "fold1_net_10bps": fold1.get("net_10bps"),
            "fold1_selection_net_0bps": next(
                (
                    row["net_0bps"]
                    for row in failure["baseline_h12"]["selection_reference"]["folds"]
                    if int(row["fold"]) == 1
                ),
                None,
            ),
            "fold1_long_failure_broadness": regime["fold1_long_failure_broadness"],
            "signal_decay_classification": decay["classification"],
            "delay_60m_minus_0m_net_0bps": decay["aggregate_delta_60m_minus_0m"]["net_0bps"],
            "fold1_worst_regime_contrasts": fold1_contrasts,
        },
        "competing_explanation": "Execution cost and timing can worsen economics, but they are not the primary explanation when aggregate held-out H12 is already non-positive at 0bps.",
        "ruled_out": [
            "Pure cost-only failure" if net0 <= 0.0 else "Broad pre-cost alpha failure",
            "Trial-870 flat-trend scale rescue; trial 870 is observed and must not be retuned",
        ],
        "shortest_reasonable_next_intervention": shortest,
        "p5_selected_mechanism": "NONE",
        "p5_reason": "Fold-1 H12 LONG exposure loses across all observed causal trend/vol/activity/session states while the same directional side is useful in other folds; no single existing causal state safely identifies the temporal failure, and volatility/dispersion/flat-trend filters overlap prior rejected mechanisms.",
        "trial_871_authorized_by_this_verdict": False,
        "authorization_note": "P1-P4 diagnosis never authorizes performance access by itself; development gate, fixed candidate, methodology audit, council, and proven untouched evaluation evidence are still required.",
        "performance_trial_count_after_diagnostic": 870,
        "trial_871_consumed": False,
        "live_authorization": "LIVE_NOT_AUTHORIZED",
    }


def _guard_no_trial_871() -> None:
    forbidden = [
        ART / "trial_871_access_started.json",
        ART / "trial_871_results.json",
        ART / "hypothesis_predeclaration_871.json",
    ]
    present = [str(path) for path in forbidden if path.exists()]
    if present:
        raise RuntimeError(f"V11 diagnostic refuses to run after trial-871 state exists: {present}")


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
    args = parser.parse_args()

    _guard_no_trial_871()
    frame = _load(args.panel)
    delayed = _load(args.delay)
    failure, components = _failure_decomposition(frame)
    regime = _regime_localization(components)
    decay = _signal_decay(frame, delayed)
    verdict = _root_cause_verdict(failure, regime, decay)
    _write_json("failure_decomposition.json", failure)
    _write_json("regime_localization.json", regime)
    _write_json("signal_decay.json", decay)
    _write_json("root_cause_verdict.json", verdict)
    _guard_no_trial_871()
    print(json.dumps(_jsonable(verdict), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
