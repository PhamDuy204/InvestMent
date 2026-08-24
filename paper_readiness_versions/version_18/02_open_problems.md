# Open Problems — Ordered by Leverage

## P0 — Reconcile V18 model diagnostics with corrected execution semantics

The predictive diagnostic is interpretable, but the exploratory cost-aware PnL numbers do not reproduce the corrected V11 H12 replay and therefore cannot be used for promotion.

Smallest falsifiable question:

> When the same V18 model scores are passed through the exact corrected V11/V10 decision/execution flow, does any fixed nonlinear model improve development economics and wrong-side damage consistently across at least two chronological development slices without using post-2026-08-20 outcomes?

Do not tune thresholds or model hyperparameters before this reconciliation.

## P1 — Decide whether HistGB deserves one exact follow-up

HistGB is the only nonlinear base learner with positive mean timestamp IC and positive IC in 2/3 development folds, but the edge is tiny. Only after P0 is reconciled may one fixed HistGB follow-up be considered. Do not broaden to XGBoost/LightGBM/neural networks yet.

## P2 — L2 remains forward-only validation evidence

Continue collecting L2. The old requirement to wait 7 contiguous days no longer blocks V18 research. L2 after the 2026-08-20 development cutoff must not be used to tune V18 before its reserved evaluation design is fixed.

## P3 — RL / Optuna

Not authorized now. The fixed ladder completed in ~110 seconds, so Optuna is unnecessary. RL requires an already stable predictive development edge and a predeclared bounded policy objective with transaction costs, turnover and risk.

## P4 — Trial 871 / paper readiness

Still blocked behind a defensible candidate, freeze/config hash, predeclaration, untouched eligibility, deterministic audit, methodology council check, exact local==remote commit gate, and required forward/paper evidence.
