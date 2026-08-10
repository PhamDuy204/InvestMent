# InvestMent — Multi-Asset Alpha V3

Research-only framework for cost-aware multi-asset futures alpha.

> **Status:** `NEEDS_MORE_RESEARCH`. This repository is for backtesting and research only. It contains no live-order execution path.

## V3 scope

- Cost-aware cross-sectional portfolio construction with turnover penalty.
- Explicit round-trip transaction-cost accounting.
- Stateful inherited positions across rebalances.
- Strictly causal covariance and uncertainty estimates.
- Nested selection helpers with a minimum-trade guard.
- Multi-horizon research helpers (4h/8h/12h/24h).
- Binance Futures `aggTrades` quarter-hour microstructure features.
- Cross-margin leverage/liquidation simulation primitive.
- Regression tests for leakage, costs, liquidation, and microstructure features.

## Latest retained H12 V3 research result

- Net return: **+51.3511%**
- Sharpe: **1.9652**
- Sortino: **2.9306**
- Max drawdown: **13.06%**
- Profit factor: **1.3817**
- One-way turnover: **170.401**
- Transaction cost at 10 bps round-trip: **0.08520**
- Turnover reduction vs V2 reference: **~90.96%**

These numbers are research artifacts, **not an untouched holdout**. The 2024–2026 outer periods were repeatedly inspected during V2/V3 development.

## Anti-leakage invariants

- Signal uses information available no later than candle close `t`.
- Earliest modeled entry is the next tradable open.
- Covariance and uncertainty statistics use only strictly prior observations.
- Hyperparameters are selected on inner chronological folds only.
- Funding used as a feature is separate from funding cash flow charged to the account.
- A quoted `10 bps` round trip means `5 bps` per one-way weight change.
- No `return × leverage` shortcut for liquidation research.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
ruff check src tests
```

See `docs/V3_STATUS.md` for completed and missing work, including the unfinished LLM/Groq module and full sequential leverage replay.
