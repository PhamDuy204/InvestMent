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

## V14 microstructure / data references

4. Cont, Kukanov & Stoikov — **The Price Impact of Order Book Events**, Journal of Financial Econometrics 12(1):47–88; arXiv:1011.6402. Shows short-interval price changes are strongly related to order-flow imbalance and market depth.
5. Stoikov — **The micro-price: a high-frequency estimator of future prices**, Quantitative Finance 18(12):1959–1966, DOI 10.1080/14697688.2018.1489139. Micro-price conditions on spread and order-book imbalance for short-horizon price estimation.
6. Binance public-data repository / Data Vision — official historical USD-M futures `bookDepth` files. V14 verified HTTP 200 on representative dates in every existing fold range.
7. Binance public-data issue #431 — reports possible USD-M `bookDepth` price/depth misalignment on some files; treat as a mandatory integrity-audit warning, not a reason to hand-fix samples.
