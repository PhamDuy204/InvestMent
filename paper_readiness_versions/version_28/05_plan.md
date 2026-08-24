# Plan — V28

1. Commit/push coverage + model predeclaration before fitting.
2. Build H21-C from cached causal hourly OI and ret_4.
3. Apply identical fixed availability mask to both models.
4. Fit StandardScaler+Ridge(alpha=1.0) per outer training fold.
5. Evaluate predictive gate.
6. Run corrected economics only on pass.
7. Create V29 with the result; no HPO/RL/trial 871.
