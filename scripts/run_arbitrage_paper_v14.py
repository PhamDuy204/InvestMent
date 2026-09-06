"""Credential-free V14 multi-asset leveraged paper arbitrage runner."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any

from crypto_research.arbitrage_v12 import (
    ArbitrageOpportunity,
    VenueBook,
    best_observed_opportunity,
)
from crypto_research.execution_v8 import ExecutionSimulatorV8

if __package__:
    from .run_arbitrage_paper_v12 import (
        DEFAULT_FEE_BPS,
        PREFERRED_BASES,
        _append_jsonl,
        linear_usdt_symbol_venues,
        make_public_clients,
        write_state,
    )
    from .run_arbitrage_paper_v13 import (
        _fetch_venue_books,
        _open_position,
        _try_close_position,
        _utc_now,
        _write_health,
    )
else:
    from run_arbitrage_paper_v12 import (
        DEFAULT_FEE_BPS,
        PREFERRED_BASES,
        _append_jsonl,
        linear_usdt_symbol_venues,
        make_public_clients,
        write_state,
    )
    from run_arbitrage_paper_v13 import (
        _fetch_venue_books,
        _open_position,
        _try_close_position,
        _utc_now,
        _write_health,
    )

SCHEMA_VERSION = "v14-arbitrage-paper-1"
LEGACY_MARGIN_MODEL = "ISOLATED_PAPER_V1"
MARGIN_MODEL = "CROSS_MARGIN_PAPER_V1"
PORTFOLIO_MODEL = "CROSS_MARGIN_OPTIMIZER_V1"


def _venue_names(values: Any) -> list[str]:
    names = sorted({str(name) for name in values if str(name)})
    if len(names) < 2:
        raise ValueError("V14 requires at least two venues")
    return names


def _default_state(
    initial_equity: float = 20.0,
    venue_names: Any = ("okx", "mexc"),
    *,
    exchange_leverage: float = 2.0,
    gross_leverage_cap: float = 2.0,
    max_open_positions: int = 6,
    single_pair_gross_fraction: float = 0.3,
    maintenance_stress_rate: float = 0.05,
    margin_utilization_cap: float = 0.8,
    venue_concentration_penalty_bps: float = 2.0,
) -> dict[str, Any]:
    if initial_equity <= 0.0:
        raise ValueError("initial_equity must be positive")
    if exchange_leverage <= 0.0 or gross_leverage_cap <= 0.0:
        raise ValueError("leverage settings must be positive")
    if max_open_positions <= 0:
        raise ValueError("max_open_positions must be positive")
    if not 0.0 < single_pair_gross_fraction <= gross_leverage_cap:
        raise ValueError("single_pair_gross_fraction must be positive and within gross cap")
    if not 0.0 < maintenance_stress_rate < 1.0:
        raise ValueError("maintenance_stress_rate must be between zero and one")
    if not 0.0 < margin_utilization_cap <= 1.0:
        raise ValueError("margin_utilization_cap must be in (0, 1]")
    if venue_concentration_penalty_bps < 0.0:
        raise ValueError("venue_concentration_penalty_bps must be non-negative")
    names = _venue_names(venue_names)
    per_venue = float(initial_equity) / len(names)
    state = {
        "schema_version": SCHEMA_VERSION,
        "initial_equity": float(initial_equity),
        "equity": float(initial_equity),
        "scan_count": 0,
        "opened_position_count": 0,
        "closed_position_count": 0,
        "qualified_opportunity_count": 0,
        "observed_signal_count": 0,
        "last_cycle_signal_count": 0,
        "last_cycle_tradeable_count": 0,
        "realized_pnl": 0.0,
        "open_positions": [],
        "last_close": None,
        "margin_model": MARGIN_MODEL,
        "portfolio_model": PORTFOLIO_MODEL,
        "maintenance_stress_rate": float(maintenance_stress_rate),
        "margin_utilization_cap": float(margin_utilization_cap),
        "venue_concentration_penalty_bps": float(venue_concentration_penalty_bps),
        "exchange_leverage": float(exchange_leverage),
        "gross_leverage_cap": float(gross_leverage_cap),
        "max_open_positions": int(max_open_positions),
        "single_pair_gross_fraction": float(single_pair_gross_fraction),
        "venue_balances": {name: per_venue for name in names},
        "venue_margin_used": {name: 0.0 for name in names},
        "venue_available_margin": {name: per_venue * margin_utilization_cap for name in names},
        "venue_account_equity": {name: per_venue for name in names},
        "venue_unrealized_pnl": {name: 0.0 for name in names},
        "venue_maintenance_stress": {name: 0.0 for name in names},
        "venue_margin_ratio": {name: None for name in names},
        "venue_margin_utilization": {name: 0.0 for name in names},
        "venue_cross_margin": {},
        "maintenance_stress_used": 0.0,
        "min_stress_margin_ratio": None,
        "gross_exposure": 0.0,
        "gross_leverage_used": 0.0,
        "initial_margin_used": 0.0,
        "available_margin": float(initial_equity),
        "opportunity_radar": [],
        "universe_symbols": [],
        "universe_venues": {},
        "invariant_failure_count": 0,
        "started_at_utc": _utc_now(),
    }
    return state



def _upgrade_v14b_state_to_c(state: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a V14-B state in place without closing paper positions."""
    state["margin_model"] = MARGIN_MODEL
    state["portfolio_model"] = PORTFOLIO_MODEL
    state.setdefault("maintenance_stress_rate", 0.05)
    state.setdefault("margin_utilization_cap", 0.8)
    state.setdefault("venue_concentration_penalty_bps", 2.0)
    for position in state.get("open_positions", []):
        position["margin_model"] = MARGIN_MODEL
        position.setdefault("leverage", float(state.get("exchange_leverage", 2.0)))
    return state

def migrate_v13_state(
    v13_state: dict[str, Any],
    venue_names: Any,
    *,
    exchange_leverage: float = 2.0,
    gross_leverage_cap: float = 2.0,
    max_open_positions: int = 6,
    single_pair_gross_fraction: float = 0.3,
) -> dict[str, Any]:
    if v13_state.get("schema_version") != "v13-arbitrage-paper-1":
        raise ValueError("expected V13 paper state")
    if v13_state.get("open_positions"):
        raise ValueError("V13 must be flat before V14 migration")
    equity = float(v13_state.get("equity", 0.0))
    state = _default_state(
        equity,
        venue_names,
        exchange_leverage=exchange_leverage,
        gross_leverage_cap=gross_leverage_cap,
        max_open_positions=max_open_positions,
        single_pair_gross_fraction=single_pair_gross_fraction,
    )
    state["initial_equity"] = float(v13_state.get("initial_equity", equity))
    state["equity"] = equity
    state["scan_count"] = int(v13_state.get("scan_count", 0))
    state["opened_position_count"] = int(v13_state.get("opened_position_count", 0))
    state["closed_position_count"] = int(v13_state.get("closed_position_count", 0))
    state["realized_pnl"] = float(v13_state.get("realized_pnl", equity - state["initial_equity"]))
    state["last_close"] = v13_state.get("last_close")
    state["migration_source"] = "v13-arbitrage-paper-1"
    state["started_at_utc"] = _utc_now()
    _refresh_risk_summary(state)
    return state


def load_state(
    path: str | Path,
    *,
    initial_equity: float,
    venue_names: Any,
    exchange_leverage: float,
    gross_leverage_cap: float,
    max_open_positions: int,
    single_pair_gross_fraction: float,
    maintenance_stress_rate: float = 0.05,
    margin_utilization_cap: float = 0.8,
    venue_concentration_penalty_bps: float = 2.0,
) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return _default_state(
            initial_equity,
            venue_names,
            exchange_leverage=exchange_leverage,
            gross_leverage_cap=gross_leverage_cap,
            max_open_positions=max_open_positions,
            single_pair_gross_fraction=single_pair_gross_fraction,
            maintenance_stress_rate=maintenance_stress_rate,
            margin_utilization_cap=margin_utilization_cap,
            venue_concentration_penalty_bps=venue_concentration_penalty_bps,
        )
    with path.open(encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported V14 paper state schema")
    if not isinstance(state.get("open_positions"), list):
        raise ValueError("open_positions must be a list")
    if not isinstance(state.get("venue_balances"), dict):
        raise ValueError("venue_balances must be an object")
    _upgrade_v14b_state_to_c(state)
    _refresh_cross_margin_summary(state)
    _assert_invariants(state)
    return state


def _position_gross(position: dict[str, Any]) -> float:
    return float(position.get("long_entry_notional", 0.0)) + float(
        position.get("short_entry_notional", 0.0)
    )


def _mark_position_for_cross_margin(
    position: dict[str, Any],
    venues: dict[str, VenueBook] | None,
) -> dict[str, tuple[float, float]]:
    quantity = float(position["quantity"])
    result = {
        str(position["long_exchange"]): (float(position["long_entry_notional"]), 0.0),
        str(position["short_exchange"]): (float(position["short_entry_notional"]), 0.0),
    }
    if not venues:
        return result
    try:
        long_venue = venues[str(position["long_exchange"])]
        short_venue = venues[str(position["short_exchange"])]
        long_fill = ExecutionSimulatorV8(fee_bps=long_venue.fee_bps).simulate_market_order_by_quantity(
            target_base_quantity=quantity, side="sell", book=long_venue.book
        )
        short_fill = ExecutionSimulatorV8(fee_bps=short_venue.fee_bps).simulate_market_order_by_quantity(
            target_base_quantity=quantity, side="buy", book=short_venue.book
        )
        if long_fill.unmodeled_tail or short_fill.unmodeled_tail:
            return result
        result[str(position["long_exchange"])] = (
            float(long_fill.filled_notional),
            quantity * (float(long_fill.vwap) - float(position["long_entry_vwap"])),
        )
        result[str(position["short_exchange"])] = (
            float(short_fill.filled_notional),
            quantity * (float(position["short_entry_vwap"]) - float(short_fill.vwap)),
        )
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return result
    return result


def _refresh_cross_margin_summary(
    state: dict[str, Any],
    books_by_symbol: dict[str, dict[str, VenueBook]] | None = None,
) -> None:
    _upgrade_v14b_state_to_c(state)
    balances = {str(name): float(value) for name, value in state.get("venue_balances", {}).items()}
    used = {name: 0.0 for name in balances}
    unrealized = {name: 0.0 for name in balances}
    maintenance = {name: 0.0 for name in balances}
    gross_by_venue = {name: 0.0 for name in balances}
    leverage_default = float(state.get("exchange_leverage", 2.0))
    stress_rate = float(state.get("maintenance_stress_rate", 0.05))
    utilization_cap = float(state.get("margin_utilization_cap", 0.8))

    for position in state.get("open_positions", []):
        position["margin_model"] = MARGIN_MODEL
        leverage = float(position.get("leverage", leverage_default))
        venues = None if books_by_symbol is None else books_by_symbol.get(str(position["symbol"]))
        marks = _mark_position_for_cross_margin(position, venues)
        for venue_name, (current_notional, price_pnl) in marks.items():
            balances.setdefault(venue_name, 0.0)
            used.setdefault(venue_name, 0.0)
            unrealized.setdefault(venue_name, 0.0)
            maintenance.setdefault(venue_name, 0.0)
            gross_by_venue.setdefault(venue_name, 0.0)
            is_long = venue_name == str(position["long_exchange"])
            entry_notional = float(position["long_entry_notional"] if is_long else position["short_entry_notional"])
            fee_bps = float(position["long_fee_bps"] if is_long else position["short_fee_bps"])
            entry_fee = entry_notional * fee_bps / 10_000.0
            used[venue_name] += current_notional / leverage
            maintenance[venue_name] += current_notional * stress_rate
            gross_by_venue[venue_name] += current_notional
            unrealized[venue_name] += float(price_pnl) - entry_fee

    account_equity = {name: balances.get(name, 0.0) + unrealized.get(name, 0.0) for name in balances}
    available = {
        name: max(0.0, account_equity[name] * utilization_cap - used.get(name, 0.0))
        for name in balances
    }
    utilization = {
        name: used.get(name, 0.0) / account_equity[name] if account_equity[name] > 0 else float("inf")
        for name in balances
    }
    margin_ratio = {
        name: account_equity[name] / maintenance[name] if maintenance.get(name, 0.0) > 0 else None
        for name in balances
    }
    finite_ratios = [value for value in margin_ratio.values() if isinstance(value, (int, float))]
    equity = float(sum(balances.values()))
    gross = float(sum(gross_by_venue.values()))
    state["equity"] = equity
    state["venue_margin_used"] = used
    state["venue_available_margin"] = available
    state["venue_account_equity"] = account_equity
    state["venue_unrealized_pnl"] = unrealized
    state["venue_maintenance_stress"] = maintenance
    state["venue_margin_ratio"] = margin_ratio
    state["venue_margin_utilization"] = utilization
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
    state["gross_exposure"] = gross
    state["gross_leverage_used"] = gross / equity if equity > 0 else 0.0
    state["initial_margin_used"] = float(sum(used.values()))
    state["available_margin"] = float(sum(available.values()))
    state["maintenance_stress_used"] = float(sum(maintenance.values()))
    state["min_stress_margin_ratio"] = min(finite_ratios) if finite_ratios else None


def _refresh_risk_summary(state: dict[str, Any]) -> None:
    _refresh_cross_margin_summary(state)


def _assert_invariants(state: dict[str, Any]) -> None:
    try:
        equity = float(state["equity"])
        balances = {str(k): float(v) for k, v in state["venue_balances"].items()}
        if equity <= 0.0 or abs(sum(balances.values()) - equity) > 1e-8:
            raise ValueError("venue balances must sum to positive equity")
        positions = state.get("open_positions", [])
        if len(positions) > int(state["max_open_positions"]):
            raise ValueError("max open positions exceeded")
        symbols = [str(position["symbol"]) for position in positions]
        if len(symbols) != len(set(symbols)):
            raise ValueError("only one position per symbol is allowed")
        if float(state["gross_leverage_used"]) > float(state["gross_leverage_cap"]) + 1e-8:
            raise ValueError("gross leverage cap exceeded")
        for name, available in state["venue_available_margin"].items():
            if float(available) < -1e-8:
                raise ValueError(f"venue margin exceeded: {name}")
    except Exception:
        state["invariant_failure_count"] = int(state.get("invariant_failure_count", 0)) + 1
        raise


def _close_leg_accounting(position: dict[str, Any], close: dict[str, Any]) -> tuple[float, float]:
    quantity = float(position["quantity"])
    long_entry_notional = float(position["long_entry_notional"])
    short_entry_notional = float(position["short_entry_notional"])
    long_fee_bps = float(position["long_fee_bps"])
    short_fee_bps = float(position["short_fee_bps"])
    long_exit_notional = quantity * float(close["long_exit_vwap"])
    short_exit_notional = quantity * float(close["short_exit_vwap"])
    long_gross = quantity * (float(close["long_exit_vwap"]) - float(position["long_entry_vwap"]))
    short_gross = quantity * (float(position["short_entry_vwap"]) - float(close["short_exit_vwap"]))
    long_net = long_gross - (long_entry_notional + long_exit_notional) * long_fee_bps / 10_000.0
    short_net = short_gross - (short_entry_notional + short_exit_notional) * short_fee_bps / 10_000.0
    close.update(
        {
            "margin_model": MARGIN_MODEL,
            "leverage": float(position["leverage"]),
            "long_initial_margin": float(position["long_initial_margin"]),
            "short_initial_margin": float(position["short_initial_margin"]),
            "initial_margin": float(position["initial_margin"]),
            "long_realized_net_pnl": float(long_net),
            "short_realized_net_pnl": float(short_net),
        }
    )
    return float(long_net), float(short_net)


def _enrich_open_margin(position: dict[str, Any], leverage: float) -> dict[str, Any]:
    long_margin = float(position["long_entry_notional"]) / leverage
    short_margin = float(position["short_entry_notional"]) / leverage
    position.update(
        {
            "margin_model": MARGIN_MODEL,
            "leverage": float(leverage),
            "long_initial_margin": long_margin,
            "short_initial_margin": short_margin,
            "initial_margin": long_margin + short_margin,
            "entry_gross_exposure": _position_gross(position),
        }
    )
    return position


def _radar_row(
    symbol: str,
    venues: dict[str, VenueBook],
    opportunity: ArbitrageOpportunity | None,
    decision: str,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "symbol": symbol,
        "available_venues": sorted(venues),
        "venue_count": len(venues),
        "decision": decision,
    }
    if opportunity is not None:
        row.update(
            {
                "buy_venue": opportunity.buy_venue,
                "sell_venue": opportunity.sell_venue,
                "gross_edge_bps": float(opportunity.gross_edge_bps),
                "total_fee_bps": float(opportunity.total_fee_bps),
                "safety_buffer_bps": float(opportunity.safety_buffer_bps),
                "best_net_edge_bps": float(opportunity.net_edge_bps),
            }
        )
    return row



def _optimizer_score_bps(state: dict[str, Any], opportunity: ArbitrageOpportunity) -> float:
    """Risk-adjust executable edge by current per-venue cross-margin concentration."""
    utilization = state.get("venue_margin_utilization", {})
    buy_util = max(0.0, float(utilization.get(opportunity.buy_venue, 0.0)))
    sell_util = max(0.0, float(utilization.get(opportunity.sell_venue, 0.0)))
    penalty = float(state.get("venue_concentration_penalty_bps", 0.0))
    return float(opportunity.net_edge_bps) - penalty * (buy_util + sell_util)

def run_cycle(
    *,
    clients: dict[str, Any],
    symbols: list[str],
    state: dict[str, Any],
    min_net_edge_bps: float,
    safety_buffer_bps: float,
    exit_threshold_bps: float,
    max_holding_seconds: float,
    depth_limit: int,
    fee_bps: dict[str, float] | None,
    max_book_age_ms: int,
    now_ms: int,
    now_utc: str,
    journal_path: Path,
    symbol_venues: dict[str, tuple[str, ...]] | None = None,
    signal_min_net_edge_bps: float = -10.0,
) -> None:
    if min_net_edge_bps < 0.0 or safety_buffer_bps < 0.0:
        raise ValueError("trade edge thresholds must be non-negative")
    if signal_min_net_edge_bps > min_net_edge_bps:
        raise ValueError("signal threshold must not exceed trade threshold")
    fees = DEFAULT_FEE_BPS if fee_bps is None else fee_bps
    missing_fees = set(clients) - set(fees)
    if missing_fees:
        raise ValueError(f"missing fee assumptions for venues: {sorted(missing_fees)}")

    state["scan_count"] = int(state.get("scan_count", 0)) + 1
    leverage = float(state["exchange_leverage"])
    pair_gross_fraction = float(state["single_pair_gross_fraction"])
    scan_symbols = list(dict.fromkeys([*symbols, *(p["symbol"] for p in state.get("open_positions", []))]))
    books_by_symbol: dict[str, dict[str, VenueBook]] = {}
    radar: dict[str, dict[str, Any]] = {}

    for symbol in scan_symbols:
        allowed = set(symbol_venues.get(symbol, ())) if symbol_venues else set(clients)
        scoped_clients = {name: client for name, client in clients.items() if name in allowed}
        venues = _fetch_venue_books(
            scoped_clients,
            symbol,
            depth_limit=depth_limit,
            fees=fees,
            max_book_age_ms=max_book_age_ms,
            now_ms=now_ms,
        )
        books_by_symbol[symbol] = venues
        if len(venues) < 2:
            radar[symbol] = _radar_row(symbol, venues, None, "INSUFFICIENT_VENUES")

    remaining: list[dict[str, Any]] = []
    closed_symbols_this_cycle: set[str] = set()
    for position in state.get("open_positions", []):
        venues = books_by_symbol.get(position["symbol"], {})
        close = _try_close_position(
            position,
            venues,
            now_ms=now_ms,
            now_utc=now_utc,
            exit_threshold_bps=exit_threshold_bps,
            max_holding_seconds=max_holding_seconds,
        )
        if close is None:
            remaining.append(position)
            continue
        long_net, short_net = _close_leg_accounting(position, close)
        long_name = str(position["long_exchange"])
        short_name = str(position["short_exchange"])
        state["venue_balances"][long_name] = float(state["venue_balances"].get(long_name, 0.0)) + long_net
        state["venue_balances"][short_name] = float(state["venue_balances"].get(short_name, 0.0)) + short_net
        state["closed_position_count"] = int(state.get("closed_position_count", 0)) + 1
        state["realized_pnl"] = float(state.get("realized_pnl", 0.0)) + float(close["realized_net_pnl"])
        state["last_close"] = close
        closed_symbols_this_cycle.add(str(position["symbol"]))
        _append_jsonl(journal_path, close)
    state["open_positions"] = remaining
    _refresh_cross_margin_summary(state, books_by_symbol)

    target_notional = float(state["equity"]) * pair_gross_fraction / 2.0
    candidates: list[tuple[ArbitrageOpportunity, dict[str, VenueBook]]] = []
    for symbol in symbols:
        venues = books_by_symbol.get(symbol, {})
        if len(venues) < 2:
            continue
        opportunity = best_observed_opportunity(
            symbol,
            list(venues.values()),
            target_notional=target_notional,
            safety_buffer_bps=safety_buffer_bps,
        )
        if opportunity is None:
            radar[symbol] = _radar_row(symbol, venues, None, "EXECUTION_DEPTH")
            continue
        row = _radar_row(symbol, venues, opportunity, "QUALIFIED")
        row["edge_to_trade_bps"] = max(0.0, float(min_net_edge_bps) - float(opportunity.net_edge_bps))
        if opportunity.net_edge_bps >= min_net_edge_bps:
            row["signal_status"] = "TRADEABLE"
            radar[symbol] = row
            candidates.append((opportunity, venues))
            continue
        row["signal_status"] = "WATCH" if opportunity.net_edge_bps >= signal_min_net_edge_bps else "REJECTED"
        row["decision"] = "NO_POSITIVE_EDGE" if opportunity.net_edge_bps <= 0.0 else "EDGE_BELOW_MIN"
        radar[symbol] = row

    cycle_signal_count = sum(
        row.get("signal_status") in {"WATCH", "TRADEABLE"}
        for row in radar.values()
    )
    state["last_cycle_signal_count"] = int(cycle_signal_count)
    state["last_cycle_tradeable_count"] = len(candidates)
    state["observed_signal_count"] = int(state.get("observed_signal_count", 0)) + int(cycle_signal_count)
    state["qualified_opportunity_count"] = int(state.get("qualified_opportunity_count", 0)) + len(candidates)
    open_symbols = {position["symbol"] for position in state["open_positions"]}
    pending = list(candidates)
    optimizer_rank = 0

    while pending:
        pending.sort(key=lambda item: _optimizer_score_bps(state, item[0]), reverse=True)
        opportunity, venues = pending.pop(0)
        optimizer_rank += 1
        row = radar[opportunity.symbol]
        row["optimizer_score_bps"] = _optimizer_score_bps(state, opportunity)
        row["optimizer_rank"] = optimizer_rank
        if opportunity.symbol in closed_symbols_this_cycle:
            row["decision"] = "CLOSED_THIS_CYCLE"
            continue
        if opportunity.symbol in open_symbols:
            row["decision"] = "DUPLICATE_SYMBOL"
            continue
        if len(state["open_positions"]) >= int(state["max_open_positions"]):
            row["decision"] = "MAX_POSITIONS"
            continue
        current_gross = float(state["gross_exposure"])
        gross_cap = float(state["equity"]) * float(state["gross_leverage_cap"])
        if current_gross + 2.0 * target_notional > gross_cap + 1e-8:
            row["decision"] = "GROSS_CAP"
            continue
        required = target_notional / leverage
        available = state["venue_available_margin"]
        if (
            float(available.get(opportunity.buy_venue, 0.0)) + 1e-8 < required
            or float(available.get(opportunity.sell_venue, 0.0)) + 1e-8 < required
        ):
            row["decision"] = "VENUE_MARGIN"
            continue
        position = _open_position(opportunity, venues, now_ms=now_ms, now_utc=now_utc)
        if position is None:
            row["decision"] = "EXECUTION_DEPTH"
            continue
        _enrich_open_margin(position, leverage)
        if current_gross + _position_gross(position) > gross_cap + 1e-8:
            row["decision"] = "GROSS_CAP"
            continue
        if (
            float(available.get(position["long_exchange"], 0.0)) + 1e-8 < float(position["long_initial_margin"])
            or float(available.get(position["short_exchange"], 0.0)) + 1e-8 < float(position["short_initial_margin"])
        ):
            row["decision"] = "VENUE_MARGIN"
            continue
        state["open_positions"].append(position)
        state["opened_position_count"] = int(state.get("opened_position_count", 0)) + 1
        open_symbols.add(position["symbol"])
        row["decision"] = "OPENED"
        _append_jsonl(journal_path, {"record_type": "PAPER_POSITION_OPEN", **position})
        _refresh_cross_margin_summary(state, books_by_symbol)

    state["opportunity_radar"] = sorted(
        radar.values(),
        key=lambda row: (
            row.get("best_net_edge_bps") is not None,
            float(row.get("best_net_edge_bps", float("-inf"))),
        ),
        reverse=True,
    )[:100]
    _refresh_cross_margin_summary(state, books_by_symbol)
    _assert_invariants(state)


def _sorted_universe(
    coverage: dict[str, tuple[str, ...]],
    limit: int,
    *,
    activity_scores: dict[str, float] | None = None,
) -> list[str]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    preferred_rank = {base: rank for rank, base in enumerate(PREFERRED_BASES)}
    scores = activity_scores or {}

    def activity(symbol: str) -> float:
        try:
            value = float(scores.get(symbol, 0.0))
        except (TypeError, ValueError):
            return 0.0
        return value if math.isfinite(value) and value >= 0.0 else 0.0

    ranked = sorted(
        coverage,
        key=lambda symbol: (
            preferred_rank.get(symbol.split("/", 1)[0], len(preferred_rank)),
            -len(coverage[symbol]),
            -activity(symbol),
            symbol,
        ),
    )
    primary: list[str] = []
    secondary: list[str] = []
    seen_bases: set[str] = set()
    for symbol in ranked:
        base = symbol.split("/", 1)[0]
        if base in seen_bases:
            secondary.append(symbol)
            continue
        seen_bases.add(base)
        primary.append(symbol)
    return (primary + secondary)[:limit]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-equity", type=float, default=20.0)
    parser.add_argument("--symbols", type=int, default=50)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--depth", type=int, default=20)
    parser.add_argument("--min-net-edge-bps", type=float, default=1.0)
    parser.add_argument("--safety-buffer-bps", type=float, default=1.0)
    parser.add_argument("--signal-min-net-edge-bps", type=float, default=-10.0)
    parser.add_argument("--exit-threshold-bps", type=float, default=5.0)
    parser.add_argument("--max-holding-seconds", type=float, default=3600.0)
    parser.add_argument("--max-book-age-ms", type=int, default=10_000)
    parser.add_argument("--exchange-leverage", type=float, default=2.0)
    parser.add_argument("--gross-leverage-cap", type=float, default=2.0)
    parser.add_argument("--max-open-positions", type=int, default=6)
    parser.add_argument("--single-pair-gross-fraction", type=float, default=0.3)
    parser.add_argument("--maintenance-stress-rate", type=float, default=0.05)
    parser.add_argument("--margin-utilization-cap", type=float, default=0.8)
    parser.add_argument("--venue-concentration-penalty-bps", type=float, default=2.0)
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/arbitrage_v14"))
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    artifacts = args.artifacts_dir
    state_path = artifacts / "state.json"
    health_path = artifacts / "health.json"
    journal_path = artifacts / "positions.jsonl"
    clients = make_public_clients(include_extended=True)
    try:
        coverage = linear_usdt_symbol_venues(clients, min_venues=2)
        symbols = _sorted_universe(coverage, args.symbols)
        if not symbols:
            raise RuntimeError("fewer than two venues share active linear USDT perpetual symbols")
        venue_names = sorted({venue for symbol in symbols for venue in coverage[symbol]})
        state = load_state(
            state_path,
            initial_equity=args.initial_equity,
            venue_names=venue_names,
            exchange_leverage=args.exchange_leverage,
            gross_leverage_cap=args.gross_leverage_cap,
            max_open_positions=args.max_open_positions,
            single_pair_gross_fraction=args.single_pair_gross_fraction,
            maintenance_stress_rate=args.maintenance_stress_rate,
            margin_utilization_cap=args.margin_utilization_cap,
            venue_concentration_penalty_bps=args.venue_concentration_penalty_bps,
        )
        for venue in venue_names:
            state["venue_balances"].setdefault(venue, 0.0)
        state["universe_symbols"] = symbols
        state["universe_venues"] = {symbol: list(coverage[symbol]) for symbol in symbols}
        _refresh_risk_summary(state)

        while True:
            now_ms = int(time.time() * 1000)
            try:
                run_cycle(
                    clients=clients,
                    symbols=symbols,
                    state=state,
                    min_net_edge_bps=args.min_net_edge_bps,
                    safety_buffer_bps=args.safety_buffer_bps,
                    exit_threshold_bps=args.exit_threshold_bps,
                    max_holding_seconds=args.max_holding_seconds,
                    depth_limit=args.depth,
                    fee_bps=None,
                    max_book_age_ms=args.max_book_age_ms,
                    now_ms=now_ms,
                    now_utc=_utc_now(),
                    journal_path=journal_path,
                    symbol_venues=coverage,
                    signal_min_net_edge_bps=args.signal_min_net_edge_bps,
                )
                write_state(state_path, state)
                _write_health(
                    health_path,
                    status="HEALTHY",
                    schema_version="v14-arbitrage-health-1",
                )
                print(
                    json.dumps(
                        {
                            "equity": state["equity"],
                            "open_positions": len(state["open_positions"]),
                            "gross_leverage_used": state["gross_leverage_used"],
                            "qualified": state["qualified_opportunity_count"],
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
                    schema_version="v14-arbitrage-health-1",
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
