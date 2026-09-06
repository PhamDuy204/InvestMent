"""Causal route-relative features and entry rules for V16 paper arbitrage."""

from __future__ import annotations

import math
import sqlite3
import statistics
from contextlib import closing
from math import isfinite
from pathlib import Path
from typing import Any

_HISTORY_TABLE = "route_history_v16"


def _connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30.0)
    connection.execute("PRAGMA busy_timeout=30000")
    if connection.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
        connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_HISTORY_TABLE} (
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
    return connection


def _connect_readonly(db_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True, timeout=30.0)
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def record_route_snapshots(db_path: str | Path, now_ms: int, rows: list[dict[str, Any]]) -> int:
    """Persist finite public route observations only."""
    values: list[tuple[int, str, str, str, float, float | None]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = row.get("symbol")
        buy = row.get("buy_venue")
        sell = row.get("sell_venue")
        gross = row.get("gross_edge_bps")
        mid = row.get("reference_mid_price")
        if not all(isinstance(value, str) and value for value in (symbol, buy, sell)):
            continue
        if not isinstance(gross, (int, float)) or not isfinite(float(gross)):
            continue
        mid_value = None
        if isinstance(mid, (int, float)) and isfinite(float(mid)) and float(mid) > 0:
            mid_value = float(mid)
        values.append((int(now_ms), symbol, buy, sell, float(gross), mid_value))
    if not values:
        return 0
    with closing(_connect(db_path)) as connection, connection:
        connection.executemany(
            f"""
            INSERT OR REPLACE INTO {_HISTORY_TABLE}
                (observed_at_ms, symbol, buy_venue, sell_venue, gross_edge_bps, reference_mid_price)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            values,
        )
    return len(values)


def _slope_bps_per_min(samples: list[tuple[int, float]]) -> float:
    if len(samples) < 2:
        return 0.0
    origin = samples[0][0]
    xs = [(timestamp - origin) / 60_000.0 for timestamp, _ in samples]
    ys = [value for _, value in samples]
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    denominator = sum((value - x_mean) ** 2 for value in xs)
    if denominator <= 0.0:
        return 0.0
    return sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True)) / denominator


def _price_volatility_bps(rows: list[tuple[int, float, float | None]]) -> float:
    prices = [float(mid) for _, _, mid in rows if mid is not None and mid > 0]
    if len(prices) < 3:
        return 0.0
    returns = [math.log(current / previous) * 10_000.0 for previous, current in zip(prices, prices[1:])]
    return statistics.pstdev(returns) if len(returns) >= 2 else 0.0


def route_features(
    db_path: str | Path,
    symbol: str,
    buy_venue: str,
    sell_venue: str,
    *,
    now_ms: int,
    baseline_window_ms: int = 60 * 60_000,
    short_window_ms: int = 5 * 60_000,
    medium_window_ms: int = 15 * 60_000,
    min_samples: int = 12,
    min_span_seconds: float = 10 * 60,
) -> dict[str, float | int] | None:
    """Return route-relative features using observations no later than ``now_ms``."""
    path = Path(db_path)
    if not path.exists():
        return None
    lower = int(now_ms) - int(baseline_window_ms)
    with closing(_connect_readonly(path)) as connection:
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (_HISTORY_TABLE,)
        ).fetchone() is None:
            return None
        raw = connection.execute(
            f"""
            SELECT observed_at_ms, gross_edge_bps, reference_mid_price
            FROM {_HISTORY_TABLE}
            WHERE symbol = ? AND buy_venue = ? AND sell_venue = ?
              AND observed_at_ms BETWEEN ? AND ?
            ORDER BY observed_at_ms ASC
            """,
            (symbol, buy_venue, sell_venue, lower, int(now_ms)),
        ).fetchall()
    rows = [(int(ts), float(gross), float(mid) if mid is not None else None) for ts, gross, mid in raw]
    if len(rows) < min_samples:
        return None
    span_seconds = (rows[-1][0] - rows[0][0]) / 1000.0
    if span_seconds < min_span_seconds:
        return None

    gross_values = [gross for _, gross, _ in rows]
    baseline = statistics.median(gross_values)
    mad = statistics.median(abs(value - baseline) for value in gross_values)
    sigma = max(0.5, 1.4826 * mad)

    short_rows = [(ts, gross) for ts, gross, _ in rows if ts >= int(now_ms) - int(short_window_ms)]
    medium_rows = [(ts, gross) for ts, gross, _ in rows if ts >= int(now_ms) - int(medium_window_ms)]
    volatility_rows = [row for row in rows if row[0] >= int(now_ms) - int(medium_window_ms)]
    return {
        "baseline_bps": float(baseline),
        "route_sigma_bps": float(sigma),
        "short_slope_bps_per_min": float(_slope_bps_per_min(short_rows)),
        "medium_slope_bps_per_min": float(_slope_bps_per_min(medium_rows)),
        "price_volatility_bps": float(_price_volatility_bps(volatility_rows)),
        "last_gross_edge_bps": float(rows[-1][1]),
        "sample_count": len(rows),
        "span_seconds": float(span_seconds),
    }


def entry_decision(
    *,
    current_gross_edge_bps: float,
    total_fee_bps: float,
    safety_buffer_bps: float,
    features: dict[str, float | int] | None,
    min_excess_after_cost_bps: float = 0.5,
    min_z_score: float = 1.0,
    turn_slope_bps_per_min: float = -0.05,
) -> dict[str, Any]:
    """Classify one route from structural-basis-adjusted executable edge."""
    if features is None:
        return {"decision": "BASELINE_WARMUP", "tradeable": False}
    baseline = float(features["baseline_bps"])
    sigma = max(0.5, float(features["route_sigma_bps"]))
    short_slope = float(features["short_slope_bps_per_min"])
    excess = float(current_gross_edge_bps) - baseline
    fee_hurdle = float(total_fee_bps) + float(safety_buffer_bps)
    after_cost = excess - fee_hurdle
    z_score = excess / sigma
    result = {
        "baseline_bps": baseline,
        "route_sigma_bps": sigma,
        "excess_spread_bps": excess,
        "fee_hurdle_bps": fee_hurdle,
        "excess_after_cost_bps": after_cost,
        "z_score": z_score,
        "short_slope_bps_per_min": short_slope,
        "medium_slope_bps_per_min": float(features.get("medium_slope_bps_per_min", 0.0)),
        "price_volatility_bps": float(features.get("price_volatility_bps", 0.0)),
        "history_sample_count": int(features.get("sample_count", 0)),
        "history_span_seconds": float(features.get("span_seconds", 0.0)),
        "tradeable": False,
    }
    if after_cost < min_excess_after_cost_bps or z_score < min_z_score:
        result["decision"] = "EXCESS_BELOW_COST"
        return result
    last_gross = features.get("last_gross_edge_bps")
    if (
        short_slope > turn_slope_bps_per_min
        or (isinstance(last_gross, (int, float)) and float(current_gross_edge_bps) > float(last_gross) + 0.5)
    ):
        result["decision"] = "WAITING_FOR_TURN"
        return result
    result["decision"] = "TRADEABLE"
    result["tradeable"] = True
    return result


def dynamic_leverage(
    *,
    excess_after_cost_bps: float,
    z_score: float,
    route_sigma_bps: float,
    price_volatility_bps: float,
) -> float:
    """Choose 1x..3x paper leverage from signal quality and observed volatility."""
    if price_volatility_bps >= 35.0 or route_sigma_bps >= 8.0 or excess_after_cost_bps < 5.0:
        return 1.0
    if excess_after_cost_bps >= 15.0 and z_score >= 2.5 and route_sigma_bps <= 5.0 and price_volatility_bps <= 20.0:
        return 3.0
    return 2.0


def _ensure_monitor_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS account_history_v16 (
            observed_at_ms INTEGER PRIMARY KEY,
            realized_equity REAL NOT NULL,
            marked_equity REAL NOT NULL,
            realized_pnl REAL NOT NULL,
            unrealized_net_pnl REAL NOT NULL,
            gross_exposure REAL NOT NULL,
            margin_used REAL NOT NULL,
            modeled_fee_drag REAL NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS position_history_v16 (
            observed_at_ms INTEGER NOT NULL,
            position_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            spread_bps REAL NOT NULL,
            net_pnl REAL NOT NULL,
            baseline_bps REAL,
            PRIMARY KEY (observed_at_ms, position_id)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_position_history_v16_position_time "
        "ON position_history_v16(position_id, observed_at_ms DESC)"
    )


def record_monitor_snapshot(
    db_path: str | Path,
    *,
    now_ms: int,
    account: dict[str, Any],
    positions: list[dict[str, Any]],
    retention_ms: int = 6 * 60 * 60_000,
) -> None:
    """Persist compact executable account/position marks and prune old samples."""
    if retention_ms <= 0:
        raise ValueError("retention_ms must be positive")
    account_keys = (
        "realized_equity",
        "marked_equity",
        "realized_pnl",
        "unrealized_net_pnl",
        "gross_exposure",
        "margin_used",
        "modeled_fee_drag",
    )
    numeric: dict[str, float] = {}
    for key in account_keys:
        value = account.get(key)
        if not isinstance(value, (int, float)) or not isfinite(float(value)):
            raise ValueError(f"account history field must be finite: {key}")
        numeric[key] = float(value)

    position_rows: list[tuple[int, str, str, float, float, float | None]] = []
    for row in positions:
        if not isinstance(row, dict):
            continue
        position_id = row.get("position_id")
        symbol = row.get("symbol")
        spread = row.get("spread_bps")
        net_pnl = row.get("net_pnl")
        baseline = row.get("baseline_bps")
        if not isinstance(position_id, str) or not position_id or not isinstance(symbol, str) or not symbol:
            continue
        if not isinstance(spread, (int, float)) or not isfinite(float(spread)):
            continue
        if not isinstance(net_pnl, (int, float)) or not isfinite(float(net_pnl)):
            continue
        baseline_value = None
        if isinstance(baseline, (int, float)) and isfinite(float(baseline)):
            baseline_value = float(baseline)
        position_rows.append(
            (int(now_ms), position_id[:128], symbol[:128], float(spread), float(net_pnl), baseline_value)
        )

    lower = int(now_ms) - int(retention_ms)
    with closing(_connect(db_path)) as connection, connection:
        _ensure_monitor_tables(connection)
        connection.execute(
            """
            INSERT OR REPLACE INTO account_history_v16
                (observed_at_ms, realized_equity, marked_equity, realized_pnl,
                 unrealized_net_pnl, gross_exposure, margin_used, modeled_fee_drag)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(now_ms),
                numeric["realized_equity"],
                numeric["marked_equity"],
                numeric["realized_pnl"],
                numeric["unrealized_net_pnl"],
                numeric["gross_exposure"],
                numeric["margin_used"],
                numeric["modeled_fee_drag"],
            ),
        )
        if position_rows:
            connection.executemany(
                """
                INSERT OR REPLACE INTO position_history_v16
                    (observed_at_ms, position_id, symbol, spread_bps, net_pnl, baseline_bps)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                position_rows,
            )
        connection.execute("DELETE FROM account_history_v16 WHERE observed_at_ms < ?", (lower,))
        connection.execute("DELETE FROM position_history_v16 WHERE observed_at_ms < ?", (lower,))
        connection.execute(f"DELETE FROM {_HISTORY_TABLE} WHERE observed_at_ms < ?", (lower,))


def read_monitor_history(
    db_path: str | Path,
    *,
    account_limit: int = 360,
    position_limit: int = 120,
) -> dict[str, Any]:
    """Read bounded V16 monitor history in chronological order."""
    if account_limit <= 0 or position_limit <= 0:
        raise ValueError("history limits must be positive")
    path = Path(db_path)
    if not path.exists():
        return {"account_history": [], "position_history": {}}
    with closing(_connect_readonly(path)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?, ?)",
                ("account_history_v16", "position_history_v16"),
            )
        }
        account_raw = (
            connection.execute(
                """
                SELECT observed_at_ms, realized_equity, marked_equity, realized_pnl,
                       unrealized_net_pnl, gross_exposure, margin_used, modeled_fee_drag
                FROM account_history_v16
                ORDER BY observed_at_ms DESC
                LIMIT ?
                """,
                (int(account_limit),),
            ).fetchall()
            if "account_history_v16" in tables
            else []
        )
        position_raw = (
            connection.execute(
                """
                WITH latest_positions AS (
                    SELECT position_id, MAX(observed_at_ms) AS latest_at
                    FROM position_history_v16
                    GROUP BY position_id
                    ORDER BY latest_at DESC
                    LIMIT 128
                ), ranked AS (
                    SELECT p.observed_at_ms, p.position_id, p.symbol, p.spread_bps, p.net_pnl, p.baseline_bps,
                           ROW_NUMBER() OVER (PARTITION BY p.position_id ORDER BY p.observed_at_ms DESC) AS row_number
                    FROM position_history_v16 AS p
                    JOIN latest_positions AS latest ON latest.position_id = p.position_id
                )
                SELECT observed_at_ms, position_id, symbol, spread_bps, net_pnl, baseline_bps
                FROM ranked
                WHERE row_number <= ?
                ORDER BY observed_at_ms ASC
                """,
                (int(position_limit),),
            ).fetchall()
            if "position_history_v16" in tables
            else []
        )

    account_history = [
        {
            "observed_at_ms": int(row[0]),
            "realized_equity": float(row[1]),
            "marked_equity": float(row[2]),
            "realized_pnl": float(row[3]),
            "unrealized_net_pnl": float(row[4]),
            "gross_exposure": float(row[5]),
            "margin_used": float(row[6]),
            "modeled_fee_drag": float(row[7]),
        }
        for row in reversed(account_raw)
    ]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for observed_at_ms, position_id, symbol, spread_bps, net_pnl, baseline_bps in position_raw:
        grouped.setdefault(str(position_id), []).append(
            {
                "observed_at_ms": int(observed_at_ms),
                "symbol": str(symbol),
                "spread_bps": float(spread_bps),
                "net_pnl": float(net_pnl),
                **({"baseline_bps": float(baseline_bps)} if baseline_bps is not None else {}),
            }
        )
    return {
        "account_history": account_history,
        "position_history": {key: rows[-int(position_limit):] for key, rows in grouped.items()},
    }


def seed_route_history_from_v15(
    target_db: str | Path,
    legacy_db: str | Path,
    *,
    now_ms: int,
    lookback_ms: int = 6 * 60 * 60_000,
) -> int:
    """Copy only causal public route spread observations from the legacy V15 radar DB."""
    source = Path(legacy_db)
    if not source.exists() or lookback_ms <= 0:
        return 0
    lower = int(now_ms) - int(lookback_ms)
    try:
        with closing(sqlite3.connect(source)) as connection:
            rows = connection.execute(
                """
                SELECT observed_at_ms, symbol, buy_venue, sell_venue, gross_edge_bps
                FROM radar_history
                WHERE observed_at_ms BETWEEN ? AND ?
                ORDER BY observed_at_ms ASC
                """,
                (lower, int(now_ms)),
            ).fetchall()
    except sqlite3.Error:
        return 0
    values = [
        (int(ts), str(symbol), str(buy), str(sell), float(gross), None)
        for ts, symbol, buy, sell, gross in rows
        if isinstance(gross, (int, float)) and isfinite(float(gross))
    ]
    if not values:
        return 0
    with closing(_connect(target_db)) as connection, connection:
        before = connection.total_changes
        connection.executemany(
            f"""
            INSERT OR IGNORE INTO {_HISTORY_TABLE}
                (observed_at_ms, symbol, buy_venue, sell_venue, gross_edge_bps, reference_mid_price)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        return connection.total_changes - before
