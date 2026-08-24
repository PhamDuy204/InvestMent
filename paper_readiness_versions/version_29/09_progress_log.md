# Progress Log

## V29 fixed augmented-Ridge result — 2026-08-24 Asia/Ho_Chi_Minh

- Ran exactly the V28-predeclared baseline Ridge and Ridge+H21-C with alpha=1.0 and the identical fixed source-availability mask.
- Predictive gate passed narrowly: aggregate IC delta `+0.0001046`, IC improvement 2/3 folds, H21-C coefficient positive 3/3 folds; candidate aggregate IC nevertheless remains negative.
- The first internal economics invocation was diagnosed as invalid because `_run_overlay` reads `in_universe` while the predeclared mask had been stored in `model_in_universe`. That output was discarded before V29 was created. Same fixed configuration reran with `in_universe=model_in_universe`; no extra configuration/trial counted.
- Valid corrected economics: baseline net `-3.77468%`; candidate `-5.51361%`; net delta `-1.73893` percentage points; turnover and wrong-side damage both worsened; only 1/3 folds improved net and 0/3 improved wrong-side damage.
- Fixed economic gate failed. No alpha/H21-C tuning, stacking, nonlinear model, Optuna, RL or trial 871 followed.
- Historical H21-C line is closed. Next blocker is materially new information / matured forward L2 evidence.
- `READY_TO_START_PAPER=false`; `LIVE_NOT_AUTHORIZED`.
