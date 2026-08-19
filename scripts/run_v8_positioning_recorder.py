"""Run the forward-only public Binance positioning recorder."""

from __future__ import annotations

import argparse
from pathlib import Path

from crypto_research.positioning_v8 import record_public_positioning


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data_v8/public_positioning"))
    parser.add_argument("--iterations", type=int)
    parser.add_argument("--interval-seconds", type=float, default=3600.0)
    args = parser.parse_args()
    record_public_positioning(
        args.symbols,
        args.output_dir,
        iterations=args.iterations,
        interval_seconds=args.interval_seconds,
    )


if __name__ == "__main__":
    main()
