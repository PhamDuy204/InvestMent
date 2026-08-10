import numpy as np

from crypto_research.leverage_v3 import simulate_cross_margin_period


def test_exchange_leverage_changes_margin_capacity_not_position_pnl():
    kwargs = dict(initial_equity=1000.0, weights=np.array([0.5]), entry_prices=np.array([100.0]), mark_prices=[np.array([110.0])], maintenance_margin_rate=0.005, round_trip_bps=0.0)
    a = simulate_cross_margin_period(exchange_leverage=2.0, **kwargs)
    b = simulate_cross_margin_period(exchange_leverage=20.0, **kwargs)
    assert a.final_equity == b.final_equity == 1050.0


def test_adverse_move_can_liquidate_high_notional_position():
    result = simulate_cross_margin_period(initial_equity=1000.0, weights=np.array([10.0]), entry_prices=np.array([100.0]), mark_prices=[np.array([90.0])], exchange_leverage=20.0, maintenance_margin_rate=0.005, round_trip_bps=0.0)
    assert result.liquidated


def test_funding_sign_long_vs_short():
    long = simulate_cross_margin_period(initial_equity=1000.0, weights=np.array([0.5]), entry_prices=np.array([100.0]), mark_prices=[np.array([100.0])], exchange_leverage=2.0, round_trip_bps=0.0, funding_rates=[np.array([0.001])])
    short = simulate_cross_margin_period(initial_equity=1000.0, weights=np.array([-0.5]), entry_prices=np.array([100.0]), mark_prices=[np.array([100.0])], exchange_leverage=2.0, round_trip_bps=0.0, funding_rates=[np.array([0.001])])
    assert long.final_equity < 1000.0
    assert short.final_equity > 1000.0
