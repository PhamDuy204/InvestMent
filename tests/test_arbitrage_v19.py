import json
import sqlite3
from pathlib import Path

import pytest

import scripts.run_arbitrage_paper_v17 as v17
import scripts.run_arbitrage_paper_v19 as v19
from crypto_research.arbitrage_v12 import ArbitrageOpportunity, VenueBook
from crypto_research.monitoring_v13 import build_monitoring_payload
from crypto_research.route_v16 import record_route_snapshots
from scripts.run_arbitrage_paper_v17 import (
    _create_pending_entry,
    _create_pending_exit,
    _default_state_v17,
    _process_maker_probes,
    _process_pending_entries,
    _process_pending_exits,
    run_cycle_v17,
)
from scripts.run_arbitrage_paper_v18 import _default_state_v18


def test_public_trade_metrics_preserve_per_venue_queue_evidence():
    assert v19._public_trade_metrics_for_state(
        {
            "public_trade_update_count": 12,
            "public_trade_update_counts_by_venue": {"okx": 7, "gate": 5},
        }
    ) == {
        "public_trade_update_count": 12,
        "public_trade_update_counts_by_venue": {"okx": 7, "gate": 5},
    }


class FakePublicClient:
    def __init__(self, books):
        self.books = books

    def fetch_order_book(self, symbol, limit=None):
        return self.books[symbol]


def _raw_book(bid, ask, timestamp, qty=100.0):
    return {"bids": [[bid, qty]], "asks": [[ask, qty]], "timestamp": timestamp}


def _venue(name, bid, ask, fee=5.0, timestamp=1_005_000, qty=100.0):
    return VenueBook(name, _raw_book(bid, ask, timestamp, qty), fee)


def _causal_venue(
    name,
    bid,
    ask,
    *,
    timestamp,
    bid_qty=100.0,
    ask_qty=100.0,
    fee=5.0,
):
    return VenueBook(
        name,
        {
            "bids": [[bid, bid_qty]],
            "asks": [[ask, ask_qty]],
            "timestamp": timestamp,
            "received_at_ms": timestamp,
            "received_mono_ms": timestamp,
        },
        fee,
    )


def _pending_entry(now_ms=1_000_000):
    venues = {
        "cheap": _venue("cheap", 99.9, 100.0),
        "rich": _venue("rich", 106.0, 106.1, 5.5),
    }
    return _create_pending_entry(
        symbol="AAA/USDT:USDT",
        buy_venue="cheap",
        sell_venue="rich",
        venues=venues,
        target_notional=10.0,
        leverage=2.0,
        pair_gross_fraction=0.16,
        decision={
            "expected_value_bps": 3.0,
            "minimum_required_ev_bps": 0.5,
            "capture_bps": 20.0,
            "baseline_60m_bps": 5.0,
            "baseline_15m_bps": 6.0,
            "baseline_5m_bps": 7.0,
            "route_sigma_bps": 3.0,
            "price_volatility_bps": 8.0,
            "p_open": 0.6,
        },
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        now_ms=now_ms,
        now_utc="2026-08-28T00:00:00+00:00",
    )


def _run_cycle(tmp_path, *, clients, symbols, state, now_ms):
    run_cycle_v17(
        clients=clients,
        symbols=symbols,
        state=state,
        history_db=tmp_path / "history.sqlite",
        stats_db=tmp_path / "stats.sqlite",
        safety_buffer_bps=0.5,
        depth_limit=20,
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        max_book_age_ms=10_000,
        now_ms=now_ms,
        now_utc="2026-08-28T00:00:00+00:00",
        journal_path=tmp_path / "positions.jsonl",
        symbol_venues={symbol: ("cheap", "rich") for symbol in symbols},
        per_symbol_history_sampling=True,
        minimum_history_span_ms=420_000,
        strict_maker_price_through=True,
    )


def test_v19_history_clock_is_per_symbol(tmp_path):
    first_symbol = "A/USDT:USDT"
    second_symbol = "B/USDT:USDT"
    state = _default_state_v17(["cheap", "rich"])
    state["history_sample_interval_ms"] = 5_000
    history = tmp_path / "history.sqlite"
    for index in range(12):
        record_route_snapshots(history, 500_000 + index * 40_000, [
            {
                "symbol": first_symbol,
                "buy_venue": "cheap",
                "sell_venue": "rich",
                "gross_edge_bps": 100.0,
                "reference_mid_price": 100.0,
            },
            {
                "symbol": second_symbol,
                "buy_venue": "cheap",
                "sell_venue": "rich",
                "gross_edge_bps": 100.0,
                "reference_mid_price": 100.0,
            },
        ])
    clients = {
        "cheap": FakePublicClient({
            first_symbol: _raw_book(99.9, 100.0, 1_000_000),
            second_symbol: _raw_book(99.9, 100.0, 1_001_000),
        }),
        "rich": FakePublicClient({
            first_symbol: _raw_book(101.0, 101.1, 1_000_000),
            second_symbol: _raw_book(101.0, 101.1, 1_001_000),
        }),
    }

    _run_cycle(tmp_path, clients=clients, symbols=[first_symbol], state=state, now_ms=1_000_000)
    _run_cycle(tmp_path, clients=clients, symbols=[second_symbol], state=state, now_ms=1_001_000)

    assert state["last_history_sample_ms_by_symbol"] == {
        first_symbol: 1_000_000,
        second_symbol: 1_001_000,
    }
    with sqlite3.connect(history) as connection:
        sampled_symbols = {
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT symbol FROM route_history_v16 WHERE observed_at_ms IN (?, ?)",
                (1_000_000, 1_001_000),
            )
        }
    assert sampled_symbols == {first_symbol, second_symbol}


def test_strict_v19_entry_processing_keeps_touched_makers_pending(tmp_path):
    symbol = "AAA/USDT:USDT"
    pending = {
        "symbol": symbol,
        "long_exchange": "cheap",
        "short_exchange": "rich",
        "long_limit_price": 100.0,
        "short_limit_price": 101.0,
        "placed_at_ms": 1_000,
    }
    state = v19._default_state_v19(["cheap", "rich"])
    state["pending_entries"] = [pending]
    touched_books = {
        symbol: {
            "cheap": VenueBook(
                "cheap",
                {"bids": [[99.9, 100.0]], "asks": [[100.0, 100.0]], "timestamp": 1_001},
                5.0,
            ),
            "rich": VenueBook(
                "rich",
                {"bids": [[101.0, 100.0]], "asks": [[101.1, 100.0]], "timestamp": 1_001},
                5.5,
            ),
        }
    }

    v19._process_pending_entries_v19(
        state,
        books_by_symbol=touched_books,
        stats_db=tmp_path / "stats.sqlite",
        now_ms=1_001,
        now_utc="2026-08-28T00:00:00.001000+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )

    assert state["pending_entries"] == [pending]
    assert state["open_positions"] == []
    assert state["maker_fill_observation_count"] == 0


def test_v19_no_causal_fill_backs_off_matching_maker_leg(tmp_path):
    pending = _pending_entry()
    pending.update(maker_side="LONG", maker_venue="cheap")
    state = v19._default_state_v19(["cheap", "rich"])
    state["pending_entries"] = [pending]
    now_ms = 1_030_000

    v19._process_pending_entries_v19(
        state,
        books_by_symbol={
            "AAA/USDT:USDT": {
                "cheap": _causal_venue("cheap", 99.8, 100.1, timestamp=now_ms),
                "rich": _causal_venue("rich", 105.9, 106.2, timestamp=now_ms, fee=5.5),
            }
        },
        stats_db=tmp_path / "stats.sqlite",
        now_ms=now_ms,
        now_utc="2026-08-28T00:00:30+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )

    assert state["pending_entries"] == []
    assert state["route_cooldowns"]["maker:AAA/USDT:USDT|cheap|LONG"] == now_ms


def test_v19_market_data_timeout_counts_no_causal_fill_once(tmp_path):
    pending = _pending_entry()
    state = v19._default_state_v19(["cheap", "rich"])
    state["pending_entries"] = [pending]
    journal_path = tmp_path / "positions.jsonl"

    v19._process_pending_entries_v19(
        state,
        books_by_symbol={},
        stats_db=tmp_path / "stats.sqlite",
        now_ms=1_030_000,
        now_utc="2026-08-28T00:00:30+00:00",
        journal_path=journal_path,
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
    )
    v19._process_pending_entries_v19(
        state,
        books_by_symbol={},
        stats_db=tmp_path / "stats.sqlite",
        now_ms=1_060_000,
        now_utc="2026-08-28T00:01:00+00:00",
        journal_path=journal_path,
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
    )

    records = [json.loads(line) for line in journal_path.read_text().splitlines()]
    assert state["pending_entries"] == []
    assert state["maker_entry_cancel_count"] == 1
    assert state["candidate_funnel_counts"]["no_causal_fill"] == 1
    assert state["route_cooldowns"] == {}
    assert [record["cancel_reason"] for record in records] == ["MARKET_DATA_TIMEOUT"]


def test_v19_post_fill_rejection_counts_terminal_abort(monkeypatch, tmp_path):
    pending = _pending_entry()
    pending.update(leverage=20.0, strategy_id=v19.STRATEGY_ID)
    state = v19._default_state_v19(["cheap", "rich"])
    state["pending_entries"] = [pending]
    monkeypatch.setattr(v19, "post_fill_entry_ev", lambda **kwargs: {
        "actual_gross_spread_bps": 0.0,
        "actual_capture_bps": 0.0,
        "post_fill_expected_value_bps": -1.0,
        "minimum_required_ev_bps": 0.5,
        "decision": "POST_FILL_EV_BELOW_MIN",
        "tradeable": False,
    })

    v19._process_pending_entries_v19(
        state,
        books_by_symbol={"AAA/USDT:USDT": {
            "cheap": _venue("cheap", 99.7, 99.8),
            "rich": _venue("rich", 106.0, 106.1, 5.5),
        }},
        stats_db=tmp_path / "stats.sqlite",
        now_ms=1_005_000,
        now_utc="2026-08-28T00:00:05+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )

    assert state["pending_entries"] == []
    assert state["open_positions"] == []
    assert state["post_fill_reject_count"] == 1
    assert state["candidate_funnel_counts"]["post_fill_rejected"] == 1
    # Changing the hedge venue must not bypass the failing maker leg's backoff.
    assert state["route_cooldowns"].get("maker:AAA/USDT:USDT|cheap|LONG") == 1_005_000
    assert "maker:AAA/USDT:USDT|cheap|SHORT" not in state["route_cooldowns"]


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
@pytest.mark.parametrize("elapsed_ms", [5_000, 35_000])
def test_confirmed_maker_fill_survives_missing_hedge_data_until_real_unwind(tmp_path, side, elapsed_ms):
    pending = _pending_entry()
    pending.update(maker_side=side, leverage=20, strategy_id=v19.STRATEGY_ID)
    state = v19._default_state_v19(["cheap", "rich"])
    state["pending_entries"] = [pending]
    maker = "cheap" if side == "LONG" else "rich"
    bid, ask = (99.7, 99.8) if side == "LONG" else (106.2, 106.3)
    now_ms = 1_000_000 + elapsed_ms
    outcomes = []

    def process(stamp, quantity):
        v19._process_pending_entries_v19(
            state, books_by_symbol={"AAA/USDT:USDT": {
                maker: _venue(maker, bid, ask, timestamp=stamp, qty=quantity),
            }}, stats_db=tmp_path / "stats.sqlite", now_ms=stamp,
            now_utc="2026-09-05T09:00:00+00:00", journal_path=tmp_path / "positions.jsonl",
            maker_fee_bps={"cheap": 2, "rich": 2}, taker_fee_bps={"cheap": 5, "rich": 5.5},
            strict_maker_price_through=True,
            execution_outcome_recorder=lambda pending, **outcome: outcomes.append(outcome),
        )

    process(now_ms, 0.001)
    assert state["pending_entries"] and state["pending_entries"][0]["status"] == "UNWIND_PENDING"
    assert state["partial_exposure_count"] == 1
    assert state["partial_exposure_reserved_margin"] > 0
    assert state["realized_pnl"] == 0 and outcomes == []
    process(now_ms + 1_000, 100)
    assert state["pending_entries"] == [] and state["partial_exposure_count"] == 0
    assert state["one_leg_abort_count"] == 1 and state["realized_pnl"] < 0
    assert len(outcomes) == 1 and outcomes[0]["accepted"] is False
    events = [json.loads(line) for line in (tmp_path / "positions.jsonl").read_text().splitlines()]
    assert [row["record_type"] for row in events] == ["PAPER_ONE_LEG_UNWIND_PENDING", "PAPER_ONE_LEG_ABORT"]


def test_v19_paired_open_counts_terminal_position(monkeypatch, tmp_path):
    pending = _pending_entry()
    pending.update(leverage=20.0, strategy_id=v19.STRATEGY_ID)
    state = v19._default_state_v19(["cheap", "rich"])
    state["pending_entries"] = [pending]
    monkeypatch.setattr(v19, "post_fill_entry_ev", lambda **kwargs: {
        "actual_gross_spread_bps": 0.0,
        "actual_capture_bps": 1.0,
        "post_fill_expected_value_bps": 1.0,
        "minimum_required_ev_bps": 0.5,
        "decision": "POST_FILL_EV_TRADEABLE",
        "tradeable": True,
    })

    v19._process_pending_entries_v19(
        state,
        books_by_symbol={"AAA/USDT:USDT": {
            "cheap": _venue("cheap", 99.7, 99.8),
            "rich": _venue("rich", 106.2, 106.3, 5.5),
        }},
        stats_db=tmp_path / "stats.sqlite",
        now_ms=1_005_000,
        now_utc="2026-08-28T00:00:05+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )

    assert state["pending_entries"] == []
    assert len(state["open_positions"]) == 1
    assert state["opened_position_count"] == 1
    assert state["candidate_funnel_counts"]["paired_open"] == 1


def test_v19_post_fill_refresh_uses_seven_minute_baseline(monkeypatch, tmp_path):
    now_ms = 2_000_000
    history = tmp_path / "history.sqlite"
    for index in range(12):
        record_route_snapshots(
            history,
            now_ms - 440_000 + index * 40_000,
            [{
                "symbol": "AAA/USDT:USDT",
                "buy_venue": "cheap",
                "sell_venue": "rich",
                "gross_edge_bps": 20.0,
                "reference_mid_price": 100.0,
            }],
        )
    pending = _pending_entry()
    pending.update(leverage=20.0, strategy_id=v19.STRATEGY_ID)
    state = v19._default_state_v19(["cheap", "rich"])
    state["pending_entries"] = [pending]
    captured = {}

    def capture_post_fill(**kwargs):
        captured.update(kwargs)
        return {
            "actual_gross_spread_bps": 20.0,
            "actual_capture_bps": 1.0,
            "post_fill_expected_value_bps": 1.0,
            "minimum_required_ev_bps": 0.5,
            "decision": "POST_FILL_EV_TRADEABLE",
            "tradeable": True,
        }

    monkeypatch.setattr(v19, "post_fill_entry_ev", capture_post_fill)
    v19._process_pending_entries_v19(
        state,
        books_by_symbol={"AAA/USDT:USDT": {
            "cheap": _venue("cheap", 99.7, 99.8, timestamp=now_ms),
            "rich": _venue("rich", 106.2, 106.3, 5.5, timestamp=now_ms),
        }},
        stats_db=history,
        now_ms=now_ms,
        now_utc="2026-08-28T00:16:40+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )

    assert captured["baseline_60m_bps"] == pytest.approx(20.0)
    assert captured["baseline_15m_bps"] == pytest.approx(20.0)
    assert state["open_positions"][0]["entry_baseline_bps"] == pytest.approx(20.0)


def _missing_depth_books(
    timestamp,
    *,
    cancelled_leg_price_through=False,
    unwind_depth_available=False,
):
    return {
        "cheap": _causal_venue(
            "cheap",
            99.7,
            99.8,
            timestamp=timestamp,
            bid_qty=100.0 if unwind_depth_available else 0.001,
        ),
        "rich": _causal_venue(
            "rich",
            106.2 if cancelled_leg_price_through else 106.0,
            106.3,
            timestamp=timestamp,
            bid_qty=0.001,
            fee=5.5,
        ),
    }


def _make_unwind_pending_state(tmp_path):
    pending = _pending_entry()
    pending.update(
        leverage=20.0,
        strategy_id=v19.STRATEGY_ID,
        placed_at_mono_ms=1_000_000,
    )
    state = v19._default_state_v19(["cheap", "rich"])
    state["pending_entries"] = [pending]
    journal_path = tmp_path / "positions.jsonl"
    books = _missing_depth_books(1_005_000)
    v19._process_pending_entries_v19(
        state,
        books_by_symbol={"AAA/USDT:USDT": books},
        stats_db=tmp_path / "stats.sqlite",
        now_ms=1_005_000,
        now_mono_ms=1_005_000,
        now_utc="2026-08-28T00:00:05+00:00",
        journal_path=journal_path,
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )
    return state, journal_path, books


def test_v19_missing_hedge_and_unwind_transitions_to_partial_exposure(tmp_path):
    state, journal_path, _ = _make_unwind_pending_state(tmp_path)

    assert len(state["pending_entries"]) == 1
    pending = state["pending_entries"][0]
    expected_notional = float(pending["quantity"]) * float(pending["long_limit_price"])
    expected_entry_fee = expected_notional * 2.0 / 10_000.0
    expected_margin = expected_notional / 20.0
    assert pending["status"] == "UNWIND_PENDING"
    assert pending["long_filled"] is True
    assert pending["short_filled"] is False
    assert pending["cancelled_maker_leg"] == "SHORT"
    assert pending["filled_side"] == "LONG"
    assert pending["partial_entry_notional"] == pytest.approx(expected_notional)
    assert pending["partial_entry_fee"] == pytest.approx(expected_entry_fee)
    assert pending["partial_gross_notional"] == pytest.approx(expected_notional)
    assert pending["partial_unrealized_pnl"] == pytest.approx(-expected_entry_fee)
    assert pending["partial_initial_margin"] == pytest.approx(expected_margin)
    assert pending["unwind_attempt_count"] == 1
    assert pending["unwind_failure_count"] == 1
    assert state["one_leg_unwind_attempt_count"] == 1
    assert state["one_leg_unwind_failure_count"] == 1
    assert state["partial_exposure_count"] == 1
    assert state["gross_exposure"] == pytest.approx(expected_notional)
    assert state["initial_margin_used"] == pytest.approx(expected_margin)
    assert state["venue_margin_used"]["cheap"] == pytest.approx(expected_margin)
    assert state["venue_unrealized_pnl"]["cheap"] == pytest.approx(-expected_entry_fee)
    assert state["equity"] == pytest.approx(100.0)
    assert state["realized_pnl"] == pytest.approx(0.0)
    assert state["one_leg_abort_count"] == 0
    records = (
        [json.loads(line) for line in journal_path.read_text().splitlines()]
        if journal_path.exists()
        else []
    )
    assert [record["record_type"] for record in records] == [
        "PAPER_ONE_LEG_UNWIND_PENDING"
    ]
    assert "gross_pnl" not in records[0]
    assert "realized_net_pnl" not in records[0]
    assert "exit_price" not in records[0]


def test_v19_unwind_pending_never_fills_cancelled_maker_or_retries_same_snapshot(
    tmp_path,
):
    state, journal_path, _ = _make_unwind_pending_state(tmp_path)
    counts_before = (
        state["one_leg_unwind_attempt_count"],
        state["one_leg_unwind_failure_count"],
        state["maker_hedge_failure_count"],
    )
    same_snapshot = _missing_depth_books(
        1_005_000,
        cancelled_leg_price_through=True,
    )

    v19._process_pending_entries_v19(
        state,
        books_by_symbol={"AAA/USDT:USDT": same_snapshot},
        stats_db=tmp_path / "stats.sqlite",
        now_ms=1_005_100,
        now_mono_ms=1_005_100,
        now_utc="2026-08-28T00:00:05.100000+00:00",
        journal_path=journal_path,
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )

    pending = state["pending_entries"][0]
    assert pending["status"] == "UNWIND_PENDING"
    assert pending["long_filled"] is True
    assert pending["short_filled"] is False
    assert state["open_positions"] == []
    assert (
        state["one_leg_unwind_attempt_count"],
        state["one_leg_unwind_failure_count"],
        state["maker_hedge_failure_count"],
    ) == counts_before


def test_v19_unwind_pending_retries_once_per_new_filled_venue_snapshot(tmp_path):
    state, journal_path, _ = _make_unwind_pending_state(tmp_path)
    newer_snapshot = _missing_depth_books(
        1_006_000,
        cancelled_leg_price_through=True,
    )

    v19._process_pending_entries_v19(
        state,
        books_by_symbol={"AAA/USDT:USDT": newer_snapshot},
        stats_db=tmp_path / "stats.sqlite",
        now_ms=1_006_000,
        now_mono_ms=1_006_000,
        now_utc="2026-08-28T00:00:06+00:00",
        journal_path=journal_path,
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )
    v19._process_pending_entries_v19(
        state,
        books_by_symbol={"AAA/USDT:USDT": newer_snapshot},
        stats_db=tmp_path / "stats.sqlite",
        now_ms=1_006_100,
        now_mono_ms=1_006_100,
        now_utc="2026-08-28T00:00:06.100000+00:00",
        journal_path=journal_path,
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )

    pending = state["pending_entries"][0]
    assert pending["unwind_attempt_count"] == 2
    assert pending["unwind_failure_count"] == 2
    assert state["one_leg_unwind_attempt_count"] == 2
    assert state["one_leg_unwind_failure_count"] == 2


def test_v19_unwind_depth_recovery_aborts_exactly_once(tmp_path):
    state, journal_path, _ = _make_unwind_pending_state(tmp_path)
    state["pending_entries"][0]["strategy_id"] = "V21_TEST_STRATEGY"
    recovery = _missing_depth_books(
        1_006_000,
        cancelled_leg_price_through=True,
        unwind_depth_available=True,
    )

    v19._process_pending_entries_v19(
        state,
        books_by_symbol={"AAA/USDT:USDT": recovery},
        stats_db=tmp_path / "stats.sqlite",
        now_ms=1_006_000,
        now_mono_ms=1_006_000,
        now_utc="2026-08-28T00:00:06+00:00",
        journal_path=journal_path,
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )
    terminal = {
        "one_leg_abort_count": state["one_leg_abort_count"],
        "one_leg_abort_pnl": state["one_leg_abort_pnl"],
        "execution_abort": state["candidate_funnel_counts"]["execution_abort"],
        "attempts": state["one_leg_unwind_attempt_count"],
    }
    v19._process_pending_entries_v19(
        state,
        books_by_symbol={"AAA/USDT:USDT": recovery},
        stats_db=tmp_path / "stats.sqlite",
        now_ms=1_006_100,
        now_mono_ms=1_006_100,
        now_utc="2026-08-28T00:00:06.100000+00:00",
        journal_path=journal_path,
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )

    assert state["pending_entries"] == []
    assert state["open_positions"] == []
    assert terminal["one_leg_abort_count"] == 1
    assert terminal["execution_abort"] == 1
    assert state["candidate_funnel_counts"]["post_fill_rejected"] == 0
    assert terminal["attempts"] == 2
    assert {
        "one_leg_abort_count": state["one_leg_abort_count"],
        "one_leg_abort_pnl": state["one_leg_abort_pnl"],
        "execution_abort": state["candidate_funnel_counts"]["execution_abort"],
        "attempts": state["one_leg_unwind_attempt_count"],
    } == terminal
    records = [json.loads(line) for line in journal_path.read_text().splitlines()]
    assert [record["record_type"] for record in records] == [
        "PAPER_ONE_LEG_UNWIND_PENDING",
        "PAPER_ONE_LEG_ABORT",
    ]
    assert records[-1]["abort_reason"] == "HEDGE_DEPTH_UNAVAILABLE"
    assert records[-1]["strategy_id"] == "V21_TEST_STRATEGY"


def test_v19_post_fill_reject_with_no_unwind_depth_cancels_other_maker(
    monkeypatch,
    tmp_path,
):
    pending = _pending_entry()
    pending.update(
        leverage=20.0,
        strategy_id=v19.STRATEGY_ID,
        placed_at_mono_ms=1_000_000,
    )
    state = v19._default_state_v19(["cheap", "rich"])
    state["pending_entries"] = [pending]
    journal_path = tmp_path / "positions.jsonl"
    first_books = {
        "cheap": _causal_venue(
            "cheap",
            99.7,
            99.8,
            timestamp=1_005_000,
            bid_qty=0.001,
        ),
        "rich": _causal_venue(
            "rich",
            106.0,
            106.3,
            timestamp=1_005_000,
            bid_qty=100.0,
            fee=5.5,
        ),
    }
    monkeypatch.setattr(
        v19,
        "post_fill_entry_ev",
        lambda **kwargs: {
            "actual_gross_spread_bps": 1.0,
            "actual_capture_bps": -1.0,
            "post_fill_expected_value_bps": -10.0,
            "minimum_required_ev_bps": 0.5,
            "decision": "POST_FILL_EV_REJECTED",
            "tradeable": False,
        },
    )

    v19._process_pending_entries_v19(
        state,
        books_by_symbol={"AAA/USDT:USDT": first_books},
        stats_db=tmp_path / "stats.sqlite",
        now_ms=1_005_000,
        now_mono_ms=1_005_000,
        now_utc="2026-08-28T00:00:05+00:00",
        journal_path=journal_path,
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )

    assert len(state["pending_entries"]) == 1
    transitioned = state["pending_entries"][0]
    assert transitioned["status"] == "UNWIND_PENDING"
    assert transitioned["unwind_reason"] == "POST_FILL_EV_REJECTED"
    assert transitioned["cancelled_maker_leg"] == "SHORT"
    assert transitioned["long_filled"] is True
    assert transitioned["short_filled"] is False
    assert transitioned["unwind_attempt_count"] == 1
    assert transitioned["unwind_failure_count"] == 1
    assert state["post_fill_reject_count"] == 0
    assert state["one_leg_abort_count"] == 0

    recovery = {
        **first_books,
        "cheap": _causal_venue(
            "cheap",
            99.7,
            99.8,
            timestamp=1_006_000,
            bid_qty=100.0,
        ),
    }
    v19._process_pending_entries_v19(
        state,
        books_by_symbol={"AAA/USDT:USDT": recovery},
        stats_db=tmp_path / "stats.sqlite",
        now_ms=1_006_000,
        now_mono_ms=1_006_000,
        now_utc="2026-08-28T00:00:06+00:00",
        journal_path=journal_path,
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )

    assert state["pending_entries"] == []
    assert state["post_fill_reject_count"] == 1
    assert state["candidate_funnel_counts"]["post_fill_rejected"] == 1
    assert state["candidate_funnel_counts"]["execution_abort"] == 0
    assert state["one_leg_abort_count"] == 1
    records = [json.loads(line) for line in journal_path.read_text().splitlines()]
    assert [record["record_type"] for record in records] == [
        "PAPER_ONE_LEG_UNWIND_PENDING",
        "PAPER_ONE_LEG_ABORT",
    ]
    assert records[-1]["abort_reason"] == "POST_FILL_EV_REJECTED"


def test_v19_unwind_pending_state_reloads_and_sanitizes_partial_risk(tmp_path):
    state, _, _ = _make_unwind_pending_state(tmp_path)
    state_path = tmp_path / "state.json"
    v19.write_state(state_path, state)

    loaded = v19.load_state_v19(
        state_path,
        venue_names=["cheap", "rich"],
    )
    payload = build_monitoring_payload(
        loaded,
        {"status": "HEALTHY", "error": None},
        [],
        monitor_history={"account_history": [], "position_history": {}},
        updated_at_utc="2026-08-28T00:00:06+00:00",
    )

    assert loaded["pending_entries"][0]["status"] == "UNWIND_PENDING"
    assert loaded["gross_exposure"] > 0.0
    assert loaded["initial_margin_used"] > 0.0
    assert loaded["equity"] == pytest.approx(100.0)
    assert payload["partial_exposure_count"] == 1
    assert payload["partial_exposure_gross_notional"] > 0.0
    assert payload["partial_exposure_reserved_margin"] > 0.0
    assert payload["pending_entries"][0]["status"] == "UNWIND_PENDING"
    assert payload["pending_entries"][0]["partial_entry_fee"] > 0.0
    assert payload["pending_entries"][0]["partial_unrealized_pnl"] < 0.0
    serialized = json.dumps(payload)
    assert "last_unwind_snapshot_at_ms" not in serialized
    assert "last_unwind_snapshot_mono_ms" not in serialized


def test_strict_v19_exit_processing_keeps_touched_makers_pending(tmp_path):
    pending = _pending_entry()
    state = _default_state_v17(["cheap", "rich"])
    state["pending_entries"] = [pending]
    entry_books = {
        "cheap": _venue("cheap", 99.8, 99.9),
        "rich": _venue("rich", 106.1, 106.2, 5.5),
    }
    _process_pending_entries(
        state,
        books_by_symbol={"AAA/USDT:USDT": entry_books},
        stats_db=tmp_path / "stats.sqlite",
        now_ms=1_005_000,
        now_utc="2026-08-28T00:00:05+00:00",
        journal_path=tmp_path / "journal.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
    )
    position = state["open_positions"][0]
    quoted = {
        "cheap": _venue("cheap", 102.0, 102.1, timestamp=1_010_000),
        "rich": _venue("rich", 102.0, 102.1, 5.5, timestamp=1_010_000),
    }
    pending_exit = _create_pending_exit(
        position,
        venues=quoted,
        reason="ROUTE_TARGET",
        now_ms=1_010_000,
        now_utc="2026-08-28T00:00:10+00:00",
    )
    state["pending_exits"] = [pending_exit]
    touched = {
        "cheap": _venue("cheap", 102.1, 102.2, timestamp=1_011_000),
        "rich": _venue("rich", 101.9, 102.0, 5.5, timestamp=1_011_000),
    }

    _process_pending_exits(
        state,
        books_by_symbol={"AAA/USDT:USDT": touched},
        stats_db=tmp_path / "stats.sqlite",
        now_ms=1_011_000,
        now_utc="2026-08-28T00:00:11+00:00",
        journal_path=tmp_path / "journal.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )

    assert state["pending_exits"] == [pending_exit]
    assert state["open_positions"] == [position]
    assert state["maker_fill_observation_count"] == 2


def test_strict_v19_probe_processing_keeps_touched_makers_pending(tmp_path):
    symbol = "AAA/USDT:USDT"
    probe = {
        "symbol": symbol,
        "long_exchange": "cheap",
        "short_exchange": "rich",
        "long_limit_price": 100.0,
        "short_limit_price": 101.0,
        "placed_at_ms": 1_000,
    }
    state = _default_state_v17(["cheap", "rich"])
    state["maker_probes"] = [probe]
    touched = {
        "cheap": _venue("cheap", 99.9, 100.0, timestamp=1_001),
        "rich": _venue("rich", 101.0, 101.1, 5.5, timestamp=1_001),
    }

    _process_maker_probes(
        state,
        books_by_symbol={symbol: touched},
        stats_db=tmp_path / "stats.sqlite",
        now_ms=1_001,
        strict_maker_price_through=True,
    )

    assert state["maker_probes"] == [probe]
    assert state["maker_fill_observation_count"] == 0


@pytest.mark.asyncio
async def test_background_runtime_refresh_isolates_live_state_until_complete():
    started = __import__("asyncio").Event()
    release = __import__("asyncio").Event()
    live_state = {"funding_snapshots": {"old": {"sampled_at_ms": 1}}, "open_positions": []}

    async def slow_refresh(*, state, **kwargs):
        started.set()
        await release.wait()
        state["funding_snapshots"] = {"new": {"sampled_at_ms": 2}}
        state["funding_snapshot_count"] = 1

    task = __import__("asyncio").create_task(
        v19._runtime_refresh_snapshot(
            slow_refresh,
            clients={},
            state=live_state,
            symbols=[],
            coverage={},
            now_ms=2,
        )
    )
    await started.wait()

    assert live_state["funding_snapshots"] == {"old": {"sampled_at_ms": 1}}
    release.set()
    refreshed = await task
    assert refreshed["funding_snapshots"] == {"new": {"sampled_at_ms": 2}}
    assert refreshed["funding_snapshot_count"] == 1
    assert live_state["funding_snapshots"] == {"old": {"sampled_at_ms": 1}}


def test_v19_defaults_are_bounded_and_paper_only():
    state = v19._default_state_v19(["binance", "okx"])
    args = v19._parser().parse_args([])

    assert state["schema_version"] == "v19-arbitrage-paper-1"
    assert state["portfolio_model"] == "WS_CAUSAL_POST_FILL_EV_V2"
    assert state["last_history_sample_ms_by_symbol"] == {}
    assert args.scan_batch_size == 5
    assert args.max_book_age_ms == 5_000
    assert args.max_book_skew_ms is None
    assert args.memory_high_water_mb == 1_200
    assert args.memory_hard_limit_mb == 1_500
    assert args.seed_history_db == Path("artifacts/arbitrage_v18/history_v18.sqlite")


@pytest.mark.parametrize(
    ("high_water_mb", "hard_limit_mb"),
    [
        (0, 1_500),
        (-1, 1_500),
        (1_200, 0),
        (1_200, 1_200),
        (1_501, 1_500),
        (1_200, 3_001),
    ],
)
def test_v19_rejects_invalid_memory_limits_before_clients_are_constructed(
    monkeypatch,
    high_water_mb,
    hard_limit_mb,
):
    constructed = False

    def construct_clients():
        nonlocal constructed
        constructed = True
        raise AssertionError("client construction must not be reached")

    monkeypatch.setattr(v19, "make_public_stream_clients", construct_clients)

    with pytest.raises(ValueError):
        v19.main(
            [
                "--memory-high-water-mb",
                str(high_water_mb),
                "--memory-hard-limit-mb",
                str(hard_limit_mb),
                "--once",
            ]
        )

    assert constructed is False


def test_v19_snapshot_is_discovery_union_active_and_connected_only():
    cache = v19.LatestBookCache(depth_limit=2, max_entries=32)
    symbols = {
        "discovery": "DISCOVERY/USDT:USDT",
        "pending_entry": "ENTRY/USDT:USDT",
        "pending_exit": "EXIT/USDT:USDT",
        "probe": "PROBE/USDT:USDT",
        "open": "OPEN/USDT:USDT",
        "unselected": "OTHER/USDT:USDT",
    }
    for symbol in symbols.values():
        for venue, received_ms in (("a", 6_000), ("b", 10_000)):
            cache.update(
                venue,
                symbol,
                _raw_book(99.9, 100.1, received_ms),
                received_at_ms=received_ms,
                received_mono_ms=received_ms,
            )
    cache.record_stream_error("a", symbols["pending_entry"], RuntimeError("disconnected"))
    state = {
        "pending_entries": [{"symbol": symbols["pending_entry"]}],
        "pending_exits": [{"symbol": symbols["pending_exit"]}],
        "maker_probes": [{"symbol": symbols["probe"]}],
        "open_positions": [{"symbol": symbols["open"]}],
    }

    clients, metrics = v19._snapshot_v19(
        cache,
        state=state,
        discovery_symbols=[symbols["discovery"]],
        now_ms=10_100,
        now_mono_ms=10_100,
        max_book_age_ms=5_000,
    )

    assert set(clients["b"].symbols) == {
        symbols["discovery"],
        symbols["pending_entry"],
        symbols["pending_exit"],
        symbols["probe"],
        symbols["open"],
    }
    assert symbols["unselected"] not in clients["b"].symbols
    assert symbols["discovery"] in clients["a"].symbols
    assert symbols["pending_entry"] not in clients["a"].symbols
    assert metrics["skew_rejected_book_count"] == 0
    assert metrics["disconnected_book_count"] == 1


def test_v19_cycle_enables_causal_history_and_strict_maker_options(monkeypatch, tmp_path):
    captured = {}

    def capture_cycle(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(v19, "run_cycle_v17", capture_cycle)
    state = v19._default_state_v19(["cheap", "rich"])

    v19.run_cycle_v19(
        clients={},
        symbols=[],
        state=state,
        history_db=tmp_path / "history.sqlite",
        now_ms=1_000,
        now_utc="2026-08-28T00:00:01+00:00",
        journal_path=tmp_path / "positions.jsonl",
        symbol_venues={},
    )

    assert captured["per_symbol_history_sampling"] is True
    assert captured["minimum_history_span_ms"] == 420_000
    assert captured["strict_maker_price_through"] is True
    assert captured["strategy_id"] == "WS_CAUSAL_POST_FILL_EV_V2"


def test_v19_rejects_v18_state_and_fake_client_has_no_private_order_api(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(_default_state_v18(["cheap", "rich"])))

    with pytest.raises(ValueError, match="V19"):
        v19.load_state_v19(state_path, venue_names=["cheap", "rich"])

    fake = FakePublicClient({"AAA/USDT:USDT": _raw_book(99.9, 100.1, 1_000)})
    assert not callable(getattr(fake, "create_order", None))


FUNNEL_KEYS = (
    "observed_route_occurrence",
    "feature_ready_occurrence",
    "ev_qualified_occurrence",
    "unique_candidate",
    "duplicate_rejected",
    "cooldown_rejected",
    "capacity_rejected",
    "margin_rejected",
    "depth_rejected",
    "reprice_ev_rejected",
    "pending_created",
    "no_causal_fill",
    "post_fill_rejected",
    "execution_abort",
    "paired_open",
)


def _run_candidate_funnel_case(monkeypatch, tmp_path, case):
    symbol = "AAA/USDT:USDT"
    venues = {
        "binance": _venue("binance", 99.9, 100.0),
        "okx": _venue("okx", 101.0, 101.1),
    }
    opportunity = ArbitrageOpportunity(
        symbol=symbol,
        buy_venue="binance",
        sell_venue="okx",
        target_notional=10.0,
        buy_vwap=100.0,
        sell_vwap=101.0,
        gross_edge_bps=100.0,
        total_fee_bps=10.0,
        safety_buffer_bps=0.5,
        net_edge_bps=89.5,
    )
    tradeable = {
        "decision": "PASSIVE_TRADEABLE",
        "tradeable": True,
        "expected_value_bps": 5.0,
        "minimum_required_ev_bps": 0.5,
        "capture_bps": 10.0,
        "baseline_60m_bps": 2.0,
        "baseline_15m_bps": 2.0,
        "baseline_5m_bps": 2.0,
        "route_sigma_bps": 1.0,
        "price_volatility_bps": 1.0,
        "z_score": 3.0,
        "p_open": 0.8,
        "maker_side": "LONG",
        "maker_venue": "binance",
    }
    state = v19._default_state_v19(["binance", "okx"])
    route_key = f"{symbol}|binance|okx"

    monkeypatch.setattr(v17, "_fetch_venue_books", lambda *args, **kwargs: venues)
    monkeypatch.setattr(v17, "_all_routes", lambda *args, **kwargs: [opportunity])
    monkeypatch.setattr(v17, "multi_horizon_route_features", lambda *args, **kwargs: {"ready": True})
    monkeypatch.setattr(v17, "_v17_route_decision", lambda *args, **kwargs: dict(tradeable))
    monkeypatch.setattr(v19, "select_v18_profile", lambda decision: {
        "leverage": 20.0,
        "pair_margin_fraction": 0.1,
        "pair_gross_fraction": 2.0,
    })
    monkeypatch.setattr(v19, "_process_pending_entries_v19", lambda *args, **kwargs: None)
    monkeypatch.setattr(v19, "_assert_v19_invariants", lambda state: None)

    if case == "duplicate_rejected":
        state["pending_entries"] = [{
            "position_key": route_key,
            "symbol": symbol,
            "long_exchange": "binance",
            "short_exchange": "okx",
            "long_target_notional": 10.0,
            "short_target_notional": 10.0,
            "leverage": 20.0,
        }]
    elif case == "cooldown_rejected":
        state["route_cooldowns"] = {route_key: 1_000_000}
    elif case == "maker_backoff_rejected":
        state["route_cooldowns"] = {f"maker:{symbol}|binance|LONG": 1_000_000}
    elif case == "max_positions_rejected":
        state["max_open_positions"] = 0
    elif case == "gross_cap_rejected":
        state["gross_leverage_cap"] = 0.0
    elif case == "margin_rejected":
        monkeypatch.setattr(v17, "shrink_target_notional", lambda *args, **kwargs: None)
    elif case == "depth_rejected":
        monkeypatch.setattr(v17, "evaluate_pair", lambda *args, **kwargs: None)
    elif case == "reprice_ev_rejected":
        decisions = iter((dict(tradeable), {"decision": "EV_BELOW_MIN", "tradeable": False}))
        monkeypatch.setattr(v17, "_v17_route_decision", lambda *args, **kwargs: next(decisions))

    v19.run_cycle_v19(
        clients={"binance": object(), "okx": object()},
        symbols=[symbol],
        state=state,
        history_db=tmp_path / f"{case}.sqlite",
        now_ms=1_000_000,
        now_utc="2026-08-28T00:00:00+00:00",
        journal_path=tmp_path / f"{case}.jsonl",
        symbol_venues={symbol: ("binance", "okx")},
    )
    return state


@pytest.mark.parametrize(
    ("case", "counter"),
    [
        ("duplicate_rejected", "duplicate_rejected"),
        ("cooldown_rejected", "cooldown_rejected"),
        ("maker_backoff_rejected", "cooldown_rejected"),
        ("max_positions_rejected", "capacity_rejected"),
        ("gross_cap_rejected", "capacity_rejected"),
        ("margin_rejected", "margin_rejected"),
        ("depth_rejected", "depth_rejected"),
        ("reprice_ev_rejected", "reprice_ev_rejected"),
    ],
)
def test_v19_candidate_funnel_counts_existing_rejection_branches(
    monkeypatch,
    tmp_path,
    case,
    counter,
):
    state = _run_candidate_funnel_case(monkeypatch, tmp_path, case)

    counts = state["candidate_funnel_counts"]
    assert tuple(counts) == FUNNEL_KEYS
    assert counts["observed_route_occurrence"] == 1
    assert counts["feature_ready_occurrence"] == 1
    assert counts["ev_qualified_occurrence"] == 1
    assert counts[counter] == 1
    assert counts["pending_created"] == 0


def test_v19_known_duplicate_is_not_counted_as_unique(monkeypatch, tmp_path):
    state = _run_candidate_funnel_case(monkeypatch, tmp_path, "duplicate_rejected")

    counts = state["candidate_funnel_counts"]
    assert counts["unique_candidate"] == 0
    assert counts["duplicate_rejected"] == 1


def test_v19_candidate_funnel_reconciles_created_pending(monkeypatch, tmp_path):
    state = _run_candidate_funnel_case(monkeypatch, tmp_path, "pending_created")

    counts = state["candidate_funnel_counts"]
    assert counts["ev_qualified_occurrence"] >= 1
    assert counts["unique_candidate"] == 1
    assert counts["pending_created"] == 1
    assert state["qualified_opportunity_count"] == counts["ev_qualified_occurrence"]
    assert sum(
        counts[key]
        for key in (
            "duplicate_rejected",
            "cooldown_rejected",
            "capacity_rejected",
            "margin_rejected",
            "depth_rejected",
            "reprice_ev_rejected",
            "pending_created",
        )
    ) <= counts["ev_qualified_occurrence"]


def test_v19_profitable_exit_closes_on_confirmed_taker_snapshot(tmp_path, monkeypatch):
    pending = _pending_entry()
    state = _default_state_v17(["cheap", "rich"])
    state["pending_entries"] = [pending]
    opening = {
        "cheap": _venue("cheap", 99.8, 99.9),
        "rich": _venue("rich", 106.1, 106.2, 5.5),
    }
    _process_pending_entries(
        state,
        books_by_symbol={"AAA/USDT:USDT": opening},
        stats_db=tmp_path / "stats.sqlite",
        now_ms=1_005_000,
        now_utc="2026-08-28T00:00:05+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
    )
    assert len(state["open_positions"]) == 1

    close_books = {
        "cheap": _raw_book(102.0, 102.1, 1_010_000),
        "rich": _raw_book(102.1, 102.2, 1_010_000),
    }
    clients = {name: FakePublicClient({"AAA/USDT:USDT": book}) for name, book in close_books.items()}
    monkeypatch.setattr(v17, "v16_exit_decision", lambda *args, **kwargs: "ROUTE_TARGET")

    run_cycle_v17(
        clients=clients,
        symbols=["AAA/USDT:USDT"],
        state=state,
        history_db=tmp_path / "history.sqlite",
        stats_db=tmp_path / "stats.sqlite",
        safety_buffer_bps=0.5,
        depth_limit=20,
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        max_book_age_ms=10_000,
        now_ms=1_010_000,
        now_utc="2026-08-28T00:00:10+00:00",
        journal_path=tmp_path / "positions.jsonl",
        symbol_venues={"AAA/USDT:USDT": ("cheap", "rich")},
        max_pending_entries=0,
        max_probes=0,
        exit_decision_filter=v19._confirm_v19_exit,
        strict_maker_price_through=True,
    )

    assert state["pending_exits"] == []
    assert state["open_positions"] == []
    assert state["last_close"]["close_reason"] == "ROUTE_TARGET"
    assert state["last_close"]["exit_execution_mode"] == "TAKER_FALLBACK"
    assert state["last_close"]["realized_net_pnl"] > 0.0


def test_v19_memory_guard_rejects_limit_above_host_headroom(monkeypatch):
    monkeypatch.setattr(v19, "_host_memory_limit_mb", lambda: 1_600.0, raising=False)
    with pytest.raises(ValueError, match="host memory budget"):
        v19.main(["--memory-high-water-mb", "1200", "--memory-hard-limit-mb", "1500", "--once"])


def test_v19_rejects_ignored_receive_skew_option():
    with pytest.raises(ValueError, match="receive-skew filter is disabled"):
        v19.main(["--max-book-skew-ms", "500", "--once"])


def test_v19_background_runtime_clients_do_not_share_stream_rate_limiter():
    class FakeExchange:
        def __init__(self, markets=None):
            self.markets = {} if markets is None else dict(markets)
            self.copied_markets = None

        def set_markets(self, markets):
            self.copied_markets = dict(markets)
            self.markets = dict(markets)

    stream = {"okx": FakeExchange({"AAA/USDT:USDT": {"symbol": "AAA/USDT:USDT"}})}
    dedicated = {"okx": FakeExchange()}

    v19._copy_runtime_market_metadata(stream, dedicated)

    assert dedicated["okx"] is not stream["okx"]
    assert dedicated["okx"].copied_markets == stream["okx"].markets

@pytest.mark.asyncio
async def test_threaded_runtime_refresh_uses_fresh_clients_and_closes_them():
    created = []

    class FakeExchange:
        def __init__(self):
            self.markets = {}
            self.closed = False
            created.append(self)

        def set_markets(self, markets):
            self.markets = dict(markets)

        async def close(self):
            self.closed = True

    async def refresh(*, clients, state, **kwargs):
        del kwargs
        assert clients["okx"].markets == {"AAA/USDT:USDT": {"symbol": "AAA/USDT:USDT"}}
        state["funding_snapshot_count"] = 1

    result = await __import__("asyncio").to_thread(
        v19._runtime_refresh_snapshot_in_fresh_loop,
        refresh,
        clients_factory=lambda: {"okx": FakeExchange()},
        market_metadata={"okx": {"AAA/USDT:USDT": {"symbol": "AAA/USDT:USDT"}}},
        state_snapshot={"open_positions": []},
        symbols=["AAA/USDT:USDT"],
        coverage={"AAA/USDT:USDT": ("okx",)},
        now_ms=2,
    )

    assert result["funding_snapshot_count"] == 1
    assert len(created) == 1
    assert created[0].closed is True


@pytest.mark.asyncio
async def test_public_outage_persists_reduced_coverage_before_reporting_health(monkeypatch, tmp_path):
    class Client:
        async def close(self):
            pass

    async def coverage(clients):
        return {"AAA/USDT:USDT": tuple(clients)}

    def start_watchers(*, cache, **kwargs):
        cache.update("cheap", "AAA/USDT:USDT", _raw_book(99, 100, 1))
        return []

    monkeypatch.setattr(v19, "start_public_book_watchers", start_watchers)
    args = v19._parser().parse_args([
        "--once", "--stream-warmup-seconds", "0", "--artifacts-dir", str(tmp_path),
    ])
    with pytest.raises(RuntimeError, match="warmup timed out"):
        await v19._run(args, clients_factory=lambda: {"cheap": Client(), "rich": Client()},
                       coverage_loader=coverage)
    state_path = tmp_path / "state.json"
    assert state_path.exists(), "outage metrics must reach the publisher even with fewer than two venues"
    persisted = json.loads(state_path.read_text())
    assert persisted["connected_venue_count"] == 1
    assert persisted["expected_venue_count"] == 2
    assert persisted["equity"] == 100
