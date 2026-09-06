from __future__ import annotations

import asyncio

import pytest

from crypto_research.stream_v18 import (
    CachedPublicClient,
    LatestBookCache,
    compact_public_stream_markets,
    make_public_stream_clients,
    start_public_book_watchers,
    start_public_trade_watchers,
    stream_subscription_limit,
    watch_public_book,
    watch_public_books,
    watch_public_trades,
)


@pytest.mark.parametrize("futures", [False, True])
def test_kucoin_expired_public_token_rejects_waiters_and_renegotiates_once(monkeypatch, futures):
    from ccxt.base.errors import AuthenticationError

    async def run_case():
        clients = make_public_stream_clients()
        exchange = clients["kucoin"]
        exchange.open()
        calls = 0
        waiter = None

        async def public_token(params):
            nonlocal calls
            assert params == {}
            calls += 1
            return {"code": "200000", "data": {
                "token": f"test-public-token-{calls}",
                "instanceServers": [{"endpoint": "wss://public.example.invalid",
                                     "pingInterval": 18000, "pingTimeout": 10000}],
            }}

        monkeypatch.setattr(exchange, "publicPostBulletPublic", public_token)
        monkeypatch.setattr(exchange, "futuresPublicPostBulletPublic", public_token)
        try:
            old_url = await exchange.negotiate(False, futures)
            socket = exchange.client(old_url)
            waiter = socket.future("orderbook:AAA/USDT:USDT")
            leaked = None
            expired = {"type": "error", "code": 401, "data": "token is expired"}
            try:
                exchange.handle_message(socket, expired)
            except Exception as exc:
                leaked = exc
            assert leaked is None, "expiry must reach watch waiters, not escape the receive callback"
            with pytest.raises(AuthenticationError):
                await asyncio.wait_for(waiter, 1)
            assert old_url not in exchange.clients
            urls = await asyncio.gather(exchange.negotiate(False, futures), exchange.negotiate(False, futures))
            assert urls[0] == urls[1] and urls[0] != old_url
            assert calls == 2, "concurrent watchers must share one public token refresh"
            # A buffered error from the retired socket must not evict the new token.
            exchange.handle_message(socket, expired)
            assert await exchange.negotiate(False, futures) == urls[0]
            assert calls == 2
        finally:
            if waiter is not None:
                waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)
            await asyncio.gather(*(client.close() for client in clients.values()))

    asyncio.run(run_case())


def _book(timestamp: int, *, bid: float = 99.0, ask: float = 101.0):
    return {
        "bids": [[bid - index, 1.0] for index in range(5)],
        "asks": [[ask + index, 1.0] for index in range(5)],
        "timestamp": timestamp,
        "symbol": "AAA/USDT:USDT",
    }


def test_cache_uses_receive_time_and_rejects_stale_or_future_exchange_timestamps():
    cache = LatestBookCache(depth_limit=2, max_entries=4)
    cache.update("okx", "AAA/USDT:USDT", _book(9_999_999), received_at_ms=1_000)

    clients, metrics = cache.snapshot(now_ms=2_600, max_age_ms=1_500)

    assert clients == {}
    assert metrics["stale_book_count"] == 1
    assert metrics["fresh_book_count"] == 0


def test_cache_freshness_uses_monotonic_receive_clock_across_wall_clock_jump():
    cache = LatestBookCache(depth_limit=2, max_entries=4)
    cache.update(
        "okx",
        "AAA/USDT:USDT",
        _book(999_999),
        received_at_ms=10_000,
        received_mono_ms=1_000,
    )

    clients, metrics = cache.snapshot(
        now_ms=5_000,
        now_mono_ms=1_100,
        max_age_ms=1_500,
    )

    book = clients["okx"].fetch_order_book("AAA/USDT:USDT")
    assert book["received_at_ms"] == 10_000
    assert book["received_mono_ms"] == 1_000
    assert metrics["book_age_ms_max"] == 100


def test_public_trade_cache_dedupes_and_exposes_cumulative_base_volume():
    cache = LatestBookCache(depth_limit=1, max_entries=4)
    symbol = "BTC/USDT:USDT"
    cache.update("okx", symbol, _book(1_000), received_at_ms=1_000, received_mono_ms=1_000)
    assert cache.record_public_trade(
        "okx", symbol, trade_id="t1", side="sell", price=99.0, amount_base=0.5, received_mono_ms=1_010
    ) is True
    assert cache.record_public_trade(
        "okx", symbol, trade_id="t1", side="sell", price=99.0, amount_base=0.5, received_mono_ms=1_011
    ) is False
    assert cache.record_public_trade(
        "okx", symbol, trade_id="t2", side="sell", price=99.0, amount_base=0.25, received_mono_ms=1_012
    ) is True

    clients, metrics = cache.snapshot(now_ms=1_020, now_mono_ms=1_020, max_age_ms=1_500)
    book = clients["okx"].fetch_order_book(symbol)
    assert book["_public_trade_volume_by_side_price"][("sell", 99.0)] == pytest.approx(0.75)
    assert metrics["public_trade_update_count"] == 2
    assert metrics["public_trade_update_counts_by_venue"] == {"okx": 2}


def test_snapshot_is_immutable_and_depth_bounded():
    cache = LatestBookCache(depth_limit=2, max_entries=4)
    raw = _book(1_000)
    cache.update("okx", "AAA/USDT:USDT", raw, received_at_ms=1_000)
    raw["bids"][0][0] = 1.0

    clients, metrics = cache.snapshot(now_ms=1_100, max_age_ms=1_500)
    first = clients["okx"].fetch_order_book("AAA/USDT:USDT")
    first["bids"][0][0] = 2.0
    second = clients["okx"].fetch_order_book("AAA/USDT:USDT")

    assert second["bids"] == [[99.0, 1.0], [98.0, 1.0]]
    assert len(second["asks"]) == 2
    assert second["timestamp"] == 1_000
    assert metrics["fresh_book_count"] == 1
    assert metrics["cache_entry_count"] == 1


def test_stream_error_window_expires_without_erasing_session_counters(monkeypatch):
    cache = LatestBookCache()
    monkeypatch.setattr("crypto_research.stream_v18.time.monotonic", lambda: 100.0)
    cache.record_stream_error("kucoin", "AAA", ConnectionError("closed"))
    cache.record_stream_error("kucoin", "BBB", ConnectionError("closed"))
    _, recent = cache.snapshot(now_ms=100_000, now_mono_ms=100_000)
    assert recent.get("stream_errors_last_60s_by_venue") == {"kucoin": 2}
    _, expired = cache.snapshot(now_ms=161_000, now_mono_ms=161_000)
    assert expired.get("stream_errors_last_60s_by_venue") == {"kucoin": 0}
    assert expired["stream_error_counts_by_venue"] == {"kucoin": {"ConnectionError": 2}}



def test_snapshot_rejects_cross_venue_books_outside_receive_time_skew():
    cache = LatestBookCache(depth_limit=1, max_entries=4)
    symbol = "AAA/USDT:USDT"
    cache.update("okx", symbol, _book(9_999_999), received_at_ms=2_000)
    cache.update("bybit", symbol, _book(1), received_at_ms=1_200)

    clients, metrics = cache.snapshot(now_ms=2_100, max_age_ms=1_500, max_skew_ms=500)

    assert set(clients) == {"okx"}
    assert clients["okx"].symbols == {symbol}
    assert metrics["fresh_book_count"] == 1
    assert metrics["stale_book_count"] == 1

def test_cache_evicts_oldest_entry_at_fixed_capacity():
    cache = LatestBookCache(depth_limit=1, max_entries=2)
    cache.update("okx", "A/USDT:USDT", _book(1_000), received_at_ms=1_000)
    cache.update("okx", "B/USDT:USDT", _book(1_100), received_at_ms=1_100)
    cache.update("bybit", "C/USDT:USDT", _book(1_200), received_at_ms=1_200)

    clients, metrics = cache.snapshot(now_ms=1_300, max_age_ms=1_500)

    assert "A/USDT:USDT" not in clients.get("okx", CachedPublicClient("okx", {})).symbols
    assert metrics["cache_entry_count"] == 2
    assert metrics["eviction_count"] == 1



def test_subscription_limits_use_compact_public_channels_without_weakening_cache_depth():
    assert stream_subscription_limit("bybit", 20) == 50
    assert stream_subscription_limit("okx", 20) == 5
    assert stream_subscription_limit("bitget", 20) == 15
    assert stream_subscription_limit("binance", 20) == 20

def test_cached_client_raises_for_unsubscribed_symbol():
    client = CachedPublicClient("okx", {})
    with pytest.raises(KeyError):
        client.fetch_order_book("MISSING/USDT:USDT")


def test_memory_pressure_prunes_only_stale_books():
    cache = LatestBookCache(depth_limit=1, max_entries=4)
    cache.update("okx", "OLD/USDT:USDT", _book(1_000), received_at_ms=1_000)
    cache.update("bybit", "LIVE/USDT:USDT", _book(2_900), received_at_ms=2_900)

    assert cache.prune_stale(now_ms=3_000, max_age_ms=1_500) == 1
    clients, metrics = cache.snapshot(now_ms=3_000, max_age_ms=1_500)

    assert set(clients) == {"bybit"}
    assert clients["bybit"].symbols == {"LIVE/USDT:USDT"}
    assert metrics["cache_entry_count"] == 1


def test_compact_public_stream_markets_keeps_only_selected_symbols():
    class FakeExchange:
        def __init__(self):
            self.markets = {
                "A/USDT:USDT": {"symbol": "A/USDT:USDT", "id": "AUSDT", "base": "A", "quote": "USDT"},
                "B/USDT:USDT": {"symbol": "B/USDT:USDT", "id": "BUSDT", "base": "B", "quote": "USDT"},
                "C/USDT:USDT": {"symbol": "C/USDT:USDT", "id": "CUSDT", "base": "C", "quote": "USDT"},
            }
            self.currencies = {"A": {}, "B": {}, "C": {}, "USDT": {}}
            self.markets_by_id = {market["id"]: [market] for market in self.markets.values()}
            self.symbols = list(self.markets)
            self.ids = list(self.markets_by_id)
            self.currencies_by_id = dict(self.currencies)
            self.baseCurrencies = {"A": {}, "B": {}, "C": {}}
            self.quoteCurrencies = {"USDT": {}}
            self.codes = list(self.currencies)

        def set_markets(self, markets, currencies=None):
            del currencies
            self.markets = dict(markets)
            self.symbols = sorted(self.markets)
            self.markets_by_id = {market["id"]: [market] for market in self.markets.values()}
            self.ids = sorted(self.markets_by_id)
            return self.markets

    exchange = FakeExchange()

    kept = compact_public_stream_markets(
        {"fake": exchange},
        {"A/USDT:USDT": ("fake",), "C/USDT:USDT": ("other",)},
    )

    assert kept == 1
    assert exchange.symbols == ["A/USDT:USDT"]
    assert set(exchange.markets) == {"A/USDT:USDT"}
    assert exchange.currencies == {}



def test_snapshot_materializes_only_selected_symbols_but_counts_full_cache():
    cache = LatestBookCache(depth_limit=2, max_entries=400)
    for index in range(50):
        for venue in ("a", "b", "c", "d", "e", "f", "g"):
            cache.update(
                venue,
                f"S{index}",
                _book(10_000),
                received_at_ms=10_000,
                received_mono_ms=10_000,
            )

    clients, metrics = cache.snapshot(
        now_ms=10_100,
        now_mono_ms=10_100,
        max_age_ms=5_000,
        max_skew_ms=None,
        selected_symbols={"S1", "S2"},
    )

    assert metrics["cache_entry_count"] == 350
    assert metrics["fresh_book_count"] == 350
    assert metrics["connected_venue_count"] == 7
    assert sum(len(client.symbols) for client in clients.values()) == 14


def test_snapshot_accepts_bounded_age_books_when_receive_skew_is_disabled():
    cache = LatestBookCache(depth_limit=1, max_entries=4)
    symbol = "AAA/USDT:USDT"
    cache.update(
        "okx",
        symbol,
        _book(9_999_999),
        received_at_ms=2_000,
        received_mono_ms=2_000,
    )
    cache.update(
        "bybit",
        symbol,
        _book(1),
        received_at_ms=1_200,
        received_mono_ms=1_200,
    )

    clients, metrics = cache.snapshot(
        now_ms=2_100,
        now_mono_ms=2_100,
        max_age_ms=1_500,
        max_skew_ms=None,
    )

    assert set(clients) == {"okx", "bybit"}
    assert metrics["fresh_book_count"] == 2
    assert metrics["age_expired_book_count"] == 0
    assert metrics["skew_rejected_book_count"] == 0


def test_stream_errors_are_separate_from_age_expiry_and_update_reconnects():
    cache = LatestBookCache(depth_limit=1, max_entries=4)
    expired = "OLD/USDT:USDT"
    disconnected = "LIVE/USDT:USDT"
    cache.update(
        "okx",
        expired,
        _book(1_000),
        received_at_ms=1_000,
        received_mono_ms=1_000,
    )
    cache.update(
        "bybit",
        disconnected,
        _book(2_900),
        received_at_ms=2_900,
        received_mono_ms=2_900,
    )
    cache.record_stream_error("bybit", disconnected, RuntimeError("credential-like-secret"))

    clients, metrics = cache.snapshot(
        now_ms=3_000,
        now_mono_ms=3_000,
        max_age_ms=1_500,
        max_skew_ms=None,
        require_connected=True,
    )

    assert clients == {}
    assert metrics["age_expired_book_count"] == 1
    assert metrics["skew_rejected_book_count"] == 0
    assert metrics["disconnected_book_count"] == 1
    assert metrics["stream_error_counts"] == {"RuntimeError": 1}
    assert metrics["stream_error_counts_by_venue"] == {"bybit": {"RuntimeError": 1}}
    assert "credential-like-secret" not in repr(metrics)

    cache.update(
        "bybit",
        disconnected,
        _book(3_000),
        received_at_ms=3_000,
        received_mono_ms=3_000,
    )
    clients, metrics = cache.snapshot(
        now_ms=3_100,
        now_mono_ms=3_100,
        max_age_ms=1_500,
        max_skew_ms=None,
        require_connected=True,
    )

    assert clients["bybit"].symbols == {disconnected}
    assert metrics["disconnected_book_count"] == 0
    assert metrics["stream_error_counts"] == {"RuntimeError": 1}


def test_snapshot_remains_isolated_after_cache_replaces_a_book():
    cache = LatestBookCache(depth_limit=1, max_entries=4)
    symbol = "AAA/USDT:USDT"
    cache.update("okx", symbol, _book(1_000, bid=99.0), received_at_ms=1_000)
    clients, _ = cache.snapshot(now_ms=1_100, max_age_ms=1_500)

    cache.update("okx", symbol, _book(1_200, bid=88.0), received_at_ms=1_200)

    assert clients["okx"].fetch_order_book(symbol)["bids"] == [[99.0, 1.0]]


def test_watcher_records_the_exact_stream_error_type():
    class StreamFailure(Exception):
        pass

    stop_event = asyncio.Event()

    class FailingExchange:
        async def watch_order_book(self, symbol, limit):
            del symbol, limit
            stop_event.set()
            raise StreamFailure("do-not-export-this-message")

    cache = LatestBookCache(depth_limit=1, max_entries=4)
    symbol = "AAA/USDT:USDT"
    cache.update("okx", symbol, _book(1_000), received_at_ms=1_000)

    asyncio.run(
        watch_public_book(
            "okx",
            FailingExchange(),
            symbol,
            cache,
            stop_event,
            depth_limit=1,
        )
    )
    clients, metrics = cache.snapshot(
        now_ms=1_100,
        max_age_ms=1_500,
        max_skew_ms=None,
        require_connected=True,
    )

    assert clients == {}
    assert metrics["stream_error_counts"] == {"StreamFailure": 1}
    assert "do-not-export-this-message" not in repr(metrics)



def test_stream_health_uses_exact_keys_when_export_labels_collide():
    cache = LatestBookCache(depth_limit=1, max_entries=4)
    venue = "collision-venue"
    failed_symbol = "A?B"
    healthy_symbol = "A_B"
    cache.update(venue, failed_symbol, _book(1_000), received_at_ms=1_000)
    cache.update(venue, healthy_symbol, _book(1_000), received_at_ms=1_000)

    cache.record_stream_error(venue, failed_symbol, RuntimeError("failed"))
    clients, metrics = cache.snapshot(
        now_ms=1_100,
        max_age_ms=1_500,
        max_skew_ms=None,
        require_connected=True,
    )

    assert clients[venue].symbols == {healthy_symbol}
    assert metrics["disconnected_book_count"] == 1

    cache.update(venue, healthy_symbol, _book(1_100), received_at_ms=1_100)
    clients, metrics = cache.snapshot(
        now_ms=1_200,
        max_age_ms=1_500,
        max_skew_ms=None,
        require_connected=True,
    )

    assert clients[venue].symbols == {healthy_symbol}
    assert metrics["disconnected_book_count"] == 1

    cache.update(venue, failed_symbol, _book(1_200), received_at_ms=1_200)
    clients, metrics = cache.snapshot(
        now_ms=1_300,
        max_age_ms=1_500,
        max_skew_ms=None,
        require_connected=True,
    )

    assert clients[venue].symbols == {failed_symbol, healthy_symbol}
    assert metrics["disconnected_book_count"] == 0


def test_stream_health_counts_overlapping_age_disconnect_and_exact_identity():
    cache = LatestBookCache(depth_limit=1, max_entries=4)
    symbol = "OLD/USDT:USDT"
    cache.update("okx", symbol, _book(1_000), received_at_ms=1_000, received_mono_ms=1_000)
    cache.record_stream_error("okx", symbol, RuntimeError("do-not-export"))
    cache.record_reconnect("okx", symbol)

    clients, metrics = cache.snapshot(
        now_ms=3_000,
        now_mono_ms=3_000,
        max_age_ms=1_500,
        max_skew_ms=None,
        require_connected=True,
    )

    assert clients == {}
    assert metrics["age_expired_book_count"] == 1
    assert metrics["disconnected_book_count"] == 1
    assert metrics["stale_book_count"] == 1
    identity = metrics["stream_identity_metrics"]
    assert identity == [
        {
            "venue": "okx",
            "symbol": symbol,
            "updates": 1,
            "reconnects": 1,
            "errors": {"RuntimeError": 1},
            "age_expired": True,
            "disconnected": True,
            "admission": "DISCONNECTED",
        }
    ]
    assert "do-not-export" not in repr(metrics)


def test_contract_book_amount_multiplier_converts_contracts_to_base_units():
    from crypto_research.stream_v18 import contract_book_amount_multiplier

    assert contract_book_amount_multiplier(
        "okx", {"contract": True, "contractSize": 0.01}
    ) == pytest.approx(0.01)
    # Runtime client key is "kucoin" even though the CCXT class is kucoinfutures.
    assert contract_book_amount_multiplier(
        "kucoin", {"contract": True, "contractSize": 0.001}
    ) == pytest.approx(0.001)
    assert contract_book_amount_multiplier(
        "kucoinfutures", {"contract": True, "contractSize": 0.001}
    ) == pytest.approx(0.001)
    assert contract_book_amount_multiplier(
        "gate", {"contract": True, "contractSize": 0.0001}
    ) == pytest.approx(0.0001)
    assert contract_book_amount_multiplier(
        "mexc", {"contract": True, "contractSize": 0.0001}
    ) == pytest.approx(0.0001)


def test_contract_book_amount_multiplier_preserves_deribit_underlying_units():
    from crypto_research.stream_v18 import contract_book_amount_multiplier

    assert contract_book_amount_multiplier(
        "deribit", {"contract": True, "contractSize": 0.0001}
    ) == pytest.approx(1.0)
    assert contract_book_amount_multiplier(
        "binance", {"contract": True, "contractSize": 1.0}
    ) == pytest.approx(1.0)


def test_cache_normalizes_contract_amount_before_execution_simulation():
    cache = LatestBookCache(depth_limit=1, max_entries=4)
    symbol = "BTC/USDT:USDT"
    raw = {
        "bids": [[78_800.0, 588.1]],
        "asks": [[78_801.0, 400.0]],
        "timestamp": 1_000,
        "symbol": symbol,
    }

    cache.update(
        "okx",
        symbol,
        raw,
        received_at_ms=1_000,
        amount_multiplier=0.01,
    )
    clients, _ = cache.snapshot(now_ms=1_100, max_age_ms=1_500)
    book = clients["okx"].fetch_order_book(symbol)

    assert book["bids"][0][1] == pytest.approx(5.881)
    assert book["asks"][0][1] == pytest.approx(4.0)
    assert book["amount_unit"] == "BASE"
    assert book["source_amount_multiplier"] == pytest.approx(0.01)


def test_watcher_applies_market_contract_multiplier_before_caching():
    stop_event = asyncio.Event()

    class ContractExchange:
        def market(self, symbol):
            assert symbol == "BTC/USDT:USDT"
            return {"contract": True, "contractSize": 0.01}

        async def watch_order_book(self, symbol, limit):
            del symbol, limit
            stop_event.set()
            return {
                "bids": [[78_800.0, 588.1]],
                "asks": [[78_801.0, 400.0]],
                "timestamp": 1_000,
            }

    cache = LatestBookCache(depth_limit=1, max_entries=4)
    asyncio.run(
        watch_public_book(
            "okx", ContractExchange(), "BTC/USDT:USDT", cache, stop_event, depth_limit=1
        )
    )
    clients, _ = cache.snapshot(max_age_ms=5_000)
    book = clients["okx"].fetch_order_book("BTC/USDT:USDT")
    assert book["bids"][0][1] == pytest.approx(5.881)
    assert book["source_amount_multiplier"] == pytest.approx(0.01)


def test_watcher_cooperatively_yields_after_successful_book_update(monkeypatch):
    stop_event = asyncio.Event()
    yielded = []

    class ImmediateExchange:
        def market(self, symbol):
            return {"contract": False, "contractSize": 1.0}

        async def watch_order_book(self, symbol, limit):
            del symbol, limit
            stop_event.set()
            return {
                "bids": [[100.0, 1.0]],
                "asks": [[101.0, 1.0]],
                "timestamp": 1_000,
            }

    real_sleep = asyncio.sleep

    async def tracking_sleep(delay):
        yielded.append(delay)
        await real_sleep(0)

    monkeypatch.setattr("crypto_research.stream_v18.asyncio.sleep", tracking_sleep)
    cache = LatestBookCache(depth_limit=1, max_entries=4)
    asyncio.run(
        watch_public_book(
            "binance", ImmediateExchange(), "BTC/USDT:USDT", cache, stop_event, depth_limit=1
        )
    )

    assert any(delay >= 0.001 for delay in yielded)


def test_multi_symbol_watcher_updates_returned_symbol_with_contract_multiplier():
    stop_event = asyncio.Event()
    symbols = ["AAA/USDT:USDT", "BBB/USDT:USDT"]

    class MultiExchange:
        has = {"watchOrderBookForSymbols": True}

        def market(self, symbol):
            assert symbol in symbols
            return {"contract": True, "contractSize": 0.01}

        async def watch_order_book_for_symbols(self, watched, limit):
            assert watched == symbols
            assert limit == 5
            stop_event.set()
            return {
                "symbol": symbols[1],
                "bids": [[100.0, 250.0]],
                "asks": [[101.0, 300.0]],
                "timestamp": 1_000,
            }

    cache = LatestBookCache(depth_limit=1, max_entries=4)
    asyncio.run(
        watch_public_books(
            "okx", MultiExchange(), symbols, cache, stop_event, depth_limit=5
        )
    )
    clients, _ = cache.snapshot(max_age_ms=5_000)
    book = clients["okx"].fetch_order_book(symbols[1])

    assert book["bids"][0][1] == pytest.approx(2.5)
    assert book["source_amount_multiplier"] == pytest.approx(0.01)


def test_public_trade_watcher_normalizes_contracts_dedupes_and_skips_internal_trades():
    stop_event = asyncio.Event()
    symbols = ["BTC/USDT:USDT"]

    class TradeExchange:
        has = {"watchTradesForSymbols": True}

        def market(self, symbol):
            assert symbol == symbols[0]
            return {"contract": True, "contractSize": 0.01}

        async def watch_trades_for_symbols(self, watched):
            assert watched == symbols
            stop_event.set()
            return [
                {"id": "t1", "symbol": symbols[0], "side": "sell", "price": 100.0, "amount": 50.0},
                {"id": "t1", "symbol": symbols[0], "side": "sell", "price": 100.0, "amount": 50.0},
                {"id": "t2", "symbol": symbols[0], "side": "sell", "price": 100.0, "amount": 25.0},
                {
                    "id": "internal",
                    "symbol": symbols[0],
                    "side": "sell",
                    "price": 100.0,
                    "amount": 100.0,
                    "info": {"is_internal": True},
                },
            ]

    cache = LatestBookCache(depth_limit=1, max_entries=4)
    cache.update("gate", symbols[0], _book(1_000, bid=100.0, ask=100.1), received_at_ms=1_000)
    asyncio.run(watch_public_trades("gate", TradeExchange(), symbols, cache, stop_event))
    clients, metrics = cache.snapshot(now_ms=1_100, now_mono_ms=1_100, max_age_ms=5_000)
    book = clients["gate"].fetch_order_book(symbols[0])
    assert book["_public_trade_volume_by_side_price"][("sell", 100.0)] == pytest.approx(0.75)
    assert metrics["public_trade_update_count"] == 2
    assert metrics["public_trade_update_counts_by_venue"] == {"gate": 2}


def test_start_public_trade_watchers_is_scoped_to_requested_multi_symbol_venues():
    stop_event = asyncio.Event()
    symbols = ["AAA/USDT:USDT", "BBB/USDT:USDT"]

    class Exchange:
        has = {"watchTradesForSymbols": True}
        async def watch_trades_for_symbols(self, watched):
            del watched
            await stop_event.wait()

    async def run_case():
        tasks = start_public_trade_watchers(
            clients={"okx": Exchange(), "binance": Exchange()},
            coverage={symbol: ("okx", "binance") for symbol in symbols},
            cache=LatestBookCache(depth_limit=1, max_entries=8),
            stop_event=stop_event,
            venues=("okx",),
        )
        assert len(tasks) == 1
        stop_event.set()
        await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(run_case())


def test_start_public_book_watchers_multiplexes_supported_venues():
    stop_event = asyncio.Event()
    symbols = ["AAA/USDT:USDT", "BBB/USDT:USDT"]

    class MultiExchange:
        has = {"watchOrderBookForSymbols": True}

        async def watch_order_book_for_symbols(self, watched, limit):
            del watched, limit
            await stop_event.wait()

    class SingleExchange:
        has = {"watchOrderBookForSymbols": None}

        async def watch_order_book(self, symbol, limit):
            del symbol, limit
            await stop_event.wait()

    async def run_case():
        cache = LatestBookCache(depth_limit=1, max_entries=8)
        tasks = start_public_book_watchers(
            clients={"binance": MultiExchange(), "gate": SingleExchange()},
            coverage={symbol: ("binance", "gate") for symbol in symbols},
            cache=cache,
            stop_event=stop_event,
            depth_limit=5,
            multi_symbol_chunk_size=20,
        )
        assert len(tasks) == 3  # one Binance multiplex task + two Gate fallback tasks
        stop_event.set()
        await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(run_case())
