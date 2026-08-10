# Multi-Asset Futures Research V5 — Final Report

## Scope and safety

V5 remains a research/backtesting project. No Binance order endpoint, live-trading permission, paper deployment, or trading credential is used. All execution types are simulated. Future returns, oracle actions, decision-error labels and jackpot labels are diagnostic/target-only and are not model inputs.

## Data

Six liquid perpetual contracts were downloaded at 1m resolution from 2025-01 through 2026-07: BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT and ADAUSDT. Each asset contains 830,880 bars, for 4,985,280 one-minute bars total. Integrity checks found zero duplicates, missing expected bars or detected gaps.

Daily public archives were also used for Aug 1-9, 2026 micro-forward evidence. The six 1m assets contain 12,960 bars each and 30 hourly candidate symbols contain 216 bars each, with zero detected gaps/duplicates.

## V4 closure

The useful V4 Groq hypothesis was a no-trade hysteresis. Inner validation selected minimum absolute weight-change bands of 0.5%, 0.5% and 1.0% across the three outer folds. The static adverse-funding threshold of 0.0002 was never selected; the liquidity ablation was not applicable to the price-only Ridge baseline.

Discovery: net **+53.20%**, Sharpe **2.006**, Sortino **3.007**, PF **1.393**, max DD **13.08%**, expectancy **4.73 bps/12h**, 10,488 trades, turnover **153.74**. Compared with drift-corrected V3, turnover fell from about 169.96 and trade count from 14,375 while net return stayed near +53%.

Frozen discovery stress: 5bps **+59.14% / PF 1.434**; 20bps **+41.80% / PF 1.313**; +1h delay **+48.56% / PF 1.362**.

## Decision-level error diagnosis

V4 produced 14,308 symbol-decisions. Post-hoc error counts: **WRONG_SIDE 5,031**, **UNNECESSARY_REBALANCE 2,529**, **LATE_EXIT 1,818**, FALSE_ENTER 39, MISSED_ENTER 35, PREMATURE_EXIT 20, CORRECT 4,836. The raw 66.2% error rate is not classifier accuracy because many rows are small continuous weight adjustments.

High error rate did not imply a bad state: high-volatility rows had more wrong-side cases but also the highest mean realized contribution; 08:00 UTC also had high wrong-side frequency but the strongest mean contribution. V5 therefore rejects blanket hour/high-volatility filters.

## One-minute jackpot / burst research

A causal 20-minute extreme-move label was created using absolute and trailing-volatility-scaled thresholds. It is target/diagnostic only.

Frozen May-Jul test: burst ROC-AUC **0.743**, AP **0.0168**, directional 20m return correlation about **0.00005**. The validation-selected event threshold failed economically: 319 events, **-9.63 bps/event after 10bps**, PF **0.645**.

Untouched Aug 1-9 micro-forward: burst ROC-AUC **0.922**, 80 events, +4.37bps gross/event but **-5.63bps net/event**, PF **0.712**. Timing of a large move is forecastable; direction is not forecastable with enough edge to trade.

A separate burst-direction classifier achieved test AUC about 0.596 but **-34.5bps/event / PF 0.216**. Rejected.

A risk-only emergency-exit overlay using the burst detector worsened Aug hourly performance from about -1.19% to **-2.04% / PF 0.556**. Rejected.

## Short-volume / taker-sell-flow

Future 5m taker-sell share achieved test correlation about **0.138**, but high vs low predicted sell-flow states had essentially zero/non-monotonic 20m directional-return difference. Taker-sell prediction is retained only as a state feature, not a simple short signal.

## Ultra-short directional sleeves

15m Ridge test: correlation 0.0107, **-31.4bps/event**, PF **0.185**.

60m Ridge test: correlation 0.0311, **-24.7bps/event**, PF **0.313**.

Rejected. V5 does not use “high volatility => trade extremely short” as alpha.

## Wrong-side meta-calibration

A continuous inner-trained correctness shrinker targeted WRONG_SIDE without flipping direction or using a threshold grid. Result: net **-1.15%**, Sharpe **-0.296**, PF **0.956**. Rejected; further meta thresholds/model grids would be unjustified mining.

## Multi-timescale policy

V5 implements a deterministic research state machine for 15m/1h/4h/12h with confidence/sign agreement and ENTER/HOLD/EXIT/FLIP actions. Because 15m and 60m directional sleeves failed, short horizons are not promoted as alpha sleeves; the longer 4h/12h relative-return structure remains the only historically supported directional family, with H12 strongest.

## Execution research

Research simulator supports MARKET, LIMIT, POST_ONLY, TRIGGER_MARKET and TRAILING_STOP with conservative OHLC crossing and no fabricated L2 queue/spread.

A fixed passive study across 10,443 rebalances used 2bps market slippage, 5bps favorable passive offset, 2.5bps required trade-through, then next-hour market fallback. Weighted passive fill rate was **89.6%**, but hybrid effective cost was **3.15bps one way**, about **+1.15bps worse than market** because missed fills/delay dominated. LIMIT/POST_ONLY are not promoted as defaults.

## Capital allocation and leverage

Target notionals use current equity, so profits compound causally. A deliberate reserve may remain undeployed.

Discovery mechanics: full 1x final equity 1.5332; 20% reserve 1x 1.4117; 20% reserve +2x multiplier 1.9465. These are mechanics, not confirmed alpha.

Fixed leverage replay on V4 weights: 1x +53.3% DD~13.3%; 2x +126.6% DD~25.1%; 3x +223.4% DD~35.4%; 5x +496.0% DD~52.2%; **10x and 20x liquidated at 2025-10-10 21:00 UTC**. Because independent alpha is weak, leverage cannot be used to manufacture returns; 1x remains the research baseline and 2x is stress/research-only.

## Groq multi-model contribution

Groq is a research generator/auditor, never a trading actor. V4 generated the useful turnover hypothesis. V5 Groq proposed three additional ideas, all rejected by deterministic local audit: one referenced a non-existent H12 feature, one duplicated/complicated hysteresis unsafely, and one high-volatility exit rule contradicted diagnostics.

## Independent evidence blocking promotion

Locked 2021-2023 confirmation, never used for V5 tuning: **+3.17% @10bps, PF 1.022, Sharpe 0.205, -18.89% @20bps, -2.42% with +1h delay, PSR ~59.9%**, bootstrap probability of ending below initial equity ~42%.

Untouched Aug 1-9, 2026 frozen V4 micro-forward: **-1.19% @10bps, PF 0.719, Sharpe -3.59, -1.45% @20bps, -1.44% with +1h delay**. Nine days is not sufficient as a long confirmation sample but is genuine negative forward evidence and cannot become a tuning set.

## Multiple testing

The counter is not reset for V4/V5. Conservative accounting increased total research/evaluation rows from 657 to **779**. Approximate DSR probability fell from ~2.59% to **~2.22%**. Prior aligned CSCV/PBO (~16-17%) is retained; no fake CPCV/PBO is created for heterogeneous V5 event experiments.

## Conclusion

V5 improved research mechanics and diagnosis but did not produce a promotable new alpha. The current crypto hypothesis family is meaningfully exhausted on already-opened data. The valid next steps are a materially longer untouched forward period, or transferring the causal framework to an independent futures market rather than mining the failed confirmation.

**NEEDS_MORE_RESEARCH**
