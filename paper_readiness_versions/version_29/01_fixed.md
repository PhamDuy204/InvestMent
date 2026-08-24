# Fixed Facts — V29

1. V29 used the model and missingness policy committed in V28 before fitting.
2. H21-C coefficient is positive in all three training folds and predictive IC improves baseline in two folds, but the improvement is extremely small and aggregate IC remains negative.
3. Corrected 10bps economics fail every promotion gate: aggregate net is negative and worse than baseline, only 1/3 folds improve net, wrong-side damage worsens, and turnover rises.
4. The invalid first internal economics invocation caused by `in_universe`/`model_in_universe` harness mismatch is discarded and does not count as a separate configuration; final V29 result uses the predeclared mask exactly.
5. Development configuration/mechanism count is now 10.
6. Do not tune Ridge alpha, H21-C sign/lag/transform, availability mask, thresholds, stacking, HistGB, ExtraTrees, Optuna or RL on this observed H21-C line.
7. Historical metrics/H21-C integration is closed for this research line unless genuinely new external evidence determines a materially different predeclared mechanism.
8. Trial 871 and post-2026-08-20 untouched evidence remain unconsumed.
