# State — Version 27

V27 rejects H26 under its predeclared fixed gate.

- H26 sign-conflict veto reduces turnover (`50.51 -> 42.03`) and wrong-side damage (`1.21854 -> 1.05483`), with wrong-side improvement in `3/3` folds.
- However candidate net is `-4.37725%` versus baseline `-3.52864%`, Sharpe worsens `-0.6999 -> -1.0189`, and net improves in only `1/3` folds.
- Fixed gates for positive aggregate net, aggregate improvement and >=2/3 fold net improvement all fail.
- Therefore H26 is rejected. No threshold or partial-veto scale will be searched.
- H21-C remains a weak but predeclared predictive DEVELOPMENT feature; two hand-written economic mappings (raw direction and sign-conflict veto) are now rejected.
- Next defensible path is to ask whether a **trained regularized linear model** can use H21-C jointly with the inherited price features, provided causal historical metrics coverage exists for model fitting/scoring.
- Trial 871 remains untouched; `LIVE_NOT_AUTHORIZED`.
