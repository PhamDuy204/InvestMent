"""Bounded public order-book WebSocket cache for V18 paper trading."""

from __future__ import annotations

import asyncio
import copy
import gc
import math
import statistics
import threading
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

_CONTRACT_BOOK_SIZE_VENUES = frozenset({"okx", "gate", "kucoin", "kucoinfutures", "mexc"})


def contract_book_amount_multiplier(venue: str, market: dict[str, Any] | None) -> float:
    """Convert venue-native contract book size to base quantity for simulation."""

    if not isinstance(market, dict) or not bool(market.get("contract")):
        return 1.0
    if str(venue).lower() not in _CONTRACT_BOOK_SIZE_VENUES:
        return 1.0
    multiplier = float(market.get("contractSize") or 0.0)
    if not math.isfinite(multiplier) or multiplier <= 0.0:
        raise ValueError("contract market requires a finite positive contractSize")
    return multiplier


class CachedPublicClient:
    """Synchronous ccxt-shaped reader over one immutable cache snapshot."""

    def __init__(self, venue: str, books: dict[str, dict[str, Any]]) -> None:
        self.venue = str(venue)
        self._books = books

    @property
    def symbols(self) -> frozenset[str]:
        return frozenset(self._books)

    def fetch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, Any]:
        raw = copy.deepcopy(self._books[symbol])
        if limit is not None:
            raw["bids"] = raw["bids"][: int(limit)]
            raw["asks"] = raw["asks"][: int(limit)]
        return raw


class LatestBookCache:
    """Thread-safe latest-only cache; memory is O(venue × symbol × depth)."""

    _MAX_VENUE_LABEL_LENGTH = 64
    _MAX_ERROR_LABEL_LENGTH = 64
    _MAX_ERROR_LABELS = 32
    _MAX_ERROR_VENUES = 32
    _OTHER_ERROR_LABEL = "Other"

    def __init__(self, *, depth_limit: int = 20, max_entries: int = 512) -> None:
        if depth_limit <= 0 or max_entries <= 0:
            raise ValueError("depth_limit and max_entries must be positive")
        self.depth_limit = int(depth_limit)
        self.max_entries = int(max_entries)
        self._lock = threading.Lock()
        self._books: dict[tuple[str, str], dict[str, Any]] = {}
        self._update_count = 0
        self._reconnect_count = 0
        self._eviction_count = 0
        self._disconnected_streams: dict[tuple[str, str], None] = {}
        self._stream_error_counts: dict[str, int] = {}
        self._stream_error_counts_by_venue: dict[str, dict[str, int]] = {}
        self._stream_error_seconds_by_venue: dict[str, dict[int, int]] = {}
        self._identity_counters: dict[tuple[str, str], dict[str, Any]] = {}
        self._trade_volume_by_stream: dict[tuple[str, str], dict[tuple[str, float], tuple[float, int]]] = {}
        self._seen_trade_ids: dict[tuple[str, str], dict[str, None]] = {}
        self._trade_update_count = 0
        self._trade_update_counts_by_venue: dict[str, int] = {}

    @staticmethod
    def _bounded_label(value: Any, *, limit: int) -> str:
        raw = str(value)[:limit]
        normalized = "".join(
            character if character.isalnum() or character in "._-:/" else "_"
            for character in raw
        )
        return normalized or "unknown"

    @classmethod
    def _increment_bounded_error_count(cls, counts: dict[str, int], label: str) -> None:
        if label in counts:
            counts[label] += 1
        elif len(counts) < cls._MAX_ERROR_LABELS - 1:
            counts[label] = 1
        else:
            counts[cls._OTHER_ERROR_LABEL] = counts.get(cls._OTHER_ERROR_LABEL, 0) + 1

    def _touch_identity_counters(self, key: tuple[str, str]) -> dict[str, Any]:
        counters = self._identity_counters.pop(key, None)
        if counters is None:
            counters = {"updates": 0, "reconnects": 0, "errors": {}}
        self._identity_counters[key] = counters
        while len(self._identity_counters) > self.max_entries:
            self._identity_counters.pop(next(iter(self._identity_counters)))
        return counters

    @staticmethod
    def _levels(value: Any, limit: int) -> list[list[float]]:
        if not isinstance(value, list):
            return []
        output: list[list[float]] = []
        for level in value[:limit]:
            if not isinstance(level, (list, tuple)) or len(level) < 2:
                continue
            price = float(level[0])
            quantity = float(level[1])
            if not math.isfinite(price) or price <= 0.0 or not math.isfinite(quantity) or quantity < 0.0:
                continue
            output.append([price, quantity])
        return output

    def update(
        self,
        venue: str,
        symbol: str,
        book: dict[str, Any],
        *,
        received_at_ms: int | None = None,
        received_mono_ms: int | None = None,
        amount_multiplier: float = 1.0,
    ) -> None:
        if not venue or not symbol or not isinstance(book, dict):
            raise ValueError("venue, symbol, and book are required")
        received = int(time.time() * 1000) if received_at_ms is None else int(received_at_ms)
        if received_mono_ms is None:
            received_mono = int(time.monotonic() * 1000) if received_at_ms is None else received
        else:
            received_mono = int(received_mono_ms)
        multiplier = float(amount_multiplier)
        if not math.isfinite(multiplier) or multiplier <= 0.0:
            raise ValueError("amount_multiplier must be finite and positive")
        bids = self._levels(book.get("bids"), self.depth_limit)
        asks = self._levels(book.get("asks"), self.depth_limit)
        if multiplier != 1.0:
            bids = [[price, quantity * multiplier] for price, quantity in bids]
            asks = [[price, quantity * multiplier] for price, quantity in asks]
        if not bids or not asks:
            raise ValueError("book must contain valid bids and asks")
        key = (str(venue), str(symbol))
        normalized = {
            "bids": bids,
            "asks": asks,
            # Local receipt time is the causal freshness clock. Exchange timestamps may be absent or skewed.
            "timestamp": received,
            "exchange_timestamp": book.get("timestamp"),
            "symbol": str(symbol),
            "received_at_ms": received,
            "received_mono_ms": received_mono,
            "amount_unit": "BASE",
            "source_amount_multiplier": multiplier,
        }
        with self._lock:
            self._books[key] = normalized
            self._disconnected_streams.pop(key, None)
            self._update_count += 1
            self._touch_identity_counters(key)["updates"] += 1
            if len(self._books) > self.max_entries:
                oldest = min(self._books, key=lambda item: int(self._books[item]["received_mono_ms"]))
                self._books.pop(oldest)
                self._disconnected_streams.pop(oldest, None)
                self._eviction_count += 1

    def record_public_trade(
        self,
        venue: str,
        symbol: str,
        *,
        trade_id: str,
        side: str,
        price: float,
        amount_base: float,
        received_mono_ms: int | None = None,
    ) -> bool:
        if side not in {"buy", "sell"} or not trade_id:
            return False
        px = float(price)
        amount = float(amount_base)
        if not math.isfinite(px) or px <= 0.0 or not math.isfinite(amount) or amount <= 0.0:
            return False
        received_mono = int(time.monotonic() * 1000) if received_mono_ms is None else int(received_mono_ms)
        stream_key = (str(venue), str(symbol))
        with self._lock:
            seen = self._seen_trade_ids.setdefault(stream_key, {})
            if str(trade_id) in seen:
                return False
            seen[str(trade_id)] = None
            while len(seen) > 2048:
                seen.pop(next(iter(seen)))

            volumes = self._trade_volume_by_stream.setdefault(stream_key, {})
            price_key = (side, px)
            previous = volumes.get(price_key)
            cumulative = amount + (float(previous[0]) if previous is not None else 0.0)
            volumes.pop(price_key, None)
            volumes[price_key] = (cumulative, received_mono)
            # ponytail: retain only recent price buckets; eviction can only create a
            # false negative because queue evidence also carries its placement baseline.
            while len(volumes) > 256:
                volumes.pop(next(iter(volumes)))
            self._trade_update_count += 1
            venue_label = self._bounded_label(venue, limit=self._MAX_VENUE_LABEL_LENGTH)
            self._trade_update_counts_by_venue[venue_label] = (
                self._trade_update_counts_by_venue.get(venue_label, 0) + 1
            )
        return True


    def record_reconnect(self, venue: str, symbol: str) -> None:
        key = (str(venue), str(symbol))
        with self._lock:
            self._reconnect_count += 1
            self._touch_identity_counters(key)["reconnects"] += 1

    def record_stream_error(self, venue: str, symbol: str, exc: Exception) -> None:
        """Record bounded cause telemetry without retaining exception objects."""

        health_key = (str(venue), str(symbol))
        second = int(time.monotonic())
        error_label = self._bounded_label(
            type(exc).__name__,
            limit=self._MAX_ERROR_LABEL_LENGTH,
        )
        venue_label = self._bounded_label(
            venue,
            limit=self._MAX_VENUE_LABEL_LENGTH,
        )
        with self._lock:
            self._disconnected_streams.pop(health_key, None)
            self._disconnected_streams[health_key] = None
            while len(self._disconnected_streams) > self.max_entries:
                self._disconnected_streams.pop(next(iter(self._disconnected_streams)))

            self._increment_bounded_error_count(self._stream_error_counts, error_label)
            identity = self._touch_identity_counters(health_key)
            self._increment_bounded_error_count(identity["errors"], error_label)
            if venue_label not in self._stream_error_counts_by_venue:
                if len(self._stream_error_counts_by_venue) < self._MAX_ERROR_VENUES - 1:
                    self._stream_error_counts_by_venue[venue_label] = {}
                else:
                    venue_label = self._OTHER_ERROR_LABEL
                    self._stream_error_counts_by_venue.setdefault(venue_label, {})
            self._increment_bounded_error_count(
                self._stream_error_counts_by_venue[venue_label],
                error_label,
            )
            # ponytail: 60 one-second buckets bound storm memory; use exact event
            # timestamps only if subsecond error-window accuracy becomes necessary.
            window = self._stream_error_seconds_by_venue.setdefault(venue_label, {})
            window[second] = window.get(second, 0) + 1
            for stamp in list(window):
                if stamp <= second - 60:
                    del window[stamp]

    def prune_stale(
        self,
        *,
        now_ms: int,
        max_age_ms: int,
        now_mono_ms: int | None = None,
    ) -> int:
        """Drop only expired snapshots; live books remain available to the paper engine."""

        if max_age_ms <= 0:
            raise ValueError("max_age_ms must be positive")
        now_mono = int(now_ms) if now_mono_ms is None else int(now_mono_ms)
        with self._lock:
            stale_keys = [
                key
                for key, raw in self._books.items()
                if (age := now_mono - int(raw["received_mono_ms"])) < 0 or age > int(max_age_ms)
            ]
            for key in stale_keys:
                self._books.pop(key)
                self._disconnected_streams.pop(key, None)
            self._eviction_count += len(stale_keys)
        return len(stale_keys)

    def snapshot(
        self,
        *,
        now_ms: int | None = None,
        now_mono_ms: int | None = None,
        max_age_ms: int = 1_500,
        max_skew_ms: int | None = None,
        selected_symbols: set[str] | None = None,
        require_connected: bool = False,
    ) -> tuple[dict[str, CachedPublicClient], dict[str, Any]]:
        if max_age_ms <= 0 or (max_skew_ms is not None and max_skew_ms <= 0):
            raise ValueError("max_age_ms and max_skew_ms must be positive")
        now = int(time.time() * 1000) if now_ms is None else int(now_ms)
        if now_mono_ms is None:
            now_mono = int(time.monotonic() * 1000) if now_ms is None else now
        else:
            now_mono = int(now_mono_ms)
        selected = None if selected_symbols is None else {str(symbol) for symbol in selected_symbols}
        with self._lock:
            # Updates replace normalized dictionaries, so references in this shallow
            # snapshot remain stable after the lock is released.
            rows = dict(self._books)
            disconnected_streams = set(self._disconnected_streams)
            counters = (self._update_count, self._reconnect_count, self._eviction_count)
            stream_error_counts = dict(self._stream_error_counts)
            stream_errors_last_60s = {
                venue: sum(count for stamp, count in window.items() if now_mono // 1000 - 60 < stamp <= now_mono // 1000)
                for venue, window in self._stream_error_seconds_by_venue.items()
            }
            stream_error_counts_by_venue = {
                venue: dict(counts)
                for venue, counts in self._stream_error_counts_by_venue.items()
            }
            trade_volume_by_stream = {key: dict(values) for key, values in self._trade_volume_by_stream.items()}
            trade_update_count = int(self._trade_update_count)
            trade_update_counts_by_venue = {
                venue: int(count)
                for venue, count in self._trade_update_counts_by_venue.items()
            }
            identity_counters = {
                key: {
                    "updates": int(counts["updates"]),
                    "reconnects": int(counts["reconnects"]),
                    "errors": dict(counts["errors"]),
                }
                for key, counts in self._identity_counters.items()
            }

        venue_books: dict[str, dict[str, dict[str, Any]]] = {}
        ages: list[int] = []
        age_expired = 0
        skew_rejected = 0
        disconnected = 0
        accepted_venues: set[str] = set()
        admission_by_key: dict[tuple[str, str], str] = {}
        age_valid_rows: list[tuple[str, str, dict[str, Any], int]] = []
        newest_by_symbol: dict[str, int] = {}
        for (venue, symbol), raw in rows.items():
            key = (venue, symbol)
            received_mono = int(raw["received_mono_ms"])
            age = now_mono - received_mono
            stream_disconnected = key in disconnected_streams
            expired = age < 0 or age > int(max_age_ms)
            if stream_disconnected:
                disconnected += 1
            if expired:
                age_expired += 1
            if require_connected and stream_disconnected:
                admission_by_key[key] = "DISCONNECTED"
                continue
            if expired:
                admission_by_key[key] = "AGE_EXPIRED"
                continue
            age_valid_rows.append((venue, symbol, raw, age))
            newest_by_symbol[symbol] = max(newest_by_symbol.get(symbol, received_mono), received_mono)

        for venue, symbol, raw, age in age_valid_rows:
            key = (venue, symbol)
            received_mono = int(raw["received_mono_ms"])
            if max_skew_ms is not None and newest_by_symbol[symbol] - received_mono > int(max_skew_ms):
                skew_rejected += 1
                admission_by_key[key] = "SKEW_REJECTED"
                continue
            admission_by_key[key] = "ACCEPTED"
            ages.append(age)
            accepted_venues.add(venue)
            if selected is None or symbol in selected:
                materialized = copy.deepcopy(raw)
                trade_levels = trade_volume_by_stream.get(key)
                if trade_levels:
                    materialized["_public_trade_volume_by_side_price"] = {
                        trade_key: float(value[0]) for trade_key, value in trade_levels.items()
                    }
                venue_books.setdefault(venue, {})[symbol] = materialized

        clients = {venue: CachedPublicClient(venue, books) for venue, books in venue_books.items()}
        stream_identity_metrics = []
        for key in sorted(rows):
            venue, symbol = key
            raw = rows[key]
            age = now_mono - int(raw["received_mono_ms"])
            counters_for_key = identity_counters.get(key, {"updates": 0, "reconnects": 0, "errors": {}})
            stream_identity_metrics.append(
                {
                    "venue": venue,
                    "symbol": symbol,
                    "updates": int(counters_for_key["updates"]),
                    "reconnects": int(counters_for_key["reconnects"]),
                    "errors": dict(counters_for_key["errors"]),
                    "age_expired": age < 0 or age > int(max_age_ms),
                    "disconnected": key in disconnected_streams,
                    "admission": admission_by_key.get(key, "NOT_EVALUATED"),
                }
            )
        metrics = {
            "book_update_count": counters[0],
            "public_trade_update_count": trade_update_count,
            "public_trade_update_counts_by_venue": trade_update_counts_by_venue,
            "ws_reconnect_count": counters[1],
            "eviction_count": counters[2],
            "cache_entry_count": len(rows),
            "fresh_book_count": len(ages),
            "stale_book_count": sum(value != "ACCEPTED" for value in admission_by_key.values()),
            "age_expired_book_count": age_expired,
            "skew_rejected_book_count": skew_rejected,
            "disconnected_book_count": disconnected,
            "connected_venue_count": len(accepted_venues),
            "book_age_ms_median": float(statistics.median(ages)) if ages else None,
            "book_age_ms_max": max(ages) if ages else None,
            "stream_error_counts": stream_error_counts,
            "stream_errors_last_60s_by_venue": stream_errors_last_60s,
            "stream_error_counts_by_venue": stream_error_counts_by_venue,
            "stream_identity_metrics": stream_identity_metrics,
        }
        return clients, metrics


def _release_unused_heap() -> None:
    """Best-effort release after dropping CCXT's unused market metadata."""

    gc.collect()
    try:
        import ctypes

        trim = getattr(ctypes.CDLL(None), "malloc_trim")
        trim(0)
    except (AttributeError, OSError):
        # ponytail: malloc_trim is glibc-specific; non-glibc hosts keep Python's
        # allocator behavior and rely on the 1 GiB hard stop in the runner.
        pass


def compact_public_stream_markets(
    clients: dict[str, Any],
    coverage: dict[str, tuple[str, ...]],
) -> int:
    """Keep only market metadata required by the selected V18 universe."""

    selected_by_venue: dict[str, set[str]] = {}
    for symbol, venues in coverage.items():
        for venue in venues:
            if venue in clients:
                selected_by_venue.setdefault(venue, set()).add(symbol)

    kept = 0
    for venue, exchange in clients.items():
        markets = getattr(exchange, "markets", None)
        set_markets = getattr(exchange, "set_markets", None)
        if not isinstance(markets, dict) or not callable(set_markets):
            continue
        wanted = selected_by_venue.get(venue, set())
        selected = {symbol: markets[symbol] for symbol in wanted if symbol in markets}
        # CCXT's set_markets merges currencies into the existing map, so clear the
        # large all-market indexes first. The selected market dicts remain alive.
        exchange.markets = {}
        exchange.markets_by_id = {}
        exchange.symbols = []
        exchange.ids = []
        exchange.currencies = {}
        exchange.currencies_by_id = {}
        exchange.baseCurrencies = {}
        exchange.quoteCurrencies = {}
        exchange.codes = []
        if selected:
            set_markets(selected)
            kept += len(selected)

    _release_unused_heap()
    return kept


def make_public_stream_clients() -> dict[str, Any]:
    """Create credential-free ccxt.pro clients for public swap order books."""

    import ccxt.pro as ccxtpro
    from ccxt.base.errors import AuthenticationError

    class PublicKucoinFutures(ccxtpro.kucoinfutures):
        def handle_error_message(self, client: Any, message: dict[str, Any]) -> bool:
            connect_id = parse_qs(urlsplit(client.url).query).get("connectId", [""])[0]
            if message.get("data") == "token is expired" and connect_id in {"public", "publicFutures"}:
                # CCXT 4.5.76 clears 'public' for futures and lets the error escape
                # the receive callback. Retire only this socket's public token;
                # the existing watchers then share CCXT's next bullet-public call.
                if self.clients.get(client.url) is client:
                    self.options.get("urls", {}).pop(connect_id, None)
                client.on_error(AuthenticationError(f"{self.id} public WebSocket token expired"))
                return False
            return super().handle_error_message(client, message)

    common = {"enableRateLimit": True}
    return {
        "binance": ccxtpro.binanceusdm(common.copy()),
        "okx": ccxtpro.okx({**common, "options": {"defaultType": "swap"}}),
        "mexc": ccxtpro.mexc({**common, "options": {"defaultType": "swap"}}),
        "bybit": ccxtpro.bybit({**common, "options": {"defaultType": "swap"}}),
        "bitget": ccxtpro.bitget({**common, "options": {"defaultType": "swap"}}),
        "kucoin": PublicKucoinFutures(common.copy()),
        "gate": ccxtpro.gate({**common, "options": {"defaultType": "swap"}}),
    }


def public_stream_health(state: dict[str, Any]) -> tuple[str, str | None]:
    """Keep the runner alive while reporting missing expected public venues."""

    if int(state.get("connected_venue_count", 0)) < int(state.get("expected_venue_count", 0)):
        return "DEGRADED", "PUBLIC_VENUE_COVERAGE"
    return "HEALTHY", None


def stream_subscription_limit(venue: str, depth_limit: int) -> int:
    if depth_limit <= 0:
        raise ValueError("depth_limit must be positive")
    # ponytail: anonymous compact feeds cap OKX at 5 and Bitget at 15 levels;
    # insufficient hedge depth is rejected rather than silently falling back to large in-memory books.
    if venue == "okx":
        return min(int(depth_limit), 5)
    if venue == "bitget":
        return min(int(depth_limit), 15)
    if venue == "bybit":
        return max(int(depth_limit), 50)
    return int(depth_limit)


def _cache_public_book_update(
    venue: str,
    exchange: Any,
    symbol: str,
    book: dict[str, Any],
    cache: LatestBookCache,
) -> None:
    market = None
    if hasattr(exchange, "market"):
        try:
            market = exchange.market(symbol)
        except (KeyError, TypeError, ValueError):
            market = None
    elif isinstance(getattr(exchange, "markets", None), dict):
        market = exchange.markets.get(symbol)
    cache.update(
        venue,
        symbol,
        book,
        amount_multiplier=contract_book_amount_multiplier(venue, market),
    )


async def watch_public_book(
    venue: str,
    exchange: Any,
    symbol: str,
    cache: LatestBookCache,
    stop_event: asyncio.Event,
    *,
    depth_limit: int = 20,
) -> None:
    """Continuously update one public book with bounded reconnect backoff."""

    backoff_seconds = 0.25
    while not stop_event.is_set():
        try:
            book = await exchange.watch_order_book(
                symbol,
                limit=stream_subscription_limit(venue, depth_limit),
            )
            _cache_public_book_update(venue, exchange, symbol, book, cache)
            backoff_seconds = 0.25
            # ponytail: fallback single-symbol streams are capped at 1 kHz; venues
            # with native multi-symbol subscriptions use watch_public_books below.
            await asyncio.sleep(0.001)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            cache.record_stream_error(venue, symbol, exc)
            cache.record_reconnect(venue, symbol)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=backoff_seconds)
            except TimeoutError:
                pass
            backoff_seconds = min(5.0, backoff_seconds * 2.0)


async def watch_public_books(
    venue: str,
    exchange: Any,
    symbols: list[str],
    cache: LatestBookCache,
    stop_event: asyncio.Event,
    *,
    depth_limit: int = 20,
) -> None:
    """Continuously update a native multi-symbol public order-book subscription."""

    if not symbols:
        return
    watched = list(dict.fromkeys(str(symbol) for symbol in symbols))
    watched_set = set(watched)
    backoff_seconds = 0.25
    while not stop_event.is_set():
        try:
            book = await exchange.watch_order_book_for_symbols(
                watched,
                limit=stream_subscription_limit(venue, depth_limit),
            )
            symbol = str(book.get("symbol") or "") if isinstance(book, dict) else ""
            if symbol not in watched_set:
                raise ValueError("multi-symbol order book returned an unexpected symbol")
            _cache_public_book_update(venue, exchange, symbol, book, cache)
            backoff_seconds = 0.25
            await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            for symbol in watched:
                cache.record_stream_error(venue, symbol, exc)
                cache.record_reconnect(venue, symbol)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=backoff_seconds)
            except TimeoutError:
                pass
            backoff_seconds = min(5.0, backoff_seconds * 2.0)


async def watch_public_trades(
    venue: str,
    exchange: Any,
    symbols: list[str],
    cache: LatestBookCache,
    stop_event: asyncio.Event,
) -> None:
    """Collect public taker prints for conservative queue-depletion evidence."""

    watched = list(dict.fromkeys(str(symbol) for symbol in symbols))
    watched_set = set(watched)
    if not watched:
        return
    backoff_seconds = 0.25
    while not stop_event.is_set():
        try:
            trades = await exchange.watch_trades_for_symbols(watched)
            received_mono_ms = int(time.monotonic() * 1000)
            for trade in trades or []:
                if not isinstance(trade, dict):
                    continue
                symbol = str(trade.get("symbol") or "")
                side = str(trade.get("side") or "").lower()
                trade_id = str(trade.get("id") or "")
                info = trade.get("info")
                is_internal = info.get("is_internal") if isinstance(info, dict) else False
                if is_internal is True or str(is_internal).lower() == "true":
                    # Gate internal prints are insurance-fund/ADL transfers and do
                    # not consume the displayed order-book queue.
                    continue
                if symbol not in watched_set or side not in {"buy", "sell"} or not trade_id:
                    continue
                try:
                    market = exchange.market(symbol)
                    multiplier = contract_book_amount_multiplier(venue, market)
                    price = float(trade.get("price"))
                    amount_base = float(trade.get("amount")) * multiplier
                except (KeyError, TypeError, ValueError):
                    continue
                cache.record_public_trade(
                    venue,
                    symbol,
                    trade_id=trade_id,
                    side=side,
                    price=price,
                    amount_base=amount_base,
                    received_mono_ms=received_mono_ms,
                )
            backoff_seconds = 0.25
            await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Trade prints are supplemental fill evidence. Book liveness remains
            # authoritative, and failure here must fail back to price-through rather
            # than incorrectly marking the public book stream disconnected.
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=backoff_seconds)
            except TimeoutError:
                pass
            backoff_seconds = min(5.0, backoff_seconds * 2.0)


def start_public_trade_watchers(
    *,
    clients: dict[str, Any],
    coverage: dict[str, tuple[str, ...]],
    cache: LatestBookCache,
    stop_event: asyncio.Event,
    venues: tuple[str, ...] = (),
) -> list[asyncio.Task[Any]]:
    """Start only explicitly requested native multi-symbol public trade feeds."""

    requested = {str(venue) for venue in venues}
    if not requested:
        return []
    by_venue: dict[str, list[str]] = {}
    for symbol, symbol_venues in coverage.items():
        for venue in symbol_venues:
            if venue in requested and venue in clients:
                by_venue.setdefault(venue, []).append(symbol)

    tasks: list[asyncio.Task[Any]] = []
    for venue, symbols in by_venue.items():
        exchange = clients[venue]
        supports_multi = bool((getattr(exchange, "has", {}) or {}).get("watchTradesForSymbols"))
        if not supports_multi or not callable(getattr(exchange, "watch_trades_for_symbols", None)):
            continue
        tasks.append(
            asyncio.create_task(watch_public_trades(venue, exchange, symbols, cache, stop_event))
        )
    return tasks


def start_public_book_watchers(
    *,
    clients: dict[str, Any],
    coverage: dict[str, tuple[str, ...]],
    cache: LatestBookCache,
    stop_event: asyncio.Event,
    depth_limit: int = 20,
    multi_symbol_chunk_size: int = 20,
) -> list[asyncio.Task[Any]]:
    """Start native multiplex subscriptions where CCXT exposes them."""

    if multi_symbol_chunk_size <= 0:
        raise ValueError("multi_symbol_chunk_size must be positive")
    by_venue: dict[str, list[str]] = {}
    for symbol, venues in coverage.items():
        for venue in venues:
            if venue in clients:
                by_venue.setdefault(venue, []).append(symbol)

    tasks: list[asyncio.Task[Any]] = []
    for venue, venue_symbols in by_venue.items():
        exchange = clients[venue]
        supports_multi = bool((getattr(exchange, "has", {}) or {}).get("watchOrderBookForSymbols"))
        if supports_multi and callable(getattr(exchange, "watch_order_book_for_symbols", None)):
            for start in range(0, len(venue_symbols), int(multi_symbol_chunk_size)):
                chunk = venue_symbols[start : start + int(multi_symbol_chunk_size)]
                tasks.append(
                    asyncio.create_task(
                        watch_public_books(
                            venue, exchange, chunk, cache, stop_event, depth_limit=depth_limit
                        )
                    )
                )
            continue
        for symbol in venue_symbols:
            tasks.append(
                asyncio.create_task(
                    watch_public_book(
                        venue, exchange, symbol, cache, stop_event, depth_limit=depth_limit
                    )
                )
            )
    return tasks


async def close_public_stream_clients(clients: dict[str, Any]) -> None:
    await asyncio.gather(
        *(client.close() for client in clients.values()),
        return_exceptions=True,
    )
