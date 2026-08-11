# V7 Final Research Report — Factor Observatory + Reliability Controller

## Scope and safety

V7 remained research-only throughout this cycle: historical backtest, simulation, factor research, and paper-trading readiness research. No live Binance order, cancel, transfer, withdrawal, exchange-side leverage change, trading API key, or OTP was used. Public Binance market data and Groq research-agent calls were used only for research evidence generation.

## Research state

- Repository: `PhamDuy204/InvestMent`
- Branch: `v7-factor-observatory`
- PR: #4 — V7: factor observatory and reliability research
- Base: `v6-integrated-controller`
- Performance trial count: **868**
- Trials 858–861 are retained as superseded/methodology-invalidated history.
- Corrected first-line trials: 862 control, 863 H1, 864 H2, 865 H3.
- Escalation trials: 866 H4, 867 H6, 868 H7.
- No performance trial was consumed by Groq council iterations that returned `NO_TEST`.

## Methodology corrections

### Fold replay contract

The original V7 replay carried portfolio state across outer-fold boundaries. This was incorrect because the V4 reference backtest treats outer folds independently. The root correction now replays each outer fold independently, unwinds at the end of the fold, and resets state before the next fold.

The exact-control reproducibility contract after the correction matches V4:

- historical aggregate net return: **0.5320169155591432**
- turnover: **153.74384840389803**
- trades: **10,488**

### Fold-local selection/evaluation

The original global chronological 70/30 split concentrated evaluation evidence in the last outer fold and could contaminate earlier-fold decisions if thresholds were fit globally. Corrected V7 now performs, independently inside each outer fold:

- first 70% chronological observations: selection/train;
- last 30% chronological observations: evaluation;
- every learned threshold/model is fit only on the selection portion of that same fold;
- the candidate is evaluated only on that fold’s own evaluation tail.

One candidate specification still counts as one performance trial, not three.

## Corrected H12 baseline

The corrected held-out evaluation baseline is materially weaker than the full historical aggregate:

| Category | Net | PF | Sharpe | Max DD | Turnover | Trades |
|---|---:|---:|---:|---:|---:|---:|
| Selection | 58.5826% | 1.6189 | 2.7956 | 7.9335% | 106.0373 | 7,338 |
| Evaluation | **-3.5286%** | **0.9092** | **-0.6999** | **6.9010%** | **50.5105** | **3,235** |

Therefore V7 does not treat retained H12 as robust OOS. The research target became reliability/risk control for periods where the directional edge weakens.

## H1–H7 results

### H1 — quarter-hour conflict veto — trial 863

**Status: `REJECTED_PRECHECK_DATA_LIMITATION`.** The available quarter-hour aggTrade pilot covers only six symbols for 2026-07-01 through 2026-07-07, versus the 21-symbol Apr-2025–Jul-2026 V7 decision universe. Causally prior fold-selection coverage is therefore insufficient. H1 was not reinterpreted as a no-op strategy failure and missing history was not fabricated.

### H2 — high cross-sectional dispersion gate — trial 864

**Status: `REJECTED_INNER` / falsified.**

- WRONG_SIDE delta: **+137**
- incremental evaluation net: about **-94.64 bps**
- positive incremental folds: **0/3**
- 20 bps stress net: **-6.7681%**
- +1h delay net: **-5.0251%**

No neighboring dispersion threshold/percentile rescue is allowed.

### H3 — weak H12 edge veto — trial 865

**Status: `REJECTED_INNER` / falsified.**

- WRONG_SIDE delta: **+126**
- incremental evaluation net: about **-3.81 bps**
- positive incremental folds: **0/3**
- 20 bps stress net: **-5.9567%**
- +1h delay net: **-3.9677%**

No neighboring weak-score threshold rescue is allowed.

### H4 — residualized lagged taker-buy flow — trial 866

**Status: `REJECTED_INNER`; factor not admitted.**

Fold flow t-statistics were approximately **+1.67, +2.31, -2.00**. Thus two folds were individually large in absolute magnitude, but coefficient sign was unstable. H4 reduced raw WRONG_SIDE count by **253**, demonstrating some diagnostic information, yet the policy mapping worsened economics:

| Metric | Baseline eval | H4 eval |
|---|---:|---:|
| Net | -3.5286% | -3.9605% |
| Sharpe | -0.6999 | -0.7654 |
| Max DD | 6.9010% | 8.3148% |

- 20 bps stress: **-5.8959%**
- +1h delay: **-4.9579%**
- factor stability score: **0.3333**

This distinguishes “factor has information” from “policy mapping makes money.” H4’s mapping failed.

### H5 — council-proposed state-conditioned flow

**Status: `NO_TEST`; no performance trial consumed.** There was no empirical basis for selecting a specific liquidity/activity state after H4, so governance correctly rejected an otherwise easy-to-overfit follow-up.

### H6 — premium-index / volatility reliability sizing — trial 867

**Status: `REJECTED_INNER`; basis factor not admitted.**

The Binance premium-index proxy panel has **14,308** decision rows, **14,278** complete basis rows, approximately **99.79%** complete coverage, and causal basis availability. It is a Binance premium-index proxy and is not described as exact cross-exchange spot-perpetual basis.

The augmented forecast was:

`future_RV12 ~ lag_RV12 + abs_basis`

The basis coefficients were approximately **-2.985, -1.536, +1.492** across the three folds. The augmented forecast failed to beat lag-vol-only OOS RMSE in every fold: **forecast pass = 0/3**. Therefore basis itself failed factor admission.

H6 nonetheless produced strong de-risking downstream:

| Metric | Baseline eval | H6 eval |
|---|---:|---:|
| Net | -3.5286% | -0.1738% |
| PF | 0.9092 | 0.9983 |
| Sharpe | -0.6999 | -0.0135 |
| Max DD | 6.9010% | 4.8637% |

- raw WRONG_SIDE delta: **+551**
- wrong-side economic damage: **1.21854 → 0.96339**
- damage delta: **-2551.53 bps**
- 20 bps stress: **-2.4794%**
- +1h delay: **-0.9478%**

Because basis forecasting failed 0/3 folds, the economic improvement could not be attributed to basis. This directly motivated H7.

### H7 — lagged-RV-only continuous inverse-vol ablation — trial 868

**Status: `REJECTED_INNER`.** H7 removed `abs_basis` from H6 and kept the continuous, fold-local, no-boost risk mapping otherwise unchanged:

`future_RV12 ~ lag_RV12`

`scale = min(1, anchor_vol / predicted_vol)`

where `anchor_vol` is the fold-selection median future RV12 used as a training target statistic. H12 direction, MARKET execution, current-equity accounting, fold reset/unwind, 1x maximum baseline exposure, costs, and delay semantics remained unchanged.

Selection:

- net: **27.6266%**
- PF: **1.5203**
- Sharpe: **2.9469**
- max DD: **6.5185%**
- turnover: **98.8423**
- trades: **9,992**

Held-out evaluation:

- net: **-0.4003%**
- PF: **0.9892**
- Sharpe: **-0.0848**
- max DD: **4.8793%**
- turnover: **46.6095**
- trades: **4,365**
- scaled fraction: **58.48%**
- positive incremental folds: **2/3**

Exposure did not collapse to zero:

- baseline mean gross exposure: **0.46494**
- H7 mean gross exposure: **0.39490**
- H7 median gross exposure: **0.23425**
- H7 max gross exposure: **0.99886**

Error attribution:

- raw WRONG_SIDE: **1530 → 2080** (`+550`)
- wrong-side economic damage: **1.21854 → 0.96049**
- damage delta: **-2580.53 bps**

Mandatory stresses:

- 20 bps net: **-2.6950%**
- +1h delay net: **-1.0700%**

H7 is slightly worse than H6 in evaluation net by about **-22.64 bps**, but reproduces nearly all of H6’s de-risking with no basis input. This strongly supports the attribution that H6’s downstream improvement was predominantly generic continuous volatility de-risking rather than admitted basis information. H7 still fails the serious-promotion stress gates and is not a candidate for freeze.

## Factor Observatory admission

| Factor | Coverage | Stability | Incremental net | Sharpe delta | Admitted |
|---|---:|---:|---:|---:|---|
| H4 controlled taker flow | 100% | 0.3333 | -43.19 bps | -0.0656 | No |
| H6 absolute premium-index proxy | 99.79% | 0.0000 | +335.48 bps downstream | +0.6864 downstream | No |

H6 is not admitted despite positive downstream portfolio deltas because its actual basis-forecast gate failed 0/3 folds. The current number of admitted factors is **zero**.

## ML and scenario escalation

- **ML challenger: `NO_ML_TEST`.** The fixed HistGradientBoosting reliability challenger requires a predeclared admitted feature set; V7 has zero admitted factors. Running it would create an unjustified nonlinear search surface.
- **Scenario sidecar: `NO_SCENARIO_TEST`.** V7 does not have the required >=12 distinct causal events and >=2 temporal folds of positive event-study evidence. Older V5 event artifacts were not relabeled as V7 evidence.

## Groq research council

Groq model discovery and GitHub-secret injection worked. Qwen was retained for scout/scientist first attempts; structured-output validation failures fall back to supported GPT-OSS models, while the local deterministic validator remains the final gate.

A transient Groq HTTP 429 exposed a shared orchestration weakness. The fix retries the same role/model once for a transient 429 using server retry guidance instead of changing hypothesis/model behavior. A separate governance bug was then found: an auditor-approved hypothesis could survive even when the Research Judge returned an empty ranking. The root fix now requires final approval to be the intersection of auditor approval and the Research Judge ranking.

Council iteration 4 produced `H_new_taker_imbalance` at scientist/auditor stages, but the Research Judge returned an empty ranking and explicit `NO_TEST`: the supporting order-flow mechanism was conditional on L2 liquidity state that V7 does not possess, and the current taker-imbalance proxy lacked a sufficiently validated causal link to the reliability target.

- council Actions run: **31481714781**
- artifact id: **9097494932**
- artifact SHA-256: `638d4488a318b9e892f5f0c17c2b3cdb85470a4e97d103f3f0671ce1bc4de8db`
- performance trial count before/after council: **868 / 868**

No H9/869 performance hypothesis was invented merely to keep the trial counter moving.

## Multiple-testing diagnostics

The latest valid stored diagnostics are inherited V6 diagnostics and are reported with their original scope rather than being renamed as stronger procedures:

- approximate DSR: status `APPROXIMATE_DSR_HISTORICAL_TRIAL_SHARPE_DISTRIBUTION_INCOMPLETE`; historical trial count 857; stored observed Sharpe 0.07427; estimated benchmark Sharpe 2.42285; stored probability 0.0. This is explicitly approximate because the complete historical trial-Sharpe distribution was not available.
- CSCV/PBO: status `VALID_CSCV_PBO_FOR_ALIGNED_V6_CANDIDATE_MATRIX_ONLY`; candidate count 13; combinations 252; PBO **0.142857**; `not_cpcv = true`.

No new V7 DSR/PBO number is fabricated. V7 ends without a promoted/frozen candidate, and the V6 PBO matrix does not become a valid V7 candidate matrix merely because trials 858–868 were appended. The stored procedure is CSCV/PBO, not CPCV.

## Execution and leverage

Execution remains **MARKET**. Prior passive/conditional execution evidence did not show a reliable advantage; no maker-fill or L2 queue model was fabricated.

Maximum baseline exposure remains **1x**. V6 leverage evidence already showed materially worse drawdown at 1.5x/2x, very large drawdown at 5x, and liquidation at 10x/20x. V7 de-risking is not used as justification to increase leverage.

## Freeze and forward A1

No V7 candidate passed promotion, 20 bps, and +1h delay gates. Therefore:

- final candidate config: **none**
- freeze hash: **none**
- freeze timestamp: **none**
- post-freeze forward A1 window: **not started**
- untouched forward calendar days: **0 because there is no freeze, not because evidence was fabricated or backfilled**
- READY_FOR_PAPER_TRADING cannot be considered.

If a future materially new mechanism eventually passes and is frozen, the A1 gate must then mature naturally for >=30 untouched calendar days and >=40 eligible H12 observations with the candidate hash unchanged and no retuning.

## Verification and integrity

Verification performed in this cycle includes:

- regression tests for independent fold reset/unwind;
- regression tests for fold-local 70/30 splitting and fold-local gate fitting;
- H7 ablation contract tests proving `_fit` is invariant to changes in `abs_basis`;
- Groq 429 retry regression test;
- Research Judge veto regression test;
- artifact audit test requiring exact trial sequence 858–868, unique trials, H7 trial 868 rejected, zero admitted factors, council iteration 4 no approved hypothesis, and no freeze artifact;
- Ruff checks and Python compileall;
- trial sequence/duplicate audit;
- JSON artifact parse audit;
- literal secret-pattern scan;
- V7 executable live-order/cancel/withdraw/transfer/leverage-mutation surface scan;
- future/oracle feature review, with `future_rv12` retained only as a training/evaluation outcome and never as H7’s causal candidate input;
- V6 artifact immutability check.

Large Binance raw caches and multi-megabyte factor/delay panels remain local and are not committed to GitHub. Lightweight code, tests, registry, methodology corrections, factor admission results, H4/H6/H7 result summaries, council summary, and failure-memory artifacts are synchronized for auditability.

## Limitations

1. Corrected H12 held-out evaluation is negative, so V7 is solving reliability of a weakened edge rather than incrementally improving a robust baseline.
2. Quarter-hour aggTrade coverage is only a pilot and cannot support H1 across the historical universe.
3. No broad historical L2 depth/spread snapshot panel exists; literature mechanisms conditional on L2 state therefore cannot be transplanted using volume proxies without validation.
4. H4 contains partial diagnostic information but no stable profitable mapping.
5. H6 basis information itself failed 0/3 forecast folds; downstream risk improvement must not be called basis alpha.
6. H7 demonstrates useful generic risk suppression but remains negative under both mandatory serious stresses.
7. Zero factors are admitted, so nonlinear ML escalation is not justified.
8. No candidate was frozen; there is no post-freeze forward evidence yet.

## Final research decision

V7 is complete as a research cycle without a surviving candidate. The scientifically defensible state is **NEEDS_MORE_RESEARCH**: do not grid failed families, do not promote basis, do not promote H7 merely because it loses less, and do not proceed to paper trading until a materially new causal mechanism passes the full gates and subsequently matures through A1.
