"""Maker-first execution math and causal fill statistics for V17 paper trading."""

from __future__ import annotations

import math
import sqlite3
import statistics
from contextlib import closing
from pathlib import Path
from typing import Any

from scripts.run_arbitrage_paper_v12 import DEFAULT_FEE_BPS

# Only lower maker rates that were directly verified from public/official fee docs.
# Unknown/unverified maker rates deliberately fall back to the existing taker assumption.
DEFAULT_MAKER_FEE_BPS: dict[str, float] = {
    "binance": 2.0,
    "okx": 2.0,
    "mexc": 6.0,
    "bybit": 2.0,
    "bitget": 2.0,
    "kucoin": 2.0,
    "gate": 2.0,
}

_FILL_TABLE = "maker_fill_stats_v17"
_Z_75_ONE_SIDED = 0.6744897501960817


def _connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_FILL_TABLE} (
            venue TEXT NOT NULL,
            side TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            fills INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (venue, side)
        )
        """
    )
    return connection


def record_fill_outcome(db_path: str | Path, venue: str, side: str, *, filled: bool) -> None:
    if not venue:
        raise ValueError("venue must be non-empty")
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    with closing(_connect(db_path)) as connection, connection:
        connection.execute(
            f"""
            INSERT INTO {_FILL_TABLE} (venue, side, attempts, fills)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(venue, side) DO UPDATE SET
                attempts = attempts + 1,
                fills = fills + excluded.fills
            """,
            (venue, side, int(bool(filled))),
        )


def conservative_fill_probability(db_path: str | Path, venue: str, side: str) -> dict[str, float | int]:
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    with closing(_connect(db_path)) as connection, connection:
        row = connection.execute(
            f"SELECT attempts, fills FROM {_FILL_TABLE} WHERE venue = ? AND side = ?",
            (venue, side),
        ).fetchone()
    attempts = int(row[0]) if row else 0
    fills = int(row[1]) if row else 0
    alpha = fills + 0.5
    beta = attempts - fills + 0.5
    total = alpha + beta
    mean = alpha / total
    variance = alpha * beta / (total * total * (total + 1.0))
    conservative = max(0.05, min(0.95, mean - _Z_75_ONE_SIDED * math.sqrt(variance)))
    return {
        "attempts": attempts,
        "fills": fills,
        "posterior_mean": mean,
        "posterior_variance": variance,
        "conservative_probability": conservative,
    }


def passive_limit_filled(
    side: str,
    limit_price: float,
    later_book: dict[str, Any],
    *,
    placed_at_ms: int | None = None,
    placed_at_mono_ms: int | None = None,
    strict_price_through: bool = False,
    queue_ahead_quantity: float | None = None,
    order_quantity: float | None = None,
    trade_volume_baseline: float | None = None,
) -> bool:
    """Conservative causal fill from an opposite quote received after placement."""
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    if not math.isfinite(limit_price) or limit_price <= 0.0:
        raise ValueError("limit_price must be finite and positive")
    if placed_at_mono_ms is not None:
        stamp = later_book.get("received_mono_ms")
        try:
            if stamp is None or int(stamp) <= int(placed_at_mono_ms):
                return False
        except (TypeError, ValueError):
            return False
    elif placed_at_ms is not None:
        stamp = later_book.get("received_at_ms", later_book.get("timestamp"))
        try:
            if stamp is None or int(stamp) <= int(placed_at_ms):
                return False
        except (TypeError, ValueError):
            return False
    levels = later_book.get("asks" if side == "buy" else "bids")
    if not isinstance(levels, list) or not levels:
        return False
    try:
        best = float(levels[0][0])
    except (TypeError, ValueError, IndexError):
        return False
    if not math.isfinite(best) or best <= 0.0:
        return False
    if side == "buy":
        quote_fill = best < limit_price if strict_price_through else best <= limit_price
    else:
        quote_fill = best > limit_price if strict_price_through else best >= limit_price
    if quote_fill:
        return True

    trade_levels = later_book.get("_public_trade_volume_by_side_price")
    if not isinstance(trade_levels, dict):
        return False
    try:
        queue_ahead = float(queue_ahead_quantity)
        quantity = float(order_quantity)
        baseline = float(trade_volume_baseline)
        taker_side = "sell" if side == "buy" else "buy"
        current = float(trade_levels.get((taker_side, float(limit_price)), baseline))
    except (TypeError, ValueError):
        return False
    if (
        not math.isfinite(queue_ahead) or queue_ahead < 0.0
        or not math.isfinite(quantity) or quantity <= 0.0
        or not math.isfinite(baseline) or baseline < 0.0
        or not math.isfinite(current)
    ):
        return False
    # Risk-averse queue model: cancellations never advance us. Only observed
    # post-placement opposing taker volume can consume queue ahead + our order.
    return current - baseline >= queue_ahead + quantity


def _price_volatility_bps(rows: list[tuple[int, float, float | None]]) -> float:
    prices = [float(mid) for _, _, mid in rows if mid is not None and mid > 0.0]
    if len(prices) < 3:
        return 0.0
    returns = [math.log(current / previous) * 10_000.0 for previous, current in zip(prices, prices[1:])]
    return statistics.pstdev(returns) if len(returns) >= 2 else 0.0


def multi_horizon_route_features(
    db_path: str | Path,
    symbol: str,
    buy_venue: str,
    sell_venue: str,
    *,
    now_ms: int,
    min_samples: int = 12,
    minimum_span_ms: int = 600_000,
    minimum_window_samples: int = 3,
    require_5m_window: bool = True,
) -> dict[str, float | int] | None:
    if int(minimum_span_ms) <= 0:
        raise ValueError("minimum_span_ms must be positive")
    if int(minimum_window_samples) < 1:
        raise ValueError("minimum_window_samples must be positive")
    path = Path(db_path)
    if not path.exists():
        return None
    lower = int(now_ms) - 60 * 60_000
    try:
        with closing(sqlite3.connect(path)) as connection:
            raw = connection.execute(
                """
                SELECT observed_at_ms, gross_edge_bps, reference_mid_price
                FROM route_history_v16
                WHERE symbol = ? AND buy_venue = ? AND sell_venue = ?
                  AND observed_at_ms BETWEEN ? AND ?
                ORDER BY observed_at_ms ASC
                """,
                (symbol, buy_venue, sell_venue, lower, int(now_ms)),
            ).fetchall()
    except sqlite3.Error:
        return None
    rows = [(int(ts), float(gross), float(mid) if mid is not None else None) for ts, gross, mid in raw]
    if len(rows) < min_samples:
        return None
    span_ms = rows[-1][0] - rows[0][0]
    span_seconds = span_ms / 1000.0
    if span_ms < int(minimum_span_ms):
        return None

    def median_since(window_ms: int) -> float | None:
        values = [gross for ts, gross, _ in rows if ts >= int(now_ms) - window_ms]
        return statistics.median(values) if len(values) >= int(minimum_window_samples) else None

    baseline_60 = median_since(60 * 60_000)
    baseline_15 = median_since(15 * 60_000)
    baseline_5 = median_since(5 * 60_000)
    if baseline_60 is None or baseline_15 is None:
        return None
    if baseline_5 is None:
        if require_5m_window:
            return None
        fast_values = [gross for ts, gross, _ in rows if ts >= int(now_ms) - 5 * 60_000]
        baseline_5 = statistics.median(fast_values) if fast_values else baseline_15
    mad = statistics.median(abs(gross - baseline_60) for _, gross, _ in rows)
    sigma = max(0.5, 1.4826 * mad)
    volatility_rows = [row for row in rows if row[0] >= int(now_ms) - 15 * 60_000]
    return {
        "baseline_60m_bps": float(baseline_60),
        "baseline_15m_bps": float(baseline_15),
        "baseline_5m_bps": float(baseline_5),
        "route_sigma_bps": float(sigma),
        "price_volatility_bps": float(_price_volatility_bps(volatility_rows)),
        "sample_count": len(rows),
        "span_seconds": float(span_seconds),
        "last_gross_edge_bps": float(rows[-1][1]),
    }


def maker_attempt_ev(
    *,
    capture_bps: float,
    long_maker_fee_bps: float,
    long_taker_fee_bps: float,
    short_maker_fee_bps: float,
    short_taker_fee_bps: float,
    long_fill_probability: float,
    short_fill_probability: float,
    long_exit_fill_probability: float,
    short_exit_fill_probability: float,
    route_sigma_bps: float,
    price_volatility_bps: float,
    safety_buffer_bps: float,
    long_quote_spread_bps: float = 0.0,
    short_quote_spread_bps: float = 0.0,
) -> dict[str, float | bool]:
    values = [
        capture_bps,
        long_maker_fee_bps,
        long_taker_fee_bps,
        short_maker_fee_bps,
        short_taker_fee_bps,
        route_sigma_bps,
        price_volatility_bps,
        safety_buffer_bps,
        long_quote_spread_bps,
        short_quote_spread_bps,
    ]
    if not all(math.isfinite(float(value)) and float(value) >= 0.0 for value in values):
        raise ValueError("EV inputs must be finite and non-negative")
    probabilities = [
        long_fill_probability,
        short_fill_probability,
        long_exit_fill_probability,
        short_exit_fill_probability,
    ]
    if not all(0.0 <= float(value) <= 1.0 for value in probabilities):
        raise ValueError("fill probabilities must be in [0, 1]")

    p_long = float(long_fill_probability)
    p_short = float(short_fill_probability)
    p_open = 1.0 - (1.0 - p_long) * (1.0 - p_short)
    p_one = p_long * (1.0 - p_short) + (1.0 - p_long) * p_short

    expected_entry_fee = (
        p_long * long_maker_fee_bps
        + (1.0 - p_long) * p_short * long_taker_fee_bps
        + p_short * short_maker_fee_bps
        + (1.0 - p_short) * p_long * short_taker_fee_bps
    )
    expected_exit_fee_conditional = (
        float(long_exit_fill_probability) * long_maker_fee_bps
        + (1.0 - float(long_exit_fill_probability)) * long_taker_fee_bps
        + float(short_exit_fill_probability) * short_maker_fee_bps
        + (1.0 - float(short_exit_fill_probability)) * short_taker_fee_bps
    )
    expected_entry_price_improvement = (
        p_long * long_quote_spread_bps
        + p_short * short_quote_spread_bps
    )
    expected_exit_price_improvement_conditional = (
        float(long_exit_fill_probability) * long_quote_spread_bps
        + float(short_exit_fill_probability) * short_quote_spread_bps
    )
    adverse_selection = max(0.25, 0.10 * route_sigma_bps + 0.05 * price_volatility_bps)
    hedge_risk = max(0.5, 0.25 * route_sigma_bps + 0.10 * price_volatility_bps)
    expected_value = (
        p_open
        * (
            capture_bps
            + expected_exit_price_improvement_conditional
            - expected_exit_fee_conditional
            - safety_buffer_bps
            - adverse_selection
        )
        + expected_entry_price_improvement
        - expected_entry_fee
        - p_one * hedge_risk
    )
    minimum_required = max(0.25, 0.05 * route_sigma_bps + 0.02 * price_volatility_bps)
    return {
        "p_open": p_open,
        "p_one_leg": p_one,
        "expected_entry_fee_bps": expected_entry_fee,
        "expected_exit_fee_bps": expected_exit_fee_conditional,
        "expected_entry_price_improvement_bps": expected_entry_price_improvement,
        "expected_exit_price_improvement_bps": expected_exit_price_improvement_conditional,
        "adverse_selection_bps": adverse_selection,
        "hedge_risk_bps": hedge_risk,
        "expected_value_bps": expected_value,
        "minimum_required_ev_bps": minimum_required,
        "four_taker_hurdle_bps": 2.0 * (long_taker_fee_bps + short_taker_fee_bps) + safety_buffer_bps,
        "maker_round_trip_hurdle_bps": 2.0 * (long_maker_fee_bps + short_maker_fee_bps) + safety_buffer_bps,
        "tradeable": expected_value >= minimum_required,
    }


def seed_route_history_from_v16(
    target_db: str | Path,
    source_db: str | Path,
    *,
    now_ms: int,
    lookback_ms: int = 6 * 60 * 60_000,
) -> int:
    """Copy only public route observations from V16; never copy account/position state."""
    source = Path(source_db)
    if not source.exists() or lookback_ms <= 0:
        return 0
    lower = int(now_ms) - int(lookback_ms)
    try:
        with closing(sqlite3.connect(source)) as connection:
            rows = connection.execute(
                """
                SELECT observed_at_ms, symbol, buy_venue, sell_venue, gross_edge_bps, reference_mid_price
                FROM route_history_v16
                WHERE observed_at_ms BETWEEN ? AND ?
                ORDER BY observed_at_ms ASC
                """,
                (lower, int(now_ms)),
            ).fetchall()
    except sqlite3.Error:
        return 0
    if not rows:
        return 0
    target = Path(target_db)
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(target)) as connection, connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS route_history_v16 (
                observed_at_ms INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                buy_venue TEXT NOT NULL,
                sell_venue TEXT NOT NULL,
                gross_edge_bps REAL NOT NULL,
                reference_mid_price REAL,
                PRIMARY KEY (observed_at_ms, symbol, buy_venue, sell_venue)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_route_history_v16_route_time "
            "ON route_history_v16(symbol, buy_venue, sell_venue, observed_at_ms)"
        )
        before = connection.total_changes
        connection.executemany(
            """
            INSERT OR IGNORE INTO route_history_v16
                (observed_at_ms, symbol, buy_venue, sell_venue, gross_edge_bps, reference_mid_price)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        return connection.total_changes - before
