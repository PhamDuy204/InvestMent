from __future__ import annotations

import pandas as pd

from scripts.build_v8_execution_panel import (
    build_execution_panel,
    candidate_feature_columns,
)


def _decision_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "decision_timestamp": ["2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z"],
            "fold": [0, 0],
            "symbol": ["BTCUSDT", "ETHUSDT"],
            "previous_weight": [0.0, 0.2],
            "target_weight": [0.5, 0.1],
            "holding_return_label": [0.03, -0.01],
            "funding_sum_label": [0.0, 0.0],
        }
    )


def test_build_execution_panel_is_one_to_one_and_causal() -> None:
    immediate = _decision_rows()
    delayed = immediate[["decision_timestamp", "symbol", "holding_return_label", "funding_sum_label"]].copy()
    delayed["holding_return_label"] = [0.01, -0.02]
    hourly = pd.DataFrame(
        {
            "decision_timestamp": immediate["decision_timestamp"],
            "symbol": immediate["symbol"],
            "feature_cutoff": ["2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z"],
            "lag_return_1h": [0.01, -0.02],
            "lag_quote_volume": [1_000_000.0, 2_000_000.0],
        }
    )
    basis = pd.DataFrame(
        {
            "decision_timestamp": immediate["decision_timestamp"],
            "symbol": immediate["symbol"],
            "lag_rv12": [0.02, 0.03],
        }
    )

    panel = build_execution_panel(immediate, delayed, hourly, basis)

    assert len(panel) == len(immediate)
    assert not panel.duplicated(["decision_timestamp", "symbol"]).any()
    assert panel[["log_impact_1h", "lag_rv12"]].notna().all(axis=1).all()
    cutoff = pd.to_datetime(panel["feature_cutoff"], utc=True)
    decision = pd.to_datetime(panel["decision_timestamp"], utc=True)
    assert (cutoff <= decision).all()


def test_candidate_features_exclude_outcome_and_oracle_columns() -> None:
    features = candidate_feature_columns()

    assert features == ["lag_rv12", "log_impact_1h"]
    assert not any("future" in column or "oracle" in column or "label" in column for column in features)
