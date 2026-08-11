import json

import numpy as np
import pandas as pd
import pytest

from crypto_research.reliability_v7 import ReliabilityGateConfig
from crypto_research.run_v6 import replay_weight_overlay
from crypto_research.run_v7 import (
    attribute_candidate_errors,
    replay_v7_reliability,
    run_v7_first_line,
    split_selection_evaluation,
)


def _toy_log():
    return pd.DataFrame(
        {
            "decision_timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00Z",
                    "2026-01-01T00:00Z",
                    "2026-01-01T12:00Z",
                    "2026-01-01T12:00Z",
                ]
            ),
            "symbol": ["A", "B", "A", "B"],
            "previous_weight": [0.0, 0.0, 0.0, 0.0],
            "target_weight": [0.2, -0.2, 0.2, -0.2],
            "holding_return_label": [0.02, -0.01, -0.03, 0.01],
            "funding_sum_label": [0.0, 0.0, 0.0, 0.0],
            "effective_score": [0.01, -0.01, 0.01, -0.01],
            "qh_order_imbalance": [0.0, 0.0, 0.0, 0.0],
            "dispersion_iqr": [0.01, 0.01, 0.01, 0.01],
        }
    )


def _first_line_inputs():
    times = pd.date_range("2026-01-01", periods=12, freq="12h", tz="UTC")
    rows = []
    qh_rows = []
    for index, timestamp in enumerate(times):
        fold = index // 4
        for symbol, side in (("A", 1.0), ("B", -1.0)):
            score = 0.04 * side
            realized = 0.01 if index % 3 else -0.015
            rows.append(
                {
                    "decision_timestamp": timestamp,
                    "symbol": symbol,
                    "previous_weight": 0.0,
                    "target_weight": 0.20 * side,
                    "holding_return_label": realized * side,
                    "funding_sum_label": 0.0,
                    "effective_score": score,
                    "realized_net_contribution": realized * 0.20,
                    "error_class": "WRONG_SIDE" if realized < 0 else "CORRECT",
                    "fold": fold,
                }
            )
            qh_rows.append(
                {
                    "decision_timestamp": timestamp,
                    "symbol": symbol,
                    "qh_order_imbalance": score * 5.0,
                    "qh_abs_order_imbalance": abs(score * 5.0),
                    "qh_trade_count": 5,
                }
            )
    decisions = pd.DataFrame(rows)
    qh = pd.DataFrame(qh_rows)
    dispersion = pd.DataFrame(
        {
            "decision_timestamp": times,
            "dispersion_iqr": [0.01 + 0.001 * index for index in range(len(times))],
            "eligible_symbol_count": [2] * len(times),
        }
    )
    return decisions, qh, dispersion


def test_disabled_v7_gates_match_v6_control_replay():
    log = _toy_log()
    v6_periods, _, v6_metrics = replay_weight_overlay(
        log,
        scale_fn=lambda row: 1.0,
        round_trip_cost_bps=10.0,
    )
    v7_periods, _, v7_metrics = replay_v7_reliability(
        log,
        ReliabilityGateConfig(None, None, None, False),
        round_trip_cost_bps=10.0,
    )
    for column in (
        "gross_return",
        "funding_return",
        "transaction_cost",
        "net_return",
        "turnover",
        "gross_exposure",
        "net_exposure",
    ):
        np.testing.assert_allclose(v7_periods[column], v6_periods[column], atol=1e-14, rtol=0.0)
    for key in ("net_return", "sharpe", "max_drawdown", "turnover", "transaction_cost"):
        assert v7_metrics[key] == pytest.approx(v6_metrics[key], abs=1e-14)


def test_v7_replay_uses_candidate_drifted_state_not_baseline_previous_column():
    log = pd.DataFrame(
        {
            "decision_timestamp": pd.to_datetime(["2026-01-01T00:00Z", "2026-01-01T12:00Z"]),
            "symbol": ["A", "A"],
            "previous_weight": [0.0, 0.0],
            "target_weight": [0.2, 0.3],
            "holding_return_label": [0.10, 0.0],
            "funding_sum_label": [0.0, 0.0],
            "effective_score": [0.05, 0.05],
            "qh_order_imbalance": [0.0, 0.0],
            "dispersion_iqr": [0.0, 0.05],
        }
    )
    cfg = ReliabilityGateConfig(None, 0.01, None, False, high_dispersion_scale=0.5)
    _, decisions, _ = replay_v7_reliability(log, cfg, round_trip_cost_bps=0.0)
    second = decisions.iloc[1]
    expected_drift = 0.2 * 1.10 / 1.02
    expected_target = expected_drift + 0.5 * (0.3 - expected_drift)
    assert second["current_weight"] == pytest.approx(expected_drift)
    assert second["current_weight"] != log.iloc[1]["previous_weight"]
    assert second["proposed_target_weight"] == pytest.approx(expected_target)


def test_split_selection_evaluation_is_chronological():
    decisions, _, _ = _first_line_inputs()
    selection, evaluation = split_selection_evaluation(decisions, selection_fraction=0.70)
    assert selection["decision_timestamp"].max() < evaluation["decision_timestamp"].min()
    assert set(selection.index).isdisjoint(set(evaluation.index))


def test_first_line_sequence_starts_at_858_and_does_not_spend_unused_combination(tmp_path):
    decisions, qh, dispersion = _first_line_inputs()
    result = run_v7_first_line(decisions, qh, dispersion, artifact_root=tmp_path)
    registry = pd.read_csv(tmp_path / "experiment_registry.csv")
    assert registry.iloc[0]["trial_number"] == 858
    assert registry["hypothesis"].tolist()[:4] == [
        "exact_v6_control",
        "H1_qh_conflict_veto",
        "H2_high_dispersion_gate",
        "H3_weak_edge_veto",
    ]
    combination = json.loads((tmp_path / "combination_results.json").read_text())
    if len(result["promoted"]) < 2:
        assert combination["status"] == "NOT_RUN_FEWER_THAN_TWO_PROMOTED"
        assert len(registry) == 4
    assert result["trial_count_after"] == 857 + len(registry)


def test_error_attribution_reports_counts_and_economic_bps():
    timestamp = pd.Timestamp("2026-01-01T00:00Z")
    base = pd.DataFrame(
        {
            "decision_timestamp": [timestamp, timestamp],
            "symbol": ["A", "B"],
            "previous_weight": [0.0, 0.0],
            "target_weight": [0.2, 0.2],
            "holding_return_label": [-0.02, 0.02],
            "funding_sum_label": [0.0, 0.0],
        }
    )
    candidate = pd.DataFrame(
        {
            "decision_timestamp": [timestamp, timestamp],
            "symbol": ["A", "B"],
            "current_weight": [0.0, 0.0],
            "proposed_target_weight": [0.0, 0.1],
        }
    )
    result = attribute_candidate_errors(base, candidate, round_trip_cost_bps=10.0)
    wrong = result["by_error"]["FALSE_ENTER"]
    assert wrong["baseline_count"] == 1
    assert wrong["candidate_count"] == 0
    assert wrong["count_delta"] == -1
    assert wrong["avoided_loss_bps"] > 0.0
    correct = result["by_error"]["CORRECT"]
    assert correct["lost_correct_trade_bps"] > 0.0
    assert result["net_bps_effect"] == pytest.approx(
        sum(bucket["net_bps_effect"] for bucket in result["by_error"].values())
    )
