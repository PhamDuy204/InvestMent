# V8 Final Research Report — Execution, Liquidity, Positioning, Macro, Sentiment Reliability

## Scope and safety

V8 remained research/backtest/simulation/shadow-paper only. No live Binance order, cancellation, withdrawal, transfer, borrow/repay, exchange-side leverage or margin mutation, OTP flow, trading API key, or signed private trading request was used. Forward collectors consume public market data only; the shadow engine routes decisions only through `SimulatedBroker` / `ExecutionSimulatorV8`.

## Source-of-truth reconciliation

- Repository: `PhamDuy204/InvestMent`
- V7 remote branch: `v7-factor-observatory`, PR #4, remote head observed during this audit: `9713d98b2472957bf8ee2bde107a18a3bacee5df`.
- V8 branch: `v8-execution-liquidity-shadow`, PR #5.
- Existing synchronized V8 remote head before this continuation sync: `6c2adc7ea7f8692920f0af127f620992443594b4`.
- Local PC uses linked worktrees. Heavy raw/research data remains local; lightweight code/tests/manifests/artifacts are the GitHub synchronization surface.
- V7 remote final research artifact and local registry agree on trial continuity through 868 and the corrected H12 baseline.
- PR #4 prose contains stale CI wording relative to its later head: the current PR head's run #376 failed, while V8 PR #5 later root-fixed the CI invocation and run #398 passed.

## Trial continuity and corrected baseline

Performance trials remain append-only:

- V7 last performance trial: **868** (H7, rejected).
- V8 H8: **trial 869** exactly.
- Next performance trial: **870**.
- Trial 870 was deliberately **not consumed** because forward L2/positioning evidence is not mature enough for a causal performance test.

Corrected held-out H12 baseline:

- net: **-3.5286%**
- PF: **0.9092**
- Sharpe: **-0.6999**
- max DD: **6.9010%**

## V8-E1 / H8 — lagged-impact execution fragility

H8 was a single predeclared execution-risk test, not an L2 backfill. The causal candidate inputs were lagged RV12 and an Amihud-style lagged price-impact proxy. The policy could reduce only new/increased H12 exposure; it could not flip direction or boost above the inherited target.

**Result: `REJECTED_INNER`; factor not admitted.**

Held-out candidate:

- net: **-3.5774%**
- PF: **0.9076**
- Sharpe: **-0.7123**
- max DD: **6.8871%**
- positive incremental economic folds: **1/3**
- 20 bps stress net: **-5.9728%**
- +1h delay stress net: **-4.0460%**

Attribution:

- delay implementation-damage proxy improved slightly (`0.109862 -> 0.108489`), but portfolio economics worsened;
- wrong-side economic damage improved by about **28.83 bps**, while raw WRONG_SIDE count increased by **551**;
- forecast admission failed, evaluation net did not improve, evaluation Sharpe worsened, and both mandatory stresses remained negative.

No neighboring threshold/transform rescue was run. The H8 fingerprint is recorded in `do_not_repeat`.

## Forward execution / liquidity observatory

A public USD-M order-book recorder is running on the PC for **21 symbols**, writing local WAL/chunked parquet state and health metadata. At `2026-08-19T12:30:46Z` its health file reported:

- status: `RUNNING`
- PID: `1144925`
- cycles completed: **411**
- records appended: **8,631**
- errors: **0**

A separate verification observed the count increase from **8,421 to 8,442 (+21)** over one collection interval, so the recorder was not merely a stale process record.

Causal status remains **FORWARD_PENDING**. Current L2 must not be used to fabricate historical H12 book state.

`ExecutionSimulatorV8` walks only recorded book levels, reports partial/unfilled notional and an unmodeled tail rather than assuming infinite depth. This improves execution realism, but the forward sample is still too young for factor admission or calibration claims.

## Positioning / crowding observatory

A public Binance positioning recorder is running for the same 21-symbol universe. The first completed cycle wrote **126 rows** with **0 errors**, covering current OI, premium/funding and public long/short/taker-ratio families where available.

Status: **FORWARD_ONLY**. No rule such as `high long ratio -> BUY` is encoded. Historical backfill was not fabricated when the public interface could not support the required old first-seen history.

Therefore V8-E2 remains `NO_TEST_FORWARD_COVERAGE_NOT_MATURE` and trial 870 is untouched.

## Macro / policy observatory

The point-in-time macro layer records official schedule observations with `first_seen_at` / `available_at` semantics. Current forward schedule snapshots include BLS/BEA releases and Federal Reserve meeting dates.

Limitations are explicit:

- no local `FRED_API_KEY`, so no ALFRED vintage ingestion was performed;
- current schedule observations first seen on 2026-08-19 cannot be backdated into historical decisions;
- date-only FOMC meeting rows are excluded from precise H12 event flags;
- no historical consensus feed exists, so no macro surprise is fabricated.

V8-E3 is therefore an observatory/forward research layer, not an admitted performance factor.

## News / narrative / sentiment

The causal news module implements and tests:

- timestamp-aware normalization and content hashing;
- `first_seen_at` causal filtering;
- near-duplicate narrative clustering;
- structured LLM feature validation;
- rejection of direct trade/order/leverage instructions.

However, this execution environment currently has **no timestamp-provenanced news corpus and no `GROQ_API_KEY` in the process environment**. Consequently `sentiment_observatory.json` is intentionally `DATA_LIMITATION_NO_CORPUS_NO_TEST`, with zero labeled rows. No historical sentiment was invented and no performance trial was consumed.

## Groq council / current model compatibility

V7 historical council artifacts remain part of the inherited evidence and show Groq-assisted research iterations, including an independent Research Judge veto. V8 did not rerun Groq locally because no Groq key was present in the execution environment.

The V8 structured-output contract remains compatible with the currently documented Groq GPT-OSS strict-schema models; model discovery should still be done at runtime before future calls rather than hardcoding an old catalog.

## MiroFish forward scenario sidecar

MiroFish is retained only as an external forward scenario reference/sidecar. It is not vendored into this repo and is not used for historical causal evidence.

Current status: `SCENARIO_RESEARCH_ONLY_NOT_CONFIGURED`.

- locked forward predictions: **0**
- scenario registry exists and remains empty rather than fabricating a run;
- minimum evidence before factor consideration remains **>=12 distinct events** and **>=2 temporal groups**;
- no alpha trial is consumed by scenario infrastructure.

## Reuse decisions

V8 intentionally avoids wholesale framework migration:

- TradingAgents: architecture reference only; existing council already provides the smaller role/debate/judge/logging pattern.
- FinGPT: defer as a sentiment benchmark until a real labeled validation sample exists.
- Qlib: concept reference only; existing fold/trial infrastructure already covers the needed workflow.
- ABIDES-JPMC: microstructure/latency concept reference only; no claim that its market model is Binance.
- MiroFish: external forward sidecar only; no historical oracle use.

## Shadow paper infrastructure

`ShadowPaperEngine` is implemented with `SimulatedBroker`, append-only decision/outcome journaling, candidate hash, simulated fill, fees/slippage fields, funding input and A1 eligibility rules.

Because there is no frozen candidate, any current shadow decision is **ENGINEERING_ONLY**, not untouched A1 evidence. No historical engineering record may be relabeled as A1 later.

## Multiple testing / factor admission

- performance trial count: **869**
- next trial: **870**
- current V8 admitted factors: **0**
- DSR: not recomputed because the complete comparable historical trial metric distribution is incomplete
- PBO/CSCV: not recomputed because there is no aligned complete V8 candidate-return matrix
- CPCV is not claimed
- no H8 rescue grid and no trial 870 placeholder/reservation

## Verification

Fresh PC verification after restoring the missing synchronized V7 council summary and Ruff-normalizing four inherited V7 script import blocks:

- `.venv/bin/python -m pytest -q` -> **177 passed**
- `.venv/bin/ruff check .` -> **All checks passed**
- `.venv/bin/python -m compileall -q src scripts tests` -> exit 0
- public L2 recorder health count increased during verification
- static/live-order safety tests remain in the suite

GitHub V8 PR #5 head `6c2adc7...` had GitHub Actions run #402 complete successfully before this continuation sync.

## Readiness scorecard

Latest stored heuristic readiness index: **52.89 / 100** (`HEURISTIC_READINESS_INDEX_NOT_PROBABILITY`). Strongest areas are causal integrity and multiple-testing discipline; weakest are forward evidence, signal evidence, and stress robustness.

There is **no final candidate**, **no freeze hash**, **no freeze timestamp**, and **no A1 window**. The required >=30 untouched calendar days and >=40 eligible H12 observations therefore have not started.

## Final decision

V8 materially improves research infrastructure and execution observability, but it has not found a robust admitted alpha/reliability factor. H8 is falsified under the predeclared mapping, forward L2/positioning data is immature, macro/news/scenario evidence is not historically causal enough for another performance trial, and no candidate can be frozen.

**NEEDS_MORE_RESEARCH**


## Continuation audit — 2026-08-19 causal recorder integrity

A fresh PC audit found a causal timestamp defect in the original positioning recorder schema. In `v8-positioning-1`, one batch-level `first_seen_at` was captured before serial HTTP calls; **67/252** retained rows therefore had `event_time > available_at`. Those rows remain on disk for auditability but are now **superseded and excluded from causal feature use**.

A regression test reproduced the defect before the fix. The recorder now stamps `first_seen_at` after each individual public HTTP response and writes schema **`v8-positioning-2`**. The first post-restart cycle produced **126 rows across 21 symbols and 6 feature families**, with **0** `event_time > available_at` violations and **0** duplicate checksums.

The L2 forward recorder remains healthy and public-data-only. This audit inspected **14,940** current parquet+WAL rows across **21 symbols** with **0** duplicate checksums, **0** crossed books, **0** causal-ordering violations, and **0** depth-monotonicity violations.

This integrity fix is engineering-only and consumes **no performance trial**. Performance count remains **869** and trial **870 remains unconsumed** because fresh L2/positioning coverage is still far below a defensible temporal evidence window. No H8 rescue or parameter search was run.

`GROQ_API_KEY` and `FRED_API_KEY` are not present in the current MCP execution environment, so no Groq council rerun or ALFRED vintage ingestion is claimed in this continuation.

## Final provenance sync verification — 2026-08-19

The authenticated GitHub synchronization path was completed without force-pushing V7 or V8 history. The final provenance/data-artifact head verified before this report-only update was `6a9849774e95aedb159c59425ad499b74ff04264` on PR #5.

GitHub Actions run **#442** on that head completed successfully in a clean Ubuntu 24.04 / Python 3.11 environment:

- `python -m pytest -q` -> **198 passed**
- `ruff check src tests scripts/build_v8_execution_panel.py scripts/run_v8_h8_execution_fragility.py` -> **All checks passed**
- `python -m compileall -q src tests scripts` -> exit 0

The previously observed intermediate CI failures were remote synchronization drift rather than research-economics failures: remote V8 initially lacked the already-tested local `ccxt`/`pyarrow` dependencies, `ExecutionSimulatorV8`, and several inherited Ruff-only import normalizations. Those gaps were root-fixed and verified by the clean run above; no test was disabled and no H8 result was changed.

The lightweight V8 provenance set is now synchronized to GitHub, including the append-only experiment registry through trial 869, hypothesis/agent logs, failure ledger, factor/liquidity/positioning/macro/sentiment/scenario observatories, multiple-testing status, readiness scorecard, source/reuse audit, trial metric catalog, and final report. Raw forward parquet/WAL data remains PC-local by design.

At the last PC health checkpoint in this continuation, the public L2 recorder had reached **21,420 records across 1,020 cycles with 0 errors**. The corrected `v8-positioning-2` recorder remained alive with its first **126-row / 21-symbol / 6-family** clean cycle and **0 causal-ordering violations**. The older `v8-positioning-1` rows remain retained only for audit and are excluded from causal feature use.

Research status is unchanged by synchronization work: performance trial count = **869**, trial **870 remains unconsumed**, admitted V8 factors = **0**, freeze = **none**, A1 = **not started**, stored heuristic readiness index = **52.89/100**, and verdict = **NEEDS_MORE_RESEARCH**.
