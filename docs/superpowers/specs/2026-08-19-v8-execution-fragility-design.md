# V8 Execution Fragility Design

## Scope
Research/backtest/simulation only. No live orders, cancellations, transfers, withdrawals, exchange leverage changes, trading credentials, or OTP flows.

V8 inherits V7 trial accounting through trial 868. The next performance inspection is trial 869. V7 failure memory remains append-only.

## Goal
Test one materially new execution-risk mechanism: whether lagged price movement per traded quote-notional identifies H12 exposure increases that are unusually fragile to a one-hour execution delay, after controlling generic lagged realized volatility.

## H8 predeclared hypothesis
Name: `H8_lagged_impact_execution_fragility`

Causal feature at decision time:
`log_impact_1h = log10(max(abs(lag_return_1h) / lag_quote_volume, 1e-18))`.

This is an Amihud-style price-impact proxy derived from already-available public Binance USD-M hourly kline fields. It is not order-book depth and must never be labelled L2 liquidity.

Outcome-only training/evaluation target:
`delay_damage_per_unit = max(0, sign(target_weight) * ((immediate_holding_return + immediate_funding) - (delayed_holding_return + delayed_funding)))`
computed only for rows that increase absolute exposure. Future labels may never be candidate inputs.

Per outer fold, keep V7's chronological 70/30 selection/evaluation split. Fit on that fold's selection only:
- baseline damage model: `delay_damage ~ 1 + lag_rv12`
- augmented damage model: `delay_damage ~ 1 + lag_rv12 + log_impact_1h`

Factor forecast admission requires augmented evaluation RMSE to beat baseline in at least 2/3 folds and a positive impact coefficient in at least 2/3 folds. No nearby transform, percentile, or threshold rescue is allowed.

## Policy mapping
If and only if the candidate is evaluated as trial 869, compute per row:
- `pred_base`
- `pred_aug`
- `excess_damage = max(0, pred_aug - pred_base)`
- `anchor_damage = median positive delay_damage_per_unit` from that fold selection
- `scale = anchor_damage / (anchor_damage + excess_damage)` when anchor is valid, else `1.0`.

Apply this scale only when `abs(target_weight) > abs(previous_weight)`; reductions/unwinds are never blocked. H12 sign is unchanged. Exposure cannot exceed the H12 baseline target. MARKET execution and 1x maximum effective exposure remain fixed.

## Promotion gates
A serious H8 promotion requires all of:
- candidate evaluation net > corrected H12 baseline;
- candidate evaluation net > 0;
- Sharpe not materially worse;
- max drawdown not materially worse;
- >=2 evaluation folds with positive incremental net;
- wrong-side economic damage or delay implementation damage improves;
- 20 bps stress net >= 0;
- +1h delay net >= 0;
- meaningful exposure retained (not a near-zero portfolio);
- factor forecast admission passes.

Failure consumes trial 869 and is logged append-only with a fingerprint and do-not-repeat rule. No local grid rescue.

## Forward L2 shadow sidecar
Separately from H8 performance testing, V8 will add a public-data-only order-book snapshot recorder using the already-installed `ccxt` public Binance USD-M market-data path. It records top-of-book/depth snapshots for forward execution research only. It never requires API keys and never submits orders.

Historical Binance `bookDepth` archives are treated as coarse/derived public data, not exact executable L2, because sampling/quality semantics are not sufficiently reliable for the V8 execution simulator. Exact replay may later reuse a mature open-source engine such as `hftbacktest` only after suitable full-depth data exists; V8 does not add that dependency prematurely.

## Trial discipline
- Inherited count: 868.
- H8, if inspected economically: trial 869 exactly.
- Data/coverage prechecks and forward recorder smoke tests do not consume performance trials.
- No new trial is created unless a complete hypothesis is predeclared before evaluation.
