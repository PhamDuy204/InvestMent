import pandas as pd
import pandas.testing as pdt

from crypto_research.reliability_v7 import ReliabilityGateConfig
from crypto_research.run_v7 import replay_v7_reliability


def _row(timestamp: str, fold: int, target: float, holding: float) -> dict[str, object]:
    return {
        "decision_timestamp": timestamp,
        "fold": fold,
        "symbol": "BTCUSDT",
        "target_weight": target,
        "holding_return_label": holding,
        "funding_sum_label": 0.0,
        "effective_score": 0.01,
    }


def test_replay_resets_and_unwinds_at_fold_boundaries() -> None:
    frame = pd.DataFrame([
        _row("2026-01-01T00:00:00Z", 0, 0.10, 0.02),
        _row("2026-01-01T12:00:00Z", 0, 0.05, -0.01),
        _row("2026-02-01T00:00:00Z", 1, -0.10, 0.03),
        _row("2026-02-01T12:00:00Z", 1, -0.05, -0.02),
    ])
    config = ReliabilityGateConfig(None, None, None, False)
    combined, _, _ = replay_v7_reliability(frame, config, round_trip_cost_bps=10.0)
    fold0, _, _ = replay_v7_reliability(frame.loc[frame["fold"] == 0], config, round_trip_cost_bps=10.0)
    fold1, _, _ = replay_v7_reliability(frame.loc[frame["fold"] == 1], config, round_trip_cost_bps=10.0)
    expected = pd.concat([fold0, fold1], ignore_index=True)
    columns = ["decision_timestamp", "net_return", "turnover", "transaction_cost", "rebalance_trade_count"]
    pdt.assert_frame_equal(
        combined[columns].reset_index(drop=True),
        expected[columns].reset_index(drop=True),
        check_exact=False,
        rtol=1e-12,
        atol=1e-12,
    )
