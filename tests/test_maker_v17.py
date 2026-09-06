import sqlite3

import pytest

from crypto_research.maker_v17 import (
    DEFAULT_MAKER_FEE_BPS,
    conservative_fill_probability,
    maker_attempt_ev,
    multi_horizon_route_features,
    passive_limit_filled,
    record_fill_outcome,
)
from crypto_research.route_v16 import record_route_snapshots


def test_verified_maker_fee_defaults_are_never_above_taker_defaults():
    assert DEFAULT_MAKER_FEE_BPS["okx"] == 2.0
    assert DEFAULT_MAKER_FEE_BPS["bybit"] == 2.0
    assert DEFAULT_MAKER_FEE_BPS["bitget"] == 2.0
    assert DEFAULT_MAKER_FEE_BPS["kucoin"] == 2.0
    assert DEFAULT_MAKER_FEE_BPS["mexc"] == 6.0
    assert DEFAULT_MAKER_FEE_BPS["binance"] == 2.0
    assert DEFAULT_MAKER_FEE_BPS["gate"] == 2.0


def test_jeffreys_fill_probability_is_smoothed_and_conservative(tmp_path):
    db = tmp_path / "v17.sqlite"
    cold = conservative_fill_probability(db, "okx", "buy")
    assert cold["attempts"] == 0
    assert cold["posterior_mean"] == pytest.approx(0.5)
    assert 0.20 < cold["conservative_probability"] < 0.30

    for filled in [True, True, True, False]:
        record_fill_outcome(db, "okx", "buy", filled=filled)
    warm = conservative_fill_probability(db, "okx", "buy")
    assert warm["attempts"] == 4
    assert warm["fills"] == 3
    assert warm["posterior_mean"] == pytest.approx(3.5 / 5.0)
    assert 0.0 < warm["conservative_probability"] < warm["posterior_mean"]


def test_passive_fill_requires_later_opposite_quote_to_trade_through_limit():
    # Resting maker buy at 100 only fills when a later ask reaches/crosses 100.
    assert passive_limit_filled("buy", 100.0, {"bids": [[99.9, 2]], "asks": [[100.1, 3]]}) is False
    assert passive_limit_filled("buy", 100.0, {"bids": [[99.8, 2]], "asks": [[100.0, 3]]}) is True
    # Resting maker sell at 101 only fills when a later bid reaches/crosses 101.
    assert passive_limit_filled("sell", 101.0, {"bids": [[100.9, 2]], "asks": [[101.1, 3]]}) is False
    assert passive_limit_filled("sell", 101.0, {"bids": [[101.0, 2]], "asks": [[101.1, 3]]}) is True


def test_strict_paper_fill_requires_price_through_not_touch():
    touched_buy = {
        "bids": [[99.9, 1]],
        "asks": [[100.0, 1]],
        "received_at_ms": 1_001,
    }
    crossed_buy = {
        "bids": [[99.8, 1]],
        "asks": [[99.9, 1]],
        "received_at_ms": 1_001,
    }
    assert passive_limit_filled(
        "buy",
        100.0,
        touched_buy,
        placed_at_ms=1_000,
        strict_price_through=True,
    ) is False
    assert passive_limit_filled(
        "buy",
        100.0,
        crossed_buy,
        placed_at_ms=1_000,
        strict_price_through=True,
    ) is True

    touched_sell = {
        "bids": [[100.0, 1]],
        "asks": [[100.1, 1]],
        "received_at_ms": 1_001,
    }
    crossed_sell = {
        "bids": [[100.1, 1]],
        "asks": [[100.2, 1]],
        "received_at_ms": 1_001,
    }
    assert passive_limit_filled(
        "sell",
        100.0,
        touched_sell,
        placed_at_ms=1_000,
        strict_price_through=True,
    ) is False
    assert passive_limit_filled(
        "sell",
        100.0,
        crossed_sell,
        placed_at_ms=1_000,
        strict_price_through=True,
    ) is True


def test_strict_fill_accepts_risk_averse_public_trade_queue_depletion():
    later = {
        "bids": [[100.0, 4.0]],
        "asks": [[100.2, 4.0]],
        "received_at_ms": 1_010,
        "_public_trade_volume_by_side_price": {("sell", 100.0): 16.1},
    }
    common = dict(
        placed_at_ms=1_000,
        strict_price_through=True,
        queue_ahead_quantity=10.0,
        order_quantity=1.0,
        trade_volume_baseline=5.0,
    )
    assert passive_limit_filled("buy", 100.0, later, **common) is True
    # 10.9 base traded after placement is not enough to consume 10 ahead + our 1.
    later["_public_trade_volume_by_side_price"][("sell", 100.0)] = 15.9
    assert passive_limit_filled("buy", 100.0, later, **common) is False


def test_queue_depletion_never_uses_same_side_aggressor_or_cancellations():
    later = {
        "bids": [[100.0, 0.1]],  # visible queue disappeared; could be cancellations
        "asks": [[100.2, 4.0]],
        "received_at_ms": 1_010,
        "_public_trade_volume_by_side_price": {("buy", 100.0): 50.0, ("sell", 100.0): 2.0},
    }
    assert passive_limit_filled(
        "buy", 100.0, later, placed_at_ms=1_000, strict_price_through=True,
        queue_ahead_quantity=10.0, order_quantity=1.0, trade_volume_baseline=1.0,
    ) is False


def test_passive_fill_requires_post_order_snapshot_when_placement_time_is_supplied():
    touched = {
        "bids": [[99.8, 2]],
        "asks": [[100.0, 3]],
        "received_at_ms": 1_000,
    }

    assert passive_limit_filled("buy", 100.0, touched, placed_at_ms=1_000) is False
    assert passive_limit_filled(
        "buy",
        100.0,
        {**touched, "received_at_ms": 1_001},
        placed_at_ms=1_000,
    ) is True

def test_passive_fill_prefers_monotonic_receive_order_when_available():
    # Wall clock moved backwards after placement, but the monotonic receive clock
    # proves this touched book arrived later.
    touched = {
        "bids": [[99.8, 2]],
        "asks": [[100.0, 3]],
        "received_at_ms": 900,
        "received_mono_ms": 1_001,
    }

    assert passive_limit_filled(
        "buy",
        100.0,
        touched,
        placed_at_ms=1_000,
        placed_at_mono_ms=1_000,
    ) is True


def test_multi_horizon_features_use_only_prior_causal_samples(tmp_path):
    db = tmp_path / "history.sqlite"
    rows = []
    start = 1_000_000
    for index in range(40):
        rows.append({
            "symbol": "AAA/USDT:USDT",
            "buy_venue": "okx",
            "sell_venue": "bybit",
            "gross_edge_bps": 5.0 if index < 30 else 7.0,
            "reference_mid_price": 100.0 + index * 0.01,
        })
        record_route_snapshots(db, start + index * 60_000, [rows[-1]])
    now = start + 40 * 60_000
    features = multi_horizon_route_features(db, "AAA/USDT:USDT", "okx", "bybit", now_ms=now)
    assert features is not None
    assert features["baseline_60m_bps"] == pytest.approx(5.0)
    assert features["baseline_15m_bps"] == pytest.approx(7.0)
    assert features["sample_count"] == 40


def test_maker_attempt_ev_can_be_positive_while_four_taker_v16_is_negative():
    result = maker_attempt_ev(
        capture_bps=20.0,
        long_maker_fee_bps=2.0,
        long_taker_fee_bps=5.0,
        short_maker_fee_bps=2.0,
        short_taker_fee_bps=5.5,
        long_fill_probability=0.70,
        short_fill_probability=0.70,
        long_exit_fill_probability=0.70,
        short_exit_fill_probability=0.70,
        route_sigma_bps=3.0,
        price_volatility_bps=8.0,
        safety_buffer_bps=0.5,
    )
    assert result["four_taker_hurdle_bps"] == pytest.approx(21.5)
    assert result["expected_value_bps"] > 0.0
    assert result["minimum_required_ev_bps"] > 0.0
    assert result["tradeable"] is True
    assert 0.0 < result["p_open"] < 1.0


def test_maker_attempt_ev_rejects_low_capture_even_with_good_fill_probability():
    result = maker_attempt_ev(
        capture_bps=4.0,
        long_maker_fee_bps=2.0,
        long_taker_fee_bps=5.0,
        short_maker_fee_bps=2.0,
        short_taker_fee_bps=5.5,
        long_fill_probability=0.85,
        short_fill_probability=0.85,
        long_exit_fill_probability=0.85,
        short_exit_fill_probability=0.85,
        route_sigma_bps=2.0,
        price_volatility_bps=5.0,
        safety_buffer_bps=0.5,
    )
    assert result["tradeable"] is False
    assert result["expected_value_bps"] < result["minimum_required_ev_bps"]


def test_seed_from_v16_copies_only_route_history_idempotently(tmp_path):

    from crypto_research.maker_v17 import seed_route_history_from_v16

    source = tmp_path / "v16.sqlite"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE route_history_v16 (observed_at_ms INTEGER, symbol TEXT, buy_venue TEXT, sell_venue TEXT, gross_edge_bps REAL, reference_mid_price REAL, PRIMARY KEY(observed_at_ms,symbol,buy_venue,sell_venue))")
        connection.execute("CREATE TABLE account_history_v16 (observed_at_ms INTEGER PRIMARY KEY, realized_equity REAL)")
        connection.executemany("INSERT INTO route_history_v16 VALUES (?, ?, ?, ?, ?, ?)", [(1_000_000+i*15_000,"A/USDT:USDT","okx","bybit",5.0,100.0) for i in range(10)])
        connection.execute("INSERT INTO account_history_v16 VALUES (?, ?)", (1_000_000, 999.0))
    target = tmp_path / "v17.sqlite"
    assert seed_route_history_from_v16(target, source, now_ms=1_200_000) == 10
    assert seed_route_history_from_v16(target, source, now_ms=1_200_000) == 0
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT COUNT(*) FROM route_history_v16").fetchone()[0] == 10
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "account_history_v16" not in names


def test_maker_attempt_ev_counts_causal_quote_price_improvement():
    base = maker_attempt_ev(
        capture_bps=8.0,
        long_maker_fee_bps=2.0,
        long_taker_fee_bps=5.0,
        short_maker_fee_bps=2.0,
        short_taker_fee_bps=5.5,
        long_fill_probability=0.60,
        short_fill_probability=0.60,
        long_exit_fill_probability=0.60,
        short_exit_fill_probability=0.60,
        route_sigma_bps=2.0,
        price_volatility_bps=4.0,
        safety_buffer_bps=0.5,
    )
    improved = maker_attempt_ev(
        capture_bps=8.0,
        long_maker_fee_bps=2.0,
        long_taker_fee_bps=5.0,
        short_maker_fee_bps=2.0,
        short_taker_fee_bps=5.5,
        long_fill_probability=0.60,
        short_fill_probability=0.60,
        long_exit_fill_probability=0.60,
        short_exit_fill_probability=0.60,
        route_sigma_bps=2.0,
        price_volatility_bps=4.0,
        safety_buffer_bps=0.5,
        long_quote_spread_bps=3.0,
        short_quote_spread_bps=4.0,
    )
    # Entry maker fills improve price relative to taker by each venue's quoted spread.
    assert improved["expected_entry_price_improvement_bps"] == pytest.approx(0.6 * 3.0 + 0.6 * 4.0)
    # Maker exits similarly improve the close price, conditional on an opened position.
    assert improved["expected_exit_price_improvement_bps"] == pytest.approx(0.6 * 3.0 + 0.6 * 4.0)
    assert improved["expected_value_bps"] > base["expected_value_bps"]


def test_multi_horizon_features_accept_opt_in_seven_minute_span(tmp_path):
    db = tmp_path / "history.sqlite"
    start = 1_000_000
    for i in range(12):
        record_route_snapshots(db, start + i * 40_000, [{
            "symbol": "AAA/USDT:USDT",
            "buy_venue": "okx",
            "sell_venue": "bybit",
            "gross_edge_bps": 5.0,
            "reference_mid_price": 100.0,
        }])
    now = start + 12 * 40_000
    assert multi_horizon_route_features(
        db, "AAA/USDT:USDT", "okx", "bybit", now_ms=now
    ) is None
    assert multi_horizon_route_features(
        db,
        "AAA/USDT:USDT",
        "okx",
        "bybit",
        now_ms=now,
        minimum_span_ms=420_000,
    ) is not None


def test_multi_horizon_features_can_opt_in_to_two_short_window_samples(tmp_path):
    db = tmp_path / "history.sqlite"
    start = 1_000_000
    sample_seconds = [0, 60, 120, 180, 240, 300, 360, 420, 480, 540, 650, 850]
    for seconds in sample_seconds:
        record_route_snapshots(db, start + seconds * 1_000, [{
            "symbol": "AAA/USDT:USDT",
            "buy_venue": "okx",
            "sell_venue": "bybit",
            "gross_edge_bps": 5.0,
            "reference_mid_price": 100.0,
        }])
    now = start + 900_000

    assert multi_horizon_route_features(
        db,
        "AAA/USDT:USDT",
        "okx",
        "bybit",
        now_ms=now,
        minimum_span_ms=420_000,
    ) is None
    assert multi_horizon_route_features(
        db,
        "AAA/USDT:USDT",
        "okx",
        "bybit",
        now_ms=now,
        minimum_span_ms=420_000,
        minimum_window_samples=2,
    ) is not None


def test_current_gate_vip0_futures_maker_fee_is_two_bps():
    assert DEFAULT_MAKER_FEE_BPS["gate"] == 2.0


def test_multi_horizon_features_can_treat_fast_window_as_diagnostic(tmp_path):
    db = tmp_path / "history.sqlite"
    start = 1_000_000
    # Eight samples span >7 minutes and leave only one sample in the last 5m.
    for seconds in [0, 60, 120, 180, 240, 300, 360, 850]:
        record_route_snapshots(db, start + seconds * 1_000, [{
            "symbol": "FAST/USDT:USDT",
            "buy_venue": "okx",
            "sell_venue": "bybit",
            "gross_edge_bps": 5.0 + seconds / 1000.0,
            "reference_mid_price": 100.0,
        }])
    now = start + 900_000

    assert multi_horizon_route_features(
        db,
        "FAST/USDT:USDT",
        "okx",
        "bybit",
        now_ms=now,
        min_samples=8,
        minimum_span_ms=420_000,
        minimum_window_samples=2,
    ) is None

    features = multi_horizon_route_features(
        db,
        "FAST/USDT:USDT",
        "okx",
        "bybit",
        now_ms=now,
        min_samples=8,
        minimum_span_ms=420_000,
        minimum_window_samples=2,
        require_5m_window=False,
    )
    assert features is not None
    assert features["sample_count"] == 8
    assert features["baseline_5m_bps"] == pytest.approx(5.85)
