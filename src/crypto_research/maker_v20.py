"""Execution-aware maker admission for V20 paper research."""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any

_PRIOR_STRENGTH = 12.0
_MIN_GLOBAL_FILLS = 20
_MIN_GLOBAL_REJECTS = 10


def _connect(db_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS maker_execution_stats_v20 (
            venue TEXT NOT NULL,
            side TEXT NOT NULL,
            fill_count INTEGER NOT NULL DEFAULT 0,
            accept_count INTEGER NOT NULL DEFAULT 0,
            reject_count INTEGER NOT NULL DEFAULT 0,
            reject_net_bps_sum REAL NOT NULL DEFAULT 0.0,
            reject_net_bps_sq_sum REAL NOT NULL DEFAULT 0.0,
            PRIMARY KEY (venue, side)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS maker_execution_seed_v20 (
            source_path TEXT PRIMARY KEY,
            seeded_event_count INTEGER NOT NULL
        )
        """
    )
    return connection


def _validated_side(side: str) -> str:
    normalized = str(side).upper()
    if normalized not in {"LONG", "SHORT"}:
        raise ValueError("side must be LONG or SHORT")
    return normalized


def _record_outcome(
    connection: sqlite3.Connection,
    *,
    venue: str,
    side: str,
    accepted: bool,
    reject_net_bps: float | None,
) -> None:
    venue = str(venue).strip().lower()
    side = _validated_side(side)
    if not venue:
        raise ValueError("venue must be non-empty")
    reject = 0.0
    if not accepted:
        if reject_net_bps is None or not math.isfinite(float(reject_net_bps)):
            raise ValueError("rejected outcome requires finite reject_net_bps")
        reject = min(0.0, float(reject_net_bps))
    connection.execute(
        """
        INSERT INTO maker_execution_stats_v20 (
            venue, side, fill_count, accept_count, reject_count,
            reject_net_bps_sum, reject_net_bps_sq_sum
        ) VALUES (?, ?, 1, ?, ?, ?, ?)
        ON CONFLICT(venue, side) DO UPDATE SET
            fill_count = fill_count + 1,
            accept_count = accept_count + excluded.accept_count,
            reject_count = reject_count + excluded.reject_count,
            reject_net_bps_sum = reject_net_bps_sum + excluded.reject_net_bps_sum,
            reject_net_bps_sq_sum = reject_net_bps_sq_sum + excluded.reject_net_bps_sq_sum
        """,
        (
            venue,
            side,
            int(bool(accepted)),
            int(not accepted),
            reject,
            reject * reject,
        ),
    )


def record_v20_execution_outcome(
    db_path: str | Path,
    *,
    venue: str,
    side: str,
    accepted: bool,
    reject_net_bps: float | None = None,
) -> None:
    """Record one causal maker-fill terminal outcome without touching equity."""

    with _connect(db_path) as connection:
        _record_outcome(
            connection,
            venue=venue,
            side=side,
            accepted=accepted,
            reject_net_bps=reject_net_bps,
        )


def _target_notional(pending: dict[str, Any] | None, terminal: dict[str, Any]) -> float | None:
    if pending is not None:
        side = str(terminal.get("filled_side") or "").upper()
        key = "long_target_notional" if side == "LONG" else "short_target_notional" if side == "SHORT" else None
        if key is not None:
            value = float(pending.get(key, 0.0) or 0.0)
            if math.isfinite(value) and value > 0.0:
                return value
        values = [
            float(pending.get("long_target_notional", 0.0) or 0.0),
            float(pending.get("short_target_notional", 0.0) or 0.0),
        ]
        positive = [value for value in values if math.isfinite(value) and value > 0.0]
        if len(positive) == 1:
            return positive[0]
    quantity = float(terminal.get("quantity", 0.0) or 0.0)
    entry_price = float(terminal.get("entry_price", 0.0) or 0.0)
    notional = quantity * entry_price
    return notional if math.isfinite(notional) and notional > 0.0 else None


def seed_v20_execution_outcomes(db_path: str | Path, journal_path: str | Path) -> int:
    """Seed calibration once from a real paper journal; repeated calls are idempotent."""

    source = str(Path(journal_path).resolve())
    with _connect(db_path) as connection:
        if connection.execute(
            "SELECT 1 FROM maker_execution_seed_v20 WHERE source_path = ?", (source,)
        ).fetchone():
            return 0

        rows = [
            json.loads(line)
            for line in Path(journal_path).read_text().splitlines()
            if line.strip()
        ]
        pending_by_id = {
            str(row["pending_id"]): row
            for row in rows
            if row.get("record_type") == "PAPER_MAKER_ENTRY_PENDING" and row.get("pending_id")
        }
        pending_by_route: dict[str, list[dict[str, Any]]] = {}
        for pending in pending_by_id.values():
            pending_by_route.setdefault(str(pending.get("position_key", "")), []).append(pending)
        for route_rows in pending_by_route.values():
            route_rows.sort(key=lambda row: int(row.get("placed_at_ms", 0)))

        seeded = 0
        for row in rows:
            record_type = row.get("record_type")
            if record_type == "PAPER_ONE_LEG_ABORT":
                pending = pending_by_id.get(str(row.get("pending_id", "")))
                target = _target_notional(pending, row)
                if target is None:
                    continue
                net = float(row.get("realized_net_pnl", 0.0))
                reject_bps = net / target * 10_000.0
                if not math.isfinite(reject_bps):
                    continue
                _record_outcome(
                    connection,
                    venue=str(row.get("venue", "")),
                    side=str(row.get("filled_side", "")),
                    accepted=False,
                    reject_net_bps=reject_bps,
                )
                seeded += 1
            elif record_type == "PAPER_POSITION_OPEN":
                maker_paths: list[tuple[str, str]] = []
                if row.get("long_entry_liquidity") == "MAKER":
                    maker_paths.append((str(row.get("long_exchange", "")), "LONG"))
                if row.get("short_entry_liquidity") == "MAKER":
                    maker_paths.append((str(row.get("short_exchange", "")), "SHORT"))
                for venue, side in maker_paths:
                    if not venue:
                        continue
                    _record_outcome(
                        connection,
                        venue=venue,
                        side=side,
                        accepted=True,
                        reject_net_bps=None,
                    )
                    seeded += 1

        connection.execute(
            "INSERT INTO maker_execution_seed_v20(source_path, seeded_event_count) VALUES (?, ?)",
            (source, seeded),
        )
        return seeded


def _stats(connection: sqlite3.Connection, venue: str | None = None, side: str | None = None) -> tuple[int, int, int, float, float]:
    sql = (
        "SELECT COALESCE(SUM(fill_count),0), COALESCE(SUM(accept_count),0), "
        "COALESCE(SUM(reject_count),0), COALESCE(SUM(reject_net_bps_sum),0.0), "
        "COALESCE(SUM(reject_net_bps_sq_sum),0.0) FROM maker_execution_stats_v20"
    )
    params: tuple[object, ...] = ()
    if venue is not None and side is not None:
        sql += " WHERE venue = ? AND side = ?"
        params = (str(venue).lower(), _validated_side(side))
    row = connection.execute(sql, params).fetchone()
    assert row is not None
    return int(row[0]), int(row[1]), int(row[2]), float(row[3]), float(row[4])


def v20_execution_calibration(
    db_path: str | Path,
    *,
    venue: str,
    side: str,
) -> dict[str, float | int | bool]:
    """Return conservative side/venue calibration with global shrinkage."""

    side = _validated_side(side)
    with _connect(db_path) as connection:
        global_fill, global_accept, global_reject, global_sum, global_sq_sum = _stats(connection)
        local_fill, local_accept, local_reject, local_sum, _ = _stats(connection, venue, side)

    ready = global_fill >= _MIN_GLOBAL_FILLS and global_reject >= _MIN_GLOBAL_REJECTS
    if global_fill <= 0:
        global_q = 0.0
    else:
        global_q = global_accept / global_fill
    shrunk_q = (local_accept + _PRIOR_STRENGTH * global_q) / (local_fill + _PRIOR_STRENGTH)
    effective_n = local_fill + _PRIOR_STRENGTH
    # One-sided 95% Wilson lower bound. It is defined for fractional pseudo-counts,
    # stays in [0,1], and is materially safer than mean-minus-one-SE for sparse data.
    z = 1.6448536269514722
    z2_over_n = z * z / effective_n
    denominator = 1.0 + z2_over_n
    center = (shrunk_q + z * z / (2.0 * effective_n)) / denominator
    margin = z / denominator * math.sqrt(
        max(0.0, shrunk_q * (1.0 - shrunk_q) / effective_n + z * z / (4.0 * effective_n * effective_n))
    )
    conservative_q = max(0.0, min(1.0, center - margin))

    global_reject_mean = global_sum / global_reject if global_reject else -25.0
    local_reject_mean = local_sum / local_reject if local_reject else global_reject_mean
    shrunk_reject_mean = (
        local_sum + _PRIOR_STRENGTH * global_reject_mean
    ) / (local_reject + _PRIOR_STRENGTH)
    conservative_reject = min(global_reject_mean, local_reject_mean, shrunk_reject_mean)
    if not math.isfinite(conservative_reject) or conservative_reject >= 0.0:
        conservative_reject = -25.0

    global_reject_std = 0.0
    if global_reject > 1:
        variance = max(0.0, global_sq_sum / global_reject - global_reject_mean**2)
        global_reject_std = math.sqrt(variance)

    return {
        "ready": ready,
        "global_fill_count": global_fill,
        "global_accept_count": global_accept,
        "global_reject_count": global_reject,
        "local_fill_count": local_fill,
        "local_accept_count": local_accept,
        "local_reject_count": local_reject,
        "global_accept_probability": global_q,
        "shrunk_accept_probability": shrunk_q,
        "conservative_accept_probability": conservative_q,
        "accept_lower_bound_confidence": 0.95,
        "global_reject_net_bps_mean": global_reject_mean,
        "global_reject_net_bps_std": global_reject_std,
        "conservative_reject_net_bps": conservative_reject,
    }


def single_maker_attempt_ev(
    *,
    pair_capture_bps: float,
    maker_fee_bps: float,
    hedge_taker_fee_bps: float,
    expected_exit_fee_bps: float,
    expected_exit_price_improvement_bps: float,
    maker_quote_improvement_bps: float,
    adverse_selection_bps: float,
    safety_buffer_bps: float,
    expected_funding_cost_bps: float,
    fill_probability: float,
    minimum_attempt_ev_bps: float,
    calibration: dict[str, Any],
) -> dict[str, float | bool | str]:
    """Value one passive-maker attempt by all terminal account outcomes."""

    values = (
        pair_capture_bps, maker_fee_bps, hedge_taker_fee_bps, expected_exit_fee_bps,
        expected_exit_price_improvement_bps, maker_quote_improvement_bps,
        adverse_selection_bps, safety_buffer_bps, expected_funding_cost_bps,
        fill_probability, minimum_attempt_ev_bps,
    )
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("attempt EV inputs must be finite")
    if any(float(value) < 0.0 for value in values[1:]):
        raise ValueError("fees, improvements, risks, probabilities, funding, and minimums must be non-negative")
    if not 0.0 <= float(fill_probability) <= 1.0:
        raise ValueError("fill_probability must be in [0, 1]")

    q_accept = float(calibration.get("conservative_accept_probability", 0.0))
    reject_net = float(calibration.get("conservative_reject_net_bps", -25.0))
    if not math.isfinite(q_accept) or not 0.0 <= q_accept <= 1.0:
        raise ValueError("calibration accept probability must be in [0, 1]")
    if not math.isfinite(reject_net) or reject_net > 0.0:
        raise ValueError("calibration reject net bps must be finite and non-positive")

    pair_value = (
        float(pair_capture_bps) + float(maker_quote_improvement_bps)
        + float(expected_exit_price_improvement_bps) - float(maker_fee_bps)
        - float(hedge_taker_fee_bps) - float(expected_exit_fee_bps)
        - float(adverse_selection_bps) - float(safety_buffer_bps)
        - float(expected_funding_cost_bps)
    )
    conditional_fill_value = q_accept * pair_value + (1.0 - q_accept) * reject_net
    attempt_ev = float(fill_probability) * conditional_fill_value
    minimum_attempt = float(minimum_attempt_ev_bps)
    ready = bool(calibration.get("ready", False))
    tradeable = ready and pair_value > 0.0 and attempt_ev >= minimum_attempt
    if not ready:
        decision = "EXECUTION_CALIBRATION_WARMUP"
    elif tradeable:
        decision = "EXECUTION_AWARE_EV_ACCEPTED"
    else:
        decision = "EXECUTION_AWARE_EV_BELOW_MIN"

    return {
        "conditional_pair_value_bps": pair_value,
        "conditional_fill_value_bps": conditional_fill_value,
        "expected_attempt_ev_bps": attempt_ev,
        "expected_value_bps": attempt_ev,
        "minimum_required_attempt_ev_bps": minimum_attempt,
        "minimum_required_ev_bps": minimum_attempt,
        "expected_funding_cost_bps": float(expected_funding_cost_bps),
        "fill_probability": float(fill_probability),
        "post_fill_accept_probability": q_accept,
        "reject_net_bps": reject_net,
        "tradeable": tradeable,
        "decision": decision,
    }


def select_v20_profile(decision: dict[str, Any]) -> dict[str, float]:
    """Scale paper leverage only when corrected execution quality supports it."""

    expected_attempt_ev = float(decision["expected_attempt_ev_bps"])
    minimum = float(decision["minimum_required_ev_bps"])
    accept_probability = float(decision["post_fill_accept_probability"])
    pair_value = float(decision["conditional_pair_value_bps"])
    sigma = float(decision["route_sigma_bps"])
    volatility = float(decision["price_volatility_bps"])
    values = (
        expected_attempt_ev,
        minimum,
        accept_probability,
        pair_value,
        sigma,
        volatility,
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("V20 profile inputs must be finite")
    if not 0.0 <= accept_probability <= 1.0:
        raise ValueError("post-fill accept probability must be in [0, 1]")

    leverage = 20.0
    quality_margin = expected_attempt_ev - minimum
    # ponytail: three discrete paper-leverage buckets deliberately avoid fitting a
    # continuous sizing curve to a tiny V19 sample; upgrade after enough V20
    # terminal outcomes exist for out-of-sample calibration.
    if (
        quality_margin >= 1.0
        and accept_probability >= 0.55
        and pair_value >= 12.0
        and sigma <= 6.0
        and volatility <= 25.0
    ):
        leverage = 30.0
    if (
        quality_margin >= 2.0
        and accept_probability >= 0.70
        and pair_value >= 20.0
        and sigma <= 5.0
        and volatility <= 15.0
    ):
        leverage = 40.0

    pair_margin_fraction = 0.10
    return {
        "leverage": leverage,
        "pair_margin_fraction": pair_margin_fraction,
        "pair_gross_fraction": leverage * pair_margin_fraction,
    }
