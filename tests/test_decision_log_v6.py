import pandas as pd

from crypto_research.decision_diagnostics import (
    V6_CAUSAL_COLUMNS,
    V6_LABEL_COLUMNS,
    enrich_v6_decision_log,
    summarize_v6_errors,
)


def test_oracle_fields_are_label_only():
    assert not set(V6_CAUSAL_COLUMNS) & set(V6_LABEL_COLUMNS)
    assert "oracle_direction" in V6_LABEL_COLUMNS
    assert "oracle_direction" not in V6_CAUSAL_COLUMNS
    assert "realized_return" in V6_LABEL_COLUMNS


def test_enrichment_keeps_future_fields_posthoc_only():
    base = pd.DataFrame(
        {
            "decision_timestamp": pd.to_datetime(["2026-01-01T00:00Z"]),
            "symbol": ["BTCUSDT"],
            "previous_weight": [0.2],
            "target_weight": [0.2],
            "effective_score": [0.01],
            "error_class": ["LATE_EXIT"],
        }
    )
    controller = pd.DataFrame(
        {
            "decision_timestamp": pd.to_datetime(["2026-01-01T00:00Z"]),
            "symbol": ["BTCUSDT"],
            "decision": ["REDUCE"],
            "proposed_target_weight": [0.1],
            "chosen_horizon": [60],
            "effective_leverage": [0.5],
            "execution_mode": ["MARKET"],
            "burst_probability": [0.8],
            "vol_state": ["high"],
            "vn_session": ["VN_08_17"],
            "flow_state": ["neutral"],
            "funding": [0.0],
            "trend_state": ["up"],
            "correlation_state": ["high"],
            "account_equity": [1.0],
            "drawdown": [0.02],
            "margin_buffer": [0.6],
        }
    )
    outcomes = pd.DataFrame(
        {
            "decision_timestamp": pd.to_datetime(["2026-01-01T00:00Z"]),
            "symbol": ["BTCUSDT"],
            "realized_return": [-0.02],
            "oracle_direction": [-1],
            "oracle_exit": [True],
            "execution_miss": [False],
            "slippage_damage": [True],
            "leverage_damage": [False],
            "liquidation": [False],
        }
    )
    out = enrich_v6_decision_log(base, controller, outcomes)
    assert out.loc[0, "decision"] == "REDUCE"
    assert out.loc[0, "SLIPPAGE_DAMAGE"]
    assert out.loc[0, "realized_return"] == -0.02
    assert set(V6_LABEL_COLUMNS).issubset(out.columns)


def test_error_summary_reports_before_and_after_counts():
    frame = pd.DataFrame(
        {
            "symbol": ["BTCUSDT", "ETHUSDT"],
            "vn_session": ["VN_08_17", "VN_17_08"],
            "vol_state": ["low", "high"],
            "error_class": ["WRONG_SIDE", "LATE_EXIT"],
            "v6_error_class": ["CORRECT", "LATE_EXIT"],
        }
    )
    summary = summarize_v6_errors(frame)
    assert summary["before"]["WRONG_SIDE"] == 1
    assert summary["after"]["LATE_EXIT"] == 1
