# Version 17 — State Snapshot

## Scientific state

- Branch: `v11-root-cause-paper-readiness`.
- Root cause remains **ALPHA_FAILURE (dominant)**.
- V12: `NO_STABLE_RELATIVE_RANK_EDGE`.
- V13: `NO_MATERIALLY_NEW_EXISTING_CAUSAL_INTERACTION`.
- V15: `REJECT_BOOKDEPTH_AS_CROSS_FOLD_DEVELOPMENT_SOURCE`.
- V16: `STOP_HISTORICAL_MICROSTRUCTURE_RESCUE_AND_USE_FORWARD_ONLY_L2`.
- V17: **FORWARD_L2_BOUNDARY_PREDECLARED_BUT_NOT_YET_SUFFICIENT**.
- Existing recorder already computes the first research feature: `top_of_book_imbalance = (bid_qty - ask_qty) / (bid_qty + ask_qty)`; no new feature code is required.
- Parquet schema contains causal `event_time`, `available_at`, `captured_at`, top book, microprice, spread and depth-5/10/20 fields for all 21 expected symbols.
- Existing stored parquet currently has 180,180 rows = 8,580 rows/symbol, but this is **not** 85.96 hours of continuous evidence.
- Coverage has two common segments: about `6.04h` on 2026-08-20 and `11.62h` from 2026-08-23 to 2026-08-24, separated by a common outage of about `68.3h`.
- Current contiguous data is therefore insufficient for the predeclared forward development boundary.
- Performance trial max: `870`; trial `871` remains **not authorized, not consumed**.
- Factor admitted: `false`; candidate frozen: `false`.
- `READY_TO_START_PAPER=false`; `A1=NOT_STARTED`; `PAPER_VALIDATED=false`.
- `LIVE_NOT_AUTHORIZED`.
