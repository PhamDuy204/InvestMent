"""V18 public-WebSocket, causal post-fill EV paper arbitrage runner."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from crypto_research.maker_v17 import (
    DEFAULT_MAKER_FEE_BPS,
    multi_horizon_route_features,
    passive_limit_filled,
    record_fill_outcome,
    seed_route_history_from_v16,
)
from crypto_research.maker_v18 import post_fill_entry_ev, select_v18_profile
from crypto_research.monitoring_v13 import mark_open_position
from crypto_research.stream_v18 import (
    LatestBookCache,
    close_public_stream_clients,
    compact_public_stream_markets,
    make_public_stream_clients,
    watch_public_book,
)

if __package__:
    from .run_arbitrage_paper_v12 import (
        DEFAULT_FEE_BPS,
        _append_jsonl,
        _eligible_linear_usdt_swap,
        write_state,
    )
    from .run_arbitrage_paper_v13 import _utc_now, _write_health
    from .run_arbitrage_paper_v14 import _sorted_universe
    from .run_arbitrage_paper_v17 import (
        _assert_v17_invariants,
        _default_state_v17,
        _elapsed_since_placement_ms,
        _market_fill,
        _position_from_pending,
        _refresh_v17_margin,
        run_cycle_v17,
    )
else:
    from run_arbitrage_paper_v12 import (
        DEFAULT_FEE_BPS,
        _append_jsonl,
        _eligible_linear_usdt_swap,
        write_state,
    )
    from run_arbitrage_paper_v13 import _utc_now, _write_health
    from run_arbitrage_paper_v14 import _sorted_universe
    from run_arbitrage_paper_v17 import (
        _assert_v17_invariants,
        _default_state_v17,
        _elapsed_since_placement_ms,
        _market_fill,
        _position_from_pending,
        _refresh_v17_margin,
        run_cycle_v17,
    )

SCHEMA_VERSION = "v18-arbitrage-paper-1"
HEALTH_SCHEMA_VERSION = "v18-arbitrage-health-1"
PORTFOLIO_MODEL = "WS_CAUSAL_POST_FILL_EV_V1"
MARGIN_MODEL = "CROSS_MARGIN_PAPER_V1"
STRATEGY_ID = "WS_CAUSAL_POST_FILL_EV_V1"


def _default_state_v18(
    venue_names: list[str],
    *,
    initial_equity: float = 100.0,
    gross_leverage_cap: float = 40.0,
    max_open_positions: int = 8,
) -> dict[str, Any]:
    state = _default_state_v17(
        venue_names,
        initial_equity=initial_equity,
        gross_leverage_cap=gross_leverage_cap,
        max_open_positions=max_open_positions,
    )
    state.update(
        {
            "schema_version": SCHEMA_VERSION,
            "portfolio_model": PORTFOLIO_MODEL,
            "margin_model": MARGIN_MODEL,
            "exchange_leverage": 40.0,
            "min_position_leverage": 20.0,
            "max_position_leverage": 40.0,
            "history_sample_interval_ms": 5_000,
            "safety_buffer_bps": 0.5,
            "post_fill_accept_count": 0,
            "post_fill_reject_count": 0,
            "both_maker_fill_count": 0,
            "one_leg_abort_count": 0,
            "one_leg_abort_pnl": 0.0,
            "book_update_count": 0,
            "ws_reconnect_count": 0,
            "book_cache_entry_count": 0,
            "fresh_book_count": 0,
            "stale_book_count": 0,
            "connected_venue_count": 0,
            "book_age_ms_median": None,
            "book_age_ms_max": None,
            "memory_prune_count": 0,
            "process_rss_bytes": 0,
            "divergence_confirmations": {},
        }
    )
    return state


def _refresh_v18_state(state: dict[str, Any]) -> None:
    state["schema_version"] = SCHEMA_VERSION
    state["portfolio_model"] = PORTFOLIO_MODEL
    state["margin_model"] = MARGIN_MODEL
    state["exchange_leverage"] = 40.0
    state["min_position_leverage"] = 20.0
    state["max_position_leverage"] = 40.0


def _assert_v18_invariants(state: dict[str, Any]) -> None:
    _assert_v17_invariants(state)
    for position in state.get("open_positions", []):
        if str(position.get("strategy_id")) != STRATEGY_ID:
            raise ValueError("V18 position has the wrong strategy")
        if not 20.0 <= float(position.get("leverage", 0.0)) <= 40.0:
            raise ValueError("V18 position leverage outside 20x..40x")
    _refresh_v18_state(state)


def _confirm_v18_exit(
    state: dict[str, Any],
    position: dict[str, Any],
    reason: str | None,
    *,
    now_ms: int,
) -> str | None:
    confirmations = state.setdefault("divergence_confirmations", {})
    position_id = str(position["position_id"])
    if reason != "DIVERGENCE_STOP":
        confirmations.pop(position_id, None)
        return reason

    previous = confirmations.get(position_id)
    if not isinstance(previous, dict) or int(now_ms) - int(previous.get("last_ms", 0)) > 5_000:
        row = {"count": 1, "first_ms": int(now_ms), "last_ms": int(now_ms)}
    else:
        row = {
            "count": int(previous.get("count", 0)) + 1,
            "first_ms": int(previous.get("first_ms", now_ms)),
            "last_ms": int(now_ms),
        }
    confirmations[position_id] = row
    if row["count"] >= 3 and int(now_ms) - row["first_ms"] >= 1_000:
        confirmations.pop(position_id, None)
        return reason
    return None


def _record_one_leg_abort(
    state: dict[str, Any],
    pending: dict[str, Any],
    *,
    long_filled: bool,
    long_book: Any,
    short_book: Any,
    taker_fee_bps: dict[str, float],
    maker_fee_bps: dict[str, float],
    now_ms: int,
    now_utc: str,
    journal_path: Path,
    abort_reason: str = "POST_FILL_EV_REJECTED",
) -> bool:
    quantity = float(pending["quantity"])
    if long_filled:
        venue = str(pending["long_exchange"])
        entry_price = float(pending["long_limit_price"])
        exit_fill = _market_fill(
            long_book,
            side="sell",
            quantity=quantity,
            fee_bps=float(taker_fee_bps[venue]),
        )
        if exit_fill is None:
            return False
        exit_price = float(exit_fill.vwap)
        gross_pnl = quantity * (exit_price - entry_price)
        side = "LONG"
    else:
        venue = str(pending["short_exchange"])
        entry_price = float(pending["short_limit_price"])
        exit_fill = _market_fill(
            short_book,
            side="buy",
            quantity=quantity,
            fee_bps=float(taker_fee_bps[venue]),
        )
        if exit_fill is None:
            return False
        exit_price = float(exit_fill.vwap)
        gross_pnl = quantity * (entry_price - exit_price)
        side = "SHORT"

    entry_fee = quantity * entry_price * float(maker_fee_bps[venue]) / 10_000.0
    exit_fee = quantity * exit_price * float(taker_fee_bps[venue]) / 10_000.0
    net_pnl = gross_pnl - entry_fee - exit_fee
    state["venue_balances"][venue] = float(state["venue_balances"][venue]) + net_pnl
    state["equity"] = float(state["equity"]) + net_pnl
    state["realized_pnl"] = float(state.get("realized_pnl", 0.0)) + net_pnl
    state["realized_fee_drag"] = float(state.get("realized_fee_drag", 0.0)) + entry_fee + exit_fee
    if abort_reason == "POST_FILL_EV_REJECTED":
        state["post_fill_reject_count"] = int(state.get("post_fill_reject_count", 0)) + 1
    state["one_leg_abort_count"] = int(state.get("one_leg_abort_count", 0)) + 1
    state["one_leg_abort_pnl"] = float(state.get("one_leg_abort_pnl", 0.0)) + net_pnl
    state.setdefault("route_cooldowns", {})[str(pending["position_key"])] = int(now_ms)
    _append_jsonl(
        journal_path,
        {
            "record_type": "PAPER_ONE_LEG_ABORT",
            "strategy_id": STRATEGY_ID,
            "pending_id": str(pending["pending_id"]),
            "position_key": str(pending["position_key"]),
            "symbol": str(pending["symbol"]),
            "filled_side": side,
            "venue": venue,
            "quantity": quantity,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "entry_fees": entry_fee,
            "exit_fees": exit_fee,
            "gross_pnl": gross_pnl,
            "realized_net_pnl": net_pnl,
            "abort_reason": abort_reason,
            "post_fill_decision": abort_reason,
            "actual_capture_bps": pending.get("actual_capture_bps"),
            "post_fill_expected_value_bps": pending.get("post_fill_expected_value_bps"),
            "closed_at": now_utc,
        },
    )
    return True


def _process_pending_entries_v18(
    state: dict[str, Any],
    *,
    books_by_symbol: dict[str, dict[str, Any]],
    stats_db: str | Path,
    now_ms: int,
    now_utc: str,
    journal_path: Path,
    maker_fee_bps: dict[str, float],
    taker_fee_bps: dict[str, float],
    timeout_ms: int = 30_000,
    now_mono_ms: int | None = None,
    strict_maker_price_through: bool = False,
) -> None:
    remaining: list[dict[str, Any]] = []
    for pending in list(state.get("pending_entries", [])):
        if int(now_ms) <= int(pending["placed_at_ms"]):
            remaining.append(pending)
            continue
        expired = _elapsed_since_placement_ms(
            pending, now_ms=now_ms, now_mono_ms=now_mono_ms
        ) >= int(timeout_ms)
        venues = books_by_symbol.get(str(pending["symbol"]), {})
        long_book = venues.get(str(pending["long_exchange"]))
        short_book = venues.get(str(pending["short_exchange"]))
        if long_book is None or short_book is None:
            if expired and not pending.get("long_filled") and not pending.get("short_filled"):
                state["maker_entry_cancel_count"] = int(state.get("maker_entry_cancel_count", 0)) + 1
                _append_jsonl(
                    journal_path,
                    {
                        "record_type": "PAPER_MAKER_ENTRY_CANCEL",
                        **pending,
                        "cancelled_at": now_utc,
                        "cancel_reason": "MARKET_DATA_TIMEOUT",
                    },
                )
                continue
            remaining.append(pending)
            continue

        was_long_filled = bool(pending.get("long_filled"))
        was_short_filled = bool(pending.get("short_filled"))
        long_filled = was_long_filled or passive_limit_filled(
            "buy",
            float(pending["long_limit_price"]),
            long_book.book,
            placed_at_ms=int(pending["placed_at_ms"]),
            placed_at_mono_ms=pending.get("placed_at_mono_ms"),
            strict_price_through=strict_maker_price_through,
        )
        short_filled = was_short_filled or passive_limit_filled(
            "sell",
            float(pending["short_limit_price"]),
            short_book.book,
            placed_at_ms=int(pending["placed_at_ms"]),
            placed_at_mono_ms=pending.get("placed_at_mono_ms"),
            strict_price_through=strict_maker_price_through,
        )
        if long_filled and not was_long_filled:
            pending["long_fill_observed_at_ms"] = int(
                long_book.book.get("received_at_ms", long_book.book.get("timestamp", now_ms))
            )
            received_mono = long_book.book.get("received_mono_ms")
            if received_mono is not None:
                pending["long_fill_observed_mono_ms"] = int(received_mono)
        if short_filled and not was_short_filled:
            pending["short_fill_observed_at_ms"] = int(
                short_book.book.get("received_at_ms", short_book.book.get("timestamp", now_ms))
            )
            received_mono = short_book.book.get("received_mono_ms")
            if received_mono is not None:
                pending["short_fill_observed_mono_ms"] = int(received_mono)
        if not long_filled and not short_filled:
            if not expired:
                remaining.append(pending)
                continue
            record_fill_outcome(stats_db, str(pending["long_exchange"]), "buy", filled=False)
            record_fill_outcome(stats_db, str(pending["short_exchange"]), "sell", filled=False)
            state["maker_fill_observation_count"] = int(state.get("maker_fill_observation_count", 0)) + 2
            state["maker_entry_cancel_count"] = int(state.get("maker_entry_cancel_count", 0)) + 1
            _append_jsonl(
                journal_path,
                {
                    "record_type": "PAPER_MAKER_ENTRY_CANCEL",
                    **pending,
                    "cancelled_at": now_utc,
                    "cancel_reason": "NO_CAUSAL_FILL",
                },
            )
            continue

        if not pending.get("fill_outcomes_recorded"):
            record_fill_outcome(stats_db, str(pending["long_exchange"]), "buy", filled=long_filled)
            record_fill_outcome(stats_db, str(pending["short_exchange"]), "sell", filled=short_filled)
            state["maker_fill_observation_count"] = int(state.get("maker_fill_observation_count", 0)) + 2
            pending["fill_outcomes_recorded"] = True
        pending["long_filled"] = long_filled
        pending["short_filled"] = short_filled

        quantity = float(pending["quantity"])
        if long_filled:
            long_price = float(pending["long_limit_price"])
            long_liquidity = "MAKER"
            long_entry_fee_bps = float(maker_fee_bps[str(pending["long_exchange"])])
        else:
            long_fill = _market_fill(
                long_book,
                side="buy",
                quantity=quantity,
                fee_bps=float(taker_fee_bps[str(pending["long_exchange"])]),
            )
            if long_fill is None:
                state["maker_hedge_failure_count"] = int(state.get("maker_hedge_failure_count", 0)) + 1
                if short_filled and _record_one_leg_abort(
                    state,
                    pending,
                    long_filled=False,
                    long_book=long_book,
                    short_book=short_book,
                    taker_fee_bps=taker_fee_bps,
                    maker_fee_bps=maker_fee_bps,
                    now_ms=now_ms,
                    now_utc=now_utc,
                    journal_path=journal_path,
                    abort_reason="HEDGE_DEPTH_UNAVAILABLE",
                ):
                    continue
                remaining.append(pending)
                continue
            long_price = float(long_fill.vwap)
            long_liquidity = "TAKER"
            long_entry_fee_bps = float(taker_fee_bps[str(pending["long_exchange"])])

        if short_filled:
            short_price = float(pending["short_limit_price"])
            short_liquidity = "MAKER"
            short_entry_fee_bps = float(maker_fee_bps[str(pending["short_exchange"])])
        else:
            short_fill = _market_fill(
                short_book,
                side="sell",
                quantity=quantity,
                fee_bps=float(taker_fee_bps[str(pending["short_exchange"])]),
            )
            if short_fill is None:
                state["maker_hedge_failure_count"] = int(state.get("maker_hedge_failure_count", 0)) + 1
                if long_filled and _record_one_leg_abort(
                    state,
                    pending,
                    long_filled=True,
                    long_book=long_book,
                    short_book=short_book,
                    taker_fee_bps=taker_fee_bps,
                    maker_fee_bps=maker_fee_bps,
                    now_ms=now_ms,
                    now_utc=now_utc,
                    journal_path=journal_path,
                    abort_reason="HEDGE_DEPTH_UNAVAILABLE",
                ):
                    continue
                remaining.append(pending)
                continue
            short_price = float(short_fill.vwap)
            short_liquidity = "TAKER"
            short_entry_fee_bps = float(taker_fee_bps[str(pending["short_exchange"])])

        features = multi_horizon_route_features(
            stats_db,
            str(pending["symbol"]),
            str(pending["long_exchange"]),
            str(pending["short_exchange"]),
            now_ms=now_ms,
        )
        baseline_60m = float((features or pending).get("baseline_60m_bps", 0.0))
        baseline_15m = float((features or pending).get("baseline_15m_bps", baseline_60m))
        route_sigma = float((features or pending).get("route_sigma_bps", pending.get("route_sigma_bps", 0.5)))
        volatility = float(
            (features or pending).get("price_volatility_bps", pending.get("price_volatility_bps", 0.0))
        )
        # Post-fill admission is deliberately stricter than the placement EV:
        # assume both eventual exits are taker and grant zero future maker-price
        # improvement until V18 has its own causal calibration evidence.
        conservative_exit_fee_bps = float(taker_fee_bps[str(pending["long_exchange"])]) + float(
            taker_fee_bps[str(pending["short_exchange"])]
        )
        fresh_adverse_selection_bps = max(0.25, 0.10 * route_sigma + 0.05 * volatility)
        post_fill = post_fill_entry_ev(
            long_entry_price=long_price,
            short_entry_price=short_price,
            baseline_60m_bps=baseline_60m,
            baseline_15m_bps=baseline_15m,
            long_entry_fee_bps=long_entry_fee_bps,
            short_entry_fee_bps=short_entry_fee_bps,
            expected_exit_fee_bps=conservative_exit_fee_bps,
            expected_exit_price_improvement_bps=0.0,
            adverse_selection_bps=fresh_adverse_selection_bps,
            route_sigma_bps=route_sigma,
            price_volatility_bps=volatility,
            safety_buffer_bps=float(state.get("safety_buffer_bps", 0.5)),
            placement_capture_bps=float(pending.get("capture_bps", 0.0)),
        )
        pending.update(
            {
                "baseline_60m_bps": baseline_60m,
                "baseline_15m_bps": baseline_15m,
                "route_sigma_bps": route_sigma,
                "price_volatility_bps": volatility,
                "post_fill_exit_fee_bps": conservative_exit_fee_bps,
                "post_fill_adverse_selection_bps": fresh_adverse_selection_bps,
                "actual_gross_spread_bps": float(post_fill["actual_gross_spread_bps"]),
                "actual_capture_bps": float(post_fill["actual_capture_bps"]),
                "post_fill_expected_value_bps": float(post_fill["post_fill_expected_value_bps"]),
                "minimum_required_ev_bps": float(post_fill["minimum_required_ev_bps"]),
                "post_fill_decision": str(post_fill["decision"]),
            }
        )

        one_leg = long_filled != short_filled
        if one_leg and not bool(post_fill["tradeable"]):
            if not _record_one_leg_abort(
                state,
                pending,
                long_filled=long_filled,
                long_book=long_book,
                short_book=short_book,
                taker_fee_bps=taker_fee_bps,
                maker_fee_bps=maker_fee_bps,
                now_ms=now_ms,
                now_utc=now_utc,
                journal_path=journal_path,
            ):
                state["maker_hedge_failure_count"] = int(state.get("maker_hedge_failure_count", 0)) + 1
                remaining.append(pending)
            continue

        if bool(post_fill["tradeable"]):
            state["post_fill_accept_count"] = int(state.get("post_fill_accept_count", 0)) + 1
        elif long_filled and short_filled:
            pending["post_fill_decision"] = "BOTH_MAKER_FILLED_SUNK_ENTRY"
            state["both_maker_fill_count"] = int(state.get("both_maker_fill_count", 0)) + 1

        position = _position_from_pending(
            pending,
            long_price=long_price,
            short_price=short_price,
            long_liquidity=long_liquidity,
            short_liquidity=short_liquidity,
            long_fee_bps=long_entry_fee_bps,
            short_fee_bps=short_entry_fee_bps,
            now_ms=now_ms,
            now_utc=now_utc,
        )
        position["entry_maker_wait_ms"] = _elapsed_since_placement_ms(
            pending, now_ms=now_ms, now_mono_ms=now_mono_ms
        )
        if one_leg:
            fill_side = "long" if long_filled else "short"
            fill_mono = pending.get(f"{fill_side}_fill_observed_mono_ms")
            if fill_mono is not None and now_mono_ms is not None:
                position["entry_hedge_delay_ms"] = max(0, int(now_mono_ms) - int(fill_mono))
            else:
                fill_received_ms = pending.get(f"{fill_side}_fill_observed_at_ms", now_ms)
                position["entry_hedge_delay_ms"] = max(0, int(now_ms) - int(fill_received_ms))
        state.setdefault("open_positions", []).append(position)
        state["opened_position_count"] = int(state.get("opened_position_count", 0)) + 1
        if position["entry_execution_mode"] == "MAKER_TAKER_HEDGE":
            state["one_leg_hedge_count"] = int(state.get("one_leg_hedge_count", 0)) + 1
        _append_jsonl(journal_path, {"record_type": "PAPER_POSITION_OPEN", **position})

    state["pending_entries"] = remaining
    _refresh_v17_margin(state, books_by_symbol)
    _refresh_v18_state(state)


def run_cycle_v18(
    *,
    clients: dict[str, Any],
    symbols: list[str],
    state: dict[str, Any],
    history_db: str | Path,
    now_ms: int,
    now_utc: str,
    journal_path: Path,
    symbol_venues: dict[str, tuple[str, ...]],
    max_book_age_ms: int = 1_500,
    depth_limit: int = 20,
    safety_buffer_bps: float = 0.5,
    monotonic_ms: int | None = None,
    max_pending_entries: int = 2,
    max_probes: int = 4,
    strict_maker_price_through: bool = False,
) -> None:
    state["safety_buffer_bps"] = float(safety_buffer_bps)
    run_cycle_v17(
        clients=clients,
        symbols=symbols,
        state=state,
        history_db=history_db,
        stats_db=history_db,
        safety_buffer_bps=safety_buffer_bps,
        depth_limit=depth_limit,
        taker_fee_bps=DEFAULT_FEE_BPS,
        maker_fee_bps=DEFAULT_MAKER_FEE_BPS,
        max_book_age_ms=max_book_age_ms,
        now_ms=now_ms,
        now_utc=now_utc,
        journal_path=journal_path,
        symbol_venues=symbol_venues,
        profile_selector=select_v18_profile,
        pending_entry_processor=_process_pending_entries_v18,
        invariant_checker=_assert_v18_invariants,
        max_pending_entries=max_pending_entries,
        max_probes=max_probes,
        strategy_id=STRATEGY_ID,
        exit_decision_filter=_confirm_v18_exit,
        monotonic_ms=monotonic_ms,
        strict_maker_price_through=strict_maker_price_through,
    )
    _refresh_v18_state(state)


def load_state_v18(
    path: str | Path,
    *,
    venue_names: list[str],
    initial_equity: float = 100.0,
    gross_leverage_cap: float = 40.0,
    max_open_positions: int = 8,
) -> dict[str, Any]:
    state_path = Path(path)
    if not state_path.exists():
        return _default_state_v18(
            venue_names,
            initial_equity=initial_equity,
            gross_leverage_cap=gross_leverage_cap,
            max_open_positions=max_open_positions,
        )
    with state_path.open(encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported V18 paper state schema")
    for key, default in (
        ("pending_entries", []),
        ("pending_exits", []),
        ("maker_probes", []),
        ("route_cooldowns", {}),
        ("post_fill_accept_count", 0),
        ("post_fill_reject_count", 0),
        ("both_maker_fill_count", 0),
        ("one_leg_abort_count", 0),
        ("one_leg_abort_pnl", 0.0),
        ("memory_prune_count", 0),
        ("divergence_confirmations", {}),
    ):
        state.setdefault(key, default)
    _refresh_v18_state(state)
    _assert_v18_invariants(state)
    return state


async def _load_coverage(clients: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    results = await asyncio.gather(
        *(client.load_markets() for client in clients.values()),
        return_exceptions=True,
    )
    coverage: dict[str, set[str]] = {}
    for (venue, _), markets in zip(clients.items(), results, strict=True):
        if isinstance(markets, BaseException) or not isinstance(markets, dict):
            continue
        for market in markets.values():
            if _eligible_linear_usdt_swap(market):
                coverage.setdefault(str(market["symbol"]), set()).add(venue)
    return {
        symbol: tuple(sorted(venues))
        for symbol, venues in coverage.items()
        if len(venues) >= 2
    }


def _mark_open_positions_v18(
    state: dict[str, Any],
    clients: dict[str, Any],
    *,
    marked_at_utc: str,
) -> None:
    """Persist marks from the exact public snapshot used by the strategy cycle."""

    for position in state.get("open_positions", []):
        long_name = str(position.get("long_exchange") or "")
        short_name = str(position.get("short_exchange") or "")
        symbol = str(position.get("symbol") or "")
        long_client = clients.get(long_name)
        short_client = clients.get(short_name)
        if not symbol or long_client is None or short_client is None:
            position["mark_status"] = "UNAVAILABLE"
            continue
        try:
            long_raw = (
                long_client.fetch_order_book(symbol, limit=20)
                if hasattr(long_client, "fetch_order_book")
                else long_client.book
            )
            short_raw = (
                short_client.fetch_order_book(symbol, limit=20)
                if hasattr(short_client, "fetch_order_book")
                else short_client.book
            )
            mark_input = {
                **position,
                "long_fee_bps": float(DEFAULT_FEE_BPS[long_name]),
                "short_fee_bps": float(DEFAULT_FEE_BPS[short_name]),
            }
            position.update(
                mark_open_position(
                    mark_input,
                    long_book=long_raw,
                    short_book=short_raw,
                    marked_at_utc=marked_at_utc,
                )
            )
        except (KeyError, TypeError, ValueError):
            position["mark_status"] = "UNAVAILABLE"


def _process_rss_bytes() -> int:
    try:
        pages = int(Path("/proc/self/statm").read_text().split()[1])
        return pages * int(__import__("os").sysconf("SC_PAGE_SIZE"))
    except (OSError, ValueError, IndexError):
        return 0


async def _run(args: argparse.Namespace) -> int:
    artifacts = args.artifacts_dir
    state_path = artifacts / "state.json"
    health_path = artifacts / "health.json"
    journal_path = artifacts / "positions.jsonl"
    history_db = artifacts / "history_v18.sqlite"
    clients = make_public_stream_clients()
    stop_event = asyncio.Event()
    tasks: list[asyncio.Task[Any]] = []
    try:
        coverage = await _load_coverage(clients)
        symbols = _sorted_universe(coverage, args.symbols)
        if not symbols:
            raise RuntimeError("fewer than two venues share active linear USDT perpetual symbols")
        coverage = {symbol: coverage[symbol] for symbol in symbols}
        venue_names = sorted({venue for symbol in symbols for venue in coverage[symbol]})
        retained_market_count = compact_public_stream_markets(clients, coverage)
        state = load_state_v18(
            state_path,
            venue_names=venue_names,
            initial_equity=args.initial_equity,
            gross_leverage_cap=args.gross_leverage_cap,
            max_open_positions=args.max_open_positions,
        )
        state["universe_symbols"] = symbols
        state["universe_venues"] = {symbol: list(coverage[symbol]) for symbol in symbols}
        state["retained_market_count"] = retained_market_count
        state["maker_fill_calibration_source"] = "V18_CAUSAL_ONLY"
        if not history_db.exists() and args.seed_history_db.exists():
            state["seeded_route_history_count"] = seed_route_history_from_v16(
                history_db,
                args.seed_history_db,
                now_ms=int(time.time() * 1000),
            )

        cache = LatestBookCache(
            depth_limit=args.depth,
            max_entries=max(512, len(symbols) * len(venue_names) + 32),
        )
        for symbol in symbols:
            for venue in coverage[symbol]:
                tasks.append(
                    asyncio.create_task(
                        watch_public_book(
                            venue,
                            clients[venue],
                            symbol,
                            cache,
                            stop_event,
                            depth_limit=args.depth,
                        )
                    )
                )

        started = time.monotonic()
        scan_cursor = 0
        while True:
            now_ms = int(time.time() * 1000)
            now_mono_ms = int(time.monotonic() * 1000)
            snapshot_clients, metrics = cache.snapshot(
                now_ms=now_ms,
                now_mono_ms=now_mono_ms,
                max_age_ms=args.max_book_age_ms,
                max_skew_ms=args.max_book_skew_ms,
            )
            state.update(
                {
                    "book_update_count": int(metrics["book_update_count"]),
                    "ws_reconnect_count": int(metrics["ws_reconnect_count"]),
                    "book_cache_entry_count": int(metrics["cache_entry_count"]),
                    "fresh_book_count": int(metrics["fresh_book_count"]),
                    "stale_book_count": int(metrics["stale_book_count"]),
                    "connected_venue_count": int(metrics["connected_venue_count"]),
                    "book_age_ms_median": metrics["book_age_ms_median"],
                    "book_age_ms_max": metrics["book_age_ms_max"],
                    "process_rss_bytes": _process_rss_bytes(),
                }
            )
            if state["process_rss_bytes"] >= int(args.memory_hard_limit_mb * 1024 * 1024):
                write_state(state_path, state)
                _write_health(
                    health_path,
                    status="DEGRADED",
                    error="PROCESS_RSS_HARD_LIMIT",
                    schema_version=HEALTH_SCHEMA_VERSION,
                )
                raise MemoryError("V18 RSS exceeded hard safety limit")
            if state["process_rss_bytes"] >= int(args.memory_high_water_mb * 1024 * 1024):
                pruned = cache.prune_stale(
                    now_ms=now_ms,
                    max_age_ms=args.max_book_age_ms,
                    now_mono_ms=now_mono_ms,
                )
                state["memory_prune_count"] = int(state.get("memory_prune_count", 0)) + pruned
            if len(snapshot_clients) >= 2:
                batch_size = min(int(args.scan_batch_size), len(symbols))
                discovery_symbols = [
                    symbols[(scan_cursor + offset) % len(symbols)]
                    for offset in range(batch_size)
                ]
                scan_cursor = (scan_cursor + batch_size) % len(symbols)
                state["discovery_scan_batch_size"] = batch_size
                state["discovery_scan_cursor"] = scan_cursor
                await asyncio.to_thread(
                    run_cycle_v18,
                    clients=snapshot_clients,
                    symbols=discovery_symbols,
                    state=state,
                    history_db=history_db,
                    now_ms=now_ms,
                    now_utc=_utc_now(),
                    journal_path=journal_path,
                    symbol_venues=coverage,
                    max_book_age_ms=args.max_book_age_ms,
                    depth_limit=args.depth,
                    safety_buffer_bps=args.safety_buffer_bps,
                    monotonic_ms=now_mono_ms,
                    max_pending_entries=args.max_pending_entries,
                    max_probes=args.max_probes,
                )
                _mark_open_positions_v18(state, snapshot_clients, marked_at_utc=_utc_now())
                write_state(state_path, state)
                _write_health(
                    health_path,
                    status="HEALTHY",
                    schema_version=HEALTH_SCHEMA_VERSION,
                )
                print(
                    json.dumps(
                        {
                            "equity": state["equity"],
                            "open_positions": len(state["open_positions"]),
                            "pending_entries": len(state["pending_entries"]),
                            "book_age_ms_median": state["book_age_ms_median"],
                            "post_fill_rejects": state["post_fill_reject_count"],
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                if args.once:
                    break
            elif time.monotonic() - started >= args.stream_warmup_seconds:
                _write_health(
                    health_path,
                    status="DEGRADED",
                    error="PUBLIC_BOOK_WARMUP_TIMEOUT",
                    schema_version=HEALTH_SCHEMA_VERSION,
                )
                if args.once:
                    raise RuntimeError("public WebSocket book warmup timed out")

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=args.interval)
            except TimeoutError:
                pass
        return 0
    finally:
        stop_event.set()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await close_public_stream_clients(clients)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-equity", type=float, default=100.0)
    parser.add_argument("--symbols", type=int, default=50)
    parser.add_argument("--scan-batch-size", type=int, default=2)
    parser.add_argument("--max-pending-entries", type=int, default=2)
    parser.add_argument("--max-probes", type=int, default=4)
    parser.add_argument("--interval", type=float, default=0.25)
    parser.add_argument("--depth", type=int, default=20)
    parser.add_argument("--safety-buffer-bps", type=float, default=0.5)
    parser.add_argument("--max-book-age-ms", type=int, default=1_500)
    parser.add_argument("--max-book-skew-ms", type=int, default=500)
    parser.add_argument("--stream-warmup-seconds", type=float, default=30.0)
    parser.add_argument("--gross-leverage-cap", type=float, default=40.0)
    parser.add_argument("--max-open-positions", type=int, default=8)
    parser.add_argument("--memory-high-water-mb", type=float, default=700.0)
    parser.add_argument("--memory-hard-limit-mb", type=float, default=1_024.0)
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/arbitrage_v18"))
    parser.add_argument(
        "--seed-history-db",
        type=Path,
        default=Path("artifacts/arbitrage_v17/history_v17.sqlite"),
    )
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.interval <= 0.0 or args.stream_warmup_seconds <= 0.0:
        raise ValueError("interval and stream warmup must be positive")
    if args.scan_batch_size <= 0 or args.max_pending_entries <= 0 or args.max_probes <= 0:
        raise ValueError("scan batch, pending entry, and probe limits must be positive")
    if args.max_book_age_ms <= 0 or args.max_book_skew_ms <= 0:
        raise ValueError("book age and skew limits must be positive")
    if not 20.0 <= args.gross_leverage_cap <= 40.0:
        raise ValueError("V18 gross leverage cap must be in 20x..40x")
    if args.memory_high_water_mb < 128.0:
        raise ValueError("memory high-water must be at least 128 MB")
    if args.memory_hard_limit_mb <= args.memory_high_water_mb:
        raise ValueError("memory hard limit must exceed the soft high-water mark")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
