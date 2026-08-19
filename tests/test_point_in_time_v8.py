from __future__ import annotations

import pandas as pd
import pytest

from crypto_research.point_in_time_v8 import (
    causal_events_for_decision,
    validate_point_in_time_frame,
)


def _events() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "event_time": ["2026-01-01T09:00:00Z", "2026-01-01T11:00:00Z"],
            "published_at": ["2026-01-01T09:01:00Z", "2026-01-01T11:01:00Z"],
            "first_seen_at": ["2026-01-01T09:02:00Z", "2026-01-01T11:02:00Z"],
            "available_at": ["2026-01-01T09:02:00Z", "2026-01-01T11:02:00Z"],
            "decision_time": ["2026-01-01T10:00:00Z", "2026-01-01T12:00:00Z"],
            "source": ["official", "official"],
            "source_id": ["a", "b"],
            "symbol": ["BTCUSDT", "BTCUSDT"],
            "raw_value": [1.0, 2.0],
            "derived_value": [10.0, 20.0],
            "data_version": ["v1", "v1"],
            "checksum": ["x", "y"],
        }
    )


def test_validate_point_in_time_rejects_feature_available_after_its_decision() -> None:
    frame = _events()
    frame.loc[0, "available_at"] = "2026-01-01T10:01:00Z"

    with pytest.raises(ValueError, match="available_at"):
        validate_point_in_time_frame(frame)


def test_causal_events_ignore_future_rows_and_future_mutation() -> None:
    frame = _events()
    decision = pd.Timestamp("2026-01-01T10:00:00Z")

    before = causal_events_for_decision(frame, decision_time=decision, symbol="BTCUSDT")
    mutated = frame.copy()
    mutated.loc[1, "derived_value"] = 999999.0
    after = causal_events_for_decision(mutated, decision_time=decision, symbol="BTCUSDT")

    assert before[["source_id", "derived_value"]].to_dict("records") == [
        {"source_id": "a", "derived_value": 10.0}
    ]
    pd.testing.assert_frame_equal(before, after)


def test_causal_events_include_global_and_symbol_specific_rows_only() -> None:
    frame = pd.concat(
        [
            _events().iloc[[0]],
            _events().iloc[[0]].assign(source_id="global", symbol="global", derived_value=3.0),
            _events().iloc[[0]].assign(source_id="eth", symbol="ETHUSDT", derived_value=4.0),
        ],
        ignore_index=True,
    )

    result = causal_events_for_decision(
        frame,
        decision_time=pd.Timestamp("2026-01-01T10:00:00Z"),
        symbol="BTCUSDT",
    )

    assert set(result["source_id"]) == {"a", "global"}
