# V21 Cohort-Calibrated Risk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a V21 paper-only execution path that calibrates by route-quality cohort, uses a 90% risk-confidence policy, and exits riskier positions sooner.

**Architecture:** Extend the existing V17 orchestration with backward-compatible probe/exit hooks, add a small V21 calibration module that reuses V20 EV math, and add a V21 runner that reuses V20 funding/stream/runtime helpers. Extend monitoring schema recognition only as needed for the new runner.

**Tech Stack:** Python 3, SQLite, pytest, CCXT Pro public WebSocket, existing Next.js monitor.

**Spec:** `docs/v21-cohort-calibrated-risk-design.md`

## Global Constraints

- Paper/simulation only; public data only; no authenticated exchange actions.
- Keep after-cost EV positive; do not lower the gate merely to create trades.
- Preserve 20x/30x/40x paper leverage buckets and current contract/funding accounting.
- Do not alter the running V20 process until V21 verification passes.

---

### Task 1: Backward-compatible orchestration hooks

**Files:** `scripts/run_arbitrage_paper_v17.py`, `tests/test_arbitrage_v20.py`

- [ ] Write failing tests for custom probe metadata/priority and custom exit decision/immediate reasons.
- [ ] Run the focused tests and verify the new behavior is absent.
- [ ] Add only optional hooks with V17-V20 defaults unchanged.
- [ ] Re-run focused tests.

### Task 2: V21 cohort calibration

**Files:** `src/crypto_research/maker_v21.py`, `tests/test_maker_v21.py`

- [ ] Write failing tests for capture buckets, audit events, 90% one-sided Wilson calibration, and 90% empirical acceptance floor.
- [ ] Verify RED.
- [ ] Implement the minimal SQLite event/stats calibration and EV wrapper using V20 attempt-EV math.
- [ ] Verify GREEN.

### Task 3: V21 runner and safer exit

**Files:** `scripts/run_arbitrage_paper_v21.py`, `tests/test_arbitrage_v21.py`

- [ ] Write failing tests for high-quality shadow selection, cohort outcome recording, V21 entry decision, and faster exit rules.
- [ ] Verify RED.
- [ ] Implement V21 by reusing V20 funding/stream helpers and V17 orchestration hooks.
- [ ] Verify GREEN.

### Task 4: Monitoring compatibility and verification

**Files:** `src/crypto_research/monitoring_v13.py`, `scripts/publish_monitoring_v13.py`, `monitoring-web/lib/telemetry.ts`, `monitoring-web/components/dashboard.tsx`, existing monitoring tests.

- [ ] Add failing compatibility tests for V21 schemas.
- [ ] Add minimal V21 schema aliases/labels while reusing V20 account-level fields.
- [ ] Run Python focused/full checks, Ruff, compileall, frontend tests/lint/build, and a V21 paper-only CLI smoke.
- [ ] Commit only tracked V21 source/docs/tests; leave historical artifacts untouched.
