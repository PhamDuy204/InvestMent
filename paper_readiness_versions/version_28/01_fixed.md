# Fixed Facts — V28

1. Full eligible-row finite H21-C coverage is 99.9352%; 199 rows are source-unavailable due zero/nonfinite OI endpoints.
2. Availability mask is fixed before model fitting and applies identically to baseline and candidate.
3. Candidate adds exactly one feature and no hyperparameter.
4. Predictive gate before economics: candidate aggregate timestamp IC > baseline; candidate IC > baseline in >=2/3 folds; learned standardized H21-C coefficient >0 in >=2/3 folds.
5. Only if predictive gate passes, run corrected 10bps economics.
6. Economic gate: aggregate candidate net > baseline AND >0, net improves in >=2/3 folds, wrong-side damage < baseline and improves in >=2/3 folds, turnover not greater than baseline.
7. If predictive gate fails, V29 rejects the augmented model without economic replay.
8. If economics fails, V29 records economic rejection; do not tune alpha or H21-C transform.
9. Trial 871 remains untouched.
