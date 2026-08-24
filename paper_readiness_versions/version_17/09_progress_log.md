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

## Hourly check — 2026-08-24T01:51:49Z

- Re-read the complete V17 protocol/state before acting; worktree started clean at `ea8b7b5df3de398ca03dbb57765976ed41a3fe96` and `origin/v11-root-cause-paper-readiness` matched exactly by `git ls-remote`.
- Recorder health: L2 `RUNNING`, 6,179 cycles, 129,759 health-counter records, 0 errors; positioning `RUNNING`, 13 cycles, 1,638 rows, 0 errors.
- Recomputed continuity from parquet **filenames only** (no parquet content or H12 outcome access): 21 symbols, common latest segment `2026-08-23T13:07:34.665826Z` to `2026-08-24T01:44:00.742588Z` = `12.607h`.
- Fixed V17 eligibility still fails: `12.607h < 168h`; therefore status remains `NEED_MORE_FORWARD_L2_EVIDENCE`.
- No feature/strategy code, dependency, threshold, development outcome, replay, candidate, or performance trial was opened. No `version_18` was created because no meaningful scientific/readiness checkpoint changed.
- Trial 871 remains unauthorized/unconsumed; `LIVE_NOT_AUTHORIZED` remains invariant.
