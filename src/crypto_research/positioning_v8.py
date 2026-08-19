"""Forward-only public Binance positioning observatory for V8."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

_BASE = "https://fapi.binance.com"
_SCHEMA_VERSION = "v8-positioning-2"
_ENDPOINTS: dict[str, tuple[str, str, str]] = {
    "open_interest": ("/fapi/v1/openInterest", "time", "openInterest"),
    "premium_funding_rate": ("/fapi/v1/premiumIndex", "time", "lastFundingRate"),
    "global_long_short_account_ratio": (
        "/futures/data/globalLongShortAccountRatio",
        "timestamp",
        "longShortRatio",
    ),
    "top_long_short_account_ratio": (
        "/futures/data/topLongShortAccountRatio",
        "timestamp",
        "longShortRatio",
    ),
    "top_long_short_position_ratio": (
        "/futures/data/topLongShortPositionRatio",
        "timestamp",
        "longShortRatio",
    ),
    "taker_buy_sell_ratio": (
        "/futures/data/takerlongshortRatio",
        "timestamp",
        "buySellRatio",
    ),
}
_HISTORY_ENDPOINTS = {name for name in _ENDPOINTS if name not in {"open_interest", "premium_funding_rate"}}


def _iso_from_ms(value: Any) -> str:
    return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc).isoformat()


def normalize_positioning_payload(
    feature_name: str,
    symbol: str,
    payload: dict[str, Any] | list[dict[str, Any]],
    *,
    first_seen_at: datetime,
) -> list[dict[str, Any]]:
    """Normalize public data without pretending historical rows were seen in the past."""
    if feature_name not in _ENDPOINTS:
        raise ValueError(f"unsupported positioning feature: {feature_name}")
    if first_seen_at.tzinfo is None:
        raise ValueError("first_seen_at must be timezone-aware")
    first_seen = first_seen_at.astimezone(timezone.utc)
    _, time_field, value_field = _ENDPOINTS[feature_name]
    records = payload if isinstance(payload, list) else [payload]
    rows: list[dict[str, Any]] = []
    for record in records:
        if time_field not in record or value_field not in record:
            raise ValueError(f"payload missing {time_field} or {value_field}")
        event_time = _iso_from_ms(record[time_field])
        raw = json.dumps(record, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256(
            f"{feature_name}|{symbol}|{event_time}|{raw}".encode("utf-8")
        ).hexdigest()
        rows.append(
            {
                "event_time": event_time,
                "published_at": event_time,
                "first_seen_at": first_seen.isoformat(),
                "available_at": first_seen.isoformat(),
                "decision_time": first_seen.isoformat(),
                "source": "binance_public_usdm",
                "source_id": f"{feature_name}:{symbol}:{record[time_field]}",
                "symbol": symbol,
                "feature_name": feature_name,
                "raw_value": raw,
                "derived_value": float(record[value_field]),
                "data_version": _SCHEMA_VERSION,
                "checksum": content_hash,
                "causal_status": "FORWARD_ONLY",
            }
        )
    return rows


def _public_json(path: str, params: dict[str, Any]) -> Any:
    url = f"{_BASE}{path}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "InvestMent-V8-public-research/1.0"})
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_positioning_snapshot(symbol: str, *, first_seen_at: datetime | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature_name, (path, _, _) in _ENDPOINTS.items():
        params: dict[str, Any] = {"symbol": symbol}
        if feature_name in _HISTORY_ENDPOINTS:
            params.update({"period": "1h", "limit": 1})
        payload = _public_json(path, params)
        first_seen = first_seen_at or datetime.now(timezone.utc)
        rows.extend(
            normalize_positioning_payload(
                feature_name,
                symbol,
                payload,
                first_seen_at=first_seen,
            )
        )
    return rows


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def _write_chunk(output_dir: Path, rows: list[dict[str, Any]], captured_at: datetime) -> Path | None:
    if not rows:
        return None
    frame = pd.DataFrame(rows).drop_duplicates("checksum").sort_values(["symbol", "feature_name"])
    digest = hashlib.sha256("".join(sorted(frame["checksum"])).encode("utf-8")).hexdigest()[:16]
    partition = output_dir / f"date={captured_at.date().isoformat()}"
    partition.mkdir(parents=True, exist_ok=True)
    stamp = captured_at.strftime("%Y%m%dT%H%M%S%fZ")
    target = partition / f"positioning_{stamp}_{digest}.parquet"
    tmp = target.with_suffix(".parquet.tmp")
    frame.to_parquet(tmp, index=False, compression="zstd", engine="pyarrow")
    tmp.replace(target)
    target.with_suffix(target.suffix + ".sha256").write_text(
        hashlib.sha256(target.read_bytes()).hexdigest() + "\n",
        encoding="utf-8",
    )
    return target


def record_public_positioning(
    symbols: list[str],
    output_dir: Path,
    *,
    iterations: int | None = None,
    interval_seconds: float = 3600.0,
) -> None:
    if not symbols:
        raise ValueError("at least one symbol is required")
    if iterations is not None and iterations <= 0:
        raise ValueError("iterations must be positive when provided")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / "recorder_state.json"
    health_path = output_dir / "recorder_health.json"
    coverage_path = output_dir / "coverage_report.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    completed = 0
    errors = 0
    stored = 0

    while iterations is None or completed < iterations:
        captured = datetime.now(timezone.utc)
        fresh_rows: list[dict[str, Any]] = []
        available_symbols: set[str] = set()
        for symbol in symbols:
            try:
                rows = fetch_positioning_snapshot(symbol)
                available_symbols.add(symbol)
                for row in rows:
                    key = f"{row['symbol']}|{row['feature_name']}"
                    if state.get(key) == row["checksum"]:
                        continue
                    fresh_rows.append(row)
                    state[key] = row["checksum"]
            except (OSError, ValueError, json.JSONDecodeError):
                errors += 1
        chunk = _write_chunk(output_dir, fresh_rows, captured)
        if chunk is not None:
            stored += len(fresh_rows)
            _atomic_json(state_path, state)
        completed += 1
        _atomic_json(
            coverage_path,
            {
                "symbols_expected": symbols,
                "symbols_available": sorted(available_symbols),
                "feature_families": sorted(_ENDPOINTS),
                "latest_cycle_at": captured.isoformat(),
                "rows_written_total": stored,
                "error_count": errors,
                "causal_availability": "FORWARD_ONLY_FIRST_SEEN",
                "historical_backfill": "DATA_LIMITATION",
                "schema_version": _SCHEMA_VERSION,
            },
        )
        _atomic_json(
            health_path,
            {
                "pid": os.getpid(),
                "status": "RUNNING" if iterations is None or completed < iterations else "COMPLETED",
                "cycles_completed": completed,
                "rows_written_total": stored,
                "error_count": errors,
                "last_health_at": datetime.now(timezone.utc).isoformat(),
                "research_only": True,
            },
        )
        if iterations is None or completed < iterations:
            time.sleep(interval_seconds)
