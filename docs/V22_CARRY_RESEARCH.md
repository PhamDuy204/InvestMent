# Carry research alongside V21

The V21 account continues its existing causal spread strategy. V22 now automatically observes same-symbol, cross-venue funding differentials from the existing public funding feed. The publisher displays the six strongest current quotes and records one snapshot per new source timestamp in `artifacts/arbitrage_v21_live/carry_observations_v22.sqlite`. It does not allocate capital, place paper fills, modify V21 calibration, or credit account PnL.

## What the observation means

Each route has equal base quantity on the long and short legs. The displayed quote prices one next funding event shared by both venues, using their current mark prices and signed funding rates. Four taker fees, using the existing project fee assumptions, are deducted. This is an after-fee quote, not expected after-cost EV: executable spreads, depth, adverse selection, basis movement, margin stress and changing funding rates remain unmeasured for this sleeve.

Quotes more than 180 seconds old, future-dated samples, nonfinite values, missing mark prices, expired settlement timestamps, unknown fee venues and continuous-funding venues are excluded. Different settlement times are counted separately rather than compared as if they were the same event. The observer never extends a current quote into repeated future payments.

## The $1/hour objective on $100

With all $100 available and ignoring reserves, the gross leverage ceiling gives the following algebraic upper bounds. Fragmented venue balances, fees, margin buffers, minimum order sizes and depth reduce executable capacity further.

| Gross leverage cap | Gross exposure | Notional per equal-price leg | Net edge needed for $1 per hour |
| --- | ---: | ---: | ---: |
| 20x | $2,000 | $1,000 | 10 bps/hour |
| 40x | $4,000 | $2,000 | 5 bps/hour |

These are capacity calculations, not return forecasts. A 10 bps quote paid once every eight hours is 1.25 bps/hour before any cost, and that arithmetic itself assumes the rate repeats. Counting only time remaining to the next payment as a repeatable hourly yield would overstate performance. Increasing trade frequency is useful only when the incremental attempts have positive conservative after-cost EV.

## Expansion decisions

| Approach | Current status | Evidence required before paper execution |
| --- | --- | --- |
| Cross-venue spread convergence | V21 paper execution | Continue monitoring realized paired and one-leg results after the recovery revision |
| Cross-venue funding differential | Automated V22 observations and separate history | Prospective executable books, synchronized funding events, observed final settlement rates, partial-fill handling, per-venue margin and capital allocation |
| Spot–perpetual cash-and-carry | Researched; no execution sleeve enabled | Tradable spot books, full spot cash cost, contract precision, fees on both products, settlement evidence and basis exits |
| Directional/momentum or DeFi yield | No new execution enabled | A separate causal validation and cost/capital model; neither follows from the spread strategy's PnL |

Spot cash-and-carry cannot apply a 20–40x multiplier to the spot purchase without a separate borrow model. Index/mark dislocation is also not an executable spot–perpetual basis. Those shortcuts are intentionally absent.

## Promotion rule

Collect prospective observations and final settlement evidence first. Any later paper sleeve needs its own causal entry/exit and adverse-outcome calibration, a ledger with real simulated holdings at each funding event, and a shared capital allocator before its results could be combined with the $100 account. The target is measured across rolling and long-run realized windows; no new sleeve has demonstrated $1/hour yet.

## Primary sources checked on 2026-09-05

- [OKX funding fee mechanism](https://www.okx.com/help/perps-funding-fee-mechanism): only positions held at assessment pay or receive funding; intervals vary by contract.
- [OKX automatic settlement frequency updates](https://www.okx.com/help/okx-to-enable-automatic-updates-for-funding-fee-settlement-period): interval changes must be handled explicitly.
- [Bybit funding rate calculation](https://www.bybit.com/en/help-center/article/Introduction-to-Funding-Rate): rates are updated before settlement.
- [Bybit arbitrage introduction](https://www.bybit.com/en/help-center/article/Arbitrage-Trading): spot/futures legs and funding/spread concepts.

This research does not establish queue priority, exchange acknowledgements, real hedge latency or liquidation parity with funded trading. The public-data-only boundary remains in force.
