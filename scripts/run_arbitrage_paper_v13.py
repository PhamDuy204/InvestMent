"""Credential-free V13 paper arbitrage lifecycle runner."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from crypto_research.arbitrage_v12 import VenueBook, best_opportunity
from crypto_research.execution_v8 import ExecutionSimulatorV8

if __package__:
    from .run_arbitrage_paper_v12 import (
        DEFAULT_FEE_BPS,
        _append_jsonl,
        common_linear_usdt_symbols,
        make_public_clients,
        write_state,
    )
else:
    from run_arbitrage_paper_v12 import (
        DEFAULT_FEE_BPS,
        _append_jsonl,
        common_linear_usdt_symbols,
        make_public_clients,
        write_state,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_health(
    path: Path,
    *,
    status: str,
    error: str | None = None,
    schema_version: str = "v13-arbitrage-health-1",
) -> None:
    write_state(
        path,
        {
            "schema_version": schema_version,
            "status": status,
            "updated_at_utc": _utc_now(),
            "error": error,
        },
    )


def _default_state(initial_equity: float = 20.0) -> dict[str, Any]:
    if initial_equity <= 0.0:
        raise ValueError("initial_equity must be positive")
    return {
        "schema_version": "v13-arbitrage-paper-1",
        "initial_equity": float(initial_equity),
        "equity": float(initial_equity),
        "scan_count": 0,
        "opened_position_count": 0,
        "closed_position_count": 0,
        "realized_pnl": 0.0,
        "open_positions": [],
        "last_close": None,
    }


def load_state(path: str | Path, initial_equity: float = 20.0) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return _default_state(initial_equity)
    with path.open(encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("schema_version") != "v13-arbitrage-paper-1":
        raise ValueError("unsupported arbitrage paper state schema")
    if not isinstance(state.get("open_positions"), list):
        raise ValueError("open_positions must be a list")
    return state


def _position_key(symbol: str, long_exchange: str, short_exchange: str) -> str:
    return f"{symbol}|{long_exchange}|{short_exchange}"


def _fetch_venue_books(
    clients: dict[str, Any],
    symbol: str,
    *,
    depth_limit: int,
    fees: dict[str, float],
    max_book_age_ms: int,
    now_ms: int,
) -> dict[str, VenueBook]:
    venues: dict[str, VenueBook] = {}
    for name, client in clients.items():
        try:
            raw = client.fetch_order_book(symbol, limit=depth_limit)
        except Exception:
            continue
        timestamp = raw.get("timestamp")
        if timestamp is not None and now_ms - int(timestamp) > max_book_age_ms:
            continue
        venues[name] = VenueBook(
            name=name,
            book={
                "bids": raw.get("bids", []),
                "asks": raw.get("asks", []),
                "timestamp": timestamp,
                "received_at_ms": raw.get("received_at_ms", now_ms),
                "received_mono_ms": raw.get("received_mono_ms"),
            },
            fee_bps=float(fees[name]),
        )
    return venues


def _open_position(opportunity, venues: dict[str, VenueBook], *, now_ms: int, now_utc: str):
    long_venue = venues[opportunity.buy_venue]
    short_venue = venues[opportunity.sell_venue]
    long_sim = ExecutionSimulatorV8(fee_bps=long_venue.fee_bps)
    short_sim = ExecutionSimulatorV8(fee_bps=short_venue.fee_bps)

    long_probe = long_sim.simulate_market_order(
        target_notional=opportunity.target_notional,
        side="buy",
        book=long_venue.book,
    )
    short_probe = short_sim.simulate_market_order(
        target_notional=opportunity.target_notional,
        side="sell",
        book=short_venue.book,
    )
    quantity = min(long_probe.filled_base_quantity, short_probe.filled_base_quantity)
    long_fill = long_sim.simulate_market_order_by_quantity(
        target_base_quantity=quantity,
        side="buy",
        book=long_venue.book,
    )
    short_fill = short_sim.simulate_market_order_by_quantity(
        target_base_quantity=quantity,
        side="sell",
        book=short_venue.book,
    )
    if long_fill.unmodeled_tail or short_fill.unmodeled_tail:
        return None

    entry_fees = (
        long_fill.filled_notional * long_venue.fee_bps
        + short_fill.filled_notional * short_venue.fee_bps
    ) / 10_000.0
    return {
        "position_id": uuid4().hex,
        "position_key": _position_key(
            opportunity.symbol,
            opportunity.buy_venue,
            opportunity.sell_venue,
        ),
        "symbol": opportunity.symbol,
        "long_exchange": opportunity.buy_venue,
        "short_exchange": opportunity.sell_venue,
        "quantity": float(quantity),
        "opened_at": now_utc,
        "opened_at_ms": int(now_ms),
        "long_entry_vwap": float(long_fill.vwap),
        "short_entry_vwap": float(short_fill.vwap),
        "long_entry_notional": float(long_fill.filled_notional),
        "short_entry_notional": float(short_fill.filled_notional),
        "long_fee_bps": float(long_venue.fee_bps),
        "short_fee_bps": float(short_venue.fee_bps),
        "entry_fees": float(entry_fees),
        "initial_net_edge_bps": float(opportunity.net_edge_bps),
        "status": "OPEN",
    }



def _try_close_position(
    position: dict[str, Any],
    venues: dict[str, VenueBook],
    *,
    now_ms: int,
    now_utc: str,
    exit_threshold_bps: float,
    max_holding_seconds: float,
) -> dict[str, Any] | None:
    long_venue = venues.get(position["long_exchange"])
    short_venue = venues.get(position["short_exchange"])
    if long_venue is None or short_venue is None:
        return None

    quantity = float(position["quantity"])
    try:
        long_fill = ExecutionSimulatorV8(
            fee_bps=long_venue.fee_bps
        ).simulate_market_order_by_quantity(
            target_base_quantity=quantity,
            side="sell",
            book=long_venue.book,
        )
        short_fill = ExecutionSimulatorV8(
            fee_bps=short_venue.fee_bps
        ).simulate_market_order_by_quantity(
            target_base_quantity=quantity,
            side="buy",
            book=short_venue.book,
        )
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if long_fill.unmodeled_tail or short_fill.unmodeled_tail:
        return None

    midpoint = (long_fill.vwap + short_fill.vwap) / 2.0
    remaining_spread_bps = (short_fill.vwap - long_fill.vwap) / midpoint * 10_000.0
    held_seconds = max(0.0, (int(now_ms) - int(position["opened_at_ms"])) / 1000.0)
    timed_out = held_seconds >= max_holding_seconds
    if remaining_spread_bps > exit_threshold_bps and not timed_out:
        return None

    exit_fees = (
        long_fill.filled_notional * long_venue.fee_bps
        + short_fill.filled_notional * short_venue.fee_bps
    ) / 10_000.0
    gross_pnl = quantity * (
        (long_fill.vwap - float(position["long_entry_vwap"]))
        + (float(position["short_entry_vwap"]) - short_fill.vwap)
    )
    realized_net_pnl = gross_pnl - float(position["entry_fees"]) - exit_fees
    return {
        "record_type": "PAPER_POSITION_CLOSE",
        "position_id": position["position_id"],
        "position_key": position["position_key"],
        "symbol": position["symbol"],
        "long_exchange": position["long_exchange"],
        "short_exchange": position["short_exchange"],
        "quantity": quantity,
        "closed_at": now_utc,
        "held_seconds": held_seconds,
        "close_reason": "MAX_HOLD" if timed_out else "CONVERGENCE",
        "remaining_spread_bps": float(remaining_spread_bps),
        "long_exit_vwap": float(long_fill.vwap),
        "short_exit_vwap": float(short_fill.vwap),
        "exit_fees": float(exit_fees),
        "gross_pnl": float(gross_pnl),
        "realized_net_pnl": float(realized_net_pnl),
    }

def run_cycle(
    *,
    clients: dict[str, Any],
    symbols: list[str],
    state: dict[str, Any],
    target_fraction: float,
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
) -> None:
    if not 0.0 < target_fraction <= 0.5:
        raise ValueError("target_fraction must be in (0, 0.5]")
    if max_book_age_ms <= 0:
        raise ValueError("max_book_age_ms must be positive")
    if exit_threshold_bps < 0.0:
        raise ValueError("exit_threshold_bps must be non-negative")
    if max_holding_seconds <= 0.0:
        raise ValueError("max_holding_seconds must be positive")

    fees = DEFAULT_FEE_BPS if fee_bps is None else fee_bps
    missing_fees = set(clients) - set(fees)
    if missing_fees:
        raise ValueError(f"missing fee assumptions for venues: {sorted(missing_fees)}")

    state["scan_count"] = int(state.get("scan_count", 0)) + 1
    open_keys = {position["position_key"] for position in state.get("open_positions", [])}
    closed_keys_this_cycle: set[str] = set()
    target_notional = float(state["equity"]) * target_fraction

    for symbol in symbols:
        venues = _fetch_venue_books(
            clients,
            symbol,
            depth_limit=depth_limit,
            fees=fees,
            max_book_age_ms=max_book_age_ms,
            now_ms=now_ms,
        )
        if len(venues) < 2:
            continue

        remaining_positions = []
        for position in state.get("open_positions", []):
            if position["symbol"] != symbol:
                remaining_positions.append(position)
                continue
            close = _try_close_position(
                position,
                venues,
                now_ms=now_ms,
                now_utc=now_utc,
                exit_threshold_bps=exit_threshold_bps,
                max_holding_seconds=max_holding_seconds,
            )
            if close is None:
                remaining_positions.append(position)
                continue
            state["closed_position_count"] = int(state.get("closed_position_count", 0)) + 1
            state["realized_pnl"] = float(state.get("realized_pnl", 0.0)) + close["realized_net_pnl"]
            state["equity"] = float(state["equity"]) + close["realized_net_pnl"]
            state["last_close"] = close
            closed_keys_this_cycle.add(position["position_key"])
            _append_jsonl(journal_path, close)
        state["open_positions"] = remaining_positions
        open_keys = {position["position_key"] for position in state["open_positions"]}

        opportunity = best_opportunity(
            symbol,
            list(venues.values()),
            target_notional=target_notional,
            min_net_edge_bps=min_net_edge_bps,
            safety_buffer_bps=safety_buffer_bps,
        )
        if opportunity is None:
            continue
        key = _position_key(symbol, opportunity.buy_venue, opportunity.sell_venue)
        if key in open_keys or key in closed_keys_this_cycle:
            continue
        position = _open_position(opportunity, venues, now_ms=now_ms, now_utc=now_utc)
        if position is None:
            continue
        state["open_positions"].append(position)
        state["opened_position_count"] = int(state.get("opened_position_count", 0)) + 1
        open_keys.add(key)
        _append_jsonl(journal_path, {"record_type": "PAPER_POSITION_OPEN", **position})


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-equity", type=float, default=20.0)
    parser.add_argument("--target-fraction", type=float, default=0.25)
    parser.add_argument("--symbols", type=int, default=20)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--depth", type=int, default=20)
    parser.add_argument("--min-net-edge-bps", type=float, default=5.0)
    parser.add_argument("--safety-buffer-bps", type=float, default=5.0)
    parser.add_argument("--exit-threshold-bps", type=float, default=5.0)
    parser.add_argument("--max-holding-seconds", type=float, default=3600.0)
    parser.add_argument("--max-book-age-ms", type=int, default=10_000)
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/arbitrage_v13"))
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    artifacts = args.artifacts_dir
    state_path = artifacts / "state.json"
    state = load_state(state_path, initial_equity=args.initial_equity)
    health_path = artifacts / "health.json"
    journal_path = artifacts / "positions.jsonl"
    clients = make_public_clients()

    try:
        symbols = common_linear_usdt_symbols(clients, limit=args.symbols)
        if not symbols:
            raise RuntimeError("fewer than two venues share active linear USDT perpetual symbols")
        while True:
            now_ms = int(time.time() * 1000)
            try:
                run_cycle(
                    clients=clients,
                    symbols=symbols,
                    state=state,
                    target_fraction=args.target_fraction,
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
                )
                write_state(state_path, state)
                _write_health(health_path, status="HEALTHY")
                print(json.dumps({"equity": state["equity"], "open_positions": len(state["open_positions"])}, sort_keys=True), flush=True)
            except Exception as exc:
                _write_health(health_path, status="DEGRADED", error=type(exc).__name__)
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
