import pandas as pd

from crypto_research.execution_v5 import ResearchOrder, simulate_order


def _bars():
    return pd.DataFrame({"timestamp": pd.date_range("2026-01-01", periods=4, freq="min", tz="UTC"), "open": [100.0, 101.0, 103.0, 102.0], "high": [101.0, 104.0, 104.0, 103.0], "low": [99.0, 100.0, 101.0, 98.0], "close": [100.5, 103.0, 102.0, 99.0]})


def test_market_next_open_with_adverse_slippage():
    fill = simulate_order(ResearchOrder("MARKET", side=1), _bars(), slippage_bps=10.0)
    assert fill.filled and fill.fill_price == 100.1 and not fill.maker


def test_limit_and_post_only_are_conservative():
    assert not simulate_order(ResearchOrder("LIMIT", side=1, limit_price=97.0), _bars()).filled
    assert not simulate_order(ResearchOrder("LIMIT", side=1, limit_price=98.0), _bars(), passive_cross_bps=20.0).filled
    post = simulate_order(ResearchOrder("POST_ONLY", side=1, limit_price=101.0), _bars())
    assert not post.filled and post.reason == "POST_ONLY_MARKETABLE_CANCEL"


def test_trigger_and_trailing_use_adverse_causal_fills():
    trigger = simulate_order(ResearchOrder("TRIGGER_MARKET", side=1, trigger_price=102.0), _bars(), slippage_bps=10.0)
    assert trigger.filled and trigger.fill_price >= 102.0
    trail = simulate_order(ResearchOrder("TRAILING_STOP", side=-1, trailing_fraction=0.02, initial_reference=101.0), _bars())
    assert trail.filled and trail.fill_price == 101.92
