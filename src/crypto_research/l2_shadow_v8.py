"""Public USD-M order-book recorder for V8 forward research only."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ccxt
import pandas as pd

_SCHEMA_VERSION = "v8-l2-snapshot-1"
_FLUSH_ROWS = 60


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("captured_at must be timezone-aware")
    return value.astimezone(timezone.utc)


def _clean_levels(levels: Any, *, reverse: bool) -> list[tuple[float, float]]:
    if not isinstance(levels, list):
        raise ValueError("order book levels must be lists")
    cleaned: list[tuple[float, float]] = []
    for level in levels:
        if not isinstance(level, (list, tuple)) or len(level) < 2:
            raise ValueError("order book level must contain price and quantity")
        price, quantity = float(level[0]), float(level[1])
        if price <= 0.0 or quantity < 0.0:
            raise ValueError("order book price must be positive and quantity non-negative")
        if quantity > 0.0:
            cleaned.append((price, quantity))
    return sorted(cleaned, key=lambda item: item[0], reverse=reverse)


def _notional_depth(levels: list[tuple[float, float]], count: int) -> float:
    return float(sum(price * quantity for price, quantity in levels[:count]))


def snapshot_from_order_book(symbol: str, book: dict[str, Any], captured_at: datetime) -> dict[str, Any]:
    """Normalize one public order-book snapshot into causal microstructure fields."""
    captured = _utc(captured_at)
    bids = _clean_levels(book.get("bids", []), reverse=True)
    asks = _clean_levels(book.get("asks", []), reverse=False)
    if not bids or not asks:
        raise ValueError("order book must contain non-empty bids and asks")

    best_bid, bid_qty = bids[0]
    best_ask, ask_qty = asks[0]
    if best_bid >= best_ask:
        raise ValueError("crossed order book snapshot")

    mid = (best_bid + best_ask) / 2.0
    top_qty = bid_qty + ask_qty
    exchange_ms = book.get("timestamp")
    event_time = (
        datetime.fromtimestamp(float(exchange_ms) / 1000.0, tz=timezone.utc).isoformat()
        if exchange_ms is not None
        else captured.isoformat()
    )
    row: dict[str, Any] = {
        "event_time": event_time,
        "available_at": captured.isoformat(),
        "captured_at": captured.isoformat(),
        "source": "binance_public_usdm_order_book",
        "source_id": str(book.get("nonce")) if book.get("nonce") is not None else None,
        "symbol": symbol,
        "update_id": book.get("nonce"),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "bid_qty": bid_qty,
        "ask_qty": ask_qty,
        "mid_price": mid,
        "spread_bps": (best_ask - best_bid) / mid * 10_000.0,
        "microprice": (best_ask * bid_qty + best_bid * ask_qty) / top_qty,
        "top_of_book_imbalance": (bid_qty - ask_qty) / top_qty,
        "depth_5_bid": _notional_depth(bids, 5),
        "depth_5_ask": _notional_depth(asks, 5),
        "depth_10_bid": _notional_depth(bids, 10),
        "depth_10_ask": _notional_depth(asks, 10),
        "depth_20_bid": _notional_depth(bids, 20),
        "depth_20_ask": _notional_depth(asks, 20),
        "data_version": _SCHEMA_VERSION,
    }
    canonical = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
    row["checksum"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return row


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, indent=2, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def _append_wal(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _wal_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _flush_wal(path: Path, destination: Path) -> int:
    rows = _wal_rows(path)
    if not rows:
        return 0
    unique = {str(row["checksum"]): row for row in rows}
    frame = pd.DataFrame(unique.values()).sort_values("captured_at")
    digest = hashlib.sha256("".join(sorted(unique)).encode("utf-8")).hexdigest()[:16]
    start = str(frame["captured_at"].iloc[0]).replace(":", "").replace("+", "_")
    end = str(frame["captured_at"].iloc[-1]).replace(":", "").replace("+", "_")
    target = destination / f"l2_{start}_{end}_{digest}.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        tmp = target.with_suffix(".parquet.tmp")
        frame.to_parquet(tmp, index=False, compression="zstd", engine="pyarrow")
        tmp.replace(target)
        checksum = hashlib.sha256(target.read_bytes()).hexdigest()
        target.with_suffix(target.suffix + ".sha256").write_text(checksum + "\n", encoding="utf-8")
    path.unlink(missing_ok=True)
    return len(unique)


def record_public_depth(
    symbols: list[str],
    output_dir: Path,
    *,
    limit: int = 20,
    iterations: int | None = None,
    interval_seconds: float = 5.0,
) -> None:
    """Record public depth snapshots; this function performs no account operations."""
    if not symbols:
        raise ValueError("at least one symbol is required")
    if limit not in {5, 10, 20}:
        raise ValueError("limit must be one of 5, 10, or 20")
    if iterations is not None and iterations <= 0:
        raise ValueError("iterations must be positive when provided")
    if interval_seconds < 0.0:
        raise ValueError("interval_seconds must be non-negative")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / "recorder_state.json"
    health_path = output_dir / "recorder_health.json"
    state: dict[str, Any] = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    exchange = ccxt.binanceusdm({"enableRateLimit": True})
    completed = 0
    errors = 0
    stored = 0
    buffers: dict[str, int] = {symbol: 0 for symbol in symbols}

    try:
        while iterations is None or completed < iterations:
            cycle_started = datetime.now(timezone.utc)
            for symbol in symbols:
                try:
                    book = exchange.fetch_order_book(symbol, limit=limit)
                    captured = datetime.now(timezone.utc)
                    row = snapshot_from_order_book(symbol, book, captured)
                    if state.get(symbol) == row["checksum"]:
                        continue
                    day = captured.date().isoformat()
                    partition = output_dir / f"date={day}" / f"symbol={_safe_symbol(symbol)}"
                    wal = partition / ".pending.jsonl"
                    _append_wal(wal, row)
                    state[symbol] = row["checksum"]
                    _atomic_json(state_path, state)
                    buffers[symbol] = len(_wal_rows(wal))
                    stored += 1
                    if buffers[symbol] >= _FLUSH_ROWS:
                        _flush_wal(wal, partition)
                        buffers[symbol] = 0
                except (ccxt.NetworkError, ccxt.ExchangeError, ValueError, OSError):
                    errors += 1
            completed += 1
            _atomic_json(
                health_path,
                {
                    "pid": os.getpid(),
                    "status": "RUNNING" if iterations is None or completed < iterations else "COMPLETING",
                    "symbols_expected": symbols,
                    "cycles_completed": completed,
                    "records_appended": stored,
                    "error_count": errors,
                    "last_cycle_started_at": cycle_started.isoformat(),
                    "last_health_at": datetime.now(timezone.utc).isoformat(),
                    "schema_version": _SCHEMA_VERSION,
                    "research_only": True,
                },
            )
            if iterations is None or completed < iterations:
                time.sleep(interval_seconds)
    finally:
        flushed = 0
        for symbol in symbols:
            safe = _safe_symbol(symbol)
            for wal in output_dir.glob(f"date=*/symbol={safe}/.pending.jsonl"):
                flushed += _flush_wal(wal, wal.parent)
        close = getattr(exchange, "close", None)
        if callable(close):
            close()
        _atomic_json(
            health_path,
            {
                "pid": os.getpid(),
                "status": "STOPPED" if iterations is None else "COMPLETED",
                "symbols_expected": symbols,
                "cycles_completed": completed,
                "records_appended": stored,
                "records_flushed_on_exit": flushed,
                "error_count": errors,
                "last_health_at": datetime.now(timezone.utc).isoformat(),
                "schema_version": _SCHEMA_VERSION,
                "research_only": True,
            },
        )
