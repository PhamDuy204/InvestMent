import json

import numpy as np
import pandas as pd
import pytest

from crypto_research.leverage_v3 import simulate_cross_margin_period, simulate_weight_schedule


def test_exchange_leverage_changes_margin_capacity_not_position_pnl():
    kwargs = dict(
        initial_equity=1000.0,
        weights=np.array([0.5]),
        entry_prices=np.array([100.0]),
        mark_prices=[np.array([110.0])],
        maintenance_margin_rate=0.005,
        round_trip_bps=0.0,
    )
    a = simulate_cross_margin_period(exchange_leverage=2.0, **kwargs)
    b = simulate_cross_margin_period(exchange_leverage=20.0, **kwargs)
    assert a.final_equity == b.final_equity == 1050.0


def test_adverse_move_can_liquidate_high_notional_position():
    result = simulate_cross_margin_period(
        initial_equity=1000.0,
        weights=np.array([10.0]),
        entry_prices=np.array([100.0]),
        mark_prices=[np.array([90.0])],
        exchange_leverage=20.0,
        maintenance_margin_rate=0.005,
        round_trip_bps=0.0,
    )
    assert result.liquidated


def test_funding_sign_long_vs_short():
    long = simulate_cross_margin_period(
        initial_equity=1000.0,
        weights=np.array([0.5]),
        entry_prices=np.array([100.0]),
        mark_prices=[np.array([100.0])],
        exchange_leverage=2.0,
        round_trip_bps=0.0,
        funding_rates=[np.array([0.001])],
    )
    short = simulate_cross_margin_period(
        initial_equity=1000.0,
        weights=np.array([-0.5]),
        entry_prices=np.array([100.0]),
        mark_prices=[np.array([100.0])],
        exchange_leverage=2.0,
        round_trip_bps=0.0,
        funding_rates=[np.array([0.001])],
    )
    assert long.final_equity < 1000.0
    assert short.final_equity > 1000.0


def _schedule_inputs(two_periods: bool = False):
    timestamps = pd.date_range("2026-01-01T00:00Z", periods=25 if two_periods else 13, freq="h")
    close = np.linspace(100.0, 110.0, len(timestamps))
    market = pd.DataFrame(
        {
            "timestamp": timestamps,
            "symbol": ["A"] * len(timestamps),
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "funding_event_rate": [0.0] * len(timestamps),
        }
    )
    if not two_periods:
        periods = pd.DataFrame(
            {
                "entry_timestamp": [timestamps[0]],
                "exit_timestamp": [timestamps[-1]],
                "weights_json": [json.dumps({"A": 0.5})],
            }
        )
        return periods, market
    market.loc[:12, ["open", "high", "low", "close"]] = np.linspace(100.0, 110.0, 13)[:, None]
    market.loc[12:, ["open", "high", "low", "close"]] = np.linspace(110.0, 121.0, 13)[:, None]
    periods = pd.DataFrame(
        {
            "entry_timestamp": [timestamps[0], timestamps[12]],
            "exit_timestamp": [timestamps[12], timestamps[24]],
            "weights_json": [json.dumps({"A": 0.5}), json.dumps({"A": 0.5})],
        }
    )
    return periods, market


def test_weight_schedule_compounds_current_equity_without_return_times_leverage_shortcut():
    periods, market = _schedule_inputs()
    result = simulate_weight_schedule(
        periods=periods,
        market=market,
        initial_equity=1.0,
        leverage_multiplier=1.0,
        exchange_leverage_setting=20.0,
        maintenance_margin_rate=0.01,
        round_trip_cost_bps=0.0,
        slippage_bps=0.0,
        liquidation_fee_rate=0.005,
    )
    assert result["liquidated"] is False
    assert result["final_equity"] == pytest.approx(1.05)
    assert result["max_effective_leverage"] == pytest.approx(0.5)


def test_weight_schedule_rebalances_on_current_equity_across_periods():
    periods, market = _schedule_inputs(two_periods=True)
    result = simulate_weight_schedule(
        periods=periods,
        market=market,
        initial_equity=1.0,
        leverage_multiplier=1.0,
        exchange_leverage_setting=20.0,
        maintenance_margin_rate=0.01,
        round_trip_cost_bps=0.0,
        slippage_bps=0.0,
        liquidation_fee_rate=0.005,
    )
    assert result["final_equity"] == pytest.approx(1.1025)


def test_weight_schedule_positive_funding_costs_long_position():
    periods, market = _schedule_inputs()
    market.loc[market.index[-1], "funding_event_rate"] = 0.01
    funded = simulate_weight_schedule(
        periods=periods,
        market=market,
        initial_equity=1.0,
        leverage_multiplier=1.0,
        exchange_leverage_setting=20.0,
        maintenance_margin_rate=0.01,
        round_trip_cost_bps=0.0,
        slippage_bps=0.0,
        liquidation_fee_rate=0.005,
    )
    assert funded["funding_cashflow"] > 0.0
    assert funded["final_equity"] < 1.05


def test_weight_schedule_uses_intrabar_low_for_long_liquidation():
    periods, market = _schedule_inputs()
    market.loc[market.index[5], "low"] = 1.0
    result = simulate_weight_schedule(
        periods=periods,
        market=market,
        initial_equity=1.0,
        leverage_multiplier=10.0,
        exchange_leverage_setting=20.0,
        maintenance_margin_rate=0.01,
        round_trip_cost_bps=0.0,
        slippage_bps=0.0,
        liquidation_fee_rate=0.005,
    )
    assert result["liquidated"] is True
    assert result["liquidation_count"] == 1
    assert result["liquidation_timestamp"] == market.loc[market.index[5], "timestamp"]
