# Open Problems — V27

## P0 — Historical hourly feature coverage for augmented Ridge

Audit Binance metrics availability over the inherited panel/model rows, including outer-training history before April 2025. Do this without reading model outcomes.

Smallest question:

> Can `sign(ret_4)*oi_log_change_1h` be constructed causally and non-null for essentially all `in_universe_15` rows needed by the inherited H12 folds from training start through 2026-07-31?

If not, do not impute future information or silently shrink folds after seeing performance.

## P1 — Predeclare augmented Ridge only if coverage passes

Fixed model: inherited PRICE_FEATURES + exactly one H21-C feature, StandardScaler -> Ridge(alpha=1.0). No alpha tuning, no nonlinear model, no stacking.

## P2 — Untouched / trial 871

Still blocked and reserved.
