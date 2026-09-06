from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from datetime import datetime
from typing import Any, Callable

from crypto_research.monitoring_v13 import build_monitoring_payload, mark_open_position
from crypto_research.funding_v20 import funding_carry_observations, record_carry_observation
from crypto_research.route_v16 import read_monitor_history

if __package__:
    from .run_arbitrage_paper_v12 import DEFAULT_FEE_BPS, make_public_clients
else:
    from run_arbitrage_paper_v12 import DEFAULT_FEE_BPS, make_public_clients

DEFAULT_ARTIFACTS_DIR = Path("artifacts/arbitrage_v13")
DEFAULT_INTERVAL_SECONDS = 2.0


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def _read_position_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                events.append(value)
    return events


def load_payload(
    artifacts_dir: str | Path,
    *,
    updated_at_utc: str | None = None,
) -> dict[str, Any]:
    artifacts = Path(artifacts_dir)
    state = _read_json(artifacts / "state.json")
    health = _read_json(artifacts / "health.json")
    events = _read_position_events(artifacts / "positions.jsonl")
    shadow = None
    shadow_path = artifacts / "shadow_v15.json"
    if shadow_path.exists():
        try:
            shadow = _read_json(shadow_path)
        except (OSError, ValueError, json.JSONDecodeError):
            shadow = None
    monitor_history = None
    state_schema = state.get("schema_version")
    history_names = {
        "v16-arbitrage-paper-1": "history_v16.sqlite",
        "v17-arbitrage-paper-1": "history_v17.sqlite",
        "v18-arbitrage-paper-1": "history_v18.sqlite",
        "v19-arbitrage-paper-1": "history_v19.sqlite",
        "v20-arbitrage-paper-1": "history_v20.sqlite",
        "v21-arbitrage-paper-1": "history_v21.sqlite",
    }
    if state_schema in history_names:
        history_name = history_names[state_schema]
        try:
            monitor_history = read_monitor_history(artifacts / history_name)
        except (OSError, ValueError):
            monitor_history = {"account_history": [], "position_history": {}}
    payload = build_monitoring_payload(
        state,
        health,
        events,
        shadow_state=shadow,
        monitor_history=monitor_history,
        updated_at_utc=updated_at_utc,
    )
    if state_schema == "v21-arbitrage-paper-1":
        payload["funding_carry_research"] = funding_carry_observations(
            state.get("funding_snapshots", {}),
            now_ms=int(datetime.fromisoformat(payload["updated_at_utc"]).timestamp() * 1000),
            taker_fee_bps=DEFAULT_FEE_BPS,
        )
    return payload


def enrich_payload_with_live_marks(
    payload: dict[str, Any],
    clients: dict[str, Any],
    *,
    depth_limit: int = 20,
    marked_at_utc: str | None = None,
) -> dict[str, Any]:
    equity = float(payload.get("equity") or 0.0)
    for position in payload.get("open_positions") or []:
        if not isinstance(position, dict):
            continue
        long_name = str(position.get("long_exchange") or "")
        short_name = str(position.get("short_exchange") or "")
        symbol = str(position.get("symbol") or "")
        long_client = clients.get(long_name)
        short_client = clients.get(short_name)
        if not symbol or long_client is None or short_client is None:
            position.update({
                "mark_status": "UNAVAILABLE",
                "margin_model": str(position.get("margin_model") or "NOT_MODELED"),
            })
            continue
        try:
            long_raw = long_client.fetch_order_book(symbol, limit=depth_limit)
            short_raw = short_client.fetch_order_book(symbol, limit=depth_limit)
            mark = mark_open_position(
                position,
                long_book={"bids": long_raw.get("bids", []), "asks": long_raw.get("asks", [])},
                short_book={"bids": short_raw.get("bids", []), "asks": short_raw.get("asks", [])},
                marked_at_utc=marked_at_utc,
            )
        except Exception:
            mark = {
                "mark_status": "UNAVAILABLE",
                "margin_model": str(position.get("margin_model") or "NOT_MODELED"),
            }
        position.update(mark)
        entry_gross = position.get("entry_gross_exposure")
        if isinstance(entry_gross, (int, float)) and equity > 0:
            position["exposure_pct_of_equity"] = float(entry_gross) / equity * 100.0
    return payload


def publish_once(
    *,
    artifacts_dir: str | Path,
    ingest_url: str,
    ingest_token: str,
    opener: Callable[..., Any] = urllib.request.urlopen,
    timeout_seconds: float = 10.0,
    clients: dict[str, Any] | None = None,
) -> bool:
    try:
        payload = load_payload(artifacts_dir)
        if clients is not None:
            enrich_payload_with_live_marks(payload, clients)
        if payload.get("funding_carry_research"):
            try:
                record_carry_observation(
                    Path(artifacts_dir) / "carry_observations_v22.sqlite", payload["funding_carry_research"],
                )
            except sqlite3.Error as exc:
                print(f"carry observation persistence: {type(exc).__name__}", file=sys.stderr)
        body = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
        request = urllib.request.Request(
            ingest_url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {ingest_token}",
                "Content-Type": "application/json",
                "User-Agent": "InvestMent-Paper-Monitor/1",
            },
        )
        response = opener(request, timeout=timeout_seconds)
        try:
            status = int(getattr(response, "status", response.getcode()))
            if not 200 <= status < 300:
                raise urllib.error.HTTPError(
                    ingest_url,
                    status,
                    f"ingest returned HTTP {status}",
                    hdrs=None,
                    fp=None,
                )
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
        return True
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
        print(f"monitor publisher: {type(exc).__name__}: {exc}", file=sys.stderr)
        return False


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish sanitized paper telemetry")
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ingest-url", default=None)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.interval <= 0:
        raise SystemExit("--interval must be positive")

    if args.dry_run:
        payload = load_payload(args.artifacts_dir)
        print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
        return 0

    ingest_url = args.ingest_url or os.environ.get("MONITOR_INGEST_URL")
    ingest_token = os.environ.get("MONITOR_INGEST_TOKEN")
    if not ingest_url or not ingest_token:
        raise SystemExit("MONITOR_INGEST_URL and MONITOR_INGEST_TOKEN are required")

    state_schema = _read_json(args.artifacts_dir / "state.json").get("schema_version")
    # V18/V19 persist marks from the engine's causal WebSocket snapshot, avoiding a second market client set.
    causal_schemas = {"v18-arbitrage-paper-1", "v19-arbitrage-paper-1", "v20-arbitrage-paper-1", "v21-arbitrage-paper-1"}
    clients = {} if state_schema in causal_schemas else make_public_clients(include_extended=True)
    mark_clients = clients or None
    try:
        if args.once:
            return 0 if publish_once(
                artifacts_dir=args.artifacts_dir,
                ingest_url=ingest_url,
                ingest_token=ingest_token,
                clients=mark_clients,
            ) else 1

        while True:
            publish_once(
                artifacts_dir=args.artifacts_dir,
                ingest_url=ingest_url,
                ingest_token=ingest_token,
                clients=mark_clients,
            )
            time.sleep(args.interval)
    finally:
        for client in clients.values():
            close = getattr(client, "close", None)
            if callable(close):
                close()


if __name__ == "__main__":
    raise SystemExit(main())
