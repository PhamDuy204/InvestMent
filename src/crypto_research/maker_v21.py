"""Cohort-aware execution calibration for V21 paper arbitrage."""

from __future__ import annotations

import math
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from crypto_research.maker_v20 import single_maker_attempt_ev

_PRIOR_STRENGTH = 6.0
_MIN_BUCKET_FILLS = 10
_ACCEPT_LOWER_BOUND_CONFIDENCE = 0.90
_WILSON_Z_90_ONE_SIDED = 1.2815515655446004


def capture_bucket_v21(capture_bps: float) -> str:
    value = float(capture_bps)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError("capture_bps must be finite and non-negative")
    if value < 5.0:
        return "0_5"
    if value < 10.0:
        return "5_10"
    if value < 20.0:
        return "10_20"
    if value < 30.0:
        return "20_30"
    if value < 40.0:
        return "30_40"
    return "40_PLUS"


def _validated_side(side: str) -> str:
    value = str(side).upper()
    if value not in {"LONG", "SHORT"}:
        raise ValueError("side must be LONG or SHORT")
    return value


def _connect(db_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=30.0)
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def _connect_readonly(db_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"file:{Path(db_path)}?mode=ro", uri=True, timeout=30.0
    )
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute("PRAGMA query_only=ON")
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS maker_execution_events_v21 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venue TEXT NOT NULL,
            side TEXT NOT NULL,
            capture_bucket TEXT NOT NULL,
            placement_capture_bps REAL NOT NULL,
            post_fill_ev_bps REAL,
            accepted INTEGER NOT NULL,
            reject_net_bps REAL,
            observed_at_ms INTEGER
        )
        """
    )
    connection.execute(
        """
        UPDATE maker_execution_events_v21
        SET capture_bucket = CASE
            WHEN placement_capture_bps < 30.0 THEN '20_30'
            WHEN placement_capture_bps < 40.0 THEN '30_40'
            ELSE '40_PLUS'
        END
        WHERE capture_bucket = '20_PLUS'
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_maker_execution_events_v21_cohort "
        "ON maker_execution_events_v21(capture_bucket, venue, side)"
    )


def ensure_v21_execution_schema(db_path: str | Path) -> None:
    """Create/migrate V21 execution tables outside the calibration read path."""
    with closing(_connect(db_path)) as connection, connection:
        _ensure_schema(connection)


def record_v21_execution_outcome(
    db_path: str | Path,
    *,
    venue: str,
    side: str,
    placement_capture_bps: float,
    post_fill_ev_bps: float | None,
    accepted: bool,
    reject_net_bps: float | None = None,
    observed_at_ms: int | None = None,
) -> None:
    """Persist one causal paper maker-fill outcome with its placement cohort."""

    venue = str(venue).strip().lower()
    side = _validated_side(side)
    capture = float(placement_capture_bps)
    post_fill_ev = None if post_fill_ev_bps is None else float(post_fill_ev_bps)
    if not venue:
        raise ValueError("venue must be non-empty")
    if post_fill_ev is None:
        if accepted:
            raise ValueError("accepted outcome requires finite post_fill_ev_bps")
    elif not math.isfinite(post_fill_ev):
        raise ValueError("post_fill_ev_bps must be finite when present")
    bucket = capture_bucket_v21(capture)
    reject: float | None = None
    if not accepted:
        if reject_net_bps is None or not math.isfinite(float(reject_net_bps)):
            raise ValueError("rejected outcome requires finite reject_net_bps")
        reject = float(reject_net_bps)
    with closing(_connect(db_path)) as connection, connection:
        _ensure_schema(connection)
        connection.execute(
            """
            INSERT INTO maker_execution_events_v21(
                venue, side, capture_bucket, placement_capture_bps,
                post_fill_ev_bps, accepted, reject_net_bps, observed_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                venue,
                side,
                bucket,
                capture,
                post_fill_ev,
                int(bool(accepted)),
                reject,
                None if observed_at_ms is None else int(observed_at_ms),
            ),
        )


def _stats(
    connection: sqlite3.Connection,
    *,
    bucket: str,
    venue: str | None = None,
    side: str | None = None,
) -> tuple[int, int, int, float]:
    sql = (
        "SELECT COUNT(*), COALESCE(SUM(accepted),0), "
        "COALESCE(SUM(CASE WHEN accepted=0 THEN 1 ELSE 0 END),0), "
        "COALESCE(SUM(CASE WHEN accepted=0 THEN MIN(reject_net_bps, 0.0) ELSE 0.0 END),0.0) "
        "FROM maker_execution_events_v21 WHERE capture_bucket=?"
    )
    params: list[object] = [bucket]
    if venue is not None and side is not None:
        sql += " AND venue=? AND side=?"
        params.extend((str(venue).lower(), _validated_side(side)))
    row = connection.execute(sql, tuple(params)).fetchone()
    assert row is not None
    return int(row[0]), int(row[1]), int(row[2]), float(row[3])


def _all_reject_mean(connection: sqlite3.Connection) -> float:
    row = connection.execute(
        "SELECT AVG(MIN(reject_net_bps, 0.0)) FROM maker_execution_events_v21 WHERE accepted=0"
    ).fetchone()
    value = None if row is None else row[0]
    if value is None or not math.isfinite(float(value)) or float(value) >= 0.0:
        return -25.0
    return float(value)


def _wilson_lower_bound(probability: float, effective_n: float) -> float:
    if effective_n <= 0.0:
        return 0.0
    z = _WILSON_Z_90_ONE_SIDED
    z2_over_n = z * z / effective_n
    denominator = 1.0 + z2_over_n
    center = (probability + z * z / (2.0 * effective_n)) / denominator
    margin = z / denominator * math.sqrt(
        max(
            0.0,
            probability * (1.0 - probability) / effective_n
            + z * z / (4.0 * effective_n * effective_n),
        )
    )
    return max(0.0, min(1.0, center - margin))


def v21_execution_calibration(
    db_path: str | Path,
    *,
    venue: str,
    side: str,
    placement_capture_bps: float,
) -> dict[str, float | int | bool | str]:
    """Estimate post-fill acceptance only from the matching pre-fill capture cohort."""

    bucket = capture_bucket_v21(placement_capture_bps)
    side = _validated_side(side)
    path = Path(db_path)
    global_fill = global_accept = global_reject = 0
    local_fill = local_accept = local_reject = 0
    global_reject_sum = local_reject_sum = 0.0
    fallback_reject_mean = -25.0
    if path.exists():
        try:
            with closing(_connect_readonly(path)) as connection:
                table_exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='maker_execution_events_v21'"
                ).fetchone() is not None
                if table_exists:
                    global_fill, global_accept, global_reject, global_reject_sum = _stats(
                        connection, bucket=bucket
                    )
                    local_fill, local_accept, local_reject, local_reject_sum = _stats(
                        connection, bucket=bucket, venue=venue, side=side
                    )
                    fallback_reject_mean = _all_reject_mean(connection)
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise
            # A transient writer/checkpoint lock must reject this cycle, not kill the runner.
            # Zero observations below keep admission fail-closed until the next cycle.

    global_q = global_accept / global_fill if global_fill else 0.0
    effective_n = local_fill + _PRIOR_STRENGTH
    estimated_q = (
        local_accept + _PRIOR_STRENGTH * global_q
    ) / effective_n
    conservative_q = _wilson_lower_bound(estimated_q, effective_n)

    global_reject_mean = (
        global_reject_sum / global_reject if global_reject else fallback_reject_mean
    )
    local_reject_mean = (
        local_reject_sum / local_reject if local_reject else global_reject_mean
    )
    conservative_reject = min(
        fallback_reject_mean,
        global_reject_mean,
        local_reject_mean,
    )
    if not math.isfinite(conservative_reject) or conservative_reject >= 0.0:
        conservative_reject = -25.0

    return {
        "ready": global_fill >= _MIN_BUCKET_FILLS,
        "capture_bucket": bucket,
        "global_fill_count": global_fill,
        "global_accept_count": global_accept,
        "global_reject_count": global_reject,
        "local_fill_count": local_fill,
        "local_accept_count": local_accept,
        "local_reject_count": local_reject,
        "global_accept_probability": global_q,
        "estimated_accept_probability": estimated_q,
        "shrunk_accept_probability": estimated_q,
        "conservative_accept_probability": conservative_q,
        "accept_lower_bound_confidence": _ACCEPT_LOWER_BOUND_CONFIDENCE,
        "conservative_reject_net_bps": conservative_reject,
    }


def v21_single_maker_attempt_ev(
    *,
    calibration: dict[str, Any],
    **kwargs: Any,
) -> dict[str, float | bool | str]:
    """Apply V20 terminal EV math with V21's 90% confidence lower bound."""

    result = single_maker_attempt_ev(calibration=calibration, **kwargs)
    estimated = float(calibration.get("estimated_accept_probability", 0.0))
    if not math.isfinite(estimated) or not 0.0 <= estimated <= 1.0:
        raise ValueError("estimated accept probability must be in [0, 1]")
    ready = bool(calibration.get("ready", False))
    tradeable = ready and bool(result["tradeable"])
    if not ready:
        decision = "V21_EXECUTION_CALIBRATION_WARMUP"
    elif tradeable:
        decision = "V21_RISK_ADJUSTED_EV_ACCEPTED"
    else:
        decision = "V21_RISK_ADJUSTED_EV_BELOW_MIN"
    return {
        **result,
        "estimated_accept_probability": estimated,
        "accept_lower_bound_confidence": float(
            calibration.get("accept_lower_bound_confidence", _ACCEPT_LOWER_BOUND_CONFIDENCE)
        ),
        "tradeable": tradeable,
        "decision": decision,
    }


def v21_exit_decision(
    position: dict[str, Any],
    *,
    held_seconds: float,
    current_spread_bps: float,
    close_now_net_pnl: float,
    spread_slope_bps_per_min: float | None,
) -> str | None:
    """Route-relative exit tuned for V21's less conservative admission policy."""

    baseline = float(position["entry_baseline_bps"])
    entry_excess = max(0.0, float(position["entry_excess_spread_bps"]))
    sigma = max(0.5, float(position["entry_route_sigma_bps"]))
    slope = None if spread_slope_bps_per_min is None else float(spread_slope_bps_per_min)

    if held_seconds >= 30 * 60:
        return "V21_MAX_HOLD"
    route_target = baseline + max(1.0, entry_excess * 0.40)
    if close_now_net_pnl > 0.0 and current_spread_bps <= route_target:
        return "ROUTE_TARGET"
    if close_now_net_pnl > 0.0 and held_seconds >= 2 * 60 and slope is not None and slope >= 0.0:
        return "PROFIT_PROTECT"
    divergence_level = baseline + entry_excess + max(5.0, sigma)
    if held_seconds >= 3 * 60 and close_now_net_pnl < 0.0 and current_spread_bps >= divergence_level:
        return "DIVERGENCE_STOP"
    if held_seconds >= 15 * 60 and (slope is None or slope > -0.10):
        return "V21_ADAPTIVE_TIMEOUT"
    return None
