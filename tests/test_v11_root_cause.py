from __future__ import annotations

import pandas as pd
import pytest

from crypto_research.reliability_v7 import ReliabilityGateConfig
from crypto_research.run_v7 import replay_v7_reliability
from scripts.run_v11_root_cause import attribute_replay_components


def test_attribute_replay_components_matches_shared_replay_totals() -> None:
    source = pd.DataFrame(
        [
            {
                "decision_timestamp": "2026-01-01T00:00:00Z",
                "fold": 0,
                "symbol": "A",
                "action": "ENTER",
                "target_weight": 0.5,
                "effective_score": 1.0,
                "holding_return_label": 0.10,
                "funding_sum_label": 0.01,
                "trend_state": "up",
                "realized_vol_24": 0.2,
                "trade_count_z24": 0.1,
                "funding_state": "neutral",
                "utc_hour": 0,
            },
            {
                "decision_timestamp": "2026-01-01T00:00:00Z",
                "fold": 0,
                "symbol": "B",
                "action": "ENTER",
                "target_weight": -0.5,
                "effective_score": -1.0,
                "holding_return_label": -0.04,
                "funding_sum_label": -0.02,
                "trend_state": "down",
                "realized_vol_24": 0.3,
                "trade_count_z24": -0.1,
                "funding_state": "neutral",
                "utc_hour": 0,
            },
        ]
    )
    config = ReliabilityGateConfig(None, None, None, False)
    periods, decisions, _ = replay_v7_reliability(source, config, round_trip_cost_bps=10.0)

    rows = attribute_replay_components(source, decisions, periods, round_trip_cost_bps=10.0)

    assert set(rows["action_type"]) == {"ENTER", "FINAL_UNWIND"}
    assert rows.loc[~rows["is_final_unwind"], "gross_holding_return"].sum() == pytest.approx(
        periods["gross_return"].sum()
    )
    assert rows["funding_contribution"].sum() == pytest.approx(periods["funding_return"].sum())
    assert rows["transaction_cost"].sum() == pytest.approx(periods["transaction_cost"].sum())
    assert rows["turnover"].sum() == pytest.approx(
        periods["turnover"].sum() + periods["final_unwind_turnover"].sum()
    )
    assert rows["net_component"].sum() == pytest.approx(periods["net_return"].sum())
    assert set(rows.loc[~rows["is_final_unwind"], "global_session"]) == {"ASIA"}
