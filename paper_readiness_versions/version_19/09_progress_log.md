# Progress Log

## V19 exact-replay checkpoint — 2026-08-24 Asia/Ho_Chi_Minh

- Re-read the complete V18 state and reconciled a clean worktree at starting SHA `0340dfbe3c500c5b825f943e9b138a551f23ada5`; remote branch matched exactly.
- Recorder snapshot: L2 `RUNNING`, 6,660 cycles, 139,860 records, 0 errors; positioning `RUNNING`, 14 cycles, 1,764 rows, 0 errors.
- Traced the actual V4 -> decision log -> V7/V10/V11 replay flow and identified the V18 reproduction mismatch: the first V18 probe used `in_universe_10`, while inherited V4/V11 uses `in_universe_15`.
- Corrected the PC-local development panel to include `in_universe_15`; no new market data or dependency was needed for that fix.
- With `in_universe_15`, regenerated Ridge produces exactly 14,308 decision keys and matches inherited target weights/scores/labels to floating-point precision. Corrected replay reproduces V11 net `-0.035286447021` and Sharpe `-0.699873546093`.
- Fixed HistGB under the identical flow is rejected: net `-0.070824194959`, Sharpe `-1.553732827252`, economic wrong-side damage increases by `+0.363076241579`, net improves in only 1/3 folds and damage improves in only 1/3.
- No stacking, Optuna, or RL follow-up was run; the price-only nonlinear rescue path is closed for now.
- Searched for a materially new existing/public family. Binance USD-M daily `metrics` exposes 5-minute open-interest and trader-positioning fields. Metadata/schema audit only: all 21 V11 symbols were present with 288 rows/day on four representative dates spanning the historical folds. No H12 outcomes were inspected for this audit.
- Next blocker is full-range metrics continuity/semantics audit before any new factor test.
- Trial 871 remains unauthorized/unconsumed. `READY_TO_START_PAPER=false`; `LIVE_NOT_AUTHORIZED`.
- Full local verification after the checkpoint: `219 passed in 4.23s` using the existing V9 research venv; no code/dependency changes were introduced.
- Checkpoint commit/push was reconciled with PR #8 open against `v10-scientific-candidate`; exact local/remote/PR head matched before this final log-only commit. GitHub `V5 CI` was queued on that checkpoint SHA.
