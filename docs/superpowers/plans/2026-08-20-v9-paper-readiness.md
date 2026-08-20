# V9 Paper Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the verified V8 research head into a causally governed, Qwen-audited, paper-runtime-capable V9 and issue an evidence-based readiness verdict without consuming trial 870 unless a legitimate test exists.

**Architecture:** Keep V7/V8 research and execution primitives. Add only V9 governance/council/runtime adapters, V9 artifacts, and focused tests; MiroFish stays an optional external sidecar.

**Tech Stack:** Python 3.11+, pandas, pyarrow, ccxt public market data, Groq SDK, pytest, ruff, standard library JSON/hash/fsync; no new repository dependency.

**Spec:** `docs/superpowers/specs/2026-08-20-v9-paper-readiness-design.md`

## Global Constraints
- Research/backtest/simulation/shadow-paper/paper only; no live exchange order/cancel/private-account path.
- V8 source SHA is `3eaf36efbcc8933bab173df521bb4a4c8897ab60`; V8 history and registry are immutable.
- V9 prospective evidence starts at `2026-08-20T10:34:19Z`; pre-boundary forward data is development/calibration only.
- First V9 performance trial is 870 only if a predeclared materially distinct test is independently admitted.
- Qwen only for all four council roles; no GPT fallback; one same-model repair attempt maximum.
- MiroFish is optional scenario/stress evidence only and must stay localhost-only if configured.
- No new dependency unless current declared dependencies and stdlib cannot satisfy a requirement.

---

### Task 1: Reconcile and audit immutable inputs

**Files:**
- Create: `artifacts/multi_asset_v9/source_reconciliation.json`
- Create: `artifacts/multi_asset_v9/execution_observatory.json`
- Create: `artifacts/multi_asset_v9/positioning_observatory.json`

**Interfaces:**
- Consumes: committed `v9_start_manifest.json`, V8 artifact hashes, PC-local L2/positioning parquet/WAL.
- Produces: deterministic audit summaries used by readiness and council context.

- [ ] Create `.venv` from the existing `pyproject.toml` extras; do not change dependencies.
- [ ] Run `python -m pytest -q` on untouched V8-derived code and record the fresh baseline result.
- [ ] Audit sidecars, row/checksum uniqueness, causal timestamp inequalities, book validity/depth monotonicity, per-symbol coverage/gaps, schema separation, recorder PID freshness, and restart discontinuity.
- [ ] Preserve `v8-positioning-1` as `AUDIT_ONLY`; never rewrite its timestamps.
- [ ] Write compact reconciliation/observatory JSON without copying raw data into Git.

### Task 2: V9 governance and readiness

**Files:**
- Create: `tests/test_v9_governance.py`
- Create: `src/crypto_research/governance_v9.py`

**Interfaces:**
- Produces: `validate_trial_continuity(registry_path, expected_max=869, next_trial=870) -> dict`, `build_paper_readiness(...) -> dict`, and `verify_candidate_freeze(path) -> bool`.

- [ ] Write failing tests proving trial 870 cannot be duplicated/skipped, readiness is false without science/freeze, and a candidate freeze hash becomes invalid after mutation.
- [ ] Run focused tests and confirm RED due to missing V9 functions.
- [ ] Implement only the canonical hashing, continuity checks, freeze verification, and categorical seven-category readiness aggregation needed by the tests.
- [ ] Run focused tests and confirm GREEN.
- [ ] Reuse V8 registry unchanged as the inherited V9 registry baseline; do not append a row when no performance test occurs.

### Task 3: Restartable paper runtime on SimulatedBroker only

**Files:**
- Create: `tests/test_paper_v9.py`
- Create: `src/crypto_research/paper_v9.py`
- Create: `scripts/run_v9_paper.py`

**Interfaces:**
- Consumes: `ShadowPaperEngine`, `SimulatedBroker`, observed public order books, frozen or engineering-only candidate metadata.
- Produces: append-only journal plus state/health JSON and deterministic engineering smoke result.

- [ ] Write failing tests for stale-data rejection, duplicate-decision prevention across restart, state recovery, partial/unfilled accounting, and absence of any live-order client/method.
- [ ] Run focused tests and confirm RED.
- [ ] Implement the smallest file-backed wrapper around `ShadowPaperEngine`; derive state from the journal instead of introducing a database.
- [ ] Add a CLI that defaults to deterministic replay/smoke and refuses A1 mode without a valid candidate freeze.
- [ ] Run focused tests and confirm GREEN, then run one fixed replay twice and verify identical decision hash plus restart behavior.

### Task 4: Qwen-only council and optional MiroFish registry

**Files:**
- Create: `tests/test_groq_v9.py`
- Create: `src/crypto_research/groq_v9.py`
- Create: `scripts/run_v9_groq_council.py`
- Create: `src/crypto_research/mirofish_v9.py`
- Create: `artifacts/multi_asset_v9/mirofish_scenario_registry.jsonl`

**Interfaces:**
- Consumes: Groq live model list and sanitized V9 evidence context.
- Produces: final structured role outputs with `ALLOW_TEST`, `REJECT_NO_TEST`, or `NEED_MORE_EVIDENCE`; MiroFish registry validation for actual runs only.

- [ ] Write failing tests proving all roles use one Qwen model, JSON is validated locally, malformed JSON receives at most one same-model repair, and no GPT fallback is possible.
- [ ] Run focused tests and confirm RED.
- [ ] Implement Qwen selection and local shape validation by reusing V7 hypothesis validation/sanitization where safe; no multi-agent framework.
- [ ] Add deterministic admission conjunction so LLM approval alone never authorizes a performance trial.
- [ ] Add a tiny MiroFish registry row validator enforcing source/output hashes, run classification, and the no-alpha role contract.
- [ ] Locate/inspect the approved external `groq_call.py` without reading any secret file; add runtime model selection only if missing.
- [ ] Query Groq's live models, run a same-model smoke, then the four-role council; persist only final structured output.
- [ ] Pin official MiroFish SHA in an external sidecar; if Zep requirements are absent, record `MIROFISH_NOT_CONFIGURED_EXTERNAL_DEPENDENCY` and do not fabricate configuration.

### Task 5: Prospective recorders, final artifacts, and GitHub

**Files:**
- Create/update: `artifacts/multi_asset_v9/multiple_testing.json`
- Create/update: `artifacts/multi_asset_v9/paper_readiness.json`
- Create/update: `artifacts/multi_asset_v9/final_report.md`
- Create only if justified: `artifacts/multi_asset_v9/candidate_freeze.json`

**Interfaces:**
- Consumes: Tasks 1–4 evidence and existing V7/V8 scientific gates.
- Produces: final categorical V9 verdict and auditable GitHub PR.

- [ ] Smoke the existing L2 and positioning recorders into V9-local directories, then start continuous public-data recorders only after the smoke passes; record PID/health paths and do not count pre-boundary data as A1.
- [ ] Apply deterministic council/science gate. If no predeclared candidate is legitimately testable, leave trial 870 unconsumed and do not create a freeze.
- [ ] Run deterministic paper replay in engineering-only mode; do not call it A1 without a freeze.
- [ ] Generate readiness/final-report artifacts listing exact blockers and `LIVE_NOT_AUTHORIZED` unconditionally.
- [ ] Run fresh `python -m pytest -q`, `ruff check .`, `python -m compileall -q src scripts tests`, focused safety tests, registry integrity, freeze validation, and tracked secret-shaped scan.
- [ ] Commit logically, push `v9-paper-readiness`, create a PR to `v8-execution-liquidity-shadow`, fetch exact remote HEAD, rerun verification on that exact SHA, and inspect GitHub Actions for that exact commit.
