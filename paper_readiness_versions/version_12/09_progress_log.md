# Progress Log

## V12 checkpoint — 2026-08-24 Asia/Ho_Chi_Minh

- Reconciled local branch `v11-root-cause-paper-readiness`: clean at `519a1544023a0c686e92742d8434efdc49507ffb`; remote branch matched before this checkpoint.
- Recorder health: L2 RUNNING, 2800 cycles, 58,800 records, 0 errors; positioning RUNNING, 6 cycles, 756 rows, 0 errors.
- Resolved P2 diagnostic: per-timestamp cross-sectional Spearman IC of H12 `effective_score` is not stable. Fold 0 selection/eval mean IC `+0.0044/+0.0144`; fold 1 `+0.0270/-0.0765`; fold 2 `-0.0216/+0.0471`.
- Verdict: `NO_STABLE_RELATIVE_RANK_EDGE`. Do not pursue rank-only H12 rescue.
- Found runtime mismatch: V9 venv cannot import V11 `ReliabilityGateConfig(flat_trend_scale=...)`; do not use that environment for V11 scientific reruns until reconciled.
- No strategy code changed. No performance trial consumed. Trial 871 remains unauthorized/unconsumed.
- Safety invariant: `LIVE_NOT_AUTHORIZED`.
