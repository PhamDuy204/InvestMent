import pandas as pd

from crypto_research.v6_cycle import (
    REQUIRED_V6_ARTIFACTS,
    default_candidate_specs,
    merge_frozen_burst_event_state,
)


def test_required_artifact_contract_contains_user_requested_files():
    required = {
        "experiment_registry.csv",
        "integrated_controller_config.json",
        "session_state_analysis.json",
        "session_horizon_results.json",
        "trade_frequency_results.json",
        "decision_log.csv.gz",
        "final_report.md",
    }
    assert required.issubset(REQUIRED_V6_ARTIFACTS)


def test_default_weight_candidates_never_scale_above_baseline():
    for spec in default_candidate_specs():
        for key, value in spec.items():
            if key.endswith("_scale"):
                assert 0.0 <= float(value) <= 1.0


def test_burst_merge_is_backward_only_and_does_not_use_future_event():
    decisions = pd.DataFrame(
        {
            "decision_timestamp": pd.to_datetime(["2026-01-01T10:00Z", "2026-01-01T11:00Z"]),
            "symbol": ["BTCUSDT", "BTCUSDT"],
        }
    )
    events = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-01T09:45Z", "2026-01-01T10:01Z"]),
            "symbol": ["BTCUSDT", "BTCUSDT"],
            "burst_score": [3.0, 9.0],
        }
    )
    out = merge_frozen_burst_event_state(decisions, events, tolerance_minutes=60)
    first = out.loc[out["decision_timestamp"] == pd.Timestamp("2026-01-01T10:00Z")].iloc[0]
    assert first["burst_event_timestamp"] == pd.Timestamp("2026-01-01T09:45Z")
    assert first["burst_probability"] < 0.99
