# Progress Log

## V28 full-hourly OI coverage + augmented Ridge predeclaration — 2026-08-24 Asia/Ho_Chi_Minh

- Audited 12,985 required Binance metrics symbol-days (including prior-day endpoints) for all inherited `in_universe_15` hourly rows; 0 source files missing/error.
- 306,896/307,095 eligible hourly rows have finite H21-C (99.9352%). 199 non-finite rows trace to source OI zeros/anomalies, not missing downloads.
- Fixed a source-availability mask before any augmented-model fit and apply it identically to baseline/candidate; no imputation.
- Predeclared V29 as exactly one fixed Ridge(alpha=1.0) feature addition with predictive gate before economics.
- No HPO/stacking/RL/trial 871. `LIVE_NOT_AUTHORIZED`.
