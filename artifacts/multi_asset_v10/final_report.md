# V10 Final Research Report — Scientific Candidate Discovery

## Scope and safety

V10 was created from exact V9 SHA `697b137d5b4cdc8367975271ba4e86dcbeae8d2c` on branch `v10-scientific-candidate`. The work remained research/backtest/simulation/paper-only. No live exchange action was executed or authorized. **LIVE_NOT_AUTHORIZED**.

## INHERITED V9 EVIDENCE

- V9 engineering paper infrastructure was retained rather than rebuilt: public market data capture, `SimulatedBroker`, `ExecutionSimulatorV8`, deterministic decision IDs, restart recovery, duplicate/stale/future rejection, partial fills, append-only journals, funding/fees/latency, and live-order safety.
- V9 ended at max performance trial 869, no admitted factor, no candidate freeze, `READY_TO_START_PAPER=false`, `A1=NOT_STARTED`, `PAPER_VALIDATED=false`.
- Corrected H12 remained the directional baseline. Historical held-out baseline economics were negative: net `-0.03528645` and Sharpe `-0.699874` in the V10 evaluation replay.

## V10 DEVELOPMENT

The actual H1-H8/H12 failure map was reconstructed before new testing. Three materially limited mechanism families were screened on DEVELOPMENT/selection data only:

1. flat-trend incremental reliability;
2. general trend-state-transition incremental reliability;
3. non-flat up/down transition incremental reliability.

The selected hypothesis was `V10_H1_flat_trend_incremental_reliability`. Its single change was: when inherited causal `trend_state == "flat"`, scale only **new/increased** H12 exposure by `0.5`; reductions/exits are unchanged and H12 direction is never reversed. The bounded scale was selected from `{0.0, 0.5, 0.75}` on the chronological first 70% within each outer fold, before any new-candidate held-out evaluation.

Selection-only evidence for scale `0.5` showed 3/3 folds with positive net delta, aggregate candidate net `0.5988839122` vs baseline `0.5858261433`, wrong-side economic damage delta `-612.19 bps`, 20bps net `0.5188944332`, and +1h-delay net `0.5608620085`.

The deterministic methodology audit was `PASS`. Active Groq model discovery returned `qwen/qwen3.6-27b`; the final compact advisory response was `SUPPORT_TEST FATAL_NONE`. Earlier structured council attempts failed at the API/formatting layer before producing a verdict and were recorded rather than misrepresented as scientific objections.

## V10 PERFORMANCE TRIALS

Trial **870** was predeclared, committed, pushed, and local/remote synchronized before held-out access. Its code/config lock hash was `0369cd21a7523ebe0053344f395839fd1827e07b2e427e129bcf8da8ee6d63fe`. A durable access marker was written before reading the held-out partition, preventing rerun after access.

Trial 870 result: **REJECTED_INNER**.

- baseline held-out net: `-0.03528645`
- candidate held-out net: `-0.03414393`
- incremental net: `11.43 bps`
- baseline Sharpe: `-0.699874`
- candidate Sharpe: `-0.677976`
- baseline max drawdown: `0.069010`
- candidate max drawdown: `0.065904`
- turnover delta: `-1.613554`
- wrong-side economic damage delta: `-284.30 bps`
- raw wrong-side count delta: `494` (diagnostic only for this sizing controller)
- folds with positive net delta: `1/3`
- 20bps stress net: `-0.05747846`
- +1h-delay stress net: `-0.03961616`

Mandatory failures were: `evaluation_net_not_positive; insufficient_multi_fold_economic_support; negative_at_20bps; negative_with_1h_delay`.

The candidate improved aggregate H12 economics by about `11.43 bps`, Sharpe, drawdown, turnover and economic wrong-side damage, but the held-out economics remained negative, improvement occurred in only 1/3 folds, and both mandatory implementation stresses were negative. The factor observatory therefore rejected admission; stability score was `1/3`.

Trial 870 was consumed exactly once. It was not rerun and was not retuned after held-out access. Trial 871 was **not** consumed: the two other development-screened transition mechanisms were weaker and did not provide enough distinct pre-held-out evidence to justify another performance trial.

## PROSPECTIVE DATA

V9 prospective recorder roots were preserved. At report generation:

- L2 PID `2743466`: alive, status `RUNNING`, errors `0`, cycles `336`, records `7056` (V10 start `3465`).
- positioning PID `2750224`: alive, status `RUNNING`, errors `0`, rows `126`. Its process is explicitly configured with `--interval-seconds 3600`, so the unchanged first-cycle health snapshot is not treated as a failure before the next hourly cycle.

No retrospective arbitrary data-maturity threshold was invented.

## CANDIDATE

No V10 factor was admitted. `candidate_freeze.json` is intentionally absent. Candidate hash: `null`.

## PAPER ENGINEERING

Engineering categories inherited from V9 remain operational and were reverified locally. Preliminary V10 verification at the evidence head `7fcb8ce471ae5d47b3729df823504cbb443fefa9`:

- full pytest: **218 passed**
- Ruff: **PASS**
- compileall: **PASS**
- focused paper/execution/L2/positioning/live-order-safety tests: **26 passed**
- trial continuity: max 870, trial 870 count exactly 1
- candidate-freeze absence: PASS
- git diff check: PASS

Because SCIENCE and FREEZE fail, engineering readiness does not authorize paper strategy execution.

## A1 PAPER EVIDENCE

`A1 = NOT_STARTED`. `PAPER_VALIDATED = false`. No paper runtime manifest was created because no defensible candidate was frozen.

## Multiple testing

Performance trial count is 870 and next numerical trial would be 871, but 871 is not authorized by this V10 outcome. CPCV/CSCV/PBO/DSR remain `NOT_COMPUTABLE_WITH_CURRENT_PROVENANCE`; V10 does not fabricate those statistics.

## Readiness categories

- SOURCE_OF_TRUTH: PASS
- CAUSALITY: PASS
- SCIENCE: **FAIL**
- EXECUTION: PASS
- OPERATIONAL: PASS
- SAFETY: PASS
- FREEZE: **FAIL**

Final readiness: **V10_NOT_READY_FOR_PAPER**.

Primary blockers: trial 870 rejected; aggregate held-out net remains negative; only 1/3 folds improve; 20bps and +1h stresses are negative; no factor admitted; no candidate freeze.

## Git publication and verification contract

PR: `#7`, base `v9-paper-readiness`. This report was generated while local and remote V10 both pointed to `7fcb8ce471ae5d47b3729df823504cbb443fefa9`. The commit containing this report necessarily changes the branch SHA; therefore the final handoff separately verifies the post-report exact local/remote SHA and GitHub Actions on that exact final SHA without rewriting this report after CI.

## Final decision

- max performance trial: **870**
- V10 trials consumed: **1** (`870`)
- selected hypothesis: `V10_H1_flat_trend_incremental_reliability`
- trial 870: **REJECTED_INNER**
- factor admitted: **NO**
- candidate frozen: **NO**
- candidate hash: **null**
- READY_TO_START_PAPER: **false**
- A1: **NOT_STARTED**
- PAPER_VALIDATED: **false**
- MiroFish: **NOT_USED**
- Qwen model: `qwen/qwen3.6-27b`
- live trading: **LIVE_NOT_AUTHORIZED**

### Shortest defensible next scientific path

Do not tune the flat-state scale or replay trial 870. A future version should begin from the failure ledger and require a materially different causal mechanism with positive development evidence before authorizing trial 871. The current V10 result is a valid negative scientific outcome, not a readiness state.
