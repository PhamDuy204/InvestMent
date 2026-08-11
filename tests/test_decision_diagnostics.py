import pandas as pd

from crypto_research.decision_diagnostics import (
    build_decision_log,
    classify_decision,
    classify_error,
)


def test_classify_decision_actions():
    assert classify_decision(0.0, 0.2) == "ENTER"
    assert classify_decision(0.2, 0.0) == "EXIT"
    assert classify_decision(0.2, 0.2) == "HOLD"
    assert classify_decision(0.2, 0.3) == "REBALANCE"
    assert classify_decision(0.2, -0.2) == "FLIP"
    assert classify_decision(0.0, 0.0) == "NO_POSITION"


def test_posthoc_error_classes():
    assert classify_error(0.0, 0.2, holding_return=-0.02, funding_sum=0.0, round_trip_cost_bps=10.0) == "FALSE_ENTER"
    assert classify_error(0.2, -0.2, holding_return=0.02, funding_sum=0.0, round_trip_cost_bps=10.0) == "WRONG_SIDE"
    assert classify_error(0.0, 0.0, holding_return=0.02, funding_sum=0.0, round_trip_cost_bps=10.0) == "MISSED_ENTER"
    assert classify_error(0.2, 0.0, holding_return=0.02, funding_sum=0.0, round_trip_cost_bps=10.0) == "PREMATURE_EXIT"
    assert classify_error(0.2, 0.2, holding_return=-0.02, funding_sum=0.0, round_trip_cost_bps=10.0) == "LATE_EXIT"
    assert classify_error(0.2, 0.21, holding_return=0.001, funding_sum=0.0, round_trip_cost_bps=10.0) == "UNNECESSARY_REBALANCE"


def test_build_decision_log_expands_details_as_labels():
    periods = pd.DataFrame([{"decision_timestamp": pd.Timestamp("2026-01-01", tz="UTC"), "fold": 0, "decision_details_json": '{"A":{"eligible":true,"previous_weight":0.0,"target_weight":0.2,"delta_weight":0.2,"raw_score":0.01,"effective_score":0.01,"funding_rate_feature":0.0,"holding_return":-0.02,"funding_sum":0.0,"gross_contribution":-0.004,"funding_contribution":0.0}}'}])
    log = build_decision_log(periods, round_trip_cost_bps=10.0)
    assert log.iloc[0]["action"] == "ENTER"
    assert log.iloc[0]["error_class"] == "FALSE_ENTER"
    assert "oracle_action" in log.columns
    assert "holding_return_label" in log.columns
