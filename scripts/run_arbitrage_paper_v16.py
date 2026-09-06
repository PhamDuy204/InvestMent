"""V16 route-relative, dynamic-leverage paper arbitrage runner."""

from __future__ import annotations

import argparse
import json
import time
from itertools import permutations
from pathlib import Path
from typing import Any

from crypto_research.arbitrage_v12 import ArbitrageOpportunity, VenueBook, evaluate_pair
from crypto_research.monitoring_v13 import mark_open_position
from crypto_research.route_v16 import (
    dynamic_leverage,
    entry_decision,
    record_monitor_snapshot,
    record_route_snapshots,
    route_features,
    seed_route_history_from_v15,
)

if __package__:
    from .run_arbitrage_paper_v12 import (
        DEFAULT_FEE_BPS,
        _append_jsonl,
        linear_usdt_symbol_venues,
        make_public_clients,
        write_state,
    )
    from .run_arbitrage_paper_v13 import (
        _fetch_venue_books,
        _open_position,
        _utc_now,
        _write_health,
    )
    from .run_arbitrage_paper_v14 import (
        _close_leg_accounting,
        _default_state,
        _enrich_open_margin,
        _refresh_cross_margin_summary,
        _sorted_universe,
    )
else:
    from run_arbitrage_paper_v12 import (
        DEFAULT_FEE_BPS,
        _append_jsonl,
        linear_usdt_symbol_venues,
        make_public_clients,
        write_state,
    )
    from run_arbitrage_paper_v13 import (
        _fetch_venue_books,
        _open_position,
        _utc_now,
        _write_health,
    )
    from run_arbitrage_paper_v14 import (
        _close_leg_accounting,
        _default_state,
        _enrich_open_margin,
        _refresh_cross_margin_summary,
        _sorted_universe,
    )

SCHEMA_VERSION = "v16-arbitrage-paper-1"
PORTFOLIO_MODEL = "ROUTE_RELATIVE_MULTI_STRATEGY_V1"
MARGIN_MODEL = "CROSS_MARGIN_PAPER_V1"
STRATEGY_ID = "ROUTE_RELATIVE_MEAN_REVERSION_V1"


def _default_state_v16(
    venue_names: list[str],
    *,
    initial_equity: float = 100.0,
    gross_leverage_cap: float = 2.0,
    max_open_positions: int = 8,
) -> dict[str, Any]:
    state = _default_state(
        initial_equity,
        venue_names,
        exchange_leverage=3.0,
        gross_leverage_cap=gross_leverage_cap,
        max_open_positions=max_open_positions,
        single_pair_gross_fraction=0.20,
        maintenance_stress_rate=0.05,
        margin_utilization_cap=0.85,
        venue_concentration_penalty_bps=0.5,
    )
    state.update(
        {
            "schema_version": SCHEMA_VERSION,
            "portfolio_model": PORTFOLIO_MODEL,
            "margin_model": MARGIN_MODEL,
            "route_cooldowns": {},
            "min_position_leverage": 1.0,
            "max_position_leverage": 3.0,
            "history_sample_interval_ms": 15_000,
            "last_history_sample_ms": None,
            "realized_fee_drag": 0.0,
        }
    )
    return state


def load_state_v16(
    path: str | Path,
    *,
    venue_names: list[str],
    initial_equity: float = 100.0,
    gross_leverage_cap: float = 2.0,
    max_open_positions: int = 8,
) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return _default_state_v16(
            venue_names,
            initial_equity=initial_equity,
            gross_leverage_cap=gross_leverage_cap,
            max_open_positions=max_open_positions,
        )
    with path.open(encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported V16 paper state schema")
    if not isinstance(state.get("open_positions"), list) or not isinstance(state.get("venue_balances"), dict):
        raise ValueError("invalid V16 paper state")
    state.setdefault("route_cooldowns", {})
    _refresh_v16_margin(state)
    _assert_v16_invariants(state)
    return state


def _refresh_v16_margin(
    state: dict[str, Any],
    books_by_symbol: dict[str, dict[str, VenueBook]] | None = None,
) -> None:
    _refresh_cross_margin_summary(state, books_by_symbol)
    state["schema_version"] = SCHEMA_VERSION
    state["portfolio_model"] = PORTFOLIO_MODEL
    state["margin_model"] = MARGIN_MODEL


def _assert_v16_invariants(state: dict[str, Any]) -> None:
    try:
        equity = float(state["equity"])
        balances = {str(key): float(value) for key, value in state["venue_balances"].items()}
        if equity <= 0.0 or abs(sum(balances.values()) - equity) > 1e-8:
            raise ValueError("venue balances must sum to positive equity")
        positions = list(state.get("open_positions", []))
        if len(positions) > int(state["max_open_positions"]):
            raise ValueError("max open positions exceeded")
        keys = [str(position.get("position_key") or "") for position in positions]
        if not all(keys) or len(keys) != len(set(keys)):
            raise ValueError("duplicate route")
        for position in positions:
            leverage = float(position.get("leverage", 0.0))
            if not 1.0 <= leverage <= 3.0:
                raise ValueError("position leverage outside V16 bounds")
        gross_used = float(state.get("gross_leverage_used", 0.0))
        if gross_used > float(state["gross_leverage_cap"]) + 1e-8:
            raise ValueError("gross leverage cap exceeded")
        for venue, available in state.get("venue_available_margin", {}).items():
            if float(available) < -1e-8:
                raise ValueError(f"venue margin exceeded: {venue}")
    except Exception:
        state["invariant_failure_count"] = int(state.get("invariant_failure_count", 0)) + 1
        raise


def select_pair_profile(decision: dict[str, Any]) -> dict[str, float]:
    leverage = dynamic_leverage(
        excess_after_cost_bps=float(decision["excess_after_cost_bps"]),
        z_score=float(decision["z_score"]),
        route_sigma_bps=float(decision["route_sigma_bps"]),
        price_volatility_bps=float(decision["price_volatility_bps"]),
    )
    fraction = {1.0: 0.12, 2.0: 0.16, 3.0: 0.20}[leverage]
    return {"leverage": leverage, "pair_gross_fraction": fraction}


def shrink_target_notional(
    base_target_notional: float,
    *,
    leverage: float,
    long_available_margin: float,
    short_available_margin: float,
    min_notional: float = 2.0,
) -> float | None:
    if base_target_notional <= 0.0 or leverage <= 0.0 or min_notional <= 0.0:
        raise ValueError("notional, leverage, and minimum must be positive")
    supported = min(
        float(base_target_notional),
        max(0.0, float(long_available_margin)) * float(leverage),
        max(0.0, float(short_available_margin)) * float(leverage),
    )
    return supported if supported >= min_notional else None


def cooldown_active(
    cooldowns: dict[str, Any],
    route_key: str,
    *,
    now_ms: int,
    cooldown_ms: int = 5 * 60_000,
) -> bool:
    if cooldown_ms < 0:
        raise ValueError("cooldown_ms must be non-negative")
    last_closed = cooldowns.get(route_key)
    return isinstance(last_closed, int) and int(now_ms) - last_closed <= int(cooldown_ms)


def v16_exit_decision(
    position: dict[str, Any],
    *,
    held_seconds: float,
    current_spread_bps: float,
    close_now_net_pnl: float,
    spread_slope_bps_per_min: float | None,
) -> str | None:
    baseline = float(position["entry_baseline_bps"])
    entry_excess = max(0.0, float(position["entry_excess_spread_bps"]))
    sigma = max(0.5, float(position["entry_route_sigma_bps"]))
    slope = None if spread_slope_bps_per_min is None else float(spread_slope_bps_per_min)

    if held_seconds >= 60 * 60:
        return "V16_MAX_HOLD"
    route_target = baseline + max(1.0, entry_excess * 0.25)
    if close_now_net_pnl > 0.0 and current_spread_bps <= route_target:
        return "ROUTE_TARGET"
    if close_now_net_pnl > 0.0 and held_seconds >= 5 * 60 and slope is not None and slope >= 0.0:
        return "PROFIT_PROTECT"
    divergence_level = baseline + entry_excess + max(10.0, 1.5 * sigma)
    if held_seconds >= 10 * 60 and close_now_net_pnl < 0.0 and current_spread_bps >= divergence_level:
        return "DIVERGENCE_STOP"
    if held_seconds >= 30 * 60 and (slope is None or slope > -0.05):
        return "ADAPTIVE_TIMEOUT"
    return None


def _all_routes(
    symbol: str,
    venues: dict[str, VenueBook],
    *,
    target_notional: float,
    safety_buffer_bps: float,
) -> list[ArbitrageOpportunity]:
    opportunities = [
        opportunity
        for buy, sell in permutations(venues.values(), 2)
        if (
            opportunity := evaluate_pair(
                symbol,
                buy,
                sell,
                target_notional=target_notional,
                safety_buffer_bps=safety_buffer_bps,
                allow_nonpositive=True,
            )
        )
        is not None
    ]
    return sorted(opportunities, key=lambda item: item.gross_edge_bps, reverse=True)


def _route_key(opportunity: ArbitrageOpportunity) -> str:
    return f"{opportunity.symbol}|{opportunity.buy_venue}|{opportunity.sell_venue}"


def _radar_row(
    opportunity: ArbitrageOpportunity,
    venues: dict[str, VenueBook],
    decision: dict[str, Any],
) -> dict[str, Any]:
    return {
        "symbol": opportunity.symbol,
        "available_venues": sorted(venues),
        "venue_count": len(venues),
        "buy_venue": opportunity.buy_venue,
        "sell_venue": opportunity.sell_venue,
        "gross_edge_bps": float(opportunity.gross_edge_bps),
        "total_fee_bps": float(opportunity.total_fee_bps),
        "safety_buffer_bps": float(opportunity.safety_buffer_bps),
        "best_net_edge_bps": float(opportunity.net_edge_bps),
        **{key: value for key, value in decision.items() if key != "tradeable"},
        "signal_status": "TRADEABLE" if decision.get("tradeable") else (
            "WARMUP" if decision.get("decision") == "BASELINE_WARMUP" else "WATCH"
        ),
    }


def _close_from_mark_v16(
    position: dict[str, Any],
    mark: dict[str, Any],
    *,
    reason: str,
    now_utc: str,
) -> dict[str, Any]:
    return {
        "record_type": "PAPER_POSITION_CLOSE",
        "position_id": str(position["position_id"]),
        "symbol": str(position["symbol"]),
        "long_exchange": str(position["long_exchange"]),
        "short_exchange": str(position["short_exchange"]),
        "quantity": float(position["quantity"]),
        "opened_at": position.get("opened_at"),
        "closed_at": now_utc,
        "held_seconds": float(mark["held_seconds"]),
        "close_reason": reason,
        "remaining_spread_bps": float(mark["current_spread_bps"]),
        "long_entry_vwap": float(position["long_entry_vwap"]),
        "short_entry_vwap": float(position["short_entry_vwap"]),
        "long_exit_vwap": float(mark["long_current_vwap"]),
        "short_exit_vwap": float(mark["short_current_vwap"]),
        "entry_fees": float(position["entry_fees"]),
        "exit_fees": float(mark["estimated_exit_fees"]),
        "gross_pnl": float(mark["gross_unrealized_pnl"]),
        "realized_net_pnl": float(mark["estimated_net_pnl_if_closed"]),
        "initial_net_edge_bps": float(position.get("initial_net_edge_bps", 0.0)),
        "strategy_id": str(position.get("strategy_id") or STRATEGY_ID),
        "entry_baseline_bps": float(position.get("entry_baseline_bps", 0.0)),
        "entry_excess_spread_bps": float(position.get("entry_excess_spread_bps", 0.0)),
        "entry_excess_after_cost_bps": float(position.get("entry_excess_after_cost_bps", 0.0)),
        "entry_z_score": float(position.get("entry_z_score", 0.0)),
    }


def _candidate_score(state: dict[str, Any], opportunity: ArbitrageOpportunity, decision: dict[str, Any]) -> float:
    utilization = state.get("venue_margin_utilization", {})
    concentration = float(state.get("venue_concentration_penalty_bps", 0.5)) * (
        max(0.0, float(utilization.get(opportunity.buy_venue, 0.0)))
        + max(0.0, float(utilization.get(opportunity.sell_venue, 0.0)))
    )
    return float(decision["excess_after_cost_bps"]) - concentration


def run_cycle_v16(
    *,
    clients: dict[str, Any],
    symbols: list[str],
    state: dict[str, Any],
    history_db: str | Path,
    safety_buffer_bps: float,
    depth_limit: int,
    fee_bps: dict[str, float] | None,
    max_book_age_ms: int,
    now_ms: int,
    now_utc: str,
    journal_path: Path,
    symbol_venues: dict[str, tuple[str, ...]] | None = None,
    cooldown_ms: int = 5 * 60_000,
) -> None:
    if safety_buffer_bps < 0.0:
        raise ValueError("safety buffer must be non-negative")
    fees = DEFAULT_FEE_BPS if fee_bps is None else fee_bps
    missing_fees = set(clients) - set(fees)
    if missing_fees:
        raise ValueError(f"missing fee assumptions for venues: {sorted(missing_fees)}")

    state["scan_count"] = int(state.get("scan_count", 0)) + 1
    scan_symbols = list(dict.fromkeys([*symbols, *(str(p["symbol"]) for p in state.get("open_positions", []))]))
    books_by_symbol: dict[str, dict[str, VenueBook]] = {}
    for symbol in scan_symbols:
        allowed = set(symbol_venues.get(symbol, ())) if symbol_venues else set(clients)
        scoped = {name: client for name, client in clients.items() if name in allowed}
        books_by_symbol[symbol] = _fetch_venue_books(
            scoped,
            symbol,
            depth_limit=depth_limit,
            fees=fees,
            max_book_age_ms=max_book_age_ms,
            now_ms=now_ms,
        )

    # Close with V16 route-relative marks before considering new entries.
    remaining: list[dict[str, Any]] = []
    closed_routes_this_cycle: set[str] = set()
    for position in state.get("open_positions", []):
        venues = books_by_symbol.get(str(position["symbol"]), {})
        long_venue = venues.get(str(position["long_exchange"]))
        short_venue = venues.get(str(position["short_exchange"]))
        if long_venue is None or short_venue is None:
            remaining.append(position)
            continue
        mark = mark_open_position(
            position,
            long_book=long_venue.book,
            short_book=short_venue.book,
            marked_at_utc=now_utc,
        )
        if mark.get("mark_status") != "LIVE":
            remaining.append(position)
            continue
        features = route_features(
            history_db,
            str(position["symbol"]),
            str(position["long_exchange"]),
            str(position["short_exchange"]),
            now_ms=now_ms,
        )
        slope = float(features["short_slope_bps_per_min"]) if features is not None else None
        reason = v16_exit_decision(
            position,
            held_seconds=float(mark["held_seconds"]),
            current_spread_bps=float(mark["current_spread_bps"]),
            close_now_net_pnl=float(mark["estimated_net_pnl_if_closed"]),
            spread_slope_bps_per_min=slope,
        )
        if reason is None:
            remaining.append(position)
            continue
        close = _close_from_mark_v16(position, mark, reason=reason, now_utc=now_utc)
        long_net, short_net = _close_leg_accounting(position, close)
        state["venue_balances"][str(position["long_exchange"])] += long_net
        state["venue_balances"][str(position["short_exchange"])] += short_net
        state["closed_position_count"] = int(state.get("closed_position_count", 0)) + 1
        state["realized_pnl"] = float(state.get("realized_pnl", 0.0)) + float(close["realized_net_pnl"])
        state["realized_fee_drag"] = float(state.get("realized_fee_drag", 0.0)) + float(close["entry_fees"]) + float(close["exit_fees"])
        state["last_close"] = close
        route_key = str(position["position_key"])
        state.setdefault("route_cooldowns", {})[route_key] = int(now_ms)
        closed_routes_this_cycle.add(route_key)
        _append_jsonl(journal_path, close)
    state["open_positions"] = remaining
    _refresh_v16_margin(state, books_by_symbol)

    probe_target = max(2.0, float(state["equity"]) * 0.10)
    radar: list[dict[str, Any]] = []
    candidates: list[tuple[ArbitrageOpportunity, dict[str, VenueBook], dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    history_rows: list[dict[str, Any]] = []
    should_sample = (
        state.get("last_history_sample_ms") is None
        or int(now_ms) - int(state["last_history_sample_ms"]) >= int(state.get("history_sample_interval_ms", 15_000))
    )

    for symbol in symbols:
        venues = books_by_symbol.get(symbol, {})
        if len(venues) < 2:
            continue
        routes = _all_routes(symbol, venues, target_notional=probe_target, safety_buffer_bps=safety_buffer_bps)[:3]
        for opportunity in routes:
            features = route_features(
                history_db,
                symbol,
                opportunity.buy_venue,
                opportunity.sell_venue,
                now_ms=now_ms,
            )
            decision = entry_decision(
                current_gross_edge_bps=float(opportunity.gross_edge_bps),
                total_fee_bps=float(opportunity.total_fee_bps),
                safety_buffer_bps=safety_buffer_bps,
                features=features,
            )
            row = _radar_row(opportunity, venues, decision)
            profile = None
            if decision.get("tradeable"):
                profile = select_pair_profile(decision)
                row.update(
                    {
                        "proposed_leverage": profile["leverage"],
                        "proposed_pair_gross_fraction": profile["pair_gross_fraction"],
                    }
                )
                candidates.append((opportunity, venues, decision, profile, row))
            radar.append(row)
            if should_sample:
                history_rows.append(
                    {
                        "symbol": symbol,
                        "buy_venue": opportunity.buy_venue,
                        "sell_venue": opportunity.sell_venue,
                        "gross_edge_bps": float(opportunity.gross_edge_bps),
                        "reference_mid_price": (float(opportunity.buy_vwap) + float(opportunity.sell_vwap)) / 2.0,
                    }
                )

    if should_sample and history_rows:
        record_route_snapshots(history_db, now_ms, history_rows)
        state["last_history_sample_ms"] = int(now_ms)

    state["last_cycle_signal_count"] = sum(row.get("signal_status") in {"WATCH", "TRADEABLE"} for row in radar)
    state["last_cycle_tradeable_count"] = len(candidates)
    state["observed_signal_count"] = int(state.get("observed_signal_count", 0)) + int(state["last_cycle_signal_count"])
    state["qualified_opportunity_count"] = int(state.get("qualified_opportunity_count", 0)) + len(candidates)

    open_routes = {str(position["position_key"]) for position in state["open_positions"]}
    candidates.sort(key=lambda item: _candidate_score(state, item[0], item[2]), reverse=True)
    rank = 0
    for opportunity, venues, decision, profile, row in candidates:
        rank += 1
        route_key = _route_key(opportunity)
        row["optimizer_rank"] = rank
        row["optimizer_score_bps"] = _candidate_score(state, opportunity, decision)
        if route_key in closed_routes_this_cycle:
            row["decision"] = "CLOSED_THIS_CYCLE"
            continue
        if route_key in open_routes:
            row["decision"] = "DUPLICATE_ROUTE"
            continue
        if cooldown_active(state.setdefault("route_cooldowns", {}), route_key, now_ms=now_ms, cooldown_ms=cooldown_ms):
            row["decision"] = "ROUTE_COOLDOWN"
            continue
        if len(state["open_positions"]) >= int(state["max_open_positions"]):
            row["decision"] = "MAX_POSITIONS"
            continue

        leverage = float(profile["leverage"])
        fraction = float(profile["pair_gross_fraction"])
        base_target = float(state["equity"]) * fraction / 2.0
        gross_room = max(0.0, float(state["equity"]) * float(state["gross_leverage_cap"]) - float(state["gross_exposure"]))
        base_target = min(base_target, gross_room / 2.0)
        if base_target < 2.0:
            row["decision"] = "GROSS_CAP"
            continue
        available = state["venue_available_margin"]
        target = shrink_target_notional(
            base_target,
            leverage=leverage,
            long_available_margin=float(available.get(opportunity.buy_venue, 0.0)),
            short_available_margin=float(available.get(opportunity.sell_venue, 0.0)),
        )
        if target is None:
            row["decision"] = "VENUE_MARGIN"
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
            continue
        exact_decision = entry_decision(
            current_gross_edge_bps=float(exact.gross_edge_bps),
            total_fee_bps=float(exact.total_fee_bps),
            safety_buffer_bps=safety_buffer_bps,
            features=route_features(
                history_db,
                exact.symbol,
                exact.buy_venue,
                exact.sell_venue,
                now_ms=now_ms,
            ),
        )
        if not exact_decision.get("tradeable"):
            row["decision"] = "REPRICE_REJECTED"
            continue
        position = _open_position(exact, venues, now_ms=now_ms, now_utc=now_utc)
        if position is None:
            row["decision"] = "EXECUTION_DEPTH"
            continue
        raw_net = float(position["initial_net_edge_bps"])
        position.update(
            {
                "strategy_id": STRATEGY_ID,
                "raw_net_edge_bps": raw_net,
                "initial_net_edge_bps": float(exact_decision["excess_after_cost_bps"]),
                "entry_baseline_bps": float(exact_decision["baseline_bps"]),
                "entry_excess_spread_bps": float(exact_decision["excess_spread_bps"]),
                "entry_excess_after_cost_bps": float(exact_decision["excess_after_cost_bps"]),
                "entry_fee_hurdle_bps": float(exact_decision["fee_hurdle_bps"]),
                "entry_z_score": float(exact_decision["z_score"]),
                "entry_route_sigma_bps": float(exact_decision["route_sigma_bps"]),
                "entry_short_slope_bps_per_min": float(exact_decision["short_slope_bps_per_min"]),
                "entry_price_volatility_bps": float(exact_decision["price_volatility_bps"]),
                "pair_gross_fraction": fraction,
            }
        )
        _enrich_open_margin(position, leverage)
        if (
            float(available.get(position["long_exchange"], 0.0)) + 1e-8 < float(position["long_initial_margin"])
            or float(available.get(position["short_exchange"], 0.0)) + 1e-8 < float(position["short_initial_margin"])
        ):
            row["decision"] = "VENUE_MARGIN"
            continue
        state["open_positions"].append(position)
        state["opened_position_count"] = int(state.get("opened_position_count", 0)) + 1
        open_routes.add(route_key)
        row["decision"] = "OPENED"
        row["proposed_target_notional"] = float(target)
        _append_jsonl(journal_path, {"record_type": "PAPER_POSITION_OPEN", **position})
        _refresh_v16_margin(state, books_by_symbol)

    state["opportunity_radar"] = sorted(
        radar,
        key=lambda row: float(row.get("excess_after_cost_bps", -1e9)),
        reverse=True,
    )[:100]
    _refresh_v16_margin(state, books_by_symbol)

    position_marks: list[dict[str, Any]] = []
    unrealized_net = 0.0
    open_modeled_fees = 0.0
    for position in state.get("open_positions", []):
        venues = books_by_symbol.get(str(position["symbol"]), {})
        long_venue = venues.get(str(position["long_exchange"]))
        short_venue = venues.get(str(position["short_exchange"]))
        if long_venue is None or short_venue is None:
            continue
        mark = mark_open_position(
            position,
            long_book=long_venue.book,
            short_book=short_venue.book,
            marked_at_utc=now_utc,
        )
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
    record_monitor_snapshot(
        history_db,
        now_ms=now_ms,
        account={
            "realized_equity": float(state["equity"]),
            "marked_equity": float(state["equity"]) + unrealized_net,
            "realized_pnl": float(state.get("realized_pnl", 0.0)),
            "unrealized_net_pnl": unrealized_net,
            "gross_exposure": float(state.get("gross_exposure", 0.0)),
            "margin_used": float(state.get("initial_margin_used", 0.0)),
            "modeled_fee_drag": float(state.get("realized_fee_drag", 0.0)) + open_modeled_fees,
        },
        positions=position_marks,
    )
    _assert_v16_invariants(state)


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
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/arbitrage_v16"))
    parser.add_argument("--seed-history-db", type=Path, default=Path("artifacts/arbitrage_v14/history_v15.sqlite"))
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    artifacts = args.artifacts_dir
    state_path = artifacts / "state.json"
    health_path = artifacts / "health.json"
    journal_path = artifacts / "positions.jsonl"
    history_db = artifacts / "history_v16.sqlite"
    clients = make_public_clients(include_extended=True)
    try:
        coverage = linear_usdt_symbol_venues(clients, min_venues=2)
        symbols = _sorted_universe(coverage, args.symbols)
        if not symbols:
            raise RuntimeError("fewer than two venues share active linear USDT perpetual symbols")
        venue_names = sorted({venue for symbol in symbols for venue in coverage[symbol]})
        state = load_state_v16(
            state_path,
            venue_names=venue_names,
            initial_equity=args.initial_equity,
            gross_leverage_cap=args.gross_leverage_cap,
            max_open_positions=args.max_open_positions,
        )
        state["universe_symbols"] = symbols
        state["universe_venues"] = {symbol: list(coverage[symbol]) for symbol in symbols}
        if not history_db.exists() and args.seed_history_db.exists():
            seeded = seed_route_history_from_v15(history_db, args.seed_history_db, now_ms=int(time.time() * 1000))
            state["seeded_route_history_count"] = seeded
        while True:
            now_ms = int(time.time() * 1000)
            now_utc = _utc_now()
            try:
                run_cycle_v16(
                    clients=clients,
                    symbols=symbols,
                    state=state,
                    history_db=history_db,
                    safety_buffer_bps=args.safety_buffer_bps,
                    depth_limit=args.depth,
                    fee_bps=None,
                    max_book_age_ms=args.max_book_age_ms,
                    now_ms=now_ms,
                    now_utc=now_utc,
                    journal_path=journal_path,
                    symbol_venues=coverage,
                )
                write_state(state_path, state)
                _write_health(health_path, status="HEALTHY", schema_version="v16-arbitrage-health-1")
                print(
                    json.dumps(
                        {
                            "equity": state["equity"],
                            "open_positions": len(state["open_positions"]),
                            "tradeable": state["last_cycle_tradeable_count"],
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
                    schema_version="v16-arbitrage-health-1",
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
