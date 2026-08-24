# Version 12 — State Snapshot

## Scientific state

- Branch: `v11-root-cause-paper-readiness`
- Final V11 SHA at initialization: `510316ef4022706d7db10b132edb19a5e44041e8`
- Final V10 source SHA: `bbed86901b01acf66698cd988c17945573ed984d`
- Root cause: **ALPHA_FAILURE (dominant)**
- New V12 diagnostic: **NO_STABLE_RELATIVE_RANK_EDGE**; rank-only rescue of H12 is not supported.
- Secondary: `REGIME_INSTABILITY`, `COST_FAILURE`
- Timing: minor; `NO_MEANINGFUL_EDGE` at instant already
- Performance trial max: `870`
- Trial `871`: **not authorized, not consumed**
- Development configurations tried in V11: `0`
- Factor admitted: `false`
- Candidate frozen: `false`
- `READY_TO_START_PAPER=false`
- `A1=NOT_STARTED`
- `PAPER_VALIDATED=false`
- `LIVE_NOT_AUTHORIZED`

## Readiness categories

- SOURCE_OF_TRUTH: PASS
- CAUSALITY: PASS
- SCIENCE: FAIL
- EXECUTION: PASS
- OPERATIONAL: PASS
- SAFETY: PASS
- FREEZE: FAIL

## Key evidence

- H12 held-out net at 0 bps: `-1.060946%`
- H12 held-out net at 10 bps: `-3.528645%`
- H12 held-out net at 20 bps: `-5.935735%`
- Aggregate gross holding-return sum: `-0.741493%`
- Fold 1 0-bps held-out: `-5.026574%`
- Fold 1 selection/development 0-bps: `+16.354103%`
- Fold 1 LONG gross contribution: about `-10.3922%`
- Fold 1 SHORT gross contribution: about `+5.2383%`
- +60m worsens aggregate pre-cost net by about `-0.489767%`

Authoritative machine artifacts remain under `artifacts/multi_asset_v11/`.
