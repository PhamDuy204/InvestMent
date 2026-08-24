# Progress Log

## V17 checkpoint — 2026-08-24 Asia/Ho_Chi_Minh

- Read the complete V16 state/protocol before acting.
- Reconciled clean worktree at starting SHA `74998a06a214b74b5d3ec152cbebbfe16dee2208`; `origin/v11-root-cause-paper-readiness` matched by `git ls-remote`.
- Recorder snapshot: L2 `RUNNING`, 5,685 cycles, 119,385 health-counter records, 0 errors; positioning `RUNNING`, 12 cycles, 1,512 rows, 0 errors.
- Inspected only L2 schema/timestamps/counts; no future-return/outcome column was opened.
- Stored parquet schema already includes `top_of_book_imbalance`, `microprice`, spread and depth-5/10/20 with causal timestamps. No new feature code is needed.
- Parquet inventory: 3,003 parquet files, 180,180 persisted rows, 8,580 rows per each of 21 symbols at the scan snapshot.
- Critical finding: apparent 85.96h wall-clock span is not continuous. All symbols share two segments (~6.04h and ~11.62h) separated by ~68.3h outage.
- Fixed the first feature to existing `top_of_book_imbalance` and predeclared a time-only sample rule: 7 contiguous calendar days at hourly decision cadence, >=20/21 symbols per hour, >=95% hourly coverage per symbol; common outage >15m resets continuity.
- Predeclared future split: two chronological development halves, then 12h H12 purge, then 7-day untouched evaluation block. Existing 30-day A1 forward gate remains unchanged.
- Current state is `NEED_MORE_FORWARD_L2_EVIDENCE`; no development outcomes inspected, no strategy code/dependency changed, no performance replay/trial consumed.
- Trial 871 remains unauthorized/unconsumed. `LIVE_NOT_AUTHORIZED`.
