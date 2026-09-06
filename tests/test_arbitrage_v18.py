from __future__ import annotations

import json
from pathlib import Path

import pytest

from crypto_research.arbitrage_v12 import VenueBook
from scripts.run_arbitrage_paper_v17 import _create_pending_entry
from scripts.run_arbitrage_paper_v18 import (
    _assert_v18_invariants,
    _confirm_v18_exit,
    _default_state_v18,
    _mark_open_positions_v18,
    _process_pending_entries_v18,
)


def _venue(name: str, bid: float, ask: float, fee: float = 5.0, qty: float = 100.0, timestamp: int = 1_000_500):
    return VenueBook(name, {"bids": [[bid, qty]], "asks": [[ask, qty]], "timestamp": timestamp}, fee)


def _pending(now_ms: int = 1_000_000, leverage: float = 40.0):
    placed = {
        "cheap": _venue("cheap", 99.9, 100.0),
        "rich": _venue("rich", 106.0, 106.1, 5.5),
    }
    pending = _create_pending_entry(
        symbol="AAA/USDT:USDT",
        buy_venue="cheap",
        sell_venue="rich",
        venues=placed,
        target_notional=200.0,
        leverage=leverage,
        pair_gross_fraction=4.0,
        decision={
            "expected_value_bps": 12.0,
            "minimum_required_ev_bps": 0.5,
            "capture_bps": 30.0,
            "baseline_60m_bps": 5.0,
            "baseline_15m_bps": 5.0,
            "baseline_5m_bps": 6.0,
            "route_sigma_bps": 3.0,
            "price_volatility_bps": 8.0,
            "p_open": 0.6,
            "expected_exit_fee_bps": 6.0,
            "expected_exit_price_improvement_bps": 1.0,
            "adverse_selection_bps": 0.5,
        },
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        now_ms=now_ms,
        now_utc="2026-08-28T00:00:00+00:00",
        strategy_id="WS_CAUSAL_POST_FILL_EV_V1",
    )
    return pending



def test_pending_maker_fill_requires_a_book_received_after_order_placement(tmp_path: Path):
    pending = _pending(now_ms=1_000_000)
    state = _default_state_v18(["cheap", "rich"])
    state["pending_entries"] = [pending]
    # Prices touch the resting maker, but both snapshots predate the paper order.
    same_snapshot = {
        "cheap": VenueBook("cheap", {"bids": [[99.8, 100.0]], "asks": [[99.9, 100.0]], "timestamp": 999_900}, 5.0),
        "rich": VenueBook("rich", {"bids": [[99.95, 100.0]], "asks": [[100.05, 100.0]], "timestamp": 999_900}, 5.5),
    }

    _process_pending_entries_v18(
        state,
        books_by_symbol={"AAA/USDT:USDT": same_snapshot},
        stats_db=tmp_path / "history.sqlite",
        now_ms=1_000_500,
        now_utc="2026-08-28T00:00:00.500000+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
    )

    assert state["pending_entries"] == [pending]
    assert state["open_positions"] == []
    assert state["maker_fill_observation_count"] == 0
    assert state["one_leg_abort_count"] == 0

def test_one_leg_fill_with_negative_actual_ev_unwinds_and_never_opens(tmp_path: Path):
    pending = _pending()
    state = _default_state_v18(["cheap", "rich"])
    state["pending_entries"] = [pending]
    # Long maker touches, but the rich bid has collapsed: the stale placement EV is gone.
    later = {
        "cheap": _venue("cheap", 99.8, 99.9),
        "rich": _venue("rich", 99.95, 100.05, 5.5),
    }

    _process_pending_entries_v18(
        state,
        books_by_symbol={"AAA/USDT:USDT": later},
        stats_db=tmp_path / "history.sqlite",
        now_ms=1_000_500,
        now_utc="2026-08-28T00:00:00.500000+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
    )

    assert state["pending_entries"] == []
    assert state["open_positions"] == []
    assert state["post_fill_reject_count"] == 1
    assert state["one_leg_abort_count"] == 1
    assert state["one_leg_abort_pnl"] < 0.0
    assert state["equity"] == pytest.approx(100.0 + state["one_leg_abort_pnl"])
    event = json.loads((tmp_path / "positions.jsonl").read_text().splitlines()[-1])
    assert event["record_type"] == "PAPER_ONE_LEG_ABORT"
    assert event["post_fill_decision"] == "POST_FILL_EV_REJECTED"
    assert event["realized_net_pnl"] == pytest.approx(state["one_leg_abort_pnl"])


def test_positive_actual_post_fill_ev_opens_with_actual_capture_and_40x(tmp_path: Path):
    pending = _pending()
    state = _default_state_v18(["cheap", "rich"])
    state["pending_entries"] = [pending]
    later = {
        "cheap": _venue("cheap", 99.8, 99.9),
        "rich": _venue("rich", 106.0, 106.05, 5.5),
    }

    _process_pending_entries_v18(
        state,
        books_by_symbol={"AAA/USDT:USDT": later},
        stats_db=tmp_path / "history.sqlite",
        now_ms=1_000_500,
        now_utc="2026-08-28T00:00:00.500000+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
    )

    position = state["open_positions"][0]
    assert position["entry_execution_mode"] == "MAKER_TAKER_HEDGE"
    assert position["leverage"] == pytest.approx(40.0)
    assert position["entry_capture_bps"] == pytest.approx(position["actual_capture_bps"])
    assert position["entry_capture_bps"] != pytest.approx(30.0)
    assert position["entry_expected_value_bps"] == pytest.approx(position["post_fill_expected_value_bps"])
    # The maker may rest for 500 ms, but the taker hedge is simulated from the
    # same causal book snapshot that revealed the fill, not from placement time.
    assert position["entry_hedge_delay_ms"] == 0
    assert position["entry_maker_wait_ms"] == 500
    _assert_v18_invariants(state)


def test_post_fill_gate_does_not_reuse_optimistic_maker_exit_assumptions(tmp_path: Path):
    pending = _pending()
    pending["expected_exit_fee_bps"] = 0.0
    pending["expected_exit_price_improvement_bps"] = 1_000.0
    pending["adverse_selection_bps"] = 0.0
    state = _default_state_v18(["cheap", "rich"])
    state["pending_entries"] = [pending]
    # The long maker fills but the actual capture is only marginally positive.
    later = {
        "cheap": _venue("cheap", 99.8, 99.9),
        "rich": _venue("rich", 100.07, 100.17, 5.5),
    }

    _process_pending_entries_v18(
        state,
        books_by_symbol={"AAA/USDT:USDT": later},
        stats_db=tmp_path / "history.sqlite",
        now_ms=1_000_500,
        now_utc="2026-08-28T00:00:00.500000+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
    )

    assert state["open_positions"] == []
    assert state["post_fill_reject_count"] == 1
    event = json.loads((tmp_path / "positions.jsonl").read_text().splitlines()[-1])
    assert event["post_fill_expected_value_bps"] < 0.0


def test_one_leg_fill_with_unhedgeable_depth_unwinds_immediately(tmp_path: Path):
    pending = _pending()
    state = _default_state_v18(["cheap", "rich"])
    state["pending_entries"] = [pending]
    # Long maker fills, but the short venue cannot hedge the requested quantity.
    # The filled leg must be unwound now instead of remaining directionally naked.
    later = {
        "cheap": _venue("cheap", 99.8, 99.9, qty=100.0, timestamp=1_000_500),
        "rich": _venue("rich", 106.0, 106.05, 5.5, qty=0.000001, timestamp=1_000_500),
    }

    _process_pending_entries_v18(
        state,
        books_by_symbol={"AAA/USDT:USDT": later},
        stats_db=tmp_path / "history.sqlite",
        now_ms=1_000_500,
        now_utc="2026-08-28T00:00:00.500000+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
    )

    assert state["pending_entries"] == []
    assert state["open_positions"] == []
    assert state["one_leg_abort_count"] == 1
    assert state["maker_hedge_failure_count"] == 1
    event = json.loads((tmp_path / "positions.jsonl").read_text().splitlines()[-1])
    assert event["record_type"] == "PAPER_ONE_LEG_ABORT"
    assert event["abort_reason"] == "HEDGE_DEPTH_UNAVAILABLE"

def test_post_fill_ev_uses_runtime_safety_buffer(tmp_path: Path):
    pending = _pending()
    state = _default_state_v18(["cheap", "rich"])
    state["safety_buffer_bps"] = 1_000.0
    state["pending_entries"] = [pending]
    later = {
        "cheap": _venue("cheap", 99.8, 99.9),
        "rich": _venue("rich", 106.0, 106.05, 5.5),
    }

    _process_pending_entries_v18(
        state,
        books_by_symbol={"AAA/USDT:USDT": later},
        stats_db=tmp_path / "history.sqlite",
        now_ms=1_000_500,
        now_utc="2026-08-28T00:00:00.500000+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
    )

    assert state["open_positions"] == []
    assert state["post_fill_reject_count"] == 1


def test_v18_persists_live_marks_from_the_causal_snapshot():
    state = _default_state_v18(["okx", "bybit"])
    state["open_positions"] = [{
        "position_id": "p1", "symbol": "AAA/USDT:USDT",
        "long_exchange": "okx", "short_exchange": "bybit", "quantity": 1.0,
        "opened_at": "2026-08-28T00:00:00+00:00",
        "long_entry_vwap": 100.0, "short_entry_vwap": 102.0,
        "long_entry_notional": 100.0, "short_entry_notional": 102.0,
        "entry_fees": 0.02, "long_fee_bps": 2.0, "short_fee_bps": 2.0,
        "margin_model": "CROSS_MARGIN_PAPER_V1",
    }]
    clients = {
        "okx": _venue("okx", 101.0, 101.1),
        "bybit": _venue("bybit", 101.4, 101.5),
    }

    _mark_open_positions_v18(state, clients, marked_at_utc="2026-08-28T00:00:01+00:00")

    position = state["open_positions"][0]
    assert position["mark_status"] == "LIVE"
    assert position["estimated_net_pnl_if_closed"] > 0.0
    assert position["mark_updated_at_utc"] == "2026-08-28T00:00:01+00:00"


def test_v18_state_is_high_leverage_paper_only():
    state = _default_state_v18(["cheap", "rich"])

    assert state["schema_version"] == "v18-arbitrage-paper-1"
    assert state["portfolio_model"] == "WS_CAUSAL_POST_FILL_EV_V1"
    assert state["min_position_leverage"] == pytest.approx(20.0)
    assert state["max_position_leverage"] == pytest.approx(40.0)
    assert state["gross_leverage_cap"] == pytest.approx(40.0)
    assert state["post_fill_reject_count"] == 0
    assert state["one_leg_abort_count"] == 0


def test_divergence_exit_requires_three_fresh_confirmations_and_resets():
    state = _default_state_v18(["cheap", "rich"])
    position = {"position_id": "p1"}

    assert _confirm_v18_exit(state, position, "DIVERGENCE_STOP", now_ms=1_000) is None
    assert _confirm_v18_exit(state, position, "DIVERGENCE_STOP", now_ms=1_500) is None
    assert _confirm_v18_exit(state, position, None, now_ms=1_750) is None
    assert _confirm_v18_exit(state, position, "DIVERGENCE_STOP", now_ms=2_000) is None
    assert _confirm_v18_exit(state, position, "DIVERGENCE_STOP", now_ms=2_500) is None
    assert _confirm_v18_exit(state, position, "DIVERGENCE_STOP", now_ms=3_000) == "DIVERGENCE_STOP"


def test_profitable_or_timeout_exit_is_not_delayed():
    state = _default_state_v18(["cheap", "rich"])
    position = {"position_id": "p1"}

    assert _confirm_v18_exit(state, position, "ROUTE_TARGET", now_ms=1_000) == "ROUTE_TARGET"
    assert _confirm_v18_exit(state, position, "ADAPTIVE_TIMEOUT", now_ms=1_100) == "ADAPTIVE_TIMEOUT"
