"""Credential-free V12 cross-exchange paper arbitrage runner."""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ccxt

from crypto_research.arbitrage_v12 import ArbitrageOpportunity, VenueBook, best_opportunity

DEFAULT_FEE_BPS = {
    # Configurable conservative taker assumptions for paper scanning.
    "binance": 5.0,
    "okx": 5.0,
    "mexc": 8.0,
}
PREFERRED_BASES = (
    "BTC",
    "ETH",
    "SOL",
    "XRP",
    "DOGE",
    "BNB",
    "ADA",
    "AVAX",
    "LINK",
    "LTC",
    "BCH",
    "DOT",
    "SUI",
    "TRX",
    "XLM",
    "NEAR",
    "AAVE",
    "UNI",
    "ETC",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_state(initial_equity: float = 20.0) -> dict[str, Any]:
    if initial_equity <= 0.0:
        raise ValueError("initial_equity must be positive")
    return {
        "schema_version": "v12-arbitrage-paper-2",
        "initial_equity": float(initial_equity),
        "equity": float(initial_equity),
        "scan_count": 0,
        "accepted_opportunity_count": 0,
        "best_net_edge_bps_seen": None,
        "last_opportunity": None,
    }


def load_state(path: str | Path, initial_equity: float = 20.0) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return _default_state(initial_equity)
    with path.open(encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("schema_version") != "v12-arbitrage-paper-2":
        raise ValueError("unsupported arbitrage paper state schema")
    if float(state.get("equity", 0.0)) <= 0.0:
        raise ValueError("paper equity must remain positive")
    return state


def write_state(path: str | Path, state: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def _write_health(path: Path, *, status: str, error: str | None = None) -> None:
    write_state(
        path,
        {
            "schema_version": "v12-arbitrage-health-1",
            "status": status,
            "updated_at_utc": _utc_now(),
            "error": error,
        },
    )


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def make_public_clients() -> dict[str, Any]:
    """Create unauthenticated public market-data clients only."""
    common = {"enableRateLimit": True}
    return {
        "binance": ccxt.binanceusdm(common.copy()),
        "okx": ccxt.okx({**common, "options": {"defaultType": "swap"}}),
        "mexc": ccxt.mexc({**common, "options": {"defaultType": "swap"}}),
    }


def _eligible_linear_usdt_swap(market: dict[str, Any]) -> bool:
    return (
        market.get("swap") is True
        and market.get("linear") is True
        and market.get("quote") == "USDT"
        and market.get("settle") == "USDT"
        and market.get("active") is not False
    )


def common_linear_usdt_symbols(clients: dict[str, Any], limit: int = 20) -> list[str]:
    if not clients:
        return []
    if limit <= 0:
        raise ValueError("limit must be positive")

    venue_symbols: list[set[str]] = []
    for client in clients.values():
        try:
            markets = client.load_markets()
        except Exception:
            continue
        venue_symbols.append(
            {
                str(market["symbol"])
                for market in markets.values()
                if _eligible_linear_usdt_swap(market)
            }
        )
    if len(venue_symbols) < 2:
        return []
    common = set.intersection(*venue_symbols)

    preferred_rank = {base: rank for rank, base in enumerate(PREFERRED_BASES)}

    def sort_key(symbol: str) -> tuple[int, str]:
        base = symbol.split("/", 1)[0]
        return preferred_rank.get(base, len(preferred_rank)), symbol

    return sorted(common, key=sort_key)[:limit]


def run_scan(
    clients: dict[str, Any],
    symbols: list[str],
    *,
    equity: float,
    target_fraction: float,
    min_net_edge_bps: float,
    safety_buffer_bps: float,
    depth_limit: int,
    fee_bps: dict[str, float] | None = None,
) -> list[ArbitrageOpportunity]:
    """Fetch public books and return one best paper opportunity per symbol."""
    if equity <= 0.0:
        raise ValueError("equity must be positive")
    if not 0.0 < target_fraction <= 0.5:
        raise ValueError("target_fraction must be in (0, 0.5]")
    if depth_limit <= 0:
        raise ValueError("depth_limit must be positive")

    fees = DEFAULT_FEE_BPS if fee_bps is None else fee_bps
    missing_fees = set(clients) - set(fees)
    if missing_fees:
        raise ValueError(f"missing fee assumptions for venues: {sorted(missing_fees)}")

    target_notional = equity * target_fraction
    opportunities: list[ArbitrageOpportunity] = []
    for symbol in symbols:
        venues: list[VenueBook] = []
        for name, client in clients.items():
            try:
                book = client.fetch_order_book(symbol, limit=depth_limit)
            except Exception:
                continue
            venues.append(
                VenueBook(
                    name=name,
                    book={"bids": book.get("bids", []), "asks": book.get("asks", [])},
                    fee_bps=float(fees[name]),
                )
            )
        if len(venues) < 2:
            continue
        opportunity = best_opportunity(
            symbol,
            venues,
            target_notional=target_notional,
            min_net_edge_bps=min_net_edge_bps,
            safety_buffer_bps=safety_buffer_bps,
        )
        if opportunity is not None:
            opportunities.append(opportunity)
    return opportunities


def _record_scan(
    state: dict[str, Any],
    opportunities: list[ArbitrageOpportunity],
    journal_path: Path,
) -> None:
    state["scan_count"] = int(state.get("scan_count", 0)) + 1
    if not opportunities:
        return

    best = max(opportunities, key=lambda item: item.net_edge_bps)
    estimated_value = best.target_notional * best.net_edge_bps / 10_000.0
    state["accepted_opportunity_count"] = int(state.get("accepted_opportunity_count", 0)) + 1
    previous_best = state.get("best_net_edge_bps_seen")
    state["best_net_edge_bps_seen"] = max(
        best.net_edge_bps,
        float(previous_best) if previous_best is not None else best.net_edge_bps,
    )
    state["last_opportunity"] = {**asdict(best), "observed_at_utc": _utc_now()}

    # ponytail: this is opportunity-value accounting, not realized PnL. Upgrade to a
    # persistent open/close convergence lifecycle before allowing equity to change.
    _append_jsonl(
        journal_path,
        {
            "record_type": "PAPER_OPPORTUNITY",
            "observed_at_utc": _utc_now(),
            "estimated_edge_value": estimated_value,
            **asdict(best),
        },
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-equity", type=float, default=20.0)
    parser.add_argument("--target-fraction", type=float, default=0.25)
    parser.add_argument("--symbols", type=int, default=20)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--depth", type=int, default=20)
    parser.add_argument("--min-net-edge-bps", type=float, default=5.0)
    parser.add_argument("--safety-buffer-bps", type=float, default=5.0)
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/arbitrage_v12"))
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.interval <= 0.0:
        raise ValueError("interval must be positive")

    artifacts = args.artifacts_dir
    state_path = artifacts / "state.json"
    health_path = artifacts / "health.json"
    journal_path = artifacts / "opportunities.jsonl"
    state = load_state(state_path, initial_equity=args.initial_equity)
    clients = make_public_clients()

    try:
        symbols = common_linear_usdt_symbols(clients, limit=args.symbols)
        if not symbols:
            raise RuntimeError("fewer than two venues share active linear USDT perpetual symbols")

        while True:
            try:
                # ponytail: sequential REST snapshots are not synchronized. Upgrade to
                # exchange WebSocket books before any real execution experiment.
                opportunities = run_scan(
                    clients,
                    symbols,
                    equity=float(state["equity"]),
                    target_fraction=args.target_fraction,
                    min_net_edge_bps=args.min_net_edge_bps,
                    safety_buffer_bps=args.safety_buffer_bps,
                    depth_limit=args.depth,
                )
                _record_scan(state, opportunities, journal_path)
                write_state(state_path, state)
                _write_health(health_path, status="HEALTHY")
                best = max(opportunities, key=lambda item: item.net_edge_bps, default=None)
                print(
                    json.dumps(
                        {
                            "time": _utc_now(),
                            "equity": state["equity"],
                            "symbols": len(symbols),
                            "opportunities": len(opportunities),
                            "best": asdict(best) if best is not None else None,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
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
