# References

## Primary methodology

1. Bailey, D.H. & López de Prado, M. — **The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality**. Use for multiple-testing/selection-bias treatment when the required trial/return provenance exists.
2. Bailey, D.H., Borwein, J.M., López de Prado, M., Zhu, Q.J. — **The Probability of Backtest Overfitting**. Journal of Computational Finance / SSRN 2326253. Introduces PBO via combinatorially symmetric cross-validation (CSCV).
3. López de Prado, M. — **Advances in Financial Machine Learning**, chapter on cross-validation in finance. Use purging/embargo for overlapping-label leakage only where applicable.

## Current web-accessible references checked at version initialization

- PBO SSRN abstract: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- A recent scikit-learn-compatible purged/CPCV implementation and methodology note: https://github.com/eslazarev/purged-cross-validation
- Independent purged/CPCV implementation with explicit leakage verification: https://github.com/landtml/purgedcv

## Local source of truth

Before external literature, use the repository's own tested replay/causal/state helpers and the V11 artifacts:

- `artifacts/multi_asset_v11/failure_decomposition.json`
- `artifacts/multi_asset_v11/regime_localization.json`
- `artifacts/multi_asset_v11/signal_decay.json`
- `artifacts/multi_asset_v11/root_cause_verdict.json`
- `artifacts/multi_asset_v11/paper_readiness.json`
- `artifacts/multi_asset_v11/final_report.md`
