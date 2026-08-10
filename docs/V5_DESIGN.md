# V5 causal research contract

V5 is research/backtesting only. It does not contain or authorize live/paper order submission.

## Frozen evidence

- The 2021-2023 listing-aware confirmation was opened before V5 and must never be used for parameter selection.
- Aug 1-9, 2026 was opened as untouched micro-forward evidence and must never become a tuning set.
- Failed experiments remain counted in the research/multiple-testing ledger.

## Architecture

V5 is modular rather than a monolithic LONG/SHORT model:

1. H12 relative-return forecast remains the retained directional research family.
2. Cost-aware inherited positions plus a small no-trade hysteresis control turnover.
3. Decision diagnostics classify post-hoc ENTER/HOLD/EXIT/FLIP errors; oracle/error labels are never inputs.
4. One-minute models estimate volatility/burst and taker-flow state. Burst probability is not directional alpha.
5. A deterministic multi-horizon policy can represent 15m/1h/4h/12h, but a horizon is promoted only after net-of-cost evidence.
6. Market/Limit/Post-only/Trigger/Trailing are simulated conservatively; no L2 queue/depth is invented.
7. Position notionals use current account equity for compounding, with reserve, covariance/correlation and liquidation-aware risk caps.
8. Groq/Qwen/GPT-OSS generate research hypotheses only. Deterministic local audit can reject them before a backtest.

## Promotion rules

No module is promoted because accuracy, gross return, or terminal leveraged equity looks good. Promotion requires positive net expectancy, PF > 1 (preferably >=1.2), acceptable drawdown, multiple positive temporal folds, cost/delay robustness, no single asset/session/regime dependence, and no severe liquidation sensitivity.

V5 final evidence does not meet these gates, so the current status is `NEEDS_MORE_RESEARCH`.
