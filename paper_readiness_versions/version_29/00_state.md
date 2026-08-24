# State — Version 29

V29 completes the single fixed augmented-Ridge experiment predeclared in V28.

## Predictive result

Candidate = inherited price-only H12 Ridge plus exactly one causal feature:

`h21c_oi_trend = sign(ret_4) * oi_log_change_1h`.

Both baseline and candidate use the identical V28 source-availability mask and Ridge `alpha=1.0`.

The predictive gate passes, but only marginally:
- baseline mean timestamp IC: `-0.02008898`;
- candidate mean timestamp IC: `-0.01998439`;
- delta: `+0.00010459`;
- candidate IC improves baseline in `2/3` folds;
- standardized H21-C coefficient is positive in `3/3` folds.

The candidate therefore contains statistically direction-consistent incremental information, but its aggregate cross-sectional IC remains negative.

## Corrected economic result

On the exact V28 masked universe and inherited V4/V11 10bps replay:
- baseline net: `-3.774677%`, Sharpe `-0.75535`, turnover `50.3615`, wrong-side damage `1.21860`;
- candidate net: `-5.513609%`, Sharpe `-1.13409`, turnover `55.1670`, wrong-side damage `1.30649`.

Candidate minus baseline:
- net `-1.73893` percentage points;
- Sharpe `-0.37875`;
- turnover `+4.80545`;
- wrong-side damage `+0.08789`;
- net improves only `1/3` folds;
- wrong-side damage improves `0/3` folds.

All V28 economic promotion gates fail. Therefore the fixed Ridge+H21-C integration is **REJECTED**.

## Harness audit

The first internal economics invocation after the predictive gate accidentally left the original panel `in_universe` column active while the V28 fixed mask was stored as `model_in_universe`. `_run_overlay` consumes `in_universe`, so that invocation incorrectly admitted symbols outside the predeclared mask. The inconsistency was detected before any V29 checkpoint was created; that output was discarded. The same fixed model/configuration was rerun after assigning `in_universe = model_in_universe`. This was a harness correction, not an additional research configuration or trial.

## Research conclusion

Historical H21-C remains a legitimate weak DEVELOPMENT signal, but three economic uses are now rejected:
1. raw standalone H21-C direction;
2. zero-threshold H21-C/H12 conflict veto;
3. fixed Ridge(alpha=1.0) augmentation with H21-C.

Do not retune H21-C transform, Ridge alpha, heuristic threshold, or add a model zoo to rescue this observed line.

Trial 871 remains unauthorized/unconsumed. `READY_TO_START_PAPER=false`; `A1=NOT_STARTED`; `PAPER_VALIDATED=false`; `LIVE_NOT_AUTHORIZED`.
