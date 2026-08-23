"""Deterministic engineering smoke for the V9 simulated-only paper runtime."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import ccxt

from crypto_research.governance_v9 import verify_candidate_freeze
from crypto_research.paper_v9 import PaperRuntimeV9, capture_public_order_book


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", type=Path, default=Path("runtime_v9/paper"))
    parser.add_argument("--candidate-freeze", type=Path)
    parser.add_argument("--a1", action="store_true")
    parser.add_argument("--public-market-data", action="store_true")
    parser.add_argument("--symbol", default="BTC/USDT:USDT")
    parser.add_argument("--book-limit", type=int, default=20)
    args = parser.parse_args()
    if args.a1 and (args.candidate_freeze is None or not verify_candidate_freeze(args.candidate_freeze)):
        raise SystemExit("A1 requires a valid immutable candidate freeze")
    if args.a1:
        raise SystemExit("A1 requires candidate-specific frozen decision wiring; engineering smoke cannot start A1")

    runtime = PaperRuntimeV9(
        journal_path=args.runtime_dir / "journal.jsonl",
        state_path=args.runtime_dir / "state.json",
        health_path=args.runtime_dir / "health.json",
        initial_equity=1_000.0,
        fee_bps=4.0,
        max_staleness_seconds=30.0,
    )
    if args.public_market_data:
        exchange = ccxt.binanceusdm({"enableRateLimit": True})
        snapshot = capture_public_order_book(exchange, args.symbol, limit=args.book_limit)
        now = snapshot["available_at"]
        book = snapshot["book"]
    else:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        book = {"bids": [[99.0, 2.0]], "asks": [[100.0, 2.0]]}

    row = runtime.process_decision(
        decision_time=now,
        market_available_at=now,
        candidate_hash="engineering-smoke-v9",
        candidate_frozen=False,
        freeze_timestamp=None,
        signal=0.25,
        target_exposure=0.10,
        target_notional=100.0,
        side="buy",
        book=book,
    )
    print(json.dumps({"decision_id": row["decision_id"], "evidence_class": row["evidence_class"]}, sort_keys=True))


if __name__ == "__main__":
    main()
