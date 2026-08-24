# Progress Log

## V14 checkpoint — 2026-08-24 03:51 +07

- Read the complete V13 directory before acting.
- Reverified clean branch `v11-root-cause-paper-readiness`; local and remote started equal at `0f6f28f6821db3f8af4db85187db1f561b35f485`.
- Actual worktrees enumerated; no uncommitted V11 work was overwritten.
- Current recorder snapshot during this run: L2 `RUNNING`, 3,757 cycles, 78,897 records, 0 errors; positioning `RUNNING`, 8 cycles, 1,008 rows, 0 errors.
- Historical H12 panel spans 2025-04-16 through 2026-07-31. Local L2 and positioning start on 2026-08-20, so neither can legally be joined backward into historical folds.
- Positioning source code/coverage explicitly says `FORWARD_ONLY_FIRST_SEEN` and `historical_backfill=DATA_LIMITATION`; historical-fold positioning rescue is rejected unless a separate historical source is proven.
- Local L2 has only two short pre-boundary sessions, insufficient for the existing cross-fold development gate.
- Web/source audit found official Binance Data Vision historical USD-M `bookDepth`. HTTP 200 verified on BTCUSDT for 2025-04-16, 2025-09-20, 2026-02-24 and 2026-07-31, covering representative points in all three fold ranges. Sample schema: `timestamp,percentage,depth,notional` with ±1..±5 buckets.
- Historical `bookTicker` on 2025-04-16 returned HTTP 404, so historical top-of-book data is not assumed.
- Literature supports order-book imbalance/depth as a plausible independent microstructure family, but Binance `bookDepth` is aggregated and known public-data issue reports possible misalignment. Next action is integrity/semantics audit, not a performance test.
- No strategy code/dependency changed, no reserved post-boundary outcome inspected, no trial consumed.
- Trial 871 remains unauthorized/unconsumed. `LIVE_NOT_AUTHORIZED`.
