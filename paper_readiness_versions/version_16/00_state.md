# Version 16 — State Snapshot

## Scientific state

- Branch: `v11-root-cause-paper-readiness`.
- Root cause remains **ALPHA_FAILURE (dominant)**.
- V12: `NO_STABLE_RELATIVE_RANK_EDGE`.
- V13: `NO_MATERIALLY_NEW_EXISTING_CAUSAL_INTERACTION`.
- V15: `REJECT_BOOKDEPTH_AS_CROSS_FOLD_DEVELOPMENT_SOURCE`.
- V16: **STOP_HISTORICAL_MICROSTRUCTURE_RESCUE_AND_USE_FORWARD_ONLY_L2**.
- No local/repo historical order-book archive overlaps the old H12 panel.
- Official Binance USD-M `bookTicker` bulk history does not cover the old 2025–2026 folds; public reports show it stopped in March 2024 and the old futures L2 download path is no longer public bulk access.
- Tardis has appropriate Binance USD-M `depth`, `bookTicker`, generated snapshots and integrity checks since 2019, but full-date data requires its API/service; free downloadable CSV is sample coverage only and is not sufficient for the three old folds.
- No paid/new historical pipeline is justified while a forward public L2 recorder is already running.
- Performance trial max: `870`; trial `871` remains **not authorized, not consumed**.
- Factor admitted: `false`; candidate frozen: `false`.
- `READY_TO_START_PAPER=false`; `A1=NOT_STARTED`; `PAPER_VALIDATED=false`.
- `LIVE_NOT_AUTHORIZED`.
