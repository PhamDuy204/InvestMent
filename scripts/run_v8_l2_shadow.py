"""Run the public-data-only V8 L2 forward recorder."""

from __future__ import annotations

import argparse
from pathlib import Path

from crypto_research.l2_shadow_v8 import record_public_depth


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=["BTC/USDT:USDT", "ETH/USDT:USDT"])
    parser.add_argument("--output-dir", type=Path, default=Path("data_v8/public_l2"))
    parser.add_argument("--limit", type=int, choices=(5, 10, 20), default=20)
    parser.add_argument("--iterations", type=int)
    parser.add_argument("--interval-seconds", type=float, default=5.0)
    args = parser.parse_args()
    record_public_depth(
        args.symbols,
        args.output_dir,
        limit=args.limit,
        iterations=args.iterations,
        interval_seconds=args.interval_seconds,
    )


if __name__ == "__main__":
    main()
