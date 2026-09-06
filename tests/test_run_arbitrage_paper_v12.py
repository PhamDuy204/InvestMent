from __future__ import annotations

from scripts.run_arbitrage_paper_v12 import (
    DEFAULT_FEE_BPS,
    common_linear_usdt_symbols,
    linear_usdt_symbol_venues,
    load_state,
    make_public_clients,
    run_scan,
    write_state,
)


class FakePublicClient:
    def __init__(self, markets, books):
        self._markets = markets
        self._books = books
        self.public_calls = []

    def load_markets(self):
        self.public_calls.append(("load_markets",))
        return self._markets

    def fetch_order_book(self, symbol, limit=None):
        self.public_calls.append(("fetch_order_book", symbol, limit))
        return self._books[symbol]

    def create_order(self, *args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("private order path must never be called")


class UnavailablePublicClient(FakePublicClient):
    def load_markets(self):
        self.public_calls.append(("load_markets",))
        raise RuntimeError("venue unavailable")


def _market(symbol, *, swap=True, linear=True, active=True, quote="USDT", settle="USDT"):
    return {
        "symbol": symbol,
        "swap": swap,
        "linear": linear,
        "active": active,
        "quote": quote,
        "settle": settle,
    }


def _book(bid, ask, qty=10.0):
    return {"bids": [[bid, qty]], "asks": [[ask, qty]]}


def test_common_symbols_keeps_only_active_linear_usdt_perpetuals():
    btc = "BTC/USDT:USDT"
    eth = "ETH/USDT:USDT"
    clients = {
        "binance": FakePublicClient(
            {
                btc: _market(btc),
                eth: _market(eth),
                "BTC/USDT": _market("BTC/USDT", swap=False),
            },
            {},
        ),
        "okx": FakePublicClient({btc: _market(btc), eth: _market(eth, active=False)}, {}),
        "mexc": FakePublicClient({btc: _market(btc), eth: _market(eth)}, {}),
    }

    assert common_linear_usdt_symbols(clients, limit=20) == [btc]


def test_symbol_venues_keeps_symbols_listed_on_any_two_available_venues():
    btc = "BTC/USDT:USDT"
    eth = "ETH/USDT:USDT"
    clients = {
        "binance": FakePublicClient({btc: _market(btc)}, {}),
        "okx": FakePublicClient({btc: _market(btc), eth: _market(eth)}, {}),
        "mexc": FakePublicClient({btc: _market(btc), eth: _market(eth)}, {}),
    }

    assert linear_usdt_symbol_venues(clients, min_venues=2) == {
        btc: ("binance", "mexc", "okx"),
        eth: ("mexc", "okx"),
    }


def test_common_symbols_survives_one_unavailable_venue():
    btc = "BTC/USDT:USDT"
    clients = {
        "binance": UnavailablePublicClient({}, {}),
        "okx": FakePublicClient({btc: _market(btc)}, {}),
        "mexc": FakePublicClient({btc: _market(btc)}, {}),
    }

    assert common_linear_usdt_symbols(clients, limit=20) == [btc]


def test_run_scan_uses_public_books_and_returns_profitable_opportunity():
    symbol = "BTC/USDT:USDT"
    clients = {
        "binance": FakePublicClient({}, {symbol: _book(99.9, 100.0)}),
        "okx": FakePublicClient({}, {symbol: _book(102.0, 102.1)}),
        "mexc": FakePublicClient({}, {symbol: _book(100.5, 100.6)}),
    }

    opportunities = run_scan(
        clients,
        [symbol],
        equity=20.0,
        target_fraction=0.25,
        min_net_edge_bps=5.0,
        safety_buffer_bps=1.0,
        depth_limit=20,
        fee_bps={"binance": 1.0, "okx": 1.0, "mexc": 1.0},
    )

    assert len(opportunities) == 1
    assert opportunities[0].buy_venue == "binance"
    assert opportunities[0].sell_venue == "okx"
    for client in clients.values():
        assert client.public_calls == [("fetch_order_book", symbol, 20)]


def test_state_defaults_to_twenty_dollars_and_round_trips(tmp_path):
    path = tmp_path / "state.json"

    state = load_state(path)
    assert state["initial_equity"] == 20.0
    assert state["equity"] == 20.0
    assert state["accepted_opportunity_count"] == 0
    assert state["best_net_edge_bps_seen"] is None

    state["accepted_opportunity_count"] = 1
    state["best_net_edge_bps_seen"] = 12.5
    write_state(path, state)

    assert load_state(path) == state


def test_extended_public_clients_add_compatible_read_only_derivatives_venues():
    base = make_public_clients()
    extended = make_public_clients(include_extended=True)
    try:
        assert set(base) == {"binance", "okx", "mexc"}
        assert set(extended) == {"binance", "okx", "mexc", "bybit", "bitget", "kucoin", "gate"}
        assert "hyperliquid" not in extended
        assert DEFAULT_FEE_BPS["bybit"] == 5.5
        assert DEFAULT_FEE_BPS["bitget"] == 6.0
        assert DEFAULT_FEE_BPS["kucoin"] == 6.0
        assert DEFAULT_FEE_BPS["gate"] == 5.0
    finally:
        for client in [*base.values(), *extended.values()]:
            close = getattr(client, "close", None)
            if callable(close):
                close()
