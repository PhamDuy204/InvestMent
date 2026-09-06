from __future__ import annotations

import pytest

import scripts.run_arbitrage_paper_v19 as v19
from crypto_research.arbitrage_v12 import VenueBook
from crypto_research.stream_v18 import LatestBookCache
from scripts.run_arbitrage_paper_v13 import (
    _default_state,
    _fetch_venue_books,
    load_state,
    run_cycle,
    write_state,
)
from scripts.run_arbitrage_paper_v17 import _create_pending_entry


class FakePublicClient:
    def __init__(self, books):
        self.books = books
        self.public_calls = []

    def fetch_order_book(self, symbol, limit=None):
        self.public_calls.append(("fetch_order_book", symbol, limit))
        value = self.books[symbol]
        if isinstance(value, Exception):
            raise value
        return value

    def create_order(self, *args, **kwargs):  # pragma: no cover - safety boundary
        raise AssertionError("private order path must never be called")


def _book(bid, ask, *, timestamp=1_000_000, qty=10.0):
    return {"bids": [[bid, qty]], "asks": [[ask, qty]], "timestamp": timestamp}



def test_cached_books_drive_v19_strict_causal_price_through(tmp_path):
    symbol = "BTC/USDT:USDT"
    placed_at_ms = 1_000_000
    placement_venues = {
        "cheap": VenueBook(
            "cheap",
            _book(100.0, 100.1, timestamp=placed_at_ms),
            5.0,
        ),
        "rich": VenueBook(
            "rich",
            _book(100.9, 101.0, timestamp=placed_at_ms),
            5.5,
        ),
    }
    pending = _create_pending_entry(
        symbol=symbol,
        buy_venue="cheap",
        sell_venue="rich",
        venues=placement_venues,
        target_notional=10.0,
        leverage=20.0,
        pair_gross_fraction=2.0,
        decision={
            "expected_value_bps": 3.0,
            "minimum_required_ev_bps": 0.5,
            "capture_bps": 20.0,
            "baseline_60m_bps": 5.0,
            "baseline_15m_bps": 5.0,
            "baseline_5m_bps": 5.0,
            "route_sigma_bps": 3.0,
            "price_volatility_bps": 8.0,
            "p_open": 0.6,
        },
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        now_ms=placed_at_ms,
        now_utc="2026-08-29T00:00:00+00:00",
        strategy_id=v19.STRATEGY_ID,
        monotonic_ms=placed_at_ms,
    )

    cache = LatestBookCache(depth_limit=20, max_entries=8)
    cache.update(
        "cheap",
        symbol,
        _book(99.8, 99.9, timestamp=1_000_111),
        received_at_ms=1_001_000,
        received_mono_ms=1_001_000,
    )
    cache.update(
        "rich",
        symbol,
        _book(101.1, 101.2, timestamp=1_000_222),
        received_at_ms=1_001_000,
        received_mono_ms=1_001_000,
    )
    clients, _ = cache.snapshot(
        now_ms=1_001_000,
        now_mono_ms=1_001_000,
        max_age_ms=5_000,
        selected_symbols={symbol},
        require_connected=True,
    )
    venues = _fetch_venue_books(
        clients,
        symbol,
        depth_limit=20,
        fees={"cheap": 5.0, "rich": 5.5},
        max_book_age_ms=5_000,
        now_ms=1_001_000,
    )

    state = v19._default_state_v19(["cheap", "rich"])
    state["pending_entries"] = [pending]
    v19._process_pending_entries_v19(
        state,
        books_by_symbol={symbol: venues},
        stats_db=tmp_path / "stats.sqlite",
        now_ms=1_001_000,
        now_mono_ms=1_001_000,
        now_utc="2026-08-29T00:00:01+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )

    assert state["pending_entries"] == []
    assert len(state["open_positions"]) == 1
    assert state["open_positions"][0]["entry_execution_mode"] == "MAKER_MAKER"
    assert venues["cheap"].book["received_at_ms"] == 1_001_000
    assert venues["cheap"].book["received_mono_ms"] == 1_001_000

    legacy = _fetch_venue_books(
        {"cheap": FakePublicClient({symbol: _book(99.8, 99.9, timestamp=1_000_500)})},
        symbol,
        depth_limit=20,
        fees={"cheap": 5.0},
        max_book_age_ms=5_000,
        now_ms=1_001_000,
    )
    assert legacy["cheap"].book["received_mono_ms"] is None

def test_cycle_opens_once_without_marking_unrealized_edge_as_equity(tmp_path):
    symbol = "BTC/USDT:USDT"
    clients = {
        "cheap": FakePublicClient({symbol: _book(99.9, 100.0)}),
        "rich": FakePublicClient({symbol: _book(102.0, 102.1)}),
    }
    state = _default_state(20.0)
    kwargs = dict(
        clients=clients,
        symbols=[symbol],
        state=state,
        target_fraction=0.25,
        min_net_edge_bps=5.0,
        safety_buffer_bps=1.0,
        exit_threshold_bps=5.0,
        max_holding_seconds=3600.0,
        depth_limit=20,
        fee_bps={"cheap": 1.0, "rich": 1.0},
        max_book_age_ms=10_000,
        now_ms=1_000_000,
        now_utc="2026-08-27T08:00:00+00:00",
        journal_path=tmp_path / "positions.jsonl",
    )

    run_cycle(**kwargs)
    run_cycle(**kwargs)

    assert state["equity"] == 20.0
    assert state["opened_position_count"] == 1
    assert state["closed_position_count"] == 0
    assert len(state["open_positions"]) == 1
    assert state["open_positions"][0]["status"] == "OPEN"


class SequencedPublicClient(FakePublicClient):
    def __init__(self, symbol, sequence):
        super().__init__({})
        self.symbol = symbol
        self.sequence = list(sequence)

    def fetch_order_book(self, symbol, limit=None):
        self.public_calls.append(("fetch_order_book", symbol, limit))
        assert symbol == self.symbol
        return self.sequence.pop(0)


def test_cycle_closes_on_convergence_and_updates_only_realized_pnl(tmp_path):
    symbol = "BTC/USDT:USDT"
    clients = {
        "cheap": SequencedPublicClient(
            symbol,
            [_book(99.9, 100.0), _book(101.0, 101.1, timestamp=1_001_000)],
        ),
        "rich": SequencedPublicClient(
            symbol,
            [_book(102.0, 102.1), _book(100.9, 101.0, timestamp=1_001_000)],
        ),
    }
    state = _default_state(20.0)
    common = dict(
        clients=clients,
        symbols=[symbol],
        state=state,
        target_fraction=0.25,
        min_net_edge_bps=5.0,
        safety_buffer_bps=1.0,
        exit_threshold_bps=5.0,
        max_holding_seconds=3600.0,
        depth_limit=20,
        fee_bps={"cheap": 1.0, "rich": 1.0},
        max_book_age_ms=10_000,
        journal_path=tmp_path / "positions.jsonl",
    )

    run_cycle(
        **common,
        now_ms=1_000_000,
        now_utc="2026-08-27T08:00:00+00:00",
    )
    entry = dict(state["open_positions"][0])
    assert state["equity"] == 20.0

    run_cycle(
        **common,
        now_ms=1_001_000,
        now_utc="2026-08-27T08:00:01+00:00",
    )

    close = state["last_close"]
    expected_gross = entry["quantity"] * (
        (close["long_exit_vwap"] - entry["long_entry_vwap"])
        + (entry["short_entry_vwap"] - close["short_exit_vwap"])
    )
    expected_net = expected_gross - entry["entry_fees"] - close["exit_fees"]

    assert state["open_positions"] == []
    assert state["opened_position_count"] == 1
    assert state["closed_position_count"] == 1
    assert close["gross_pnl"] == pytest.approx(expected_gross)
    assert close["realized_net_pnl"] == pytest.approx(expected_net)
    assert state["realized_pnl"] == pytest.approx(expected_net)
    assert state["equity"] == pytest.approx(20.0 + expected_net)


def test_state_restart_preserves_open_positions(tmp_path):
    path = tmp_path / "state.json"
    state = _default_state(20.0)
    state["open_positions"].append(
        {
            "position_id": "p1",
            "position_key": "BTC/USDT:USDT|cheap|rich",
            "symbol": "BTC/USDT:USDT",
            "long_exchange": "cheap",
            "short_exchange": "rich",
            "quantity": 0.05,
            "opened_at": "2026-08-27T08:00:00+00:00",
            "opened_at_ms": 1_000_000,
            "long_entry_vwap": 100.0,
            "short_entry_vwap": 102.0,
            "long_entry_notional": 5.0,
            "short_entry_notional": 5.1,
            "long_fee_bps": 1.0,
            "short_fee_bps": 1.0,
            "entry_fees": 0.00101,
            "initial_net_edge_bps": 190.0,
            "status": "OPEN",
        }
    )
    state["opened_position_count"] = 1

    write_state(path, state)

    assert load_state(path) == state


def test_max_hold_closes_without_reopening_same_signal_in_same_cycle(tmp_path):
    symbol = "ETH/USDT:USDT"
    clients = {
        "cheap": SequencedPublicClient(
            symbol,
            [_book(99.9, 100.0), _book(99.9, 100.0, timestamp=1_005_000)],
        ),
        "rich": SequencedPublicClient(
            symbol,
            [_book(102.0, 102.1), _book(102.0, 102.1, timestamp=1_005_000)],
        ),
    }
    state = _default_state(20.0)
    common = dict(
        clients=clients,
        symbols=[symbol],
        state=state,
        target_fraction=0.25,
        min_net_edge_bps=5.0,
        safety_buffer_bps=1.0,
        exit_threshold_bps=5.0,
        max_holding_seconds=1.0,
        depth_limit=20,
        fee_bps={"cheap": 1.0, "rich": 1.0},
        max_book_age_ms=10_000,
        journal_path=tmp_path / "positions.jsonl",
    )

    run_cycle(**common, now_ms=1_000_000, now_utc="2026-08-27T08:00:00+00:00")
    run_cycle(**common, now_ms=1_005_000, now_utc="2026-08-27T08:00:05+00:00")

    assert state["closed_position_count"] == 1
    assert state["opened_position_count"] == 1
    assert state["open_positions"] == []
    assert state["last_close"]["close_reason"] == "MAX_HOLD"


def test_stale_close_book_keeps_open_position_unchanged(tmp_path):
    symbol = "SOL/USDT:USDT"
    clients = {
        "cheap": SequencedPublicClient(
            symbol,
            [_book(99.9, 100.0), _book(101.0, 101.1, timestamp=1_020_000)],
        ),
        "rich": SequencedPublicClient(
            symbol,
            [_book(102.0, 102.1), _book(100.9, 101.0, timestamp=900_000)],
        ),
    }
    state = _default_state(20.0)
    common = dict(
        clients=clients,
        symbols=[symbol],
        state=state,
        target_fraction=0.25,
        min_net_edge_bps=5.0,
        safety_buffer_bps=1.0,
        exit_threshold_bps=5.0,
        max_holding_seconds=3600.0,
        depth_limit=20,
        fee_bps={"cheap": 1.0, "rich": 1.0},
        max_book_age_ms=10_000,
        journal_path=tmp_path / "positions.jsonl",
    )

    run_cycle(**common, now_ms=1_000_000, now_utc="2026-08-27T08:00:00+00:00")
    before = dict(state["open_positions"][0])
    run_cycle(**common, now_ms=1_020_000, now_utc="2026-08-27T08:00:20+00:00")

    assert state["open_positions"] == [before]
    assert state["closed_position_count"] == 0
    assert state["equity"] == 20.0


def test_health_file_uses_v13_schema(tmp_path):
    import json

    from scripts.run_arbitrage_paper_v13 import _write_health

    path = tmp_path / "health.json"
    _write_health(path, status="HEALTHY")

    assert json.loads(path.read_text())["schema_version"] == "v13-arbitrage-health-1"


def test_invalid_close_depth_does_not_corrupt_open_position(tmp_path):
    symbol = "XRP/USDT:USDT"
    bad = {"bids": [], "asks": [], "timestamp": 1_001_000}
    clients = {
        "cheap": SequencedPublicClient(symbol, [_book(99.9, 100.0), bad]),
        "rich": SequencedPublicClient(
            symbol,
            [_book(102.0, 102.1), _book(100.9, 101.0, timestamp=1_001_000)],
        ),
    }
    state = _default_state(20.0)
    common = dict(
        clients=clients,
        symbols=[symbol],
        state=state,
        target_fraction=0.25,
        min_net_edge_bps=5.0,
        safety_buffer_bps=1.0,
        exit_threshold_bps=5.0,
        max_holding_seconds=3600.0,
        depth_limit=20,
        fee_bps={"cheap": 1.0, "rich": 1.0},
        max_book_age_ms=10_000,
        journal_path=tmp_path / "positions.jsonl",
    )

    run_cycle(**common, now_ms=1_000_000, now_utc="2026-08-27T08:00:00+00:00")
    before = dict(state["open_positions"][0])
    run_cycle(**common, now_ms=1_001_000, now_utc="2026-08-27T08:00:01+00:00")

    assert state["open_positions"] == [before]
    assert state["closed_position_count"] == 0
    assert state["equity"] == 20.0
