import json

import numpy as np
import pandas as pd

from crypto_research.stress_v7 import run_v7_stress_suite


def _account_inputs():
    timestamps = pd.date_range("2026-01-01T00:00Z", periods=13, freq="h")
    price = np.linspace(100.0, 102.0, len(timestamps))
    periods = pd.DataFrame(
        {
            "entry_timestamp": [timestamps[0]],
            "exit_timestamp": [timestamps[-1]],
            "weights_json": [json.dumps({"A": 0.5})],
            "gross_exposure": [0.5],
        }
    )
    market = pd.DataFrame(
        {
            "timestamp": timestamps,
            "symbol": ["A"] * len(timestamps),
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "funding_event_rate": [0.0] * len(timestamps),
        }
    )
    return periods, market


def test_v7_stress_suite_has_required_named_scenarios():
    periods, market = _account_inputs()
    result = run_v7_stress_suite(periods, market)
    assert set(result) == {
        "base_10bps",
        "cost_20bps",
        "delay_1h",
        "funding_x3",
        "slippage_5bps_one_way",
        "maintenance_2pct",
        "maintenance_5pct",
        "correlation_one_adverse_shock",
    }
    assert result["base_10bps"]["leverage_multiplier"] == 1
    assert result["cost_20bps"]["round_trip_cost_bps"] == 20.0
    assert result["funding_x3"]["funding_multiplier"] == 3.0
    assert result["slippage_5bps_one_way"]["slippage_bps_one_way"] == 5.0
    assert result["delay_1h"]["status"] == "NOT_EVALUATED_NO_DELAY_PERIODS"


def test_v7_stress_suite_evaluates_supplied_delay_schedule():
    periods, market = _account_inputs()
    delayed = periods.copy()
    delayed["entry_timestamp"] = delayed["entry_timestamp"] + pd.Timedelta(hours=1)
    delayed["exit_timestamp"] = delayed["exit_timestamp"]
    result = run_v7_stress_suite(periods, market, delay_periods=delayed)
    assert result["delay_1h"]["status"] == "EVALUATED"
    assert result["delay_1h"]["round_trip_cost_bps"] == 10.0
