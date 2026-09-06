"""V17 maker-first, EV-gated paper arbitrage runner."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from crypto_research.arbitrage_v12 import ArbitrageOpportunity, VenueBook, evaluate_pair
from crypto_research.execution_v8 import ExecutionSimulatorV8
from crypto_research.maker_v17 import (
    DEFAULT_MAKER_FEE_BPS,
    conservative_fill_probability,
    maker_attempt_ev,
    multi_horizon_route_features,
    passive_limit_filled,
    record_fill_outcome,
    seed_route_history_from_v16,
)
from crypto_research.monitoring_v13 import mark_open_position
from crypto_research.route_v16 import (
    record_monitor_snapshot,
    record_route_snapshots,
    route_features,
)

if __package__:
    from .run_arbitrage_paper_v12 import (
        DEFAULT_FEE_BPS,
        _append_jsonl,
        linear_usdt_symbol_venues,
        make_public_clients,
        write_state,
    )
    from .run_arbitrage_paper_v13 import _fetch_venue_books, _utc_now, _write_health
    from .run_arbitrage_paper_v14 import (
        _enrich_open_margin,
        _refresh_cross_margin_summary,
    )
    from .run_arbitrage_paper_v16 import (
        _all_routes,
        _default_state_v16,
        cooldown_active,
        select_pair_profile,
        shrink_target_notional,
        v16_exit_decision,
    )
else:
    from run_arbitrage_paper_v12 import (
        DEFAULT_FEE_BPS,
        _append_jsonl,
        linear_usdt_symbol_venues,
        make_public_clients,
        write_state,
    )
    from run_arbitrage_paper_v13 import _fetch_venue_books, _utc_now, _write_health
    from run_arbitrage_paper_v14 import (
        _enrich_open_margin,
        _refresh_cross_margin_summary,
    )
    from run_arbitrage_paper_v16 import (
        _all_routes,
        _default_state_v16,
        cooldown_active,
        select_pair_profile,
        shrink_target_notional,
        v16_exit_decision,
    )

SCHEMA_VERSION = "v17-arbitrage-paper-1"
PORTFOLIO_MODEL = "MAKER_FIRST_EV_MULTI_STRATEGY_V1"
MARGIN_MODEL = "CROSS_MARGIN_PAPER_V1"
STRATEGY_ID = "MAKER_FIRST_ROUTE_RELATIVE_V1"
MAKER_NO_FILL_BACKOFF_MS = 60_000


def _maker_leg_cooldown_key(symbol: str, maker_venue: str, maker_side: str) -> str | None:
    side = str(maker_side).upper()
    venue = str(maker_venue).strip().lower()
    if side not in {"LONG", "SHORT"} or not venue:
        return None
    return f"maker:{symbol}|{venue}|{side}"


def _increment_candidate_funnel(
    state: dict[str, Any],
    key: str,
) -> None:
    counts = state.get("candidate_funnel_counts")
    if not isinstance(counts, dict) or key not in counts:
        return
    try:
        current = int(counts[key])
    except (TypeError, ValueError):
        current = 0
    counts[key] = max(0, current) + 1


def _default_state_v17(
    venue_names: list[str],
    *,
    initial_equity: float = 100.0,
    gross_leverage_cap: float = 2.0,
    max_open_positions: int = 8,
) -> dict[str, Any]:
    state = _default_state_v16(
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
            "pending_entries": [],
            "pending_exits": [],
            "maker_probes": [],
            "maker_probe_count": 0,
            "maker_fill_observation_count": 0,
            "maker_entry_cancel_count": 0,
            "one_leg_hedge_count": 0,
            "maker_exit_fallback_count": 0,
            "maker_hedge_failure_count": 0,
        }
    )
    return state


def _refresh_v17_margin(
    state: dict[str, Any],
    books_by_symbol: dict[str, dict[str, VenueBook]] | None = None,
) -> None:
    _refresh_cross_margin_summary(state, books_by_symbol)
    _refresh_unwind_pending_exposure(state, books_by_symbol)
    state["schema_version"] = SCHEMA_VERSION
    state["portfolio_model"] = PORTFOLIO_MODEL
    state["margin_model"] = MARGIN_MODEL


def _best_price(venue: VenueBook, side: str) -> float:
    levels = venue.book.get("bids" if side == "buy" else "asks")
    if not isinstance(levels, list) or not levels:
        raise ValueError("public book has no resting level")
    price = float(levels[0][0])
    if not math.isfinite(price) or price <= 0.0:
        raise ValueError("invalid public book price")
    return price


def _quote_spread_bps(venue: VenueBook) -> float:
    bid = _best_price(venue, "buy")
    ask = _best_price(venue, "sell")
    mid = (bid + ask) / 2.0
    if mid <= 0.0:
        raise ValueError("invalid quote midpoint")
    return max(0.0, (ask - bid) / mid * 10_000.0)


def _market_fill(venue: VenueBook, *, side: str, quantity: float, fee_bps: float):
    try:
        fill = ExecutionSimulatorV8(fee_bps=fee_bps).simulate_market_order_by_quantity(
            target_base_quantity=quantity,
            side=side,
            book=venue.book,
        )
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if fill.unmodeled_tail:
        return None
    return fill


def _refresh_unwind_pending_exposure(
    state: dict[str, Any],
    books_by_symbol: dict[str, dict[str, VenueBook]] | None,
) -> None:
    """Overlay honest one-leg risk for V19 UNWIND_PENDING rows."""

    aggregate_defaults: dict[str, int | float] = {
        "partial_exposure_count": 0,
        "partial_exposure_gross_notional": 0.0,
        "partial_exposure_unrealized_pnl": 0.0,
        "partial_exposure_entry_fees": 0.0,
        "partial_exposure_reserved_margin": 0.0,
    }
    partials = [
        pending
        for pending in state.get("pending_entries", [])
        if isinstance(pending, dict) and pending.get("status") == "UNWIND_PENDING"
    ]
    if not partials:
        if any(key in state for key in aggregate_defaults):
            state.update(aggregate_defaults)
        return

    balances = {
        str(name): float(value)
        for name, value in state.get("venue_balances", {}).items()
    }
    used = {
        name: float(state.get("venue_margin_used", {}).get(name, 0.0))
        for name in balances
    }
    unrealized = {
        name: float(state.get("venue_unrealized_pnl", {}).get(name, 0.0))
        for name in balances
    }
    maintenance = {
        name: float(state.get("venue_maintenance_stress", {}).get(name, 0.0))
        for name in balances
    }
    gross_by_venue = {
        name: float(
            state.get("venue_cross_margin", {})
            .get(name, {})
            .get("gross_notional", 0.0)
        )
        for name in balances
    }
    stress_rate = float(state.get("maintenance_stress_rate", 0.05))
    utilization_cap = float(state.get("margin_utilization_cap", 0.8))
    partial_gross = 0.0
    partial_unrealized = 0.0
    partial_fees = 0.0
    partial_margin = 0.0

    for pending in partials:
        filled_side = str(pending.get("filled_side") or "")
        if filled_side == "LONG":
            venue = str(pending["long_exchange"])
            entry_price = float(pending["long_limit_price"])
            entry_fee_bps = float(pending["long_maker_fee_bps"])
            taker_fee = float(pending["long_taker_fee_bps"])
            unwind_side = "sell"
        elif filled_side == "SHORT":
            venue = str(pending["short_exchange"])
            entry_price = float(pending["short_limit_price"])
            entry_fee_bps = float(pending["short_maker_fee_bps"])
            taker_fee = float(pending["short_taker_fee_bps"])
            unwind_side = "buy"
        else:
            raise ValueError("UNWIND_PENDING must identify the filled side")

        quantity = float(pending["quantity"])
        leverage = float(pending.get("leverage", state.get("exchange_leverage", 1.0)))
        if quantity <= 0.0 or entry_price <= 0.0 or leverage <= 0.0:
            raise ValueError("UNWIND_PENDING exposure values must be positive")
        entry_notional = quantity * entry_price
        entry_fee = entry_notional * entry_fee_bps / 10_000.0
        current_notional = entry_notional
        gross_pnl = 0.0
        exit_fee: float | None = None
        current_vwap: float | None = None
        mark_status = "UNAVAILABLE"

        venue_book = None
        if books_by_symbol is not None:
            venue_book = books_by_symbol.get(str(pending["symbol"]), {}).get(venue)
        if venue_book is not None:
            exit_fill = _market_fill(
                venue_book,
                side=unwind_side,
                quantity=quantity,
                fee_bps=taker_fee,
            )
            if exit_fill is not None:
                current_notional = float(exit_fill.filled_notional)
                current_vwap = float(exit_fill.vwap)
                gross_pnl = (
                    quantity * (current_vwap - entry_price)
                    if filled_side == "LONG"
                    else quantity * (entry_price - current_vwap)
                )
                exit_fee = current_notional * taker_fee / 10_000.0
                mark_status = "LIVE"

        unrealized_after_entry = gross_pnl - entry_fee
        margin = current_notional / leverage
        pending.update(
            {
                "filled_venue": venue,
                "partial_entry_price": entry_price,
                "partial_entry_notional": entry_notional,
                "partial_entry_fee_bps": entry_fee_bps,
                "partial_entry_fee": entry_fee,
                "partial_gross_notional": current_notional,
                "partial_gross_unrealized_pnl": gross_pnl,
                "partial_unrealized_pnl": unrealized_after_entry,
                "partial_initial_margin": margin,
                "partial_mark_status": mark_status,
            }
        )
        if current_vwap is None or exit_fee is None:
            pending.pop("partial_current_vwap", None)
            pending.pop("partial_estimated_exit_fee", None)
            pending.pop("partial_estimated_net_pnl_if_unwound", None)
        else:
            pending.update(
                {
                    "partial_current_vwap": current_vwap,
                    "partial_estimated_exit_fee": exit_fee,
                    "partial_estimated_net_pnl_if_unwound": (
                        unrealized_after_entry - exit_fee
                    ),
                }
            )
        if venue_book is not None:
            for source_key, target_key in (
                ("received_at_ms", "partial_mark_received_at_ms"),
                ("received_mono_ms", "partial_mark_received_mono_ms"),
            ):
                stamp = venue_book.book.get(source_key)
                if stamp is not None:
                    pending[target_key] = int(stamp)

        balances.setdefault(venue, 0.0)
        used[venue] = used.get(venue, 0.0) + margin
        unrealized[venue] = unrealized.get(venue, 0.0) + unrealized_after_entry
        maintenance[venue] = maintenance.get(venue, 0.0) + (
            current_notional * stress_rate
        )
        gross_by_venue[venue] = gross_by_venue.get(venue, 0.0) + current_notional
        partial_gross += current_notional
        partial_unrealized += unrealized_after_entry
        partial_fees += entry_fee
        partial_margin += margin

    account_equity = {
        name: balances.get(name, 0.0) + unrealized.get(name, 0.0)
        for name in balances
    }
    available = {
        name: max(
            0.0,
            account_equity[name] * utilization_cap - used.get(name, 0.0),
        )
        for name in balances
    }
    utilization = {
        name: (
            used.get(name, 0.0) / account_equity[name]
            if account_equity[name] > 0.0
            else float("inf")
        )
        for name in balances
    }
    margin_ratio = {
        name: (
            account_equity[name] / maintenance[name]
            if maintenance.get(name, 0.0) > 0.0
            else None
        )
        for name in balances
    }
    finite_ratios = [
        value for value in margin_ratio.values() if isinstance(value, (int, float))
    ]
    gross = float(sum(gross_by_venue.values()))
    equity = float(sum(balances.values()))
    state.update(
        {
            "equity": equity,
            "venue_margin_used": used,
            "venue_available_margin": available,
            "venue_account_equity": account_equity,
            "venue_unrealized_pnl": unrealized,
            "venue_maintenance_stress": maintenance,
            "venue_margin_ratio": margin_ratio,
            "venue_margin_utilization": utilization,
            "gross_exposure": gross,
            "gross_leverage_used": gross / equity if equity > 0.0 else 0.0,
            "initial_margin_used": float(sum(used.values())),
            "available_margin": float(sum(available.values())),
            "maintenance_stress_used": float(sum(maintenance.values())),
            "min_stress_margin_ratio": min(finite_ratios) if finite_ratios else None,
            "partial_exposure_count": len(partials),
            "partial_exposure_gross_notional": partial_gross,
            "partial_exposure_unrealized_pnl": partial_unrealized,
            "partial_exposure_entry_fees": partial_fees,
            "partial_exposure_reserved_margin": partial_margin,
        }
    )
    state["venue_cross_margin"] = {
        name: {
            "balance": balances[name],
            "account_equity": account_equity[name],
            "unrealized_pnl_after_entry_fee": unrealized[name],
            "gross_notional": gross_by_venue[name],
            "initial_margin_used": used[name],
            "available_initial_margin": available[name],
            "maintenance_stress": maintenance[name],
            "stress_margin_ratio": margin_ratio[name],
            "margin_utilization": utilization[name],
        }
        for name in balances
    }


def _placement_queue_evidence(
    book: dict[str, Any],
    *,
    side: str,
    limit_price: float,
) -> tuple[float, float] | None:
    trade_levels = book.get("_public_trade_volume_by_side_price")
    if not isinstance(trade_levels, dict):
        return None
    levels = book.get("bids" if side == "buy" else "asks")
    if not isinstance(levels, list):
        return None
    queue_ahead = None
    for level in levels:
        try:
            if float(level[0]) == float(limit_price):
                queue_ahead = float(level[1])
                break
        except (TypeError, ValueError, IndexError):
            continue
    if queue_ahead is None or not math.isfinite(queue_ahead) or queue_ahead < 0.0:
        return None
    taker_side = "sell" if side == "buy" else "buy"
    try:
        baseline = float(trade_levels.get((taker_side, float(limit_price)), 0.0))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(baseline) or baseline < 0.0:
        return None
    return queue_ahead, baseline


def _queue_evidence_fields(
    prefix: str, book: dict[str, Any], *, side: str, limit_price: float
) -> dict[str, float]:
    evidence = _placement_queue_evidence(book, side=side, limit_price=limit_price)
    if evidence is None:
        return {}
    queue_ahead, baseline = evidence
    return {
        f"{prefix}_queue_ahead_quantity": queue_ahead,
        f"{prefix}_trade_volume_baseline": baseline,
    }


def _elapsed_since_placement_ms(
    pending: dict[str, Any],
    *,
    now_ms: int,
    now_mono_ms: int | None = None,
) -> int:
    """Elapsed order age; monotonic when V18 supplied a process clock."""

    placed_mono = pending.get("placed_at_mono_ms")
    if placed_mono is not None and now_mono_ms is not None:
        elapsed = int(now_mono_ms) - int(placed_mono)
        if elapsed >= 0:
            return elapsed
    return max(0, int(now_ms) - int(pending["placed_at_ms"]))


def _create_pending_entry(
    *,
    symbol: str,
    buy_venue: str,
    sell_venue: str,
    venues: dict[str, VenueBook],
    target_notional: float,
    leverage: float,
    pair_gross_fraction: float,
    decision: dict[str, Any],
    maker_fee_bps: dict[str, float],
    taker_fee_bps: dict[str, float],
    now_ms: int,
    now_utc: str,
    strategy_id: str = STRATEGY_ID,
    monotonic_ms: int | None = None,
) -> dict[str, Any]:
    if target_notional <= 0.0 or leverage <= 0.0:
        raise ValueError("target_notional and leverage must be positive")
    long_book = venues[buy_venue]
    short_book = venues[sell_venue]
    long_limit = _best_price(long_book, "buy")
    short_limit = _best_price(short_book, "sell")
    quantity = min(target_notional / long_limit, target_notional / short_limit)
    if quantity <= 0.0 or not math.isfinite(quantity):
        raise ValueError("maker quantity must be positive")
    route_key = f"{symbol}|{buy_venue}|{sell_venue}"
    return {
        "pending_id": uuid4().hex,
        "position_key": route_key,
        "symbol": symbol,
        "long_exchange": buy_venue,
        "short_exchange": sell_venue,
        "quantity": float(quantity),
        "long_limit_price": float(long_limit),
        "short_limit_price": float(short_limit),
        "long_target_notional": float(quantity * long_limit),
        "short_target_notional": float(quantity * short_limit),
        "long_maker_fee_bps": float(maker_fee_bps[buy_venue]),
        "short_maker_fee_bps": float(maker_fee_bps[sell_venue]),
        "long_taker_fee_bps": float(taker_fee_bps[buy_venue]),
        "short_taker_fee_bps": float(taker_fee_bps[sell_venue]),
        "leverage": float(leverage),
        "pair_gross_fraction": float(pair_gross_fraction),
        "placed_at_ms": int(now_ms),
        **_queue_evidence_fields("long", long_book.book, side="buy", limit_price=long_limit),
        **_queue_evidence_fields("short", short_book.book, side="sell", limit_price=short_limit),
        **({"placed_at_mono_ms": int(monotonic_ms)} if monotonic_ms is not None else {}),
        "placed_at_utc": now_utc,
        "status": "PENDING_MAKER_ENTRY",
        "strategy_id": str(strategy_id),
        **{
            key: decision[key]
            for key in (
                "expected_value_bps",
                "minimum_required_ev_bps",
                "capture_bps",
                "baseline_60m_bps",
                "baseline_15m_bps",
                "baseline_5m_bps",
                "route_sigma_bps",
                "price_volatility_bps",
                "p_open",
                "z_score",
                "long_fill_probability",
                "short_fill_probability",
                "long_exit_fill_probability",
                "short_exit_fill_probability",
                "expected_exit_fee_bps",
                "expected_exit_price_improvement_bps",
                "adverse_selection_bps",
                "hedge_risk_bps",
                "maker_side",
                "maker_venue",
                "hedge_venue",
                "post_fill_accept_probability",
                "reject_net_bps",
                "expected_attempt_ev_bps",
                "conditional_pair_value_bps",
                "conditional_fill_value_bps",
                "expected_funding_cost_bps",
                "expected_net_funding_cost_bps",
                "minimum_required_attempt_ev_bps",
                "expected_attempt_dollars",
                "minimum_required_attempt_dollars",
            )
            if key in decision
        },
    }


def _position_from_pending(
    pending: dict[str, Any],
    *,
    long_price: float,
    short_price: float,
    long_liquidity: str,
    short_liquidity: str,
    long_fee_bps: float,
    short_fee_bps: float,
    now_ms: int,
    now_utc: str,
) -> dict[str, Any]:
    quantity = float(pending["quantity"])
    long_notional = quantity * float(long_price)
    short_notional = quantity * float(short_price)
    long_entry_fee = long_notional * float(long_fee_bps) / 10_000.0
    short_entry_fee = short_notional * float(short_fee_bps) / 10_000.0
    execution_mode = "MAKER_MAKER" if long_liquidity == short_liquidity == "MAKER" else "MAKER_TAKER_HEDGE"
    position = {
        "position_id": uuid4().hex,
        "position_key": str(pending["position_key"]),
        "symbol": str(pending["symbol"]),
        "long_exchange": str(pending["long_exchange"]),
        "short_exchange": str(pending["short_exchange"]),
        "quantity": quantity,
        "opened_at": now_utc,
        "opened_at_ms": int(now_ms),
        "long_entry_vwap": float(long_price),
        "short_entry_vwap": float(short_price),
        "long_entry_notional": long_notional,
        "short_entry_notional": short_notional,
        # These remain taker rates because close-now monitoring is executable-market based.
        "long_fee_bps": float(pending["long_taker_fee_bps"]),
        "short_fee_bps": float(pending["short_taker_fee_bps"]),
        "long_entry_fee_bps": float(long_fee_bps),
        "short_entry_fee_bps": float(short_fee_bps),
        "long_entry_fee": long_entry_fee,
        "short_entry_fee": short_entry_fee,
        "entry_fees": long_entry_fee + short_entry_fee,
        "entry_execution_mode": execution_mode,
        "long_entry_liquidity": long_liquidity,
        "short_entry_liquidity": short_liquidity,
        "entry_hedge_delay_ms": int(now_ms) - int(pending["placed_at_ms"]) if execution_mode != "MAKER_MAKER" else 0,
        "initial_net_edge_bps": float(pending.get("post_fill_expected_value_bps", pending.get("expected_value_bps", 0.0))),
        "strategy_id": str(pending.get("strategy_id") or STRATEGY_ID),
        "entry_expected_value_bps": float(pending.get("post_fill_expected_value_bps", pending.get("expected_value_bps", 0.0))),
        "entry_minimum_ev_bps": float(pending.get("minimum_required_ev_bps", 0.0)),
        "entry_capture_bps": float(pending.get("actual_capture_bps", pending.get("capture_bps", 0.0))),
        "entry_excess_spread_bps": float(pending.get("actual_capture_bps", pending.get("capture_bps", 0.0))),
        "entry_excess_after_cost_bps": float(pending.get("post_fill_expected_value_bps", pending.get("expected_value_bps", 0.0))),
        "actual_gross_spread_bps": float(pending.get("actual_gross_spread_bps", 0.0)),
        "actual_capture_bps": float(pending.get("actual_capture_bps", pending.get("capture_bps", 0.0))),
        "post_fill_expected_value_bps": float(pending.get("post_fill_expected_value_bps", pending.get("expected_value_bps", 0.0))),
        "post_fill_decision": str(pending.get("post_fill_decision") or "NOT_REVALIDATED"),
        "entry_z_score": float(pending.get("z_score", 0.0)),
        "entry_baseline_bps": float(pending.get("baseline_60m_bps", 0.0)),
        "entry_baseline_15m_bps": float(pending.get("baseline_15m_bps", 0.0)),
        "entry_baseline_5m_bps": float(pending.get("baseline_5m_bps", 0.0)),
        "entry_route_sigma_bps": float(pending.get("route_sigma_bps", 0.5)),
        "entry_price_volatility_bps": float(pending.get("price_volatility_bps", 0.0)),
        "entry_fill_probability": float(pending.get("p_open", 0.0)),
        "pair_gross_fraction": float(pending["pair_gross_fraction"]),
        "status": "OPEN",
    }
    _enrich_open_margin(position, float(pending["leverage"]))
    return position


def _process_pending_entries(
    state: dict[str, Any],
    *,
    books_by_symbol: dict[str, dict[str, VenueBook]],
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

        long_filled = bool(pending.get("long_filled")) or passive_limit_filled(
            "buy",
            float(pending["long_limit_price"]),
            long_book.book,
            placed_at_ms=int(pending["placed_at_ms"]),
            placed_at_mono_ms=pending.get("placed_at_mono_ms"),
            strict_price_through=strict_maker_price_through,
        )
        short_filled = bool(pending.get("short_filled")) or passive_limit_filled(
            "sell",
            float(pending["short_limit_price"]),
            short_book.book,
            placed_at_ms=int(pending["placed_at_ms"]),
            placed_at_mono_ms=pending.get("placed_at_mono_ms"),
            strict_price_through=strict_maker_price_through,
        )
        if not long_filled and not short_filled:
            if not expired:
                remaining.append(pending)
                continue
            record_fill_outcome(stats_db, str(pending["long_exchange"]), "buy", filled=False)
            record_fill_outcome(stats_db, str(pending["short_exchange"]), "sell", filled=False)
            state["maker_fill_observation_count"] = int(state.get("maker_fill_observation_count", 0)) + 2
            state["maker_entry_cancel_count"] = int(state.get("maker_entry_cancel_count", 0)) + 1
            _append_jsonl(journal_path, {"record_type": "PAPER_MAKER_ENTRY_CANCEL", **pending, "cancelled_at": now_utc})
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
            long_fill = _market_fill(long_book, side="buy", quantity=quantity, fee_bps=float(taker_fee_bps[str(pending["long_exchange"])]))
            if long_fill is None:
                state["maker_hedge_failure_count"] = int(state.get("maker_hedge_failure_count", 0)) + 1
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
            short_fill = _market_fill(short_book, side="sell", quantity=quantity, fee_bps=float(taker_fee_bps[str(pending["short_exchange"])]))
            if short_fill is None:
                state["maker_hedge_failure_count"] = int(state.get("maker_hedge_failure_count", 0)) + 1
                remaining.append(pending)
                continue
            short_price = float(short_fill.vwap)
            short_liquidity = "TAKER"
            short_entry_fee_bps = float(taker_fee_bps[str(pending["short_exchange"])])

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
        state.setdefault("open_positions", []).append(position)
        state["opened_position_count"] = int(state.get("opened_position_count", 0)) + 1
        if position["entry_execution_mode"] == "MAKER_TAKER_HEDGE":
            state["one_leg_hedge_count"] = int(state.get("one_leg_hedge_count", 0)) + 1
        _append_jsonl(journal_path, {"record_type": "PAPER_POSITION_OPEN", **position})
    state["pending_entries"] = remaining
    _refresh_v17_margin(state, books_by_symbol)


def _create_pending_exit(
    position: dict[str, Any],
    *,
    venues: dict[str, VenueBook],
    reason: str,
    now_ms: int,
    now_utc: str,
    monotonic_ms: int | None = None,
) -> dict[str, Any]:
    long_book = venues[str(position["long_exchange"])]
    short_book = venues[str(position["short_exchange"])]
    return {
        "pending_id": uuid4().hex,
        "position_id": str(position["position_id"]),
        "position_key": str(position["position_key"]),
        "symbol": str(position["symbol"]),
        "long_exchange": str(position["long_exchange"]),
        "short_exchange": str(position["short_exchange"]),
        "quantity": float(position["quantity"]),
        "long_limit_price": _best_price(long_book, "sell"),
        "short_limit_price": _best_price(short_book, "buy"),
        "reason": reason,
        "placed_at_ms": int(now_ms),
        **({"placed_at_mono_ms": int(monotonic_ms)} if monotonic_ms is not None else {}),
        "placed_at_utc": now_utc,
        "status": "PENDING_MAKER_EXIT",
    }


def _realize_close_v17(
    state: dict[str, Any],
    position: dict[str, Any],
    *,
    long_exit_price: float,
    short_exit_price: float,
    long_exit_fee_bps: float,
    short_exit_fee_bps: float,
    long_exit_liquidity: str,
    short_exit_liquidity: str,
    reason: str,
    now_utc: str,
) -> dict[str, Any]:
    quantity = float(position["quantity"])
    long_exit_notional = quantity * long_exit_price
    short_exit_notional = quantity * short_exit_price
    long_exit_fee = long_exit_notional * long_exit_fee_bps / 10_000.0
    short_exit_fee = short_exit_notional * short_exit_fee_bps / 10_000.0
    long_gross = quantity * (long_exit_price - float(position["long_entry_vwap"]))
    short_gross = quantity * (float(position["short_entry_vwap"]) - short_exit_price)
    long_net = long_gross - float(position.get("long_entry_fee", 0.0)) - long_exit_fee
    short_net = short_gross - float(position.get("short_entry_fee", 0.0)) - short_exit_fee
    realized = long_net + short_net
    state["venue_balances"][str(position["long_exchange"])] += long_net
    state["venue_balances"][str(position["short_exchange"])] += short_net
    state["equity"] = float(sum(float(value) for value in state["venue_balances"].values()))
    state["realized_pnl"] = float(state.get("realized_pnl", 0.0)) + realized
    state["closed_position_count"] = int(state.get("closed_position_count", 0)) + 1
    exit_mode = "MAKER_MAKER" if long_exit_liquidity == short_exit_liquidity == "MAKER" else (
        "TAKER_FALLBACK" if long_exit_liquidity == short_exit_liquidity == "TAKER" else "MAKER_TAKER_HEDGE"
    )
    close = {
        "record_type": "PAPER_POSITION_CLOSE",
        "position_id": str(position["position_id"]),
        "symbol": str(position["symbol"]),
        "long_exchange": str(position["long_exchange"]),
        "short_exchange": str(position["short_exchange"]),
        "quantity": quantity,
        "opened_at": position.get("opened_at"),
        "closed_at": now_utc,
        "close_reason": reason,
        "long_entry_vwap": float(position["long_entry_vwap"]),
        "short_entry_vwap": float(position["short_entry_vwap"]),
        "long_exit_vwap": float(long_exit_price),
        "short_exit_vwap": float(short_exit_price),
        "entry_fees": float(position.get("entry_fees", 0.0)),
        "exit_fees": long_exit_fee + short_exit_fee,
        "gross_pnl": long_gross + short_gross,
        "realized_net_pnl": realized,
        "long_realized_net_pnl": long_net,
        "short_realized_net_pnl": short_net,
        "exit_execution_mode": exit_mode,
        "long_exit_liquidity": long_exit_liquidity,
        "short_exit_liquidity": short_exit_liquidity,
        "strategy_id": str(position.get("strategy_id") or STRATEGY_ID),
        "margin_model": MARGIN_MODEL,
        "leverage": float(position.get("leverage", 1.0)),
        "initial_margin": float(position.get("initial_margin", 0.0)),
    }
    state["last_close"] = close
    state["realized_fee_drag"] = float(state.get("realized_fee_drag", 0.0)) + float(position.get("entry_fees", 0.0)) + close["exit_fees"]
    return close


def _process_pending_exits(
    state: dict[str, Any],
    *,
    books_by_symbol: dict[str, dict[str, VenueBook]],
    stats_db: str | Path,
    now_ms: int,
    now_utc: str,
    journal_path: Path,
    maker_fee_bps: dict[str, float],
    taker_fee_bps: dict[str, float],
    timeout_ms: int = 20_000,
    now_mono_ms: int | None = None,
    strict_maker_price_through: bool = False,
) -> None:
    remaining_exits: list[dict[str, Any]] = []
    positions_by_id = {str(position["position_id"]): position for position in state.get("open_positions", [])}
    closed_ids: set[str] = set()
    for pending in list(state.get("pending_exits", [])):
        position = positions_by_id.get(str(pending["position_id"]))
        if position is None:
            continue
        if int(now_ms) <= int(pending["placed_at_ms"]):
            remaining_exits.append(pending)
            continue
        venues = books_by_symbol.get(str(pending["symbol"]), {})
        long_book = venues.get(str(pending["long_exchange"]))
        short_book = venues.get(str(pending["short_exchange"]))
        if long_book is None or short_book is None:
            remaining_exits.append(pending)
            continue
        expired = _elapsed_since_placement_ms(
            pending, now_ms=now_ms, now_mono_ms=now_mono_ms
        ) >= int(timeout_ms)
        long_maker = passive_limit_filled(
            "sell",
            float(pending["long_limit_price"]),
            long_book.book,
            placed_at_ms=int(pending["placed_at_ms"]),
            placed_at_mono_ms=pending.get("placed_at_mono_ms"),
            strict_price_through=strict_maker_price_through,
        )
        short_maker = passive_limit_filled(
            "buy",
            float(pending["short_limit_price"]),
            short_book.book,
            placed_at_ms=int(pending["placed_at_ms"]),
            placed_at_mono_ms=pending.get("placed_at_mono_ms"),
            strict_price_through=strict_maker_price_through,
        )

        if not long_maker and not short_maker and not expired:
            remaining_exits.append(pending)
            continue

        quantity = float(position["quantity"])
        if long_maker:
            long_price = float(pending["long_limit_price"])
            long_liq = "MAKER"
            long_fee = float(maker_fee_bps[str(position["long_exchange"])])
        else:
            fill = _market_fill(long_book, side="sell", quantity=quantity, fee_bps=float(taker_fee_bps[str(position["long_exchange"])]))
            if fill is None:
                remaining_exits.append(pending)
                continue
            long_price = float(fill.vwap)
            long_liq = "TAKER"
            long_fee = float(taker_fee_bps[str(position["long_exchange"])])
        if short_maker:
            short_price = float(pending["short_limit_price"])
            short_liq = "MAKER"
            short_fee = float(maker_fee_bps[str(position["short_exchange"])])
        else:
            fill = _market_fill(short_book, side="buy", quantity=quantity, fee_bps=float(taker_fee_bps[str(position["short_exchange"])]))
            if fill is None:
                remaining_exits.append(pending)
                continue
            short_price = float(fill.vwap)
            short_liq = "TAKER"
            short_fee = float(taker_fee_bps[str(position["short_exchange"])])

        record_fill_outcome(stats_db, str(position["long_exchange"]), "sell", filled=long_maker)
        record_fill_outcome(stats_db, str(position["short_exchange"]), "buy", filled=short_maker)
        state["maker_fill_observation_count"] = int(state.get("maker_fill_observation_count", 0)) + 2
        if not long_maker and not short_maker:
            state["maker_exit_fallback_count"] = int(state.get("maker_exit_fallback_count", 0)) + 1
        elif long_maker != short_maker:
            state["one_leg_hedge_count"] = int(state.get("one_leg_hedge_count", 0)) + 1
        close = _realize_close_v17(
            state,
            position,
            long_exit_price=long_price,
            short_exit_price=short_price,
            long_exit_fee_bps=long_fee,
            short_exit_fee_bps=short_fee,
            long_exit_liquidity=long_liq,
            short_exit_liquidity=short_liq,
            reason=str(pending["reason"]),
            now_utc=now_utc,
        )
        state.setdefault("route_cooldowns", {})[str(position["position_key"])] = int(now_ms)
        closed_ids.add(str(position["position_id"]))
        _append_jsonl(journal_path, close)
    state["pending_exits"] = remaining_exits
    if closed_ids:
        state["open_positions"] = [p for p in state.get("open_positions", []) if str(p["position_id"]) not in closed_ids]
    _refresh_v17_margin(state, books_by_symbol)



def _assert_v17_invariants(state: dict[str, Any]) -> None:
    try:
        equity = float(state["equity"])
        balances = {str(key): float(value) for key, value in state["venue_balances"].items()}
        if equity <= 0.0 or abs(sum(balances.values()) - equity) > 1e-8:
            raise ValueError("venue balances must sum to positive equity")
        positions = list(state.get("open_positions", []))
        pending = list(state.get("pending_entries", []))
        if len(positions) > int(state["max_open_positions"]):
            raise ValueError("max open positions exceeded")
        route_keys = [str(row.get("position_key") or "") for row in [*positions, *pending]]
        if not all(route_keys) or len(route_keys) != len(set(route_keys)):
            raise ValueError("duplicate open or pending route")
        min_leverage = float(state.get("min_position_leverage", 1.0))
        max_leverage = float(state.get("max_position_leverage", 3.0))
        for position in positions:
            leverage = float(position.get("leverage", 0.0))
            if not min_leverage <= leverage <= max_leverage:
                raise ValueError("position leverage outside configured bounds")
        if float(state.get("gross_leverage_used", 0.0)) > float(state["gross_leverage_cap"]) + 1e-8:
            raise ValueError("gross leverage cap exceeded")
        if any(float(value) < -1e-8 for value in state.get("venue_available_margin", {}).values()):
            raise ValueError("venue margin exceeded")
    except Exception:
        state["invariant_failure_count"] = int(state.get("invariant_failure_count", 0)) + 1
        raise


def _v17_route_decision(
    opportunity: ArbitrageOpportunity,
    *,
    features: dict[str, float | int] | None,
    stats_db: str | Path,
    maker_fee_bps: dict[str, float],
    taker_fee_bps: dict[str, float],
    safety_buffer_bps: float,
    venues: dict[str, VenueBook] | None = None,
) -> dict[str, Any]:
    if features is None:
        return {"decision": "BASELINE_WARMUP", "tradeable": False}
    current = float(opportunity.gross_edge_bps)
    excess_60 = current - float(features["baseline_60m_bps"])
    excess_15 = current - float(features["baseline_15m_bps"])
    excess_5 = current - float(features["baseline_5m_bps"])
    capture = max(0.0, min(excess_60, excess_15))
    sigma = max(0.5, float(features["route_sigma_bps"]))
    volatility = max(0.0, float(features["price_volatility_bps"]))
    long_quote_spread = _quote_spread_bps(venues[opportunity.buy_venue]) if venues is not None else 0.0
    short_quote_spread = _quote_spread_bps(venues[opportunity.sell_venue]) if venues is not None else 0.0
    long_entry = conservative_fill_probability(stats_db, opportunity.buy_venue, "buy")
    short_entry = conservative_fill_probability(stats_db, opportunity.sell_venue, "sell")
    long_exit = conservative_fill_probability(stats_db, opportunity.buy_venue, "sell")
    short_exit = conservative_fill_probability(stats_db, opportunity.sell_venue, "buy")
    ev = maker_attempt_ev(
        capture_bps=capture,
        long_maker_fee_bps=float(maker_fee_bps[opportunity.buy_venue]),
        long_taker_fee_bps=float(taker_fee_bps[opportunity.buy_venue]),
        short_maker_fee_bps=float(maker_fee_bps[opportunity.sell_venue]),
        short_taker_fee_bps=float(taker_fee_bps[opportunity.sell_venue]),
        long_fill_probability=float(long_entry["conservative_probability"]),
        short_fill_probability=float(short_entry["conservative_probability"]),
        long_exit_fill_probability=float(long_exit["conservative_probability"]),
        short_exit_fill_probability=float(short_exit["conservative_probability"]),
        route_sigma_bps=sigma,
        price_volatility_bps=volatility,
        safety_buffer_bps=safety_buffer_bps,
        long_quote_spread_bps=long_quote_spread,
        short_quote_spread_bps=short_quote_spread,
    )
    decision = {
        "baseline_60m_bps": float(features["baseline_60m_bps"]),
        "baseline_15m_bps": float(features["baseline_15m_bps"]),
        "baseline_5m_bps": float(features["baseline_5m_bps"]),
        "route_sigma_bps": sigma,
        "price_volatility_bps": volatility,
        "structural_excess_bps": excess_60,
        "local_excess_bps": excess_15,
        "fast_excess_bps": excess_5,
        "capture_bps": capture,
        "long_quote_spread_bps": long_quote_spread,
        "short_quote_spread_bps": short_quote_spread,
        "z_score": capture / sigma,
        "long_fill_probability": float(long_entry["conservative_probability"]),
        "short_fill_probability": float(short_entry["conservative_probability"]),
        "long_exit_fill_probability": float(long_exit["conservative_probability"]),
        "short_exit_fill_probability": float(short_exit["conservative_probability"]),
        **ev,
    }
    if capture <= 0.0:
        decision.update({"decision": "NO_ROUTE_DISLOCATION", "tradeable": False})
    elif bool(ev["tradeable"]):
        decision.update({"decision": "PASSIVE_TRADEABLE", "tradeable": True})
    else:
        decision.update({"decision": "EV_BELOW_MIN", "tradeable": False})
    return decision


def _process_maker_probes(
    state: dict[str, Any],
    *,
    books_by_symbol: dict[str, dict[str, VenueBook]],
    stats_db: str | Path,
    now_ms: int,
    timeout_ms: int = 20_000,
    now_mono_ms: int | None = None,
    strict_maker_price_through: bool = False,
) -> None:
    remaining: list[dict[str, Any]] = []
    for probe in list(state.get("maker_probes", [])):
        if int(now_ms) <= int(probe["placed_at_ms"]):
            remaining.append(probe)
            continue
        expired = _elapsed_since_placement_ms(
            probe, now_ms=now_ms, now_mono_ms=now_mono_ms
        ) >= int(timeout_ms)
        venues = books_by_symbol.get(str(probe["symbol"]), {})
        long_book = venues.get(str(probe["long_exchange"]))
        short_book = venues.get(str(probe["short_exchange"]))
        if long_book is None or short_book is None:
            if not expired:
                remaining.append(probe)
            continue
        long_fill = passive_limit_filled(
            "buy",
            float(probe["long_limit_price"]),
            long_book.book,
            placed_at_ms=int(probe["placed_at_ms"]),
            placed_at_mono_ms=probe.get("placed_at_mono_ms"),
            strict_price_through=strict_maker_price_through,
            queue_ahead_quantity=probe.get("long_queue_ahead_quantity"),
            order_quantity=probe.get("quantity"),
            trade_volume_baseline=probe.get("long_trade_volume_baseline"),
        )
        short_fill = passive_limit_filled(
            "sell",
            float(probe["short_limit_price"]),
            short_book.book,
            placed_at_ms=int(probe["placed_at_ms"]),
            placed_at_mono_ms=probe.get("placed_at_mono_ms"),
            strict_price_through=strict_maker_price_through,
            queue_ahead_quantity=probe.get("short_queue_ahead_quantity"),
            order_quantity=probe.get("quantity"),
            trade_volume_baseline=probe.get("short_trade_volume_baseline"),
        )
        if not long_fill and not short_fill and not expired:
            remaining.append(probe)
            continue
        record_fill_outcome(stats_db, str(probe["long_exchange"]), "buy", filled=long_fill)
        record_fill_outcome(stats_db, str(probe["short_exchange"]), "sell", filled=short_fill)
        state["maker_fill_observation_count"] = int(state.get("maker_fill_observation_count", 0)) + 2
    state["maker_probes"] = remaining


def _probe_from_route(
    opportunity: ArbitrageOpportunity,
    venues: dict[str, VenueBook],
    *,
    now_ms: int,
    monotonic_ms: int | None = None,
    decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    long_limit = _best_price(venues[opportunity.buy_venue], "buy")
    short_limit = _best_price(venues[opportunity.sell_venue], "sell")
    quantity = min(
        float(opportunity.target_notional) / long_limit,
        float(opportunity.target_notional) / short_limit,
    )
    return {
        "probe_id": uuid4().hex,
        "position_key": f"{opportunity.symbol}|{opportunity.buy_venue}|{opportunity.sell_venue}",
        "symbol": opportunity.symbol,
        "long_exchange": opportunity.buy_venue,
        "short_exchange": opportunity.sell_venue,
        "long_limit_price": long_limit,
        "short_limit_price": short_limit,
        "target_notional": float(opportunity.target_notional),
        "quantity": float(quantity),
        "placed_at_ms": int(now_ms),
        **_queue_evidence_fields("long", venues[opportunity.buy_venue].book, side="buy", limit_price=long_limit),
        **_queue_evidence_fields("short", venues[opportunity.sell_venue].book, side="sell", limit_price=short_limit),
        **({"placed_at_mono_ms": int(monotonic_ms)} if monotonic_ms is not None else {}),
        **(
            {
                "placement_capture_bps": float(decision.get("capture_bps", 0.0)),
                "placement_pair_value_bps": float(decision.get("conditional_pair_value_bps", 0.0)),
            }
            if decision is not None
            else {}
        ),
    }


def _pending_reserved_margin(state: dict[str, Any]) -> dict[str, float]:
    reserved: dict[str, float] = {}
    for pending in state.get("pending_entries", []):
        if pending.get("status") == "UNWIND_PENDING":
            # Its one filled leg is already included in the live risk summary.
            continue
        leverage = max(1.0, float(pending.get("leverage", 1.0)))
        long_venue = str(pending["long_exchange"])
        short_venue = str(pending["short_exchange"])
        reserved[long_venue] = reserved.get(long_venue, 0.0) + float(pending["long_target_notional"]) / leverage
        reserved[short_venue] = reserved.get(short_venue, 0.0) + float(pending["short_target_notional"]) / leverage
    return reserved


def run_cycle_v17(
    *,
    clients: dict[str, Any],
    symbols: list[str],
    state: dict[str, Any],
    history_db: str | Path,
    stats_db: str | Path,
    safety_buffer_bps: float,
    depth_limit: int,
    taker_fee_bps: dict[str, float] | None,
    maker_fee_bps: dict[str, float] | None,
    max_book_age_ms: int,
    now_ms: int,
    now_utc: str,
    journal_path: Path,
    symbol_venues: dict[str, tuple[str, ...]] | None = None,
    cooldown_ms: int = 5 * 60_000,
    max_pending_entries: int = 4,
    max_probes: int = 20,
    profile_selector: Any = None,
    pending_entry_processor: Any = None,
    route_decider: Any = None,
    maker_probe_processor: Any = None,
    invariant_checker: Any = None,
    strategy_id: str = STRATEGY_ID,
    exit_decision_filter: Any = None,
    exit_decider: Any = None,
    immediate_exit_reasons: set[str] | None = None,
    monotonic_ms: int | None = None,
    per_symbol_history_sampling: bool = False,
    minimum_history_span_ms: int = 600_000,
    minimum_history_samples: int = 12,
    minimum_window_samples: int = 3,
    require_5m_window: bool = True,
    strict_maker_price_through: bool = False,
    reprofile_after_reprice: bool = False,
    route_history_limit: int = 3,
    route_admission_limit: int = 3,
) -> None:
    if safety_buffer_bps < 0.0:
        raise ValueError("safety buffer must be non-negative")
    if minimum_history_samples < 2:
        raise ValueError("minimum history samples must be at least two")
    if minimum_window_samples < 1:
        raise ValueError("minimum window samples must be positive")
    if route_history_limit < 1 or route_admission_limit < 1:
        raise ValueError("route limits must be positive")
    if route_admission_limit > route_history_limit:
        raise ValueError("route admission limit cannot exceed history limit")
    profile_function = select_pair_profile if profile_selector is None else profile_selector
    entry_processor = _process_pending_entries if pending_entry_processor is None else pending_entry_processor
    decide_route = _v17_route_decision if route_decider is None else route_decider
    process_probes = _process_maker_probes if maker_probe_processor is None else maker_probe_processor
    check_invariants = _assert_v17_invariants if invariant_checker is None else invariant_checker
    exit_function = v16_exit_decision if exit_decider is None else exit_decider
    immediate_reasons = {"ROUTE_TARGET", "PROFIT_PROTECT"} if immediate_exit_reasons is None else set(immediate_exit_reasons)
    taker_fees = DEFAULT_FEE_BPS if taker_fee_bps is None else taker_fee_bps
    maker_fees = DEFAULT_MAKER_FEE_BPS if maker_fee_bps is None else maker_fee_bps
    missing = set(clients) - set(taker_fees) | (set(clients) - set(maker_fees))
    if missing:
        raise ValueError(f"missing V17 fee assumptions for venues: {sorted(missing)}")

    state["scan_count"] = int(state.get("scan_count", 0)) + 1
    active_rows = [
        *state.get("open_positions", []),
        *state.get("pending_entries", []),
        *state.get("pending_exits", []),
        *state.get("maker_probes", []),
    ]
    scan_symbols = list(dict.fromkeys([*symbols, *(str(row["symbol"]) for row in active_rows)]))
    books_by_symbol: dict[str, dict[str, VenueBook]] = {}
    for symbol in scan_symbols:
        allowed = set(symbol_venues.get(symbol, ())) if symbol_venues else set(clients)
        scoped = {name: client for name, client in clients.items() if name in allowed}
        books_by_symbol[symbol] = _fetch_venue_books(
            scoped,
            symbol,
            depth_limit=depth_limit,
            fees=taker_fees,
            max_book_age_ms=max_book_age_ms,
            now_ms=now_ms,
        )

    entry_processor(
        state,
        books_by_symbol=books_by_symbol,
        stats_db=stats_db,
        now_ms=now_ms,
        now_utc=now_utc,
        journal_path=journal_path,
        maker_fee_bps=maker_fees,
        taker_fee_bps=taker_fees,
        now_mono_ms=monotonic_ms,
        strict_maker_price_through=strict_maker_price_through,
    )
    _process_pending_exits(
        state,
        books_by_symbol=books_by_symbol,
        stats_db=stats_db,
        now_ms=now_ms,
        now_utc=now_utc,
        journal_path=journal_path,
        maker_fee_bps=maker_fees,
        taker_fee_bps=taker_fees,
        now_mono_ms=monotonic_ms,
        strict_maker_price_through=strict_maker_price_through,
    )
    process_probes(
        state,
        books_by_symbol=books_by_symbol,
        stats_db=stats_db,
        now_ms=now_ms,
        now_mono_ms=monotonic_ms,
        strict_maker_price_through=strict_maker_price_through,
    )
    _refresh_v17_margin(state, books_by_symbol)

    pending_exit_ids = {str(row["position_id"]) for row in state.get("pending_exits", [])}
    immediate_closed_ids: set[str] = set()
    for position in list(state.get("open_positions", [])):
        if str(position["position_id"]) in pending_exit_ids:
            continue
        venues = books_by_symbol.get(str(position["symbol"]), {})
        long_venue = venues.get(str(position["long_exchange"]))
        short_venue = venues.get(str(position["short_exchange"]))
        if long_venue is None or short_venue is None:
            if exit_decision_filter is not None:
                exit_decision_filter(state, position, None, now_ms=now_ms)
            continue
        mark = mark_open_position(position, long_book=long_venue.book, short_book=short_venue.book, marked_at_utc=now_utc)
        if mark.get("mark_status") != "LIVE":
            continue
        route = route_features(
            history_db,
            str(position["symbol"]),
            str(position["long_exchange"]),
            str(position["short_exchange"]),
            now_ms=now_ms,
        )
        slope = float(route["short_slope_bps_per_min"]) if route is not None else None
        reason = exit_function(
            position,
            held_seconds=float(mark["held_seconds"]),
            current_spread_bps=float(mark["current_spread_bps"]),
            close_now_net_pnl=float(mark["estimated_net_pnl_if_closed"]),
            spread_slope_bps_per_min=slope,
        )
        if exit_decision_filter is not None:
            reason = exit_decision_filter(state, position, reason, now_ms=now_ms)
        if reason in immediate_reasons:
            quantity = float(position["quantity"])
            long_fill = _market_fill(
                long_venue,
                side="sell",
                quantity=quantity,
                fee_bps=float(taker_fees[str(position["long_exchange"])]),
            )
            short_fill = _market_fill(
                short_venue,
                side="buy",
                quantity=quantity,
                fee_bps=float(taker_fees[str(position["short_exchange"])]),
            )
            if long_fill is not None and short_fill is not None:
                close = _realize_close_v17(
                    state,
                    position,
                    long_exit_price=float(long_fill.vwap),
                    short_exit_price=float(short_fill.vwap),
                    long_exit_fee_bps=float(taker_fees[str(position["long_exchange"])]),
                    short_exit_fee_bps=float(taker_fees[str(position["short_exchange"])]),
                    long_exit_liquidity="TAKER",
                    short_exit_liquidity="TAKER",
                    reason=reason,
                    now_utc=now_utc,
                )
                state.setdefault("route_cooldowns", {})[str(position["position_key"])] = int(now_ms)
                immediate_closed_ids.add(str(position["position_id"]))
                _append_jsonl(journal_path, close)
                continue
        if reason:
            state.setdefault("pending_exits", []).append(
                _create_pending_exit(
                    position,
                    venues=venues,
                    reason=reason,
                    now_ms=now_ms,
                    now_utc=now_utc,
                    monotonic_ms=monotonic_ms,
                )
            )

    if immediate_closed_ids:
        state["open_positions"] = [
            position
            for position in state.get("open_positions", [])
            if str(position["position_id"]) not in immediate_closed_ids
        ]
        _refresh_v17_margin(state, books_by_symbol)

    probe_target = max(2.0, float(state["equity"]) * 0.10)
    radar: list[dict[str, Any]] = []
    candidates: list[tuple[ArbitrageOpportunity, dict[str, VenueBook], dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    history_rows: list[dict[str, Any]] = []
    history_interval = int(state.get("history_sample_interval_ms", 15_000))
    should_sample = state.get("last_history_sample_ms") is None or int(now_ms) - int(state["last_history_sample_ms"]) >= history_interval
    sample_symbols: set[str] = set()
    if per_symbol_history_sampling:
        last_by_symbol = state.setdefault("last_history_sample_ms_by_symbol", {})
        sample_symbols = {
            symbol
            for symbol in symbols
            if int(now_ms) - int(last_by_symbol.get(symbol, 0)) >= history_interval
        }

    pending_routes = {str(row["position_key"]) for row in state.get("pending_entries", [])}
    open_routes = {str(row["position_key"]) for row in state.get("open_positions", [])}
    active_probe_routes = {str(row["position_key"]) for row in state.get("maker_probes", [])}
    probe_options: list[tuple[float, ArbitrageOpportunity, dict[str, VenueBook], dict[str, Any]]] = []

    for symbol in symbols:
        venues = books_by_symbol.get(symbol, {})
        if len(venues) < 2:
            continue
        routes = _all_routes(
            symbol, venues, target_notional=probe_target, safety_buffer_bps=safety_buffer_bps
        )[:route_history_limit]
        sample_route_history = (per_symbol_history_sampling and symbol in sample_symbols) or (
            not per_symbol_history_sampling and should_sample
        )
        if sample_route_history:
            history_rows.extend(
                {
                    "symbol": symbol,
                    "buy_venue": opportunity.buy_venue,
                    "sell_venue": opportunity.sell_venue,
                    "gross_edge_bps": float(opportunity.gross_edge_bps),
                    "reference_mid_price": (
                        float(opportunity.buy_vwap) + float(opportunity.sell_vwap)
                    ) / 2.0,
                }
                for opportunity in routes
            )
        for opportunity in routes[:route_admission_limit]:
            _increment_candidate_funnel(state, "observed_route_occurrence")
            features = multi_horizon_route_features(
                history_db,
                symbol,
                opportunity.buy_venue,
                opportunity.sell_venue,
                now_ms=now_ms,
                min_samples=minimum_history_samples,
                minimum_span_ms=minimum_history_span_ms,
                minimum_window_samples=minimum_window_samples,
                require_5m_window=require_5m_window,
            )
            if features is not None:
                _increment_candidate_funnel(state, "feature_ready_occurrence")
            decision = decide_route(
                opportunity,
                features=features,
                stats_db=stats_db,
                maker_fee_bps=maker_fees,
                taker_fee_bps=taker_fees,
                safety_buffer_bps=safety_buffer_bps,
                venues=venues,
            )
            row = {
                "symbol": opportunity.symbol,
                "available_venues": sorted(venues),
                "venue_count": len(venues),
                "buy_venue": opportunity.buy_venue,
                "sell_venue": opportunity.sell_venue,
                "gross_edge_bps": float(opportunity.gross_edge_bps),
                "total_fee_bps": float(opportunity.total_fee_bps),
                "safety_buffer_bps": float(safety_buffer_bps),
                "best_net_edge_bps": float(opportunity.net_edge_bps),
                **{key: value for key, value in decision.items() if key != "tradeable"},
                "signal_status": "TRADEABLE" if decision.get("tradeable") else ("WARMUP" if decision.get("decision") == "BASELINE_WARMUP" else "WATCH"),
            }
            if decision.get("tradeable"):
                _increment_candidate_funnel(state, "ev_qualified_occurrence")
                profile = profile_function(
                    {
                        **decision,
                        "excess_after_cost_bps": max(0.001, float(decision["expected_value_bps"])),
                        "z_score": float(decision["z_score"]),
                        "route_sigma_bps": float(decision["route_sigma_bps"]),
                        "price_volatility_bps": float(decision["price_volatility_bps"]),
                    }
                )
                row.update({"proposed_leverage": profile["leverage"], "proposed_pair_gross_fraction": profile["pair_gross_fraction"]})
                candidates.append((opportunity, venues, decision, profile, row))
            elif features is not None:
                capture_bps = float(decision.get("capture_bps", 0.0))
                probe_eligible = bool(decision.get("shadow_probe_eligible", capture_bps >= 1.0))
                if probe_eligible:
                    priority = float(decision.get("shadow_probe_priority", capture_bps))
                    if math.isfinite(priority):
                        probe_options.append((priority, opportunity, venues, decision))
            radar.append(row)

    if history_rows:
        recorded = record_route_snapshots(history_db, now_ms, history_rows)
        if recorded:
            if per_symbol_history_sampling:
                last_by_symbol = state.setdefault("last_history_sample_ms_by_symbol", {})
                for symbol in {str(row["symbol"]) for row in history_rows}:
                    last_by_symbol[symbol] = int(now_ms)
            else:
                state["last_history_sample_ms"] = int(now_ms)

    state["last_cycle_signal_count"] = sum(row.get("signal_status") in {"WATCH", "TRADEABLE"} for row in radar)
    state["last_cycle_tradeable_count"] = len(candidates)
    state["observed_signal_count"] = int(state.get("observed_signal_count", 0)) + int(state["last_cycle_signal_count"])
    state["qualified_opportunity_count"] = int(state.get("qualified_opportunity_count", 0)) + len(candidates)

    # Shadow passive probes learn fill probabilities without mutating account equity.
    for _, opportunity, venues, decision in sorted(probe_options, key=lambda item: item[0], reverse=True):
        route_key = f"{opportunity.symbol}|{opportunity.buy_venue}|{opportunity.sell_venue}"
        if len(state.get("maker_probes", [])) >= max_probes:
            break
        if route_key in active_probe_routes or route_key in pending_routes or route_key in open_routes:
            continue
        state.setdefault("maker_probes", []).append(
            _probe_from_route(
                opportunity,
                venues,
                now_ms=now_ms,
                monotonic_ms=monotonic_ms,
                decision=decision,
            )
        )
        active_probe_routes.add(route_key)
        state["maker_probe_count"] = int(state.get("maker_probe_count", 0)) + 1

    reserved = _pending_reserved_margin(state)
    pending_gross = sum(
        float(row["long_target_notional"]) + float(row["short_target_notional"])
        for row in state.get("pending_entries", [])
        if row.get("status") != "UNWIND_PENDING"
    )
    candidates.sort(key=lambda item: float(item[2]["expected_value_bps"]), reverse=True)
    rank = 0
    for opportunity, venues, decision, profile, row in candidates:
        rank += 1
        route_key = f"{opportunity.symbol}|{opportunity.buy_venue}|{opportunity.sell_venue}"
        row["optimizer_rank"] = rank
        row["optimizer_score_bps"] = float(decision["expected_value_bps"])
        if route_key in open_routes or route_key in pending_routes:
            row["decision"] = "DUPLICATE_ROUTE"
            _increment_candidate_funnel(state, "duplicate_rejected")
            continue
        _increment_candidate_funnel(state, "unique_candidate")
        cooldowns = state.setdefault("route_cooldowns", {})
        if cooldown_active(cooldowns, route_key, now_ms=now_ms, cooldown_ms=cooldown_ms):
            row["decision"] = "ROUTE_COOLDOWN"
            _increment_candidate_funnel(state, "cooldown_rejected")
            continue
        maker_cooldown_key = _maker_leg_cooldown_key(
            opportunity.symbol,
            str(decision.get("maker_venue", "")),
            str(decision.get("maker_side", "")),
        )
        if maker_cooldown_key is not None and cooldown_active(
            cooldowns,
            maker_cooldown_key,
            now_ms=now_ms,
            cooldown_ms=MAKER_NO_FILL_BACKOFF_MS,
        ):
            row["decision"] = "MAKER_NO_FILL_BACKOFF"
            _increment_candidate_funnel(state, "cooldown_rejected")
            continue
        if len(state.get("pending_entries", [])) >= max_pending_entries or len(state.get("open_positions", [])) + len(state.get("pending_entries", [])) >= int(state["max_open_positions"]):
            row["decision"] = "MAX_PENDING_OR_POSITIONS"
            _increment_candidate_funnel(state, "capacity_rejected")
            continue
        leverage = float(profile["leverage"])
        fraction = float(profile["pair_gross_fraction"])
        base_target = float(state["equity"]) * fraction / 2.0
        gross_room = max(0.0, float(state["equity"]) * float(state["gross_leverage_cap"]) - float(state.get("gross_exposure", 0.0)) - pending_gross)
        base_target = min(base_target, gross_room / 2.0)
        if base_target < 2.0:
            row["decision"] = "GROSS_CAP"
            _increment_candidate_funnel(state, "capacity_rejected")
            continue
        available = state["venue_available_margin"]
        target = shrink_target_notional(
            base_target,
            leverage=leverage,
            long_available_margin=max(0.0, float(available.get(opportunity.buy_venue, 0.0)) - reserved.get(opportunity.buy_venue, 0.0)),
            short_available_margin=max(0.0, float(available.get(opportunity.sell_venue, 0.0)) - reserved.get(opportunity.sell_venue, 0.0)),
        )
        if target is None:
            row["decision"] = "VENUE_MARGIN"
            _increment_candidate_funnel(state, "margin_rejected")
            continue
        exact = evaluate_pair(
            opportunity.symbol,
            venues[opportunity.buy_venue],
            venues[opportunity.sell_venue],
            target_notional=target,
            safety_buffer_bps=safety_buffer_bps,
            allow_nonpositive=True,
        )
        if exact is None:
            row["decision"] = "EXECUTION_DEPTH"
            _increment_candidate_funnel(state, "depth_rejected")
            continue
        exact_decision = decide_route(
            exact,
            features=multi_horizon_route_features(
                history_db,
                exact.symbol,
                exact.buy_venue,
                exact.sell_venue,
                now_ms=now_ms,
                min_samples=minimum_history_samples,
                minimum_span_ms=minimum_history_span_ms,
                minimum_window_samples=minimum_window_samples,
                require_5m_window=require_5m_window,
            ),
            stats_db=stats_db,
            maker_fee_bps=maker_fees,
            taker_fee_bps=taker_fees,
            safety_buffer_bps=safety_buffer_bps,
            venues=venues,
        )
        if not exact_decision.get("tradeable"):
            row["decision"] = "REPRICE_EV_REJECTED"
            _increment_candidate_funnel(state, "reprice_ev_rejected")
            continue
        if reprofile_after_reprice:
            # ponytail: at most two downward 40->30->20 passes; never upgrade leverage
            # after sizing because deeper books can only invalidate the probe profile.
            for _ in range(2):
                repriced_profile = profile_function({
                    **exact_decision,
                    "excess_after_cost_bps": max(0.001, float(exact_decision["expected_value_bps"])),
                    "z_score": float(exact_decision["z_score"]),
                    "route_sigma_bps": float(exact_decision["route_sigma_bps"]),
                    "price_volatility_bps": float(exact_decision["price_volatility_bps"]),
                })
                next_leverage = min(leverage, float(repriced_profile["leverage"]))
                next_fraction = min(fraction, float(repriced_profile["pair_gross_fraction"]))
                if next_leverage >= leverage and next_fraction >= fraction:
                    break
                leverage, fraction = next_leverage, next_fraction
                downgraded_base = min(float(state["equity"]) * fraction / 2.0, gross_room / 2.0)
                target = shrink_target_notional(
                    downgraded_base,
                    leverage=leverage,
                    long_available_margin=max(0.0, float(available.get(opportunity.buy_venue, 0.0)) - reserved.get(opportunity.buy_venue, 0.0)),
                    short_available_margin=max(0.0, float(available.get(opportunity.sell_venue, 0.0)) - reserved.get(opportunity.sell_venue, 0.0)),
                )
                if target is None or target < 2.0:
                    exact = None
                    break
                exact = evaluate_pair(
                    opportunity.symbol, venues[opportunity.buy_venue], venues[opportunity.sell_venue],
                    target_notional=target, safety_buffer_bps=safety_buffer_bps, allow_nonpositive=True,
                )
                if exact is None:
                    break
                exact_decision = decide_route(
                    exact,
                    features=multi_horizon_route_features(
                        history_db, exact.symbol, exact.buy_venue, exact.sell_venue,
                        now_ms=now_ms, min_samples=minimum_history_samples,
                        minimum_span_ms=minimum_history_span_ms,
                        minimum_window_samples=minimum_window_samples,
                        require_5m_window=require_5m_window,
                    ),
                    stats_db=stats_db, maker_fee_bps=maker_fees, taker_fee_bps=taker_fees,
                    safety_buffer_bps=safety_buffer_bps, venues=venues,
                )
                if not exact_decision.get("tradeable"):
                    break
            if exact is None:
                row["decision"] = "REPRICE_PROFILE_DEPTH_OR_MARGIN"
                _increment_candidate_funnel(state, "depth_rejected")
                continue
            if not exact_decision.get("tradeable"):
                row["decision"] = "REPRICE_EV_REJECTED"
                _increment_candidate_funnel(state, "reprice_ev_rejected")
                continue
        pending = _create_pending_entry(
            symbol=exact.symbol,
            buy_venue=exact.buy_venue,
            sell_venue=exact.sell_venue,
            venues=venues,
            target_notional=target,
            leverage=leverage,
            pair_gross_fraction=fraction,
            decision=exact_decision,
            maker_fee_bps=maker_fees,
            taker_fee_bps=taker_fees,
            now_ms=now_ms,
            now_utc=now_utc,
            strategy_id=strategy_id,
            monotonic_ms=monotonic_ms,
        )
        state.setdefault("pending_entries", []).append(pending)
        pending_routes.add(route_key)
        pending_gross += float(pending["long_target_notional"]) + float(pending["short_target_notional"])
        reserved[exact.buy_venue] = reserved.get(exact.buy_venue, 0.0) + float(pending["long_target_notional"]) / leverage
        reserved[exact.sell_venue] = reserved.get(exact.sell_venue, 0.0) + float(pending["short_target_notional"]) / leverage
        row["decision"] = "PENDING_MAKER_ENTRY"
        _increment_candidate_funnel(state, "pending_created")
        row["proposed_target_notional"] = float(target)
        _append_jsonl(journal_path, {"record_type": "PAPER_MAKER_ENTRY_PENDING", **pending})

    state["opportunity_radar"] = sorted(radar, key=lambda row: float(row.get("expected_value_bps", -1e9)), reverse=True)[:100]
    _refresh_v17_margin(state, books_by_symbol)

    position_marks: list[dict[str, Any]] = []
    unrealized_net = 0.0
    open_modeled_fees = 0.0
    for position in state.get("open_positions", []):
        venues = books_by_symbol.get(str(position["symbol"]), {})
        long_venue = venues.get(str(position["long_exchange"]))
        short_venue = venues.get(str(position["short_exchange"]))
        if long_venue is None or short_venue is None:
            continue
        mark = mark_open_position(position, long_book=long_venue.book, short_book=short_venue.book, marked_at_utc=now_utc)
        if mark.get("mark_status") != "LIVE":
            continue
        net_pnl = float(mark["estimated_net_pnl_if_closed"])
        unrealized_net += net_pnl
        open_modeled_fees += float(position.get("entry_fees", 0.0)) + float(mark["estimated_exit_fees"])
        position_marks.append(
            {
                "position_id": str(position["position_id"]),
                "symbol": str(position["symbol"]),
                "spread_bps": float(mark["current_spread_bps"]),
                "net_pnl": net_pnl,
                "baseline_bps": float(position.get("entry_baseline_bps", 0.0)),
            }
        )
    partial_unrealized = float(
        state.get("partial_exposure_unrealized_pnl", 0.0)
    )
    partial_entry_fees = float(state.get("partial_exposure_entry_fees", 0.0))
    record_monitor_snapshot(
        history_db,
        now_ms=now_ms,
        account={
            "realized_equity": float(state["equity"]),
            "marked_equity": (
                float(state["equity"]) + unrealized_net + partial_unrealized
            ),
            "realized_pnl": float(state.get("realized_pnl", 0.0)),
            "unrealized_net_pnl": unrealized_net + partial_unrealized,
            "gross_exposure": float(state.get("gross_exposure", 0.0)),
            "margin_used": float(state.get("initial_margin_used", 0.0)),
            "modeled_fee_drag": (
                float(state.get("realized_fee_drag", 0.0))
                + open_modeled_fees
                + partial_entry_fees
            ),
        },
        positions=position_marks,
    )
    check_invariants(state)

def load_state_v17(
    path: str | Path,
    *,
    venue_names: list[str],
    initial_equity: float = 100.0,
    gross_leverage_cap: float = 2.0,
    max_open_positions: int = 8,
) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return _default_state_v17(
            venue_names,
            initial_equity=initial_equity,
            gross_leverage_cap=gross_leverage_cap,
            max_open_positions=max_open_positions,
        )
    with path.open(encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported V17 paper state schema")
    if not isinstance(state.get("open_positions"), list) or not isinstance(state.get("venue_balances"), dict):
        raise ValueError("invalid V17 paper state")
    for key, default in (
        ("pending_entries", []),
        ("pending_exits", []),
        ("maker_probes", []),
        ("route_cooldowns", {}),
    ):
        state.setdefault(key, default)
    for key in (
        "maker_probe_count",
        "maker_fill_observation_count",
        "maker_entry_cancel_count",
        "one_leg_hedge_count",
        "maker_exit_fallback_count",
        "maker_hedge_failure_count",
    ):
        state.setdefault(key, 0)
    _refresh_v17_margin(state)
    _assert_v17_invariants(state)
    return state


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-equity", type=float, default=100.0)
    parser.add_argument("--symbols", type=int, default=50)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--depth", type=int, default=20)
    parser.add_argument("--safety-buffer-bps", type=float, default=0.5)
    parser.add_argument("--max-book-age-ms", type=int, default=10_000)
    parser.add_argument("--gross-leverage-cap", type=float, default=2.0)
    parser.add_argument("--max-open-positions", type=int, default=8)
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/arbitrage_v17"))
    parser.add_argument("--seed-history-db", type=Path, default=Path("artifacts/arbitrage_v16/history_v16.sqlite"))
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    artifacts = args.artifacts_dir
    state_path = artifacts / "state.json"
    health_path = artifacts / "health.json"
    journal_path = artifacts / "positions.jsonl"
    history_db = artifacts / "history_v17.sqlite"
    clients = make_public_clients(include_extended=True)
    try:
        coverage = linear_usdt_symbol_venues(clients, min_venues=2)
        # Reuse V16's deterministic ordering rather than creating another universe policy.
        from scripts.run_arbitrage_paper_v14 import _sorted_universe

        symbols = _sorted_universe(coverage, args.symbols)
        if not symbols:
            raise RuntimeError("fewer than two venues share active linear USDT perpetual symbols")
        venue_names = sorted({venue for symbol in symbols for venue in coverage[symbol]})
        state = load_state_v17(
            state_path,
            venue_names=venue_names,
            initial_equity=args.initial_equity,
            gross_leverage_cap=args.gross_leverage_cap,
            max_open_positions=args.max_open_positions,
        )
        state["universe_symbols"] = symbols
        state["universe_venues"] = {symbol: list(coverage[symbol]) for symbol in symbols}
        if not history_db.exists() and args.seed_history_db.exists():
            state["seeded_route_history_count"] = seed_route_history_from_v16(
                history_db,
                args.seed_history_db,
                now_ms=int(time.time() * 1000),
            )
        while True:
            now_ms = int(time.time() * 1000)
            now_utc = _utc_now()
            try:
                run_cycle_v17(
                    clients=clients,
                    symbols=symbols,
                    state=state,
                    history_db=history_db,
                    stats_db=history_db,
                    safety_buffer_bps=args.safety_buffer_bps,
                    depth_limit=args.depth,
                    taker_fee_bps=None,
                    maker_fee_bps=None,
                    max_book_age_ms=args.max_book_age_ms,
                    now_ms=now_ms,
                    now_utc=now_utc,
                    journal_path=journal_path,
                    symbol_venues=coverage,
                )
                write_state(state_path, state)
                _write_health(health_path, status="HEALTHY", schema_version="v17-arbitrage-health-1")
                print(
                    json.dumps(
                        {
                            "equity": state["equity"],
                            "open_positions": len(state["open_positions"]),
                            "pending_entries": len(state["pending_entries"]),
                            "tradeable": state["last_cycle_tradeable_count"],
                            "maker_probes": len(state["maker_probes"]),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            except Exception as exc:
                _write_health(
                    health_path,
                    status="DEGRADED",
                    error=type(exc).__name__,
                    schema_version="v17-arbitrage-health-1",
                )
                if args.once:
                    raise
            if args.once:
                break
            time.sleep(args.interval)
    finally:
        for client in clients.values():
            close = getattr(client, "close", None)
            if callable(close):
                close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
