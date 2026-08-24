# State — Version 28

V28 completes the no-outcome full-hourly OI coverage audit and predeclares one augmented Ridge experiment.

- Inherited `in_universe_15` eligible hourly model rows through 2026-07-31: `307,095` across 23 ever-eligible symbols.
- Causal finite `oi_log_change_1h`: `306,896` rows = `99.9352%`.
- Source archive files missing/error: `0`. The `199` non-finite rows arise from isolated Binance metrics OI values equal to zero or corresponding one-hour endpoint anomalies, concentrated on a small set of dates.
- No model outcome was used to choose missingness handling.

### Fixed source-availability mask

`feature_available = finite(oi_log_change_1h)` with both OI endpoints strictly positive under the existing `< t`, <=15m causal rule.

For fair comparison, BOTH baseline Ridge and candidate Ridge use `model_in_universe = in_universe_15 AND feature_available`.

No OI value is interpolated. Candidate H21-C may be filled with zero only on rows already marked `model_in_universe=false` to permit vectorized prediction; those scores cannot enter portfolio decisions.

### V29 experiment predeclaration

- Baseline: inherited `PRICE_FEATURES`, StandardScaler -> Ridge(alpha=1.0).
- Candidate: same features + exactly one `h21c_oi_trend = sign(ret_4)*oi_log_change_1h`, same scaler/Ridge alpha=1.0.
- Same purged 3 outer folds, same V4 frozen optimizer/overlay, same 10bps corrected replay semantics.
- No alpha tuning, feature search, nonlinear learner, stacking, Optuna or RL.
