# V9 Final Research Report — Paper Readiness Continuation

## Scope and safety

V9 remains research/backtest/simulation/shadow/paper infrastructure only. No live exchange order, cancellation, withdrawal, transfer, borrow/repay, leverage/margin mutation, private signed trading request, OTP flow, or trading API-key action was performed. Public market data is allowed; all execution decisions are routed only through `SimulatedBroker` and `ExecutionSimulatorV8`. `LIVE_NOT_AUTHORIZED` is unconditional.

This report evaluates the V9 implementation/provenance state rooted at implementation head `7e0d003944b5a98d0b23239feaa2bc7f28adfa66`. The publication commit that contains this report necessarily changes the Git commit SHA, so the exact final remote branch head and exact-head CI result are verified out-of-band after publication and are authoritative in the PR/final continuation verdict rather than self-referenced inside the same commit.

## HISTORICAL EVIDENCE

- Immutable V8 source SHA: `3eaf36efbcc8933bab173df521bb4a4c8897ab60`.
- V9 branch: `v9-paper-readiness`.
- V9 prospective boundary: `2026-08-20T10:34:19Z` from immutable `v9_start_manifest.json`.
- The inherited V8/V9 experiment registry remains append-only through performance trial **869**.
- Trial **870 is absent and unconsumed**.
- `v8-positioning-1` remains permanently excluded / `AUDIT_ONLY`; it was not repaired or retrospectively reclassified.

## DEVELOPMENT/CALIBRATION

Pre-boundary L2/positioning observations remain development/calibration evidence. They were not promoted into untouched V9 evidence. Historical H1-H8 failures remain unchanged; H8 remains `REJECTED_INNER` and was not renamed, threshold-rescued, grid-searched, or rerun.

The retained H12 baseline already contains BTC/ETH lead-lag, market breadth/dispersion, liquidity and risk features. A proposed BTC-to-altcoin lead-lag direction was therefore rejected as not materially distinct before any new performance trial. Generic nonlinear/interaction expansion was also not admitted because no inherited factor has passed the existing scientific gate and the external interaction literature does not uniquely determine one exact intraday-futures single-change specification for this universe without post-hoc selection.

## PROSPECTIVE V9 EVIDENCE

Fresh PC audit on 2026-08-23 found the prior recorder PIDs dead because the host had rebooted (`boot_time=2026-08-23 10:37:29 +07:00`). Existing raw files were preserved. Recorders were restarted in the **same** V9 local-data roots and the gap is explicitly a discontinuity; no pre-gap/post-gap data is relabeled as A1.

L2 restart/current integrity:

- current PID: **2743466**;
- current health: `RUNNING`, error count **0**;
- total persisted+pending audit rows: **62,909** across **21 symbols**;
- pending WAL rows: **1,169**;
- duplicate checksums: **0**;
- timestamp parse failures: **0**;
- `event_time > available_at`: **0**;
- `captured_at > available_at`: **0**;
- crossed/locked books: **0**;
- depth monotonicity violations: **0**;
- missing/bad parquet sidecar hashes: **0 / 0**.

Positioning restart/current integrity:

- current PID: **2750224**;
- current health: `RUNNING`, error count **0**;
- total rows: **1,008**, **21 symbols**, **6 feature families**;
- schema: **`v8-positioning-2` only**;
- duplicate checksums: **0**;
- timestamp parse failures: **0**;
- causal ordering violations: **0**;
- missing/bad parquet sidecar hashes: **0 / 0**.

The first positioning restart invocation incorrectly supplied CCXT-style symbols (for example `BTC/USDT:USDT`) to the Binance REST recorder, producing 21 HTTP 400 errors and zero rows. Existing recorder state showed the correct REST symbol format (`BTCUSDT`); the bad invocation was terminated and restarted with the existing format, without changing source code or raw historical data. The first corrected cycle produced 126 clean rows with zero errors.

All prospective recorder observations remain `PROSPECTIVE_V9_CAUSAL_INTEGRITY_ONLY` / `FORWARD_ONLY`; they are **not performance admission evidence** and are **not A1**.

## PERFORMANCE TRIALS

- maximum performance trial: **869**;
- next performance trial: **870**;
- trial 870 consumed: **NO**;
- V9 performance trials consumed: **0**;
- new V9 factors admitted: **0**;
- candidate freeze: **NONE**;
- candidate hash: **NONE**.

No exact distinct candidate passed the deterministic admission layer. Fresh Qwen council result is `NEED_MORE_EVIDENCE`; `performance_trial_authorized=false`. Therefore no trial-870 predeclaration or evaluation was created.

## Qwen research council

Exact model used: **`qwen/qwen3.6-27b`** for all four roles. Final structured reasoning content was not persisted (`reasoning_persisted=false`), JSON was locally validated, and no GPT fallback was used. The effective verdict is **`NEED_MORE_EVIDENCE`**. Evidence Scout / Error Scientist produced no testable hypothesis; Methodology Auditor and Research Judge both preserved the no-test state.

The live Groq documentation still lists `qwen/qwen3.6-27b` and documents hidden reasoning support; the V9 run itself remains the source of truth for the exact model actually used.

## MIROFISH SCENARIO EVIDENCE

MiroFish was **not run**. Sidecar status is `MIROFISH_NOT_CONFIGURED_EXTERNAL_DEPENDENCY`. No Zep credential was fabricated, no public ingress was enabled, and the scenario registry contains no synthetic performance evidence. MiroFish therefore contributed no alpha and consumed no trial.

## ENGINEERING PAPER SMOKE

The public-market-data paper path is **`PASS_ENGINEERING_ONLY`**, explicitly `ENGINEERING_ONLY`.

Verified behaviors include:

- real public Binance USD-M order-book fetch;
- causal capture timestamp taken after the public HTTP response;
- deterministic decision ID for fixed input/candidate/time;
- restart state restoration;
- duplicate decision rejection;
- stale-data rejection;
- future-data rejection;
- append-only journal/health state;
- observed-book depth walking through `ExecutionSimulatorV8`;
- partial fill and unfilled tail preservation (`250 target -> 101 filled -> 149 unfilled` in deterministic smoke);
- fees/slippage/funding/latency fields;
- no private exchange order path.

`paper_engine_smoke.json` records `simulated_only=true` and `private_exchange_order_call_performed=false`.

## A1 PAPER EVIDENCE

**None.** A1 was not started because no scientifically admitted candidate exists and no candidate freeze exists. Engineering smoke and recorder observations cannot be retroactively counted toward A1.

Current state:

- `A1 = NOT_STARTED`;
- `PAPER_VALIDATED = false`;
- `LIVE_NOT_AUTHORIZED`.

## Multiple testing

`multiple_testing.json` records:

- performance trial count: **869**;
- next trial: **870**;
- V9 performance trials consumed: **0**;
- DSR/PBO/CSCV/CPCV: `NOT_COMPUTABLE_WITH_CURRENT_PROVENANCE` where complete required lineage/matrices are unavailable.

Absence of required provenance is not converted into zero, and no metric was fabricated.

## Readiness categories

| Category | Result | Evidence |
| --- | --- | --- |
| SOURCE_OF_TRUTH | PASS | immutable V8 SHA, V9 boundary/lineage, intact registry |
| CAUSALITY | PASS | V9 boundary preserved, v1 excluded, fresh timestamp/hash audits clean |
| SCIENCE | **FAIL** | no admitted factor, no authorized/consumed trial 870 |
| EXECUTION | PASS | observed-book simulator, partial/unfilled, fees/slippage/funding/latency |
| OPERATIONAL | PASS | public-data smoke, deterministic/restart/stale/future/duplicate fail-safe |
| SAFETY | PASS | simulated-only path; static/live-order safety remains enforced |
| FREEZE | **FAIL** | no candidate freeze/hash |

Categorical verdict: **`V9_NOT_READY_FOR_PAPER`**.

This is deliberately not expressed as a probability or weighted readiness percentage.

## Git publication and verification contract

Before the final artifact commit, local branch state was clean at `7e0d003944b5a98d0b23239feaa2bc7f28adfa66` and `origin/v9-paper-readiness` did not yet exist. After this report is committed, the continuation must push `v9-paper-readiness`, create/update a PR against `v8-execution-liquidity-shadow`, fetch the exact remote head, rerun local verification on that exact remote SHA, and inspect GitHub Actions for the same SHA. The exact final SHA/PR/CI status is reported by that post-publication verification rather than embedded self-referentially here.

## Final decision

V9 paper-engine engineering, causal-integrity controls and safety are operational, but the scientific gate is not satisfied. No admitted factor exists, trial 870 was not authorized or consumed, and no candidate can be frozen. Starting A1 would therefore violate the declared methodology.

**V9_NOT_READY_FOR_PAPER**  
**A1 = NOT_STARTED**  
**PAPER_VALIDATED = false**  
**LIVE_NOT_AUTHORIZED**

### Shortest defensible next scientific path

Do not tune H8 or consume neighboring trials. The next performance trial may occur only after external/primary evidence plus the existing causal historical data jointly determine **one exact, materially distinct, predeclared single-change mechanism** without evaluation peeking, and both deterministic methodology and the Qwen council authorize that exact test. If no such specification exists, preserving trial 870 is the correct result.
