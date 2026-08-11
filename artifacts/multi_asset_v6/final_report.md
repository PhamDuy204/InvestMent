# V6 Integrated Multi-Timescale Futures Research — Final Report

## Scope and protocol

V6 is research/backtest/simulation only. It contains no live-order path, Binance trading credential, OTP flow, or permission to place orders. The retained direction source is the V4/V5 H12 Ridge relative-return core with causal top-liquidity universe, simultaneous long/short positions, no-trade hysteresis, current-equity compounding, and MARKET execution baseline.

The 2021–2023 historical confirmation and Aug 1–9, 2026 micro-forward were already observed before V6 and were never used to select V6 parameters. V6 continued the research counter from 779 instead of resetting it. The final candidate was frozen before the Aug 10 post-freeze evaluation.

## 1. V6 architecture

The implemented controller separates direction from state. H12 supplies the directional forecast. Causal state contains time/session, rolling realized volatility, burst-state proxy, flow state, trend state, liquidity/activity context, funding, correlation context, current equity, drawdown, and margin buffer. State may change HOLD/REDUCE/EXIT timing, risk scale, horizon, or execution urgency, but burst/flow cannot directly reverse H12 direction.

Decision logging separates causal fields from post-hoc oracle/realized labels. Future labels are appended only after outcomes and are excluded from the causal schema.

## 2. Combined modules tested

Hierarchical replay tested the retained baseline followed by time/volatility scaling, burst-state scaling, flow-conflict scaling, trend/HOLD-EXIT scaling, conditional execution, reserve/allocation policies, leverage/account stress, and the full H combination. Each evaluated candidate remained in the V6 registry.

## 3. Incremental value

No B–G overlay cleared the inner incremental-value promotion gate. High-volatility scaling sometimes improved Sharpe/drawdown but did not compensate for return loss and complexity penalty. Burst, flow-conflict, trend-conflict, and reserve overlays were rejected. Therefore the H candidate contains no promoted overlay and remains the retained H12 core.

## 4. Failed interactions

Burst probability did not become directional alpha or a leverage booster. Flow did not justify a `high sell flow => SHORT` rule. Short-horizon directional sleeves did not produce positive after-cost evidence. Conditional passive execution did not beat the conservative MARKET baseline. Reserve fractions did not deliver enough incremental risk-adjusted value to justify promotion.

## 5. ENTER/HOLD/EXIT diagnostic changes

Before V6: WRONG_SIDE 5,031; UNNECESSARY_REBALANCE 2,529; LATE_EXIT 1,818; FALSE_ENTER 39; MISSED_ENTER 35; PREMATURE_EXIT 20.

After the frozen V6 replay: WRONG_SIDE 5,042; UNNECESSARY_REBALANCE 2,530; LATE_EXIT 1,810; FALSE_ENTER 36; MISSED_ENTER 26; PREMATURE_EXIT 21.

The dominant failure remains directional reliability. Small improvements in missed/false entry and late exit are not enough to offset the lack of improvement in WRONG_SIDE.

## 6. Session/time findings

On the 30-symbol hourly discovery panel, the Vietnam 08:00–17:00 session had lower mean absolute 1h return than the complementary session (about 0.655% vs 0.724%) and lower activity. However trailing 24h realized volatility was approximately equal (~0.934% in both groups). This does not justify a hard rule that Vietnam daytime permits high leverage.

The original V4 decision grid occurs only at six UTC decision hours, so those account decisions alone cannot establish a complete 24-hour seasonality map. A separate hourly descriptive audit was used only as post-freeze diagnostics and not to modify the candidate.

## 7. Holding horizon by state

The 1m six-asset pilot tested shorter risk horizons. Inner selection could prefer 60m in Vietnam daytime and 30m outside it, but after-cost expectancy remained negative. These results are pilot-only and were not promoted to the account controller. The frozen account horizon remains 720 minutes / H12.

## 8. Sustainable trade frequency

The controller diagnostic contains 6,413 actionable decisions, roughly 13.6 per day in its own action definition, with loss probability above 50% and a maximum losing streak of 13. This number is not directly comparable with the V4 rebalance-trade count because the definitions differ. V6 therefore found no evidence that maximizing entry/exit frequency improves after-cost compounding; inherited hysteresis remains the frequency-control mechanism.

## 9. Jackpot/burst role

Final role: state/urgency diagnostic only. It may be useful in future causal state interactions, but V6 found no sufficient incremental evidence to use it for direction, leverage increase, or an emergency-exit rule.

## 10. Short-flow role

Final role: context only. Flow is not promoted as standalone directional short alpha.

## 11. Execution mode

Final mode: MARKET. Conservative passive/post-only simulation retains missed-fill/delay/adverse-selection penalties and did not beat market execution. No L2 queue position or 100% maker fill is fabricated.

## 12. Capital allocation

Current-equity compounding remains enabled. 10%, 20%, and 30% reserve candidates were evaluated but were not promoted. Position size is not increased after losses and no martingale behavior is present.

## 13. Recommended effective leverage

Recommended effective leverage remains 1x. Discovery account replay at 1x was approximately +53.3% net, Sharpe ~2.09, and max drawdown ~13.34%. Higher leverage raised drawdown materially and was not selected by maximum historical return.

## 14. Liquidation/stress

The account simulator applies intrabar adverse high/low, trading costs, funding, slippage, margin rules, and liquidation rather than clipping losses. 10x and 20x liquidated in the base replay around 2025-10-10 21:00 UTC. The 1x recommendation survived the tested cost/slippage/funding/maintenance-margin/correlation stress set.

During final CI repair, the exposure-cap helper was corrected from a fixed 12-step approximate projection to an exact bisection-based projection. The failing regression case exceeded the 0.05 net cap by ~3.76e-7. A separate random-vector numerical audit found old-vs-exact differences of ~3.8e-7 at 3 assets, ~1.8e-9 at 5 assets, and machine precision from 10 assets upward in the sampled cases. This is treated as a numerical hard-constraint fix, not a new alpha hypothesis or a post-forward promotion change.

## 15. Multiple testing / DSR / PBO

The candidate was frozen at total trial/evaluation count 857: 779 inherited V5 evaluations plus 78 V6 evaluations. The approximate DSR output is 0.0 but explicitly carries the status that the historical trial-Sharpe distribution is incomplete; it is not presented as a definitive probability. Aligned V6 candidate returns contain 13 candidates over 942 observations; the CSCV-style PBO estimate is ~14.29%. It is explicitly not labeled CPCV.

## 16. Independent / forward evidence

Frozen candidate SHA-256:

`be84d12f86df294fc7eaf30affe5cf6d89df99cb1092e7856f2dbfd016b3ec92`

Freeze timestamp: 2026-08-11T01:36:31.977489+00:00.

Post-freeze Aug 10, 2026 micro-forward used the unchanged candidate and produced approximately -2.144% at 10 bps, -2.241% at 20 bps, and -1.891% with +1h execution delay. One day is not independent confirmation, but it does not support promotion and is directionally consistent with the already-observed negative Aug 1–9 evidence.

The 2021–2023 historical confirmation remains weak and locked: approximately +3.17% at 10 bps, PF 1.022, Sharpe 0.205, -18.89% at 20 bps, and -2.42% with +1h delay.

## 17. GitHub / verification state

Branch: `v6-integrated-controller`.

PR: #3, based on `v5-research`.

The GitHub V5 base contained a stale API migration: `v4_overlays.py` and `test_multi_asset_v3.py` still referenced the removed `PortfolioCaps` interface. V6 completed that migration rather than restoring a dead compatibility abstraction. A second regression exposed the approximate exposure-cap projection and was fixed at the shared helper. GitHub CI subsequently passed pytest, Ruff, and compileall on the code head. This report-only commit must retain those green checks on the final PR head before the PR is considered complete.

Local PC verification performed during the V6 cycle had previously passed the broader 126-test suite, Ruff, compileall, leakage/freeze checks, secret scan, artifact/hash checks, and trial-count consistency checks. Raw multi-million-row market data are intentionally not committed to GitHub.

## 18. Remaining evidence gap and next research queue

V6 is code/research complete when the final PR-head CI remains green, but the strategy is not ready for paper trading. The principal unresolved evidence gap is independent generalization, not missing complexity.

The highest-priority next hypothesis should be predeclared for a later research cycle rather than retrofitted into the frozen V6 candidate: quarter-hour aggregated order imbalance aligned with the existing H12 forecast as a reliability/state modifier, not as direct standalone direction. Recent research reports that quarter-hour opening imbalance can forecast four-to-twelve-hour crypto-futures returns, which is structurally closer to the retained H12 horizon than the failed 15m/60m sleeves. A separate recent L2 study finds that order flow adds value only conditionally on liquidity state and is not robust across BTC/ETH, so any such test should remain state-first and should not fabricate L2 state when L2 history is unavailable.

A second priority is a genuinely independent futures market such as VN30F1M when read-only intraday market-data access is available. Crypto-specific burst/funding variables should not be forced into that branch.

No new rule discovered after the V6 freeze is allowed to change the frozen V6 candidate or its promotion gates.

NEEDS_MORE_RESEARCH
