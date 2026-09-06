"""Funding-aware economics for V20 public-data paper arbitrage."""

from __future__ import annotations

import math
from typing import Any

_EIGHT_HOURS_SECONDS = 8.0 * 60.0 * 60.0
_CONTINUOUS_FUNDING_VENUES = frozenset({"deribit"})


def funding_carry_observations(
    snapshots: dict[str, Any], *, now_ms: int, taker_fee_bps: dict[str, float],
) -> dict[str, Any]:
    """Rank next-settlement quotes; never create fills, EV, or account PnL."""
    from itertools import permutations

    grouped: dict[str, dict[str, dict[str, float]]] = {}
    sampled_at_ms = 0
    for key, raw in (snapshots.items() if isinstance(snapshots, dict) else ()):
        if not isinstance(key, str) or "|" not in key or not isinstance(raw, dict):
            continue
        venue, symbol = key.split("|", 1)
        if venue not in taker_fee_bps or venue in _CONTINUOUS_FUNDING_VENUES or not symbol.endswith("/USDT:USDT"):
            continue
        rate = _finite_rate(raw)
        try:
            sampled = int(raw.get("sampled_at_ms", 0))
            mark = float(raw.get("markPrice"))
            fee = float(taker_fee_bps[venue])
        except (ValueError, TypeError, OverflowError):
            continue
        stamp = _future_funding_timestamp(raw, now_ms=now_ms)
        if rate is None or not all(math.isfinite(v) for v in (mark, fee)) or mark <= 0 or fee < 0:
            continue
        if sampled <= 0 or not 0 <= now_ms - sampled <= 180_000 or stamp is None:
            continue
        grouped.setdefault(symbol, {})[venue] = {
            "rate": rate, "mark": mark, "fee": fee, "stamp": stamp,
        }
        sampled_at_ms = max(sampled_at_ms, sampled)

    rows: list[dict[str, Any]] = []
    asynchronous = 0
    # ponytail: seven-venue per-symbol scan; asynchronous settlement needs its own
    # event model before it can join this same-settlement observation sleeve.
    for symbol, venues in grouped.items():
        for long_venue, short_venue in permutations(venues, 2):
            long, short = venues[long_venue], venues[short_venue]
            if long["stamp"] != short["stamp"]:
                asynchronous += 1
                continue
            reference = long["mark"] / 2 + short["mark"] / 2
            if reference <= 0:
                continue
            # Equal base quantity on both legs, not equal USDT notionals.
            long_weight, short_weight = long["mark"] / reference, short["mark"] / reference
            funding_bps = (short["rate"] * short_weight - long["rate"] * long_weight) * 10_000
            fees_bps = 2 * (long["fee"] * long_weight + short["fee"] * short_weight)
            if not all(math.isfinite(value) for value in (funding_bps, fees_bps, funding_bps - fees_bps)):
                continue
            rows.append({
                "symbol": symbol, "long_venue": long_venue, "short_venue": short_venue,
                "settlement_at_ms": int(long["stamp"]), "quoted_funding_bps": funding_bps,
                "round_trip_fee_bps": fees_bps, "after_fee_quote_bps": funding_bps - fees_bps,
            })
    rows.sort(key=lambda row: (-row["after_fee_quote_bps"], row["symbol"], row["long_venue"], row["short_venue"]))
    return {
        "schema_version": "v22-carry-observations-1", "mode": "OBSERVATION_ONLY",
        "sampled_at_ms": sampled_at_ms, "fresh_quote_count": sum(map(len, grouped.values())),
        "asynchronous_pair_count": asynchronous,
        "positive_after_fee_quote_count": sum(row["after_fee_quote_bps"] > 0 for row in rows),
        "rows": rows[:6],
    }


def record_carry_observation(db_path: Any, observation: dict[str, Any]) -> None:
    """Keep quote research separate from V21 account and fill calibration tables."""
    import json
    import sqlite3
    from contextlib import closing

    if observation.get("schema_version") != "v22-carry-observations-1" or not observation.get("sampled_at_ms"):
        return
    with closing(sqlite3.connect(db_path, timeout=2)) as connection, connection:
        connection.execute("CREATE TABLE IF NOT EXISTS carry_observations_v22 (sampled_at_ms INTEGER PRIMARY KEY, observation_json TEXT NOT NULL)")
        connection.execute(
            "INSERT OR IGNORE INTO carry_observations_v22 VALUES (?, ?)",
            (observation["sampled_at_ms"], json.dumps(observation, allow_nan=False, separators=(",", ":"))),
        )


def _finite_rate(snapshot: dict[str, Any] | None) -> float | None:
    if not isinstance(snapshot, dict):
        return None
    try:
        rate = float(snapshot.get("fundingRate"))
    except (TypeError, ValueError):
        return None
    return rate if math.isfinite(rate) else None


def _future_funding_timestamp(snapshot: dict[str, Any], *, now_ms: int) -> int | None:
    for key in ("fundingTimestamp", "nextFundingTimestamp"):
        value = snapshot.get(key)
        if value is None:
            continue
        try:
            stamp = int(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if stamp > int(now_ms):
            return stamp
    return None


def accrue_discrete_funding_cashflow(
    *,
    side: str,
    notional: float,
    funding_rate: float,
) -> float:
    """Return one linear-perpetual funding settlement cashflow."""

    normalized_side = str(side).upper()
    if normalized_side not in {"LONG", "SHORT"}:
        raise ValueError("side must be LONG or SHORT")
    values = (float(notional), float(funding_rate))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("funding inputs must be finite")
    if notional < 0.0:
        raise ValueError("notional must be non-negative")
    payment = float(notional) * float(funding_rate)
    return -payment if normalized_side == "LONG" else payment


def accrue_deribit_funding_cashflow(
    *,
    side: str,
    notional: float,
    funding_rate: float,
    elapsed_seconds: float,
) -> float:
    """Return paper cashflow for Deribit's continuously accrued 8h funding quote."""

    normalized_side = str(side).upper()
    if normalized_side not in {"LONG", "SHORT"}:
        raise ValueError("side must be LONG or SHORT")
    values = (float(notional), float(funding_rate), float(elapsed_seconds))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("funding inputs must be finite")
    if notional < 0.0 or elapsed_seconds < 0.0:
        raise ValueError("notional and elapsed_seconds must be non-negative")
    payment = float(notional) * float(funding_rate) * float(elapsed_seconds) / _EIGHT_HOURS_SECONDS
    return -payment if normalized_side == "LONG" else payment


def pair_funding_admission(
    *,
    long_venue: str,
    short_venue: str,
    long_snapshot: dict[str, Any] | None,
    short_snapshot: dict[str, Any] | None,
    now_ms: int,
    max_hold_seconds: float,
    max_snapshot_age_ms: int = 180_000,
    price_discrete_funding: bool = False,
) -> dict[str, Any]:
    """Fail closed on unknown/discrete funding and price continuous Deribit carry."""

    if max_hold_seconds <= 0.0 or not math.isfinite(float(max_hold_seconds)):
        raise ValueError("max_hold_seconds must be finite and positive")
    horizon_ms = int(float(max_hold_seconds) * 1000.0)
    expected_net_cost_bps = 0.0

    for side, venue, snapshot in (
        ("LONG", str(long_venue).lower(), long_snapshot),
        ("SHORT", str(short_venue).lower(), short_snapshot),
    ):
        rate = _finite_rate(snapshot)
        try:
            sampled_at_ms = int((snapshot or {}).get("sampled_at_ms", 0))
        except (TypeError, ValueError):
            sampled_at_ms = 0
        age_ms = int(now_ms) - sampled_at_ms
        if rate is None or sampled_at_ms <= 0 or age_ms < -5_000 or age_ms > int(max_snapshot_age_ms):
            return {
                "ready": False,
                "blocked": True,
                "reason": "FUNDING_DATA_WARMUP",
                "expected_net_funding_cost_bps": 0.0,
                "expected_funding_cost_bps": 0.0,
            }
        if venue in _CONTINUOUS_FUNDING_VENUES:
            try:
                mark_price = float((snapshot or {}).get("markPrice"))
            except (TypeError, ValueError):
                mark_price = math.nan
            if not math.isfinite(mark_price) or mark_price <= 0.0:
                return {
                    "ready": False,
                    "blocked": True,
                    "reason": "FUNDING_DATA_WARMUP",
                    "expected_net_funding_cost_bps": 0.0,
                    "expected_funding_cost_bps": 0.0,
                }
            signed_cost = rate * float(max_hold_seconds) / _EIGHT_HOURS_SECONDS * 10_000.0
            expected_net_cost_bps += signed_cost if side == "LONG" else -signed_cost
            continue

        assert isinstance(snapshot, dict)
        funding_at = _future_funding_timestamp(snapshot, now_ms=int(now_ms))
        if funding_at is None:
            return {
                "ready": False,
                "blocked": True,
                "reason": "FUNDING_DATA_WARMUP",
                "expected_net_funding_cost_bps": 0.0,
                "expected_funding_cost_bps": 0.0,
            }
        if funding_at <= int(now_ms) + horizon_ms:
            if not price_discrete_funding:
                return {
                    "ready": True,
                    "blocked": True,
                    "reason": "FUNDING_WINDOW_RISK",
                    "expected_net_funding_cost_bps": 0.0,
                    "expected_funding_cost_bps": 0.0,
                }
            expected_net_cost_bps += rate * 10_000.0 if side == "LONG" else -rate * 10_000.0

    # ponytail: funding benefits are never admitted as alpha; only adverse net carry
    # is charged. Upgrade when venue-specific realized funding histories justify it.
    adverse_cost = max(0.0, expected_net_cost_bps)
    return {
        "ready": True,
        "blocked": False,
        "reason": "FUNDING_OK",
        "expected_net_funding_cost_bps": float(expected_net_cost_bps),
        "expected_funding_cost_bps": float(adverse_cost),
    }
