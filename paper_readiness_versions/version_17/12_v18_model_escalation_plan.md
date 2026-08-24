# V18 Model Escalation Plan — Deferred Until V17 Closes

Status: **PREDECLARED RESEARCH PLAN ONLY**. V17 has not yet accumulated its required 7 contiguous development days, so no V18 training or outcome access is authorized now.

## What H12 actually is

H12 is not a hand-written trading rule. The retained directional core is a **12-hour relative-return Ridge regression**. The current implementation uses `StandardScaler -> Ridge(alpha=1.0)` over the inherited price/market feature family and predicts `future_residual_return_12`. Historical V10/V11 work intentionally reused the frozen H12 outputs rather than refitting them.

## Why H12 is not retrained now

The historical H12 folds and V10/V11 held-out results are already observed. Re-training on them and then presenting improved results as fresh evidence would violate the evidence boundary. They may be used only as DEVELOPMENT/diagnostic data for a future model family.

## Trigger for V18

V18 may start only after the predeclared V17 forward-L2 development block reaches 7 contiguous calendar days and its two chronological development halves are evaluated.

- If `top_of_book_imbalance` shows stable, economically useful development evidence: first integrate the smallest model change needed; do not jump to RL.
- If V17 development is clearly negative/unstable: V18 may investigate a new predictive model family using DEVELOPMENT data only while preserving a future untouched block.

## Minimum model ladder

Stop at the first rung that works.

1. **Ridge refit benchmark** — same model family, fixed `alpha=1.0`, with the new forward-L2 causal feature. This is a benchmark, not a new performance trial.
2. **Existing nonlinear baselines** — reuse repo support for `HistGradientBoostingRegressor` and `ExtraTreesRegressor`; no new dependency.
3. **Leakage-safe stacking** — combine Ridge + HistGB + ExtraTrees using manually constructed chronological out-of-fold predictions and a regularized Ridge meta-learner. Do not use random K-fold stacking and do not use `cv="prefit"` on the same data.
4. **RL only if justified** — RL is not the default price-direction model. Consider it only as a bounded policy layer for position sizing/rebalancing/execution after a predictive signal has stable development edge. Reward must include transaction cost, turnover and risk; maximum exposure remains 1x and paper/simulation only.

## Hyperparameter policy

Do **not** run a broad search automatically.

- First run fixed/default configurations for Ridge, HistGB and ExtraTrees.
- Count every tried configuration in `DEVELOPMENT_CONFIGURATION_COUNT`.
- If a candidate training job is estimated to exceed one hour **and** tuning is scientifically justified, use Optuna with persistent storage and pruning; keep the search space small and predeclared.
- Optuna objective must be chronological development economics/robustness, not a single in-sample fit metric.
- Never use untouched/evaluation data in Optuna.

## Long-running training rule

If an actual training/Optuna job is expected to exceed one hour:

1. launch it as a PC background task;
2. record run ID/config/data boundary/commit SHA;
3. create a condition-watch schedule checking no more frequently than hourly;
4. notify only on completion/failure or a material anomaly;
5. disable that training-specific watcher when the run ends.

## Promotion discipline

A more complex model is accepted only if it beats simpler baselines across >=2 chronological development slices after costs and relevant delay stress. Complexity is not evidence. Trial 871 remains untouched until the existing fixed scientific authorization gates pass.

`LIVE_NOT_AUTHORIZED` remains invariant.
