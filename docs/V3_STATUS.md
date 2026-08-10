# V3 status and remaining work

## Reconstructed and committed core

The GitHub version contains the V3 components that could be reconstructed faithfully from the completed research session:

- Cost-aware portfolio target with risk and turnover penalty.
- Gross, net, and per-asset exposure caps.
- Correct round-trip versus one-way execution cost accounting.
- Stateful backtest helper and final unwind accounting.
- Strictly prior covariance history guard.
- Causal residual-based uncertainty shrink helper.
- 32-point cost-aware configuration grid and sparse-trial rejection.
- Multi-horizon evaluation helper.
- Binance Futures `aggTrades` parser/downloader and quarter-hour feature builder.
- Cross-margin liquidation simulation primitive with funding and execution costs.
- Regression tests covering the core methodology invariants.

## Retained research findings

The final H12 cost-aware run after the open-to-open timing correction produced approximately:

| Metric | Result |
|---|---:|
| Net return | +51.3511% |
| Sharpe | 1.9652 |
| Sortino | 2.9306 |
| Max drawdown | 13.06% |
| Profit factor | 1.3817 |
| One-way turnover | 170.401 |
| Transaction cost @ 10 bps round-trip | 0.08520 |

This was much lower turnover than the V2 reference and all three chronological outer folds were positive. However, the first inner validation fold remained negative and the 2024–2026 outer periods were repeatedly inspected during development. Treat these results as mined research evidence, not as an untouched confirmation set.

The seven-day six-asset `aggTrades` pilot covered about 23.27 million aggregate trades and generated 4,032 quarter-hour event rows. Marginal Spearman IC was weak (roughly 0.017–0.027 absolute depending on horizon), so microstructure features were not promoted into the core model.

## Missing / not yet complete

### 1. LLM / Groq research-agent module — missing

The intended LLM layer was never completed because `GROQ_API_KEY` was not visible to the research runtime. No Groq result was fabricated. A future module should only consume structured experiment summaries and propose hypotheses/configurations; it must never execute live trades or see future/OOS labels while proposing an OOS decision.

Recommended interface:

```text
ExperimentRegistry -> sanitized research context -> LLM hypothesis JSON
LLM hypothesis JSON -> deterministic validator -> backtest queue
```

Required safeguards: JSON schema validation, model/version logging, prompt hashing, no secret logging, no direct exchange execution, and every LLM-generated hypothesis counted in the multiple-testing registry.

### 2. Sequential leverage replay — missing

The account-level primitive exists, but a full stateful replay over real hourly mark/OHLC paths for 1x/2x/3x/5x/10x/20x was not finished. This is required before any paper-trading verdict involving leverage.

Still needed: inherited-position handling across rebalances, mark-price liquidation path, maintenance-margin tier sensitivity, liquidation fees, funding shocks, 5–10% instant adverse shocks, wick shocks, and correlation-to-one stress.

### 3. Fresh untouched confirmation history — missing

The current performance cannot be called untouched. Extend the dataset to a period that was not inspected while developing V2/V3, with listing-aware universe construction and no backfilling assets before listing.

### 4. Full uncertainty experiment — incomplete

Causal uncertainty gating was implemented, but the gated configurations fell below the minimum 200-trade inner-sample guard in the first fold. The guard was intentionally not weakened. A baseline/no-gating candidate was planned for the same selection pool but the final nested run did not complete.

### 5. Multiple-testing accounting / DSR / PBO — missing

The V2 registry had 294 trials before V3. V3 trials, failed attempts, stress tests, uncertainty attempts, and microstructure hypotheses still need to be appended to one immutable experiment registry. DSR should then use the true trial count. PBO/CPCV should only be reported once aligned candidate return matrices exist.

### 6. Full post-fix stress artifact — partially retained

A post-timing-fix stress rerun completed, but its scalar JSON values were not re-extracted before the original PC connection was lost. The pre-fix stress results were robust to 5–30 bps costs and modest delays, while 50 bps remained positive and a top-30 universe variant was negative. Do not quote those as the final post-fix stress table until regenerated.

### 7. Multi-horizon artifact — needs rerun

The earlier exploratory H4/H8/H12/H24 run favored H12, but that artifact predates the final open-to-open timing correction. The helper is present; the experiment should be rerun before publication.

### 8. Raw datasets / generated artifacts — not in GitHub

Large panel files, hourly/15-minute raw data, the 23M-trade pilot raw archives, compressed period-level outputs, and the mirror's generated JSON/CSV artifacts were local-only. They are intentionally not reconstructed from memory.

## Current verdict

**NEEDS_MORE_RESEARCH**

The cost-aware V3 architecture is materially stronger than V2, but untouched confirmation, complete leverage replay, trial-accounting, and final robustness are still required before `READY_FOR_PAPER_TRADING` is defensible.
