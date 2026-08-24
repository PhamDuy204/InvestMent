# Parallel Paper-Readiness and Multi-Market Research Design

Date: 2026-08-24  
Repository: `PhamDuy204/InvestMent`  
Branch: `v11-root-cause-paper-readiness`  
Design status: user approved parallel Option 2 and Option 3 on 2026-08-24  
Execution authorization: research, backtest, simulation, and public-data paper infrastructure only  
Invariant: `LIVE_NOT_AUTHORIZED`

## 1. Purpose

Run two independent development lanes:

- **Lane A — Prospective evidence gate:** make the current frozen V17 DEVELOPMENT protocol executable, metadata-only, fail-closed, and auditable.
- **Lane B — Multi-market substrate:** widen the research platform through incremental data/accounting/execution pilots without changing V17 or treating wider coverage as evidence of alpha.

The lanes may proceed concurrently because they do not share outcome data or strategy selection. They must use separate tests and checkpoints. Only one integrator edits and commits shared files.

Broader markets increase the number of falsifiable economic hypotheses, not the truth of any hypothesis. Every family remains independently predeclared, attributed, trial-counted, and rejectable.

## 2. Fresh state at design time

Verified on 2026-08-24:

- `LATEST=version_32`.
- Local and remote branch SHA: `5ce712bfc5b05007abe40046aef8abc98be8f1c4`.
- Worktree clean; PR #8 open; exact-SHA V5 CI run 520 succeeded.
- V17 DEVELOPMENT remains `2026-08-24T06:00:00Z` through `2026-08-31T06:00:00Z`.
- Trial 871 is unauthorized and unconsumed.
- Candidate is not frozen; `READY_TO_START_PAPER=false`; `A1=NOT_STARTED`.
- L2 and positioning recorders are running, research-only, and reported zero errors.
- No post-boundary H12 return, label, PnL, Sharpe, or indirect outcome aggregate was opened during reconciliation.

## 3. Non-negotiable isolation

### 3.1 V17 isolation

Lane B must not:

- alter the fixed 21-symbol V17 universe;
- change `top_of_book_imbalance`, the H12 horizon, sampling cadence, boundary, split, or coverage rules;
- use V17 DEVELOPMENT or UNTOUCHED outcomes;
- consume trial 871;
- supply a model, threshold, sign flip, ranking, or ensemble to V17;
- relabel a Lane B result as a continuation of V17.

### 3.2 Execution isolation

Production research and paper source must not call private mutation methods, including order creation/cancellation, leverage or margin changes, borrowing, repayment, transfer, or withdrawal.

All permitted paper decisions terminate at:

`public market data → frozen candidate → SimulatedBroker → ExecutionSimulatorV8`

### 3.3 Outcome isolation

Before V17 DEVELOPMENT eligibility, Lane A may read only the current recorder's exact projected row fields `event_time`, `available_at`, `captured_at`, `source`, `source_id`, `symbol`, `update_id`, `data_version`, and opaque row `checksum`, plus file path/size/sidecar checksum and recorder health/error counters. Venue/instrument normalization belongs to Lane B and is not retrofitted into V17 evidence.

Inputs containing outcome-bearing fields such as return, label, PnL, profit, Sharpe, target, realized edge, or future price are rejected before evaluation.

## 4. Lane A — Executable prospective evidence gate

### 4.1 Root cause

The current DEVELOPMENT rules exist in versioned Markdown/JSON but no production evaluator enforces:

- seven complete contiguous days;
- at least 20 of 21 symbols at every eligible hour;
- at least 95% hourly presence per symbol;
- a prospective reset after a common outage exceeding 15 minutes;
- deny-by-default outcome access;
- trial/readiness invariants while evidence is incomplete.

### 4.2 Minimal component

Add one focused prospective-gate module and a thin CLI. It must reuse existing timestamp/checksum helpers where practical and must not add a framework.

Inputs:

- immutable boundary manifest plus expected SHA-256;
- L2 metadata rows only;
- recorder health and finalized-file checksum results;
- explicit audit cutoff.

Outputs:

- `COLLECTING`;
- `RESET_REQUIRED`;
- `DEVELOPMENT_ELIGIBLE`;
- `INVALID_METADATA`.

Every output includes:

- boundary and audit hashes;
- covered interval;
- completed-hour symbol counts;
- per-symbol hourly coverage;
- maximum per-symbol and common gaps;
- checksum/schema/time-contract violations;
- accessed field names and time ranges;
- explicit `outcomes_opened=false`;
- `trial_871_authorized=false`;
- `trial_871_consumed=false`;
- `candidate_frozen=false`;
- `READY_TO_START_PAPER=false`;
- `A1=NOT_STARTED`;
- `LIVE_NOT_AUTHORIZED`.

`GateStatus` is separate from the Section 8 candidate state machine. `DEVELOPMENT_ELIGIBLE` authorizes only the separately frozen parameter-free two-half diagnostic; only that status permits the explicit state transition `COLLECTING → DEVELOPMENT_LOCKED`. The evaluator never mutates state or a manifest, starts a diagnostic, freezes a candidate, consumes a trial, or changes paper readiness.

Coverage semantics are exact and deterministic:

- the manifest defines exactly 168 eligible UTC intervals `[h,h+1)` wholly contained in `[development_start, development_end)`;
- progress audits evaluate only eligible intervals completed by `min(audit_cutoff, development_end)`; an in-progress hour is excluded rather than scored as missing;
- each interval has one decision timestamp `d=h+1`; a symbol is present iff its latest strict-projection-valid row from a finalized file with a verified sidecar satisfies `available_at <= captured_at <= d` and `d - captured_at <= 15 minutes`;
- every eligible decision timestamp must contain usable L2 for at least 20 of the 21 expected symbols;
- each expected symbol must be present in at least 160 of the final 168 eligible hours; progress output reports the numerator and completed-hour denominator but cannot return `DEVELOPMENT_ELIGIBLE`;
- a common outage is a continuous interval longer than 15 minutes with no admitted valid row from any expected symbol; gaps from the development boundary to the first row and from the last row to the evaluated cutoff are included;
- symbol-specific gaps are reported separately and governed by the hourly rules;
- the Lane A row identity is `(data_version, source, symbol, captured_at, checksum)`; a duplicate identity, non-monotonic capture sequence, or timestamp outside the manifest/audit window returns `INVALID_METADATA`; repeated exchange `source_id/update_id` is allowed for unchanged REST snapshots and is reported rather than treated as an event-stream guarantee;
- `DEVELOPMENT_ELIGIBLE` is impossible until `audit_cutoff >= development_end`, all 168 hours and every other rule pass, and every required file is finalized and checksummed;
- after `audit_cutoff >= development_end` and all required files are finalized, any failed 20-of-21 or 160-of-168 coverage rule returns `RESET_REQUIRED` and uses the Section 4.3 new-epoch procedure;
- `COLLECTING` is permitted only before `development_end` or while a required completed-interval file remains active/unfinalized; every blocking file is listed in the result, and an active WAL is never read as evidence.

### 4.3 Boundary lock

Do not edit V32 history. On `RESET_REQUIRED`, the evaluator makes no state or manifest change. The integrator must commit a new immutable epoch manifest with new prospective DEVELOPMENT start/end, purge, untouched times, and hashes; evaluation remains `COLLECTING` against that new manifest.

A new governance checkpoint records:

- source V32 boundary path;
- source Git SHA;
- canonical SHA-256 of the boundary JSON;
- versioned strict metadata allowlist projection fixed to the nine current-recorder row fields above;
- deny-by-default rejection of every unrecognized field at every nesting level;
- evaluator code/config hashes.

A changed boundary or hash fails closed. The metadata reader exposes only the strict allowlist projection. Tests use a sentinel accessor that fails if any forbidden field or value is requested and prove that no outcome reader is instantiated. A reset creates a new epoch and new prospective times before any outcome is opened.

Lane A canonicalization uses domain `forward-l2-gate-v1` plus UTF-8 JSON with sorted keys, fixed separators, POSIX repository-relative paths, UTC RFC 3339 timestamps at fixed microsecond precision, exact integers, and finite base-10 strings for non-integer numbers. Boundary/config/audit schemas are versioned. Row identities sort lexicographically; finalized-file tuples `(relative_path, size, sidecar_sha256)` sort by path. The result hash is SHA-256 over the canonical result object excluding `result_hash` and including: boundary bytes/hash, gate config bytes/hash, evaluator source hashes, audit cutoff, sorted row identities, sorted file tuples, recorder-health input hash, accessed field names/ranges, counts/coverage/gaps/violations, verdict, and all safety invariants.

`INVALID_METADATA` never opens outcomes or advances Section 8. Results include `failure_scope=IMMUTABLE_INPUT` or `TRANSIENT_IO`. Invalid immutable input/provenance makes that epoch unusable; only a new Section 4.3 epoch may proceed. A transient unreadable artifact may be rerun in the same epoch only when its bytes and expected hash are unchanged, and the new result links the immutable prior failure event.

### 4.4 Weakness logging

Reuse the existing failure-memory pattern, but append a dedicated JSONL weakness event when the current CSV cannot express governance fields.

Every Lane A run records checks for:

`LEAKAGE, DEPENDENCE, MULTIPLE_TESTING, DATA, REGIME, COST, EXECUTION, RISK, REPRODUCIBILITY, GOVERNANCE`

A category may report no finding only with the evidence check performed. Each event contains a stable event ID, run/result hash, epoch, timestamp, severity, category, claim, evidence references, root cause, containment, remediation, retest, owner, and status. Any blocker keeps candidate freeze and paper readiness false.

### 4.5 Lane A tests

Synthetic tests must cover:

1. Seven clean complete days pass; six days and 23 hours remain `COLLECTING`.
2. Exact start/end boundaries, a partial-hour cutoff, and an active WAL obey the finalized-completed-hour rules; every blocking file is named.
3. Nineteen symbols in one eligible hour fail; twenty pass that rule without masking a common outage.
4. One symbol present in 159 of 168 finalized hours returns `RESET_REQUIRED`; 160 passes the per-symbol rule.
5. A common gap strictly over 15 minutes returns `RESET_REQUIRED`; exactly 15 minutes does not.
6. Missing/corrupt sidecar, mixed schema, duplicate row identity, non-monotonic capture time, out-of-window/future timestamp, or mutated manifest/config/code hash fails closed; repeated exchange update IDs remain valid snapshot metadata.
7. Any field outside the strict allowlist, including a nested or renamed outcome sentinel, fails before row parsing; the outcome reader is never instantiated.
8. Eligibility does not create/authorize trial 871, freeze a candidate, or change A1/paper state.
9. Re-running identical inputs on a different absolute path produces the same Lane A canonical result hash; changing any declared hash input changes it.
10. Immutable-input invalidity forces a new epoch; a recorded transient I/O failure can rerun only with byte/hash identity unchanged.
11. A fake filesystem/process controller proves no write, restart, stop, signal, or service-control operation is invoked on recorder paths.

## 5. Lane B — Incremental multi-market substrate

Lane B is a sequence of small vertical slices, not a request to implement every market contract at once. The only implementation authorization in this checkpoint is Lane A plus B1. B2–B5 are non-binding designs; each requires a separately reviewed slice specification, deterministic acceptance tests, and checkpoint before implementation.

### 5.1 Existing primitives to preserve

- `ExecutionSimulatorV8`: observed-depth walk with no extrapolation.
- `PaperRuntimeV9`, `ShadowPaperEngine`, `SimulatedBroker`: only paper execution path.
- `point_in_time_v8.py`: base causal-time validator.
- `rolling_universe`: base trailing-liquidity selection logic.
- `cost_aware_cross_sectional_backtest`: base crypto relative-value accounting.
- `V7TrialRegistry` and V9 governance: historical numbering and readiness vocabulary.
- failure ledger, `do_not_repeat.json`, `EvidenceCard`, statistics, basis, and macro helpers.

No parallel simulator, universe engine, trial registry, or paper broker is created while these primitives can be extended.

### 5.2 Slice B1 — Correct execution semantics and replay provenance

This slice may proceed concurrently with Lane A because it uses synthetic books only.

Add the smallest immutable observation payload needed by the existing runtime:

- venue and canonical instrument ID;
- event, source-available, ingest/capture, decision, and execution times;
- source ID/update ID;
- normalized bid/ask levels;
- canonical book checksum.

Canonical bytes use a versioned domain prefix plus UTF-8 JSON with sorted keys and fixed separators. Timestamps are UTC RFC 3339 at fixed microsecond precision; economic numbers are validated finite base-10 strings, not binary-float spellings. Hashes use SHA-256 and persist their encoding version.

Accepted observations require `event_time <= source_available_at <= captured_at <= decision_time <= execution_time`; equality is allowed. `decision_time - source_available_at` must not exceed the freeze manifest's immutable `max_staleness`. Duplicate source/update identity, reordered timestamps, tampered hashes, or a freeze manifest ID/hash mismatch fail closed.

Persist accepted observations and intents in the decision journal.

Execution status becomes explicit:

- `FILLED`;
- `PARTIALLY_FILLED`;
- `REJECTED_EMPTY_BOOK`;
- `REJECTED_CROSSED_BOOK`;
- `REJECTED_STALE_DATA`;
- `REJECTED_INVALID_TIME`;
- `REJECTED_INVALID_FREEZE`.

Notional fields are non-negative quote-currency amounts; exposure is signed; fees are non-negative costs; funding and PnL are signed quote-currency cash flows. A normalized return is derived from NAV once, never mixed into cash-flow fields.

For an accepted order, require `requested_notional > 0` and `0 < filled_notional <= requested_notional` before applying:

`filled_exposure = requested_exposure × filled_notional / requested_notional`

The sign of a short exposure is preserved. Exactly full fill equals requested exposure. Only filled exposure and filled notional enter recovered positions, funding, fees, and PnL, once. Zero/invalid notional is rejected. Rejected intents create immutable audit records and no position/outcome.

A pure offline replay must regenerate the same intent/fill hashes without network access and detect a reordered event, duplicate update, or tampered journal row. B1 remains engineering-only by default: the runtime accepts only a verified immutable freeze manifest containing manifest ID/hash and `max_staleness`, never a caller-supplied boolean/hash, and V17 A1 remains disabled until Lane A plus the separate discovery/freeze gates authorize it.

The production transport/client layer is strict-allowlist read-only: only declared public market-data endpoints and GET/WSS subscription operations are permitted. Authenticated/private methods, non-allowlisted routes, and state-mutating HTTP methods fail closed. A fake transport test rejects aliases, wrappers, dynamic route construction, or any request outside this allowlist.

### 5.3 Slice B2 — Point-in-time dynamic crypto-universe audit

Do not activate this universe for V17.

Extend `rolling_universe` minimally with:

- trailing data only;
- listing/history age;
- fixed reconstitution schedule;
- spread/depth/data-quality criteria;
- deterministic ties;
- inclusion/exclusion reason codes;
- immutable snapshots;
- retained excluded/delisted history.

This slice is synthetic and metadata-only until a separate epoch is predeclared.

### 5.4 Slice B3 — Cross-venue executability data pilot

This is a public-data pilot, not an arbitrage PnL test.

Requirements before any profitability calculation:

- exactly defined equivalent instruments on at least two venues;
- `load_markets` metadata and checked public capabilities;
- venue-normalized tick, lot, multiplier, quote and settlement currency;
- exchange time plus local receive/available time;
- sequence/update IDs, reconnect rules, and gap detection;
- synchronized paired observations inside frozen `tau_sync`;
- stale/crossed/missing-timestamp rejection;
- no depth extrapolation;
- per-venue fee/version provenance.

REST snapshots may support capability and slow-data checks. Latency-sensitive edge requires venue WebSocket reconstruction using each exchange's sequence rules. Missing/null exchange timestamps remain missing and are never replaced by a fabricated exchange time.

No transfer or withdrawal is called or simulated per trade. Future route research assumes pre-positioned inventory and models rebalance cost/risk separately.

### 5.5 Slice B4 — Daily US ETF accounting pilot

After B1 time and execution contracts pass, add a data/accounting-only pilot for 10–20 liquid index/sector ETFs.

It must support:

- exchange calendar, holidays, early closes, and sessions;
- point-in-time universe membership;
- split/dividend/corporate-action semantics;
- quote currency and FX attribution where applicable;
- short/borrow eligibility as unknown unless sourced;
- instrument-specific tick/lot/fee semantics;
- no forward-fill across a closed market presented as executable.

The first output is data integrity and accounting reconciliation, not alpha or a trial.

### 5.6 Slice B5 — Small liquid futures accounting pilot

Begin only after the ETF calendar/instrument layer is verified.

Use actual contracts for execution and accounting:

- contract multiplier, tick/lot, expiry, settlement and margin;
- explicit roll decision and roll cost;
- variation margin and liquidation buffer;
- active/front continuous series for signal research only;
- no synthetic continuous price used as a held executable contract.

### 5.7 Deferred markets

G10 FX waits for spot/forward/rollover and calendar semantics. Individual equities wait for point-in-time constituents, delistings, corporate actions, and borrow/short availability. Options, market making, ABIDES/JAX-LOB, Hawkes, DL, and RL remain deferred until a simple mechanism and calibrated execution substrate survive OOS tests.

## 6. Strategy-family governance

Platform expansion and hypothesis evaluation are separate.

Families are namespaced by `epoch_id`, `family_id`, and `hypothesis_id`. Each family has an independent:

- economic mechanism;
- data adequacy gate;
- predeclaration and stopping rule;
- trial budget;
- cost/fill/latency assumptions;
- candidate freeze;
- PnL and risk attribution.

The current V17 family remains first. If its discovery diagnostic fails or is inconclusive, exactly one next family is selected by:

`expected information gain / scientific degrees of freedom / implementation cost`

Lane B may make a family technically testable, but it may not test all families concurrently or combine weak PnL lines.

## 7. Shared risk and accounting contract

Every future candidate reports gross and net performance plus attributable:

- price return;
- funding/carry;
- fees and spread;
- slippage, impact, latency;
- partial/unfilled/rejected notional;
- borrow, roll, FX, tax, rebalance and margin components when applicable;
- instrument, venue, asset-class, factor/cluster, currency and family concentration;
- drawdown, recovery, block CVaR and stressed tail dependence.

Risk scaling cannot turn a rejected alpha mechanism into an admitted one.

## 8. State transitions

Allowed states:

`COLLECTING → DEVELOPMENT_LOCKED → DISCOVERY_EVALUATED → EXTENDED_PROSPECTIVE → CANDIDATE_FROZEN → UNTOUCHED_EVALUATED → READY_TO_START_PAPER → PAPER_RUNNING → PAPER_VALIDATED`

`REJECTED` and `INVALID` terminate that candidate. A retry requires a new candidate and, when necessary, a new epoch.

Lane B infrastructure checkpoints do not advance the V17 state machine.

## 9. Parallel work and integration rules

| Ownership | Files/responsibility | Rule |
|---|---|---|
| Lane A | prospective gate module, metadata-only CLI, gate tests | No paper-runtime or journal edit |
| Lane B1 | immutable observation/replay module, execution/journal tests | No V17 boundary, trial, or gate edit |
| Integrator only | shared PIT/checksum helpers, runtime, journal, governance contracts | Serialize edits and land the shared contract before dependent work |
| Read-only reviewers | all modules and artifacts within evidence restrictions | No writes or recorder/process control |

- Lane A and B1 may be developed in parallel only in isolated, non-overlapping files and commits.
- If both lanes require a shared point-in-time, governance, journal, or runtime contract, the integrator sequences that shared change before either dependent slice; agents never edit the shared file concurrently.
- B2–B5 are sequenced by their data/accounting dependencies.
- Agents may perform independent read-only review or isolated non-overlapping implementation tasks.
- One integrator reviews and commits each checkpoint.
- Each non-trivial change begins with one focused failing test.
- Focused tests pass before full pytest, Ruff, compileall, diff/JSON validation, local/remote SHA verification, and exact-SHA CI.
- PR #8 remains open and is never auto-merged.

## 10. Checkpoint policy

Do not create a new paper-readiness version for activity alone.

A new version is justified by:

- enforced prospective gate;
- verified or reset boundary;
- corrected execution accounting and deterministic replay;
- accepted/rejected hypothesis;
- validated market data/accounting contract;
- candidate freeze or readiness transition.

## 11. Acceptance criteria for the first parallel milestone

Lane A:

- metadata-only gate passes all synthetic tests;
- current data returns `COLLECTING`, not eligible;
- no outcome fields/ranges opened;
- boundary and output hashes are deterministic;
- trial/readiness/live invariants remain false/unauthorized.

Lane B1:

- zero/invalid, exact-full, signed-short, partial-fill and reject cases obey the notional/exposure/currency invariants;
- partial-fill exposure, cost, funding and PnL reconcile to filled quantity without double counting;
- rejects are immutable, positionless events;
- timestamp equality/order, staleness, duplicate update, canonical bytes, checksum and freeze-manifest validation fail closed;
- identical offline replay is deterministic and tampered/reordered journals are detected;
- a production transport allowlist permits only declared public read-only market-data requests; the fake transport rejects every private, authenticated, mutating, aliased, wrapped, dynamic, or otherwise non-allowlisted request.

Integration:

- recorders remain running and unchanged;
- full suite and static checks pass;
- code and documents are committed/pushed as the existing user;
- explicit local and remote SHA match;
- exact-SHA CI is inspected;
- PR #8 is not merged.
