"""V19 public-WebSocket, causal post-fill EV paper arbitrage runner."""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import math
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
    public_stream_health,
    start_public_book_watchers,
    start_public_trade_watchers,
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
        _increment_candidate_funnel,
        _maker_leg_cooldown_key,
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
        _increment_candidate_funnel,
        _maker_leg_cooldown_key,
        _market_fill,
        _position_from_pending,
        _refresh_v17_margin,
        run_cycle_v17,
    )

SCHEMA_VERSION = "v19-arbitrage-paper-1"
HEALTH_SCHEMA_VERSION = "v19-arbitrage-health-1"
PORTFOLIO_MODEL = "WS_CAUSAL_POST_FILL_EV_V2"
MARGIN_MODEL = "CROSS_MARGIN_PAPER_V1"
STRATEGY_ID = "WS_CAUSAL_POST_FILL_EV_V2"
CANDIDATE_FUNNEL_KEYS = (
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


def _candidate_funnel_counts(value: Any = None) -> dict[str, int]:
    source = value if isinstance(value, dict) else {}
    counts: dict[str, int] = {}
    for key in CANDIDATE_FUNNEL_KEYS:
        try:
            count = int(source.get(key, 0))
        except (TypeError, ValueError):
            count = 0
        counts[key] = max(0, count)
    return counts


def _default_state_v19(
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
            "last_history_sample_ms_by_symbol": {},
            "safety_buffer_bps": 0.5,
            "candidate_funnel_counts": _candidate_funnel_counts(),
            "post_fill_accept_count": 0,
            "post_fill_reject_count": 0,
            "both_maker_fill_count": 0,
            "one_leg_abort_count": 0,
            "one_leg_abort_pnl": 0.0,
            "one_leg_unwind_attempt_count": 0,
            "one_leg_unwind_failure_count": 0,
            "partial_exposure_count": 0,
            "partial_exposure_gross_notional": 0.0,
            "partial_exposure_unrealized_pnl": 0.0,
            "partial_exposure_entry_fees": 0.0,
            "partial_exposure_reserved_margin": 0.0,
            "book_update_count": 0,
            "ws_reconnect_count": 0,
            "book_cache_entry_count": 0,
            "fresh_book_count": 0,
            "stale_book_count": 0,
            "age_expired_book_count": 0,
            "skew_rejected_book_count": 0,
            "disconnected_book_count": 0,
            "connected_venue_count": 0,
            "stream_error_counts": {},
            "stream_error_counts_by_venue": {},
            "stream_identity_metrics": [],
            "book_age_ms_median": None,
            "book_age_ms_max": None,
            "memory_prune_count": 0,
            "process_rss_bytes": 0,
            "divergence_confirmations": {},
        }
    )
    return state


def _refresh_v19_state(state: dict[str, Any]) -> None:
    state["schema_version"] = SCHEMA_VERSION
    state["portfolio_model"] = PORTFOLIO_MODEL
    state["margin_model"] = MARGIN_MODEL
    state["exchange_leverage"] = 40.0
    state["min_position_leverage"] = 20.0
    state["max_position_leverage"] = 40.0
    state["candidate_funnel_counts"] = _candidate_funnel_counts(
        state.get("candidate_funnel_counts")
    )


def _assert_v19_invariants(
    state: dict[str, Any],
    *,
    expected_strategy_id: str = STRATEGY_ID,
    refresh_state: bool = True,
) -> None:
    _assert_v17_invariants(state)
    for position in state.get("open_positions", []):
        if str(position.get("strategy_id")) != str(expected_strategy_id):
            raise ValueError("paper position has the wrong strategy")
        if not 20.0 <= float(position.get("leverage", 0.0)) <= 40.0:
            raise ValueError("V19 position leverage outside 20x..40x")
    unwind_pending = [
        pending
        for pending in state.get("pending_entries", [])
        if pending.get("status") == "UNWIND_PENDING"
    ]
    for pending in unwind_pending:
        long_filled = bool(pending.get("long_filled"))
        short_filled = bool(pending.get("short_filled"))
        if long_filled == short_filled:
            raise ValueError("UNWIND_PENDING must have exactly one filled maker leg")
        expected_filled = "LONG" if long_filled else "SHORT"
        expected_cancelled = "SHORT" if long_filled else "LONG"
        if pending.get("filled_side") != expected_filled:
            raise ValueError("UNWIND_PENDING filled-side identity is inconsistent")
        if pending.get("cancelled_maker_leg") != expected_cancelled:
            raise ValueError("UNWIND_PENDING cancelled-leg identity is inconsistent")
        for key in (
            "partial_entry_notional",
            "partial_entry_fee",
            "partial_gross_notional",
            "partial_initial_margin",
        ):
            if float(pending.get(key, 0.0)) <= 0.0:
                raise ValueError(f"UNWIND_PENDING {key} must be positive")
    if unwind_pending:
        if int(state.get("partial_exposure_count", 0)) != len(unwind_pending):
            raise ValueError("partial exposure count must match UNWIND_PENDING rows")
        if float(state.get("gross_exposure", 0.0)) <= 0.0:
            raise ValueError("UNWIND_PENDING gross exposure must remain visible")
        if float(state.get("initial_margin_used", 0.0)) <= 0.0:
            raise ValueError("UNWIND_PENDING margin must remain reserved")
    if refresh_state:
        _refresh_v19_state(state)


def _confirm_v19_exit(
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
        _increment_candidate_funnel(state, "post_fill_rejected")
    else:
        _increment_candidate_funnel(state, "execution_abort")
    state["one_leg_abort_count"] = int(state.get("one_leg_abort_count", 0)) + 1
    state["one_leg_abort_pnl"] = float(state.get("one_leg_abort_pnl", 0.0)) + net_pnl
    state.setdefault("route_cooldowns", {})[str(pending["position_key"])] = int(now_ms)
    maker_cooldown_key = _maker_leg_cooldown_key(str(pending["symbol"]), venue, side)
    if maker_cooldown_key is not None:
        state["route_cooldowns"][maker_cooldown_key] = int(now_ms)
    _append_jsonl(
        journal_path,
        {
            "record_type": "PAPER_ONE_LEG_ABORT",
            "strategy_id": str(pending.get("strategy_id") or STRATEGY_ID),
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


def _book_snapshot_stamps(venue_book: Any) -> tuple[int | None, int | None]:
    def parse(value: Any) -> int | None:
        try:
            return None if value is None else int(value)
        except (TypeError, ValueError):
            return None

    book = venue_book.book
    received_at_ms = parse(book.get("received_at_ms", book.get("timestamp")))
    received_mono_ms = parse(book.get("received_mono_ms"))
    return received_at_ms, received_mono_ms


def _unwind_snapshot_is_newer(
    pending: dict[str, Any],
    venue_book: Any,
) -> bool:
    received_at_ms, received_mono_ms = _book_snapshot_stamps(venue_book)
    last_mono = pending.get("last_unwind_snapshot_mono_ms")
    if received_mono_ms is not None and last_mono is not None:
        return received_mono_ms > int(last_mono)
    last_at = pending.get("last_unwind_snapshot_at_ms")
    if received_at_ms is not None and last_at is not None:
        return received_at_ms > int(last_at)
    return (
        (received_mono_ms is not None and last_mono is None)
        or (received_at_ms is not None and last_at is None)
    )


def _note_unwind_attempt(
    state: dict[str, Any],
    pending: dict[str, Any],
    venue_book: Any,
) -> None:
    received_at_ms, received_mono_ms = _book_snapshot_stamps(venue_book)
    if received_at_ms is not None:
        pending["last_unwind_snapshot_at_ms"] = received_at_ms
    if received_mono_ms is not None:
        pending["last_unwind_snapshot_mono_ms"] = received_mono_ms
    pending["unwind_attempt_count"] = int(
        pending.get("unwind_attempt_count", 0)
    ) + 1
    state["one_leg_unwind_attempt_count"] = int(
        state.get("one_leg_unwind_attempt_count", 0)
    ) + 1


def _note_unwind_failure(
    state: dict[str, Any],
    pending: dict[str, Any],
) -> None:
    pending["unwind_failure_count"] = int(
        pending.get("unwind_failure_count", 0)
    ) + 1
    state["one_leg_unwind_failure_count"] = int(
        state.get("one_leg_unwind_failure_count", 0)
    ) + 1


def _transition_to_unwind_pending(
    state: dict[str, Any],
    pending: dict[str, Any],
    *,
    long_filled: bool,
    now_ms: int,
    now_utc: str,
    journal_path: Path,
    unwind_reason: str = "HEDGE_DEPTH_UNAVAILABLE",
) -> None:
    filled_side = "LONG" if long_filled else "SHORT"
    cancelled_maker_leg = "SHORT" if long_filled else "LONG"
    venue = str(
        pending["long_exchange"] if long_filled else pending["short_exchange"]
    )
    entry_price = float(
        pending["long_limit_price"] if long_filled else pending["short_limit_price"]
    )
    entry_fee_bps = float(
        pending["long_maker_fee_bps"]
        if long_filled
        else pending["short_maker_fee_bps"]
    )
    quantity = float(pending["quantity"])
    entry_notional = quantity * entry_price
    entry_fee = entry_notional * entry_fee_bps / 10_000.0
    initial_margin = entry_notional / float(pending["leverage"])
    pending.update(
        {
            "status": "UNWIND_PENDING",
            "filled_side": filled_side,
            "filled_venue": venue,
            "cancelled_maker_leg": cancelled_maker_leg,
            "unwind_reason": str(unwind_reason),
            "unwind_pending_since_ms": int(now_ms),
            "unwind_pending_since_utc": now_utc,
            "partial_entry_price": entry_price,
            "partial_entry_notional": entry_notional,
            "partial_entry_fee_bps": entry_fee_bps,
            "partial_entry_fee": entry_fee,
            "partial_gross_notional": entry_notional,
            "partial_gross_unrealized_pnl": 0.0,
            "partial_unrealized_pnl": -entry_fee,
            "partial_initial_margin": initial_margin,
            "partial_mark_status": "UNAVAILABLE",
        }
    )
    state["maker_entry_cancel_count"] = int(
        state.get("maker_entry_cancel_count", 0)
    ) + 1
    _append_jsonl(
        journal_path,
        {
            "record_type": "PAPER_ONE_LEG_UNWIND_PENDING",
            "strategy_id": STRATEGY_ID,
            "pending_id": str(pending["pending_id"]),
            "position_key": str(pending["position_key"]),
            "symbol": str(pending["symbol"]),
            "status": "UNWIND_PENDING",
            "filled_side": filled_side,
            "filled_venue": venue,
            "cancelled_maker_leg": cancelled_maker_leg,
            "quantity": quantity,
            "entry_price": entry_price,
            "entry_fee_bps": entry_fee_bps,
            "entry_fees": entry_fee,
            "gross_notional": entry_notional,
            "reserved_margin": initial_margin,
            "transition_reason": str(unwind_reason),
            "transitioned_at": now_utc,
        },
    )


def _process_unwind_pending_v19(
    state: dict[str, Any],
    pending: dict[str, Any],
    *,
    venues: dict[str, Any],
    taker_fee_bps: dict[str, float],
    maker_fee_bps: dict[str, float],
    now_ms: int,
    now_utc: str,
    journal_path: Path,
    execution_outcome_recorder: Any = None,
) -> bool:
    long_filled = bool(pending.get("long_filled"))
    filled_venue = str(
        pending["long_exchange"] if long_filled else pending["short_exchange"]
    )
    filled_book = venues.get(filled_venue)
    if filled_book is None or not _unwind_snapshot_is_newer(pending, filled_book):
        return False

    _note_unwind_attempt(state, pending, filled_book)
    realized_before = float(state.get("realized_pnl", 0.0))
    if _record_one_leg_abort(
        state,
        pending,
        long_filled=long_filled,
        long_book=filled_book if long_filled else None,
        short_book=filled_book if not long_filled else None,
        taker_fee_bps=taker_fee_bps,
        maker_fee_bps=maker_fee_bps,
        now_ms=now_ms,
        now_utc=now_utc,
        journal_path=journal_path,
        abort_reason=str(
            pending.get("unwind_reason") or "HEDGE_DEPTH_UNAVAILABLE"
        ),
    ):
        if execution_outcome_recorder is not None:
            execution_outcome_recorder(
                pending,
                accepted=False,
                realized_net_pnl=float(state.get("realized_pnl", 0.0)) - realized_before,
            )
        return True
    _note_unwind_failure(state, pending)
    return False


def _process_pending_entries_v19(
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
    execution_outcome_recorder: Any = None,
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
        if pending.get("status") == "UNWIND_PENDING":
            terminal = _process_unwind_pending_v19(
                state,
                pending,
                venues=venues,
                taker_fee_bps=taker_fee_bps,
                maker_fee_bps=maker_fee_bps,
                now_ms=now_ms,
                now_utc=now_utc,
                journal_path=journal_path,
                execution_outcome_recorder=execution_outcome_recorder,
            )
            if not terminal:
                remaining.append(pending)
            continue
        long_book = venues.get(str(pending["long_exchange"]))
        short_book = venues.get(str(pending["short_exchange"]))
        selected_maker_side = str(pending.get("maker_side") or "").upper()
        if selected_maker_side not in {"", "LONG", "SHORT"}:
            raise ValueError("maker_side must be LONG or SHORT when supplied")
        long_is_maker = selected_maker_side in {"", "LONG"}
        short_is_maker = selected_maker_side in {"", "SHORT"}
        was_long_filled = bool(pending.get("long_filled"))
        was_short_filled = bool(pending.get("short_filled"))
        long_filled = was_long_filled or (
            long_is_maker
            and long_book is not None
            and passive_limit_filled(
                "buy",
                float(pending["long_limit_price"]),
                long_book.book,
                placed_at_ms=int(pending["placed_at_ms"]),
                placed_at_mono_ms=pending.get("placed_at_mono_ms"),
                strict_price_through=strict_maker_price_through,
                queue_ahead_quantity=pending.get("long_queue_ahead_quantity"),
                order_quantity=pending.get("quantity"),
                trade_volume_baseline=pending.get("long_trade_volume_baseline"),
            )
        )
        short_filled = was_short_filled or (
            short_is_maker
            and short_book is not None
            and passive_limit_filled(
                "sell",
                float(pending["short_limit_price"]),
                short_book.book,
                placed_at_ms=int(pending["placed_at_ms"]),
                placed_at_mono_ms=pending.get("placed_at_mono_ms"),
                strict_price_through=strict_maker_price_through,
                queue_ahead_quantity=pending.get("short_queue_ahead_quantity"),
                order_quantity=pending.get("quantity"),
                trade_volume_baseline=pending.get("short_trade_volume_baseline"),
            )
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
            if long_book is None or short_book is None:
                state["maker_entry_cancel_count"] = int(state.get("maker_entry_cancel_count", 0)) + 1
                _increment_candidate_funnel(state, "no_causal_fill")
                _append_jsonl(journal_path, {
                    "record_type": "PAPER_MAKER_ENTRY_CANCEL", **pending,
                    "cancelled_at": now_utc, "cancel_reason": "MARKET_DATA_TIMEOUT",
                })
                continue
            observations = 0
            if long_is_maker:
                record_fill_outcome(stats_db, str(pending["long_exchange"]), "buy", filled=False)
                observations += 1
            if short_is_maker:
                record_fill_outcome(stats_db, str(pending["short_exchange"]), "sell", filled=False)
                observations += 1
            state["maker_fill_observation_count"] = int(state.get("maker_fill_observation_count", 0)) + observations
            state["maker_entry_cancel_count"] = int(state.get("maker_entry_cancel_count", 0)) + 1
            _increment_candidate_funnel(state, "no_causal_fill")
            maker_venue = (
                str(pending["long_exchange"])
                if selected_maker_side == "LONG"
                else str(pending["short_exchange"])
                if selected_maker_side == "SHORT"
                else ""
            )
            maker_cooldown_key = _maker_leg_cooldown_key(
                str(pending["symbol"]), maker_venue, selected_maker_side
            )
            if maker_cooldown_key is not None:
                state.setdefault("route_cooldowns", {})[maker_cooldown_key] = int(now_ms)
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
            observations = 0
            if long_is_maker:
                record_fill_outcome(stats_db, str(pending["long_exchange"]), "buy", filled=long_filled)
                observations += 1
            if short_is_maker:
                record_fill_outcome(stats_db, str(pending["short_exchange"]), "sell", filled=short_filled)
                observations += 1
            state["maker_fill_observation_count"] = int(state.get("maker_fill_observation_count", 0)) + observations
            pending["fill_outcomes_recorded"] = True
        pending["long_filled"] = long_filled
        pending["short_filled"] = short_filled

        if long_book is None or short_book is None:
            # A visible maker fill is exposure even when the hedge feed is absent.
            # Reuse durable unwind handling; never turn that fill into a no-fill cancel.
            if long_filled != short_filled:
                state["maker_hedge_failure_count"] = int(state.get("maker_hedge_failure_count", 0)) + 1
                _transition_to_unwind_pending(
                    state, pending, long_filled=long_filled, now_ms=now_ms,
                    now_utc=now_utc, journal_path=journal_path,
                    unwind_reason="HEDGE_MARKET_DATA_UNAVAILABLE",
                )
                if _process_unwind_pending_v19(
                    state, pending, venues=venues, taker_fee_bps=taker_fee_bps,
                    maker_fee_bps=maker_fee_bps, now_ms=now_ms, now_utc=now_utc,
                    journal_path=journal_path, execution_outcome_recorder=execution_outcome_recorder,
                ):
                    continue
            remaining.append(pending)
            continue

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
                state["maker_hedge_failure_count"] = int(
                    state.get("maker_hedge_failure_count", 0)
                ) + 1
                if short_filled:
                    _note_unwind_attempt(state, pending, short_book)
                    realized_before = float(state.get("realized_pnl", 0.0))
                    if _record_one_leg_abort(
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
                        if execution_outcome_recorder is not None:
                            execution_outcome_recorder(
                                pending,
                                accepted=False,
                                realized_net_pnl=float(state.get("realized_pnl", 0.0)) - realized_before,
                            )
                        continue
                    _note_unwind_failure(state, pending)
                    _transition_to_unwind_pending(
                        state,
                        pending,
                        long_filled=False,
                        now_ms=now_ms,
                        now_utc=now_utc,
                        journal_path=journal_path,
                    )
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
                state["maker_hedge_failure_count"] = int(
                    state.get("maker_hedge_failure_count", 0)
                ) + 1
                if long_filled:
                    _note_unwind_attempt(state, pending, long_book)
                    realized_before = float(state.get("realized_pnl", 0.0))
                    if _record_one_leg_abort(
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
                        if execution_outcome_recorder is not None:
                            execution_outcome_recorder(
                                pending,
                                accepted=False,
                                realized_net_pnl=float(state.get("realized_pnl", 0.0)) - realized_before,
                            )
                        continue
                    _note_unwind_failure(state, pending)
                    _transition_to_unwind_pending(
                        state,
                        pending,
                        long_filled=True,
                        now_ms=now_ms,
                        now_utc=now_utc,
                        journal_path=journal_path,
                    )
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
            minimum_span_ms=420_000,
        )
        baseline_60m = float((features or pending).get("baseline_60m_bps", 0.0))
        baseline_15m = float((features or pending).get("baseline_15m_bps", baseline_60m))
        route_sigma = float((features or pending).get("route_sigma_bps", pending.get("route_sigma_bps", 0.5)))
        volatility = float(
            (features or pending).get("price_volatility_bps", pending.get("price_volatility_bps", 0.0))
        )
        # Post-fill admission is deliberately stricter than the placement EV:
        # assume both eventual exits are taker and grant zero future maker-price
        # improvement until V19 has its own causal calibration evidence.
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
        extra_funding_cost_bps = max(0.0, float(pending.get("expected_funding_cost_bps", 0.0) or 0.0))
        if extra_funding_cost_bps > 0.0:
            original_tradeable = bool(post_fill["tradeable"])
            adjusted_ev = float(post_fill["post_fill_expected_value_bps"]) - extra_funding_cost_bps
            minimum_ev = float(post_fill["minimum_required_ev_bps"])
            post_fill = {
                **post_fill,
                "post_fill_expected_value_bps": adjusted_ev,
                "tradeable": original_tradeable and adjusted_ev >= minimum_ev,
                "expected_funding_cost_bps": extra_funding_cost_bps,
            }
            if original_tradeable and not post_fill["tradeable"]:
                post_fill["decision"] = "POST_FILL_FUNDING_COST_REJECTED"
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
            realized_before = float(state.get("realized_pnl", 0.0))
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
                state["maker_hedge_failure_count"] = int(
                    state.get("maker_hedge_failure_count", 0)
                ) + 1
                filled_book = long_book if long_filled else short_book
                _note_unwind_attempt(state, pending, filled_book)
                _note_unwind_failure(state, pending)
                _transition_to_unwind_pending(
                    state,
                    pending,
                    long_filled=long_filled,
                    now_ms=now_ms,
                    now_utc=now_utc,
                    journal_path=journal_path,
                    unwind_reason="POST_FILL_EV_REJECTED",
                )
                remaining.append(pending)
            elif execution_outcome_recorder is not None:
                execution_outcome_recorder(
                    pending,
                    accepted=False,
                    realized_net_pnl=float(state.get("realized_pnl", 0.0)) - realized_before,
                )
            continue

        if bool(post_fill["tradeable"]):
            state["post_fill_accept_count"] = int(state.get("post_fill_accept_count", 0)) + 1
            if execution_outcome_recorder is not None and selected_maker_side:
                execution_outcome_recorder(pending, accepted=True, realized_net_pnl=None)
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
        _increment_candidate_funnel(state, "paired_open")
        if position["entry_execution_mode"] == "MAKER_TAKER_HEDGE":
            state["one_leg_hedge_count"] = int(state.get("one_leg_hedge_count", 0)) + 1
        _append_jsonl(journal_path, {"record_type": "PAPER_POSITION_OPEN", **position})

    state["pending_entries"] = remaining
    _refresh_v17_margin(state, books_by_symbol)
    _refresh_v19_state(state)


def run_cycle_v19(
    *,
    clients: dict[str, Any],
    symbols: list[str],
    state: dict[str, Any],
    history_db: str | Path,
    now_ms: int,
    now_utc: str,
    journal_path: Path,
    symbol_venues: dict[str, tuple[str, ...]],
    max_book_age_ms: int = 5_000,
    depth_limit: int = 20,
    safety_buffer_bps: float = 0.5,
    monotonic_ms: int | None = None,
    max_pending_entries: int = 2,
    max_probes: int = 4,
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
        pending_entry_processor=_process_pending_entries_v19,
        invariant_checker=_assert_v19_invariants,
        max_pending_entries=max_pending_entries,
        max_probes=max_probes,
        strategy_id=STRATEGY_ID,
        exit_decision_filter=_confirm_v19_exit,
        monotonic_ms=monotonic_ms,
        per_symbol_history_sampling=True,
        minimum_history_span_ms=420_000,
        strict_maker_price_through=True,
    )
    _refresh_v19_state(state)


def load_state_v19(
    path: str | Path,
    *,
    venue_names: list[str],
    initial_equity: float = 100.0,
    gross_leverage_cap: float = 40.0,
    max_open_positions: int = 8,
) -> dict[str, Any]:
    state_path = Path(path)
    if not state_path.exists():
        return _default_state_v19(
            venue_names,
            initial_equity=initial_equity,
            gross_leverage_cap=gross_leverage_cap,
            max_open_positions=max_open_positions,
        )
    with state_path.open(encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported V19 paper state schema")
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
        ("one_leg_unwind_attempt_count", 0),
        ("one_leg_unwind_failure_count", 0),
        ("partial_exposure_count", 0),
        ("partial_exposure_gross_notional", 0.0),
        ("partial_exposure_unrealized_pnl", 0.0),
        ("partial_exposure_entry_fees", 0.0),
        ("partial_exposure_reserved_margin", 0.0),
        ("memory_prune_count", 0),
        ("divergence_confirmations", {}),
        ("last_history_sample_ms_by_symbol", {}),
    ):
        state.setdefault(key, default)
    if not isinstance(state["last_history_sample_ms_by_symbol"], dict):
        raise ValueError("V19 per-symbol history clock must be a mapping")
    _refresh_v17_margin(state)
    _refresh_v19_state(state)
    _assert_v19_invariants(state)
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


def _mark_open_positions_v19(
    state: dict[str, Any],
    clients: dict[str, Any],
    *,
    marked_at_utc: str,
    taker_fee_bps: dict[str, float] | None = None,
) -> None:
    """Persist marks from the exact public snapshot used by the strategy cycle."""

    fees = DEFAULT_FEE_BPS if taker_fee_bps is None else taker_fee_bps
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
                "long_fee_bps": float(fees[long_name]),
                "short_fee_bps": float(fees[short_name]),
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


def _snapshot_v19(
    cache: LatestBookCache,
    *,
    state: dict[str, Any],
    discovery_symbols: list[str],
    now_ms: int,
    now_mono_ms: int,
    max_book_age_ms: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    active_symbols = {
        str(row["symbol"])
        for key in ("pending_entries", "pending_exits", "maker_probes", "open_positions")
        for row in state.get(key, [])
        if isinstance(row, dict) and row.get("symbol")
    }
    selected_symbols = set(discovery_symbols) | active_symbols
    return cache.snapshot(
        now_ms=now_ms,
        now_mono_ms=now_mono_ms,
        max_age_ms=max_book_age_ms,
        max_skew_ms=None,
        selected_symbols=selected_symbols,
        require_connected=True,
    )


def _copy_runtime_market_metadata(
    stream_clients: dict[str, Any],
    runtime_clients: dict[str, Any],
) -> None:
    """Seed dedicated REST clients from the already-compacted public market universe."""

    for venue, runtime_client in runtime_clients.items():
        stream_client = stream_clients.get(venue)
        markets = getattr(stream_client, "markets", None)
        set_markets = getattr(runtime_client, "set_markets", None)
        if isinstance(markets, dict) and callable(set_markets):
            set_markets(dict(markets))


def _runtime_refresh_snapshot_in_fresh_loop(
    runtime_refresher: Any,
    *,
    clients_factory: Any,
    market_metadata: dict[str, dict[str, Any]],
    state_snapshot: dict[str, Any],
    symbols: list[str],
    coverage: dict[str, tuple[str, ...]],
    now_ms: int,
) -> dict[str, Any]:
    """Run public REST refresh on its own event loop, isolated from websocket load."""

    async def run() -> dict[str, Any]:
        runtime_clients = clients_factory()
        try:
            for venue, runtime_client in runtime_clients.items():
                markets = market_metadata.get(venue)
                set_markets = getattr(runtime_client, "set_markets", None)
                if isinstance(markets, dict) and callable(set_markets):
                    set_markets(copy.deepcopy(markets))
            await runtime_refresher(
                clients=runtime_clients,
                state=state_snapshot,
                symbols=symbols,
                coverage=coverage,
                now_ms=now_ms,
            )
            return state_snapshot
        finally:
            await close_public_stream_clients(runtime_clients)

    return asyncio.run(run())


async def _runtime_refresh_snapshot(
    runtime_refresher: Any,
    *,
    clients: dict[str, Any],
    state: dict[str, Any],
    symbols: list[str],
    coverage: dict[str, tuple[str, ...]],
    now_ms: int,
) -> dict[str, Any]:
    shadow_state = copy.deepcopy(state)
    await runtime_refresher(
        clients=clients,
        state=shadow_state,
        symbols=symbols,
        coverage=coverage,
        now_ms=now_ms,
    )
    return shadow_state


def _public_trade_metrics_for_state(metrics: dict[str, Any]) -> dict[str, Any]:
    raw_counts = metrics.get("public_trade_update_counts_by_venue")
    counts: dict[str, int] = {}
    if isinstance(raw_counts, dict):
        for venue, raw_count in raw_counts.items():
            if isinstance(raw_count, bool):
                continue
            try:
                count = int(raw_count)
            except (TypeError, ValueError):
                continue
            if count >= 0:
                counts[str(venue)[:64]] = count
    return {
        "public_trade_update_count": int(metrics.get("public_trade_update_count", 0)),
        "public_trade_update_counts_by_venue": counts,
    }


async def _run(
    args: argparse.Namespace,
    *,
    cycle_runner: Any = run_cycle_v19,
    state_loader: Any = load_state_v19,
    coverage_loader: Any = _load_coverage,
    clients_factory: Any = make_public_stream_clients,
    history_filename: str = "history_v19.sqlite",
    health_schema_version: str = HEALTH_SCHEMA_VERSION,
    state_initializer: Any = None,
    mark_positions: Any = _mark_open_positions_v19,
    runtime_label: str = "V19",
    runtime_refresher: Any = None,
    runtime_refresher_background: bool = False,
    runtime_refresher_merge_keys: tuple[str, ...] = (),
    runtime_refresher_threaded: bool = False,
    runtime_clients_factory: Any = None,
    public_trade_venues: tuple[str, ...] = (),
    universe_activity_loader: Any = None,
) -> int:
    artifacts = args.artifacts_dir
    state_path = artifacts / "state.json"
    health_path = artifacts / "health.json"
    journal_path = artifacts / "positions.jsonl"
    history_db = artifacts / history_filename
    clients = clients_factory()
    runtime_refresh_clients = clients
    stop_event = asyncio.Event()
    tasks: list[asyncio.Task[Any]] = []
    runtime_refresh_task: asyncio.Task[dict[str, Any]] | None = None
    runtime_refresh_last_start_mono = 0.0
    runtime_refresh_market_metadata: dict[str, dict[str, Any]] = {}
    try:
        coverage = await coverage_loader(clients)
        activity_scores: dict[str, float] = {}
        if universe_activity_loader is not None:
            loaded_scores = await universe_activity_loader(clients, coverage)
            if isinstance(loaded_scores, dict):
                activity_scores = loaded_scores
        symbols = _sorted_universe(
            coverage,
            args.symbols,
            activity_scores=activity_scores,
        )
        if not symbols:
            raise RuntimeError("fewer than two venues share active linear USDT perpetual symbols")
        coverage = {symbol: coverage[symbol] for symbol in symbols}
        venue_names = sorted({venue for symbol in symbols for venue in coverage[symbol]})
        retained_market_count = compact_public_stream_markets(clients, coverage)
        if runtime_refresher is not None and runtime_refresher_background:
            if runtime_refresher_threaded:
                runtime_refresh_market_metadata = {
                    venue: copy.deepcopy(getattr(client, "markets", {}))
                    for venue, client in clients.items()
                }
            else:
                # Public funding REST must not share CCXT's throttler queue with the
                # high-rate websocket clients.
                runtime_refresh_clients = clients_factory()
                _copy_runtime_market_metadata(clients, runtime_refresh_clients)
        state = state_loader(
            state_path,
            venue_names=venue_names,
            initial_equity=args.initial_equity,
            gross_leverage_cap=args.gross_leverage_cap,
            max_open_positions=args.max_open_positions,
        )
        state["universe_symbols"] = symbols
        state["expected_venue_count"] = len(clients)
        state["universe_venues"] = {symbol: list(coverage[symbol]) for symbol in symbols}
        state["universe_activity_scores"] = {
            symbol: float(activity_scores[symbol])
            for symbol in symbols
            if symbol in activity_scores
        }
        state["retained_market_count"] = retained_market_count
        state["maker_fill_calibration_source"] = "V19_CAUSAL_ONLY"
        state["public_trade_stream_venues"] = list(public_trade_venues)
        if (
            not history_db.exists()
            and args.seed_history_db is not None
            and args.seed_history_db.exists()
        ):
            state["seeded_route_history_count"] = seed_route_history_from_v16(
                history_db,
                args.seed_history_db,
                now_ms=int(time.time() * 1000),
            )
        if state_initializer is not None:
            state_initializer(
                state=state,
                history_db=history_db,
                artifacts=artifacts,
                args=args,
                symbols=symbols,
                coverage=coverage,
            )

        cache = LatestBookCache(
            depth_limit=args.depth,
            max_entries=max(512, len(symbols) * len(venue_names) + 32),
        )
        tasks.extend(
            start_public_book_watchers(
                clients=clients,
                coverage=coverage,
                cache=cache,
                stop_event=stop_event,
                depth_limit=args.depth,
            )
        )
        tasks.extend(
            start_public_trade_watchers(
                clients=clients,
                coverage=coverage,
                cache=cache,
                stop_event=stop_event,
                venues=public_trade_venues,
            )
        )

        started = time.monotonic()
        scan_cursor = 0
        while True:
            now_ms = int(time.time() * 1000)
            now_mono_ms = int(time.monotonic() * 1000)
            batch_size = min(int(args.scan_batch_size), len(symbols))
            discovery_symbols = [
                symbols[(scan_cursor + offset) % len(symbols)]
                for offset in range(batch_size)
            ]
            scan_cursor = (scan_cursor + batch_size) % len(symbols)
            state["discovery_scan_batch_size"] = batch_size
            state["discovery_scan_cursor"] = scan_cursor
            snapshot_clients, metrics = _snapshot_v19(
                cache,
                state=state,
                discovery_symbols=discovery_symbols,
                now_ms=now_ms,
                now_mono_ms=now_mono_ms,
                max_book_age_ms=args.max_book_age_ms,
            )
            state.update(
                {
                    "book_update_count": int(metrics["book_update_count"]),
                    **_public_trade_metrics_for_state(metrics),
                    "ws_reconnect_count": int(metrics["ws_reconnect_count"]),
                    "book_cache_entry_count": int(metrics["cache_entry_count"]),
                    "fresh_book_count": int(metrics["fresh_book_count"]),
                    "stale_book_count": int(metrics["stale_book_count"]),
                    "age_expired_book_count": int(metrics["age_expired_book_count"]),
                    "skew_rejected_book_count": int(metrics["skew_rejected_book_count"]),
                    "disconnected_book_count": int(metrics["disconnected_book_count"]),
                    "connected_venue_count": int(metrics["connected_venue_count"]),
                    "stream_error_counts": dict(metrics["stream_error_counts"]),
                    "stream_errors_last_60s_by_venue": dict(metrics["stream_errors_last_60s_by_venue"]),
                    "stream_error_counts_by_venue": {
                        str(venue): dict(counts)
                        for venue, counts in metrics["stream_error_counts_by_venue"].items()
                    },
                    "stream_identity_metrics": list(metrics.get("stream_identity_metrics", [])),
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
                    schema_version=health_schema_version,
                )
                raise MemoryError(f"{runtime_label} RSS exceeded hard safety limit")
            if state["process_rss_bytes"] >= int(args.memory_high_water_mb * 1024 * 1024):
                pruned = cache.prune_stale(
                    now_ms=now_ms,
                    max_age_ms=args.max_book_age_ms,
                    now_mono_ms=now_mono_ms,
                )
                state["memory_prune_count"] = int(state.get("memory_prune_count", 0)) + pruned
            if len(snapshot_clients) >= 2:
                if runtime_refresher is not None:
                    active_symbols = {
                        str(row["symbol"])
                        for key in ("pending_entries", "pending_exits", "maker_probes", "open_positions")
                        for row in state.get(key, [])
                        if isinstance(row, dict) and row.get("symbol")
                    }
                    refresh_symbols = list(dict.fromkeys([*discovery_symbols, *sorted(active_symbols)]))
                    if runtime_refresher_background:
                        if runtime_refresh_task is not None and runtime_refresh_task.done():
                            refreshed_state = await runtime_refresh_task
                            for key in runtime_refresher_merge_keys:
                                if key in refreshed_state:
                                    state[key] = refreshed_state[key]
                            runtime_refresh_task = None
                        now_mono = time.monotonic()
                        if (
                            runtime_refresh_task is None
                            and now_mono - runtime_refresh_last_start_mono >= 1.0
                        ):
                            if runtime_refresher_threaded:
                                state_snapshot = copy.deepcopy(state)
                                refresh_factory = runtime_clients_factory or clients_factory
                                runtime_refresh_task = asyncio.create_task(
                                    asyncio.to_thread(
                                        _runtime_refresh_snapshot_in_fresh_loop,
                                        runtime_refresher,
                                        clients_factory=refresh_factory,
                                        market_metadata=runtime_refresh_market_metadata,
                                        state_snapshot=state_snapshot,
                                        symbols=refresh_symbols,
                                        coverage=coverage,
                                        now_ms=now_ms,
                                    )
                                )
                            else:
                                runtime_refresh_task = asyncio.create_task(
                                    _runtime_refresh_snapshot(
                                        runtime_refresher,
                                        clients=runtime_refresh_clients,
                                        state=state,
                                        symbols=refresh_symbols,
                                        coverage=coverage,
                                        now_ms=now_ms,
                                    )
                                )
                            runtime_refresh_last_start_mono = now_mono
                    else:
                        await runtime_refresher(
                            clients=clients,
                            state=state,
                            symbols=refresh_symbols,
                            coverage=coverage,
                            now_ms=now_ms,
                        )
                await asyncio.to_thread(
                    cycle_runner,
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
                mark_positions(state, snapshot_clients, marked_at_utc=_utc_now())
                write_state(state_path, state)
                stream_status, stream_error = public_stream_health(state)
                _write_health(
                    health_path,
                    status=stream_status,
                    error=stream_error,
                    schema_version=health_schema_version,
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
                write_state(state_path, state)
                _write_health(
                    health_path,
                    status="DEGRADED",
                    error="PUBLIC_BOOK_WARMUP_TIMEOUT",
                    schema_version=health_schema_version,
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
        if runtime_refresh_task is not None:
            runtime_refresh_task.cancel()
            await asyncio.gather(runtime_refresh_task, return_exceptions=True)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if runtime_refresh_clients is not clients:
            await close_public_stream_clients(runtime_refresh_clients)
        await close_public_stream_clients(clients)


def _host_memory_limit_mb() -> float | None:
    limits: list[int] = []
    try:
        pages = int(__import__("os").sysconf("SC_PHYS_PAGES"))
        page_size = int(__import__("os").sysconf("SC_PAGE_SIZE"))
        if pages > 0 and page_size > 0:
            limits.append(pages * page_size)
    except (OSError, TypeError, ValueError):
        pass
    for raw_path in (
        "/sys/fs/cgroup/memory.max",
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",
    ):
        try:
            raw = Path(raw_path).read_text().strip()
            if raw != "max":
                value = int(raw)
                if 0 < value < (1 << 60):
                    limits.append(value)
        except (OSError, TypeError, ValueError):
            continue
    if not limits:
        return None
    return min(limits) / (1024.0 * 1024.0)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-equity", type=float, default=100.0)
    parser.add_argument("--symbols", type=int, default=50)
    parser.add_argument("--scan-batch-size", type=int, default=5)
    parser.add_argument("--max-pending-entries", type=int, default=2)
    parser.add_argument("--max-probes", type=int, default=4)
    parser.add_argument("--interval", type=float, default=0.25)
    parser.add_argument("--depth", type=int, default=20)
    parser.add_argument("--safety-buffer-bps", type=float, default=0.5)
    parser.add_argument("--max-book-age-ms", type=int, default=5_000)
    parser.add_argument("--max-book-skew-ms", type=int, default=None)
    parser.add_argument("--stream-warmup-seconds", type=float, default=30.0)
    parser.add_argument("--gross-leverage-cap", type=float, default=40.0)
    parser.add_argument("--max-open-positions", type=int, default=8)
    parser.add_argument("--memory-high-water-mb", type=float, default=1_200.0)
    parser.add_argument("--memory-hard-limit-mb", type=float, default=1_500.0)
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/arbitrage_v19"))
    parser.add_argument(
        "--seed-history-db",
        type=Path,
        default=Path("artifacts/arbitrage_v18/history_v18.sqlite"),
    )
    parser.add_argument("--once", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.interval <= 0.0 or args.stream_warmup_seconds <= 0.0:
        raise ValueError("interval and stream warmup must be positive")
    if args.scan_batch_size <= 0 or args.max_pending_entries <= 0 or args.max_probes <= 0:
        raise ValueError("scan batch, pending entry, and probe limits must be positive")
    if args.max_book_age_ms <= 0:
        raise ValueError("book age limit must be positive")
    if args.max_book_skew_ms is not None:
        raise ValueError("V19 receive-skew filter is disabled; omit --max-book-skew-ms")
    if not 20.0 <= args.gross_leverage_cap <= 40.0:
        raise ValueError("V19 gross leverage cap must be in 20x..40x")
    memory_limits = (float(args.memory_high_water_mb), float(args.memory_hard_limit_mb))
    if not all(math.isfinite(value) and value > 0.0 for value in memory_limits):
        raise ValueError("memory limits must be finite and positive")
    if args.memory_hard_limit_mb <= args.memory_high_water_mb:
        raise ValueError("memory hard limit must exceed the soft high-water mark")
    if args.memory_hard_limit_mb > 3_000.0:
        raise ValueError("memory hard limit must not exceed 3000 MB")
    host_memory_mb = _host_memory_limit_mb()
    if host_memory_mb is not None and args.memory_hard_limit_mb > host_memory_mb * 0.80:
        raise ValueError("memory hard limit exceeds the host memory budget with required headroom")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
