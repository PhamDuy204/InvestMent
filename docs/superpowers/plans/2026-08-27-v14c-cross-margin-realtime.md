# V14-C Cross-Margin Realtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the running V14-B paper system to per-venue cross-margin portfolio allocation plus 2-second monitoring and visible per-order scenario projections.

**Architecture:** Extend the existing V14 runner in place so rollback remains available at commit `93887ca`. Reuse current V14 opportunity/position lifecycle, add cross-margin summary and global candidate sizing before opens, then expose those fields through the existing strict telemetry allow-list. Keep Runtime Cache and the read-only Next.js dashboard; reduce publisher/client polling instead of adding a new realtime service.

**Tech Stack:** Python, CCXT public order books, existing execution simulator, Next.js 16/React 19/TypeScript, Vercel Runtime Cache.

**Spec:** `docs/superpowers/specs/2026-08-27-v14c-cross-margin-realtime-design.md`

## Global Constraints
- PAPER / SIMULATION ONLY; no exchange credentials/private endpoints/create_order.
- Cross margin is per venue, never shared across exchanges.
- WATCH/negative-net opportunities cannot open trades.
- Maintenance margin is a labeled conservative stress estimate, not exact venue liquidation.
- Monitoring is PUBLIC · READ ONLY.
- No new dependency unless required; reuse existing helpers.

---

### Task 1: Cross-margin accounting and migration
**Files:** Modify `scripts/run_arbitrage_paper_v14.py`; Test `tests/test_arbitrage_v14.py`.
**Interfaces:** Produce `CROSS_MARGIN_PAPER_V1`, `_refresh_cross_margin_summary(state, marks_by_symbol=None)`, and in-place B→C state upgrade.
- [ ] Add failing tests for shared per-venue margin, current unrealized venue equity, stress maintenance, utilization cap, and preserving existing B positions during upgrade.
- [ ] Run focused tests and confirm RED.
- [ ] Implement the minimal C state/accounting changes.
- [ ] Run focused tests and confirm GREEN.

### Task 2: Portfolio-wide candidate allocator
**Files:** Modify `scripts/run_arbitrage_paper_v14.py`; Test `tests/test_arbitrage_v14.py`.
**Interfaces:** Candidate sizing returns gross target per candidate after net-edge weighting, single-pair cap, gross cap, and venue concentration/cross-margin constraints.
- [ ] Add failing tests where two opportunities share a constrained venue and allocator sizes/diversifies instead of consuming stale isolated reservations.
- [ ] Run focused tests and confirm RED.
- [ ] Implement deterministic edge-weighted allocation with venue concentration penalty and current margin recheck after every open.
- [ ] Run focused tests and confirm GREEN.

### Task 3: Telemetry C fields and 2-second publisher
**Files:** Modify `src/crypto_research/monitoring_v13.py`, `scripts/publish_monitoring_v13.py`, `tests/test_monitoring_v13.py`, `tests/test_publish_monitoring_v13.py`.
**Interfaces:** Strictly sanitized C fields; default publisher interval `2.0` seconds.
- [ ] Add failing sanitizer/publisher tests for C fields and 2-second default.
- [ ] Implement allow-list additions and default interval change.
- [ ] Run targeted monitoring tests.

### Task 4: Realtime client polling and scenario orders
**Files:** Modify `monitoring-web/lib/telemetry.ts`, `monitoring-web/components/dashboard.tsx`, `monitoring-web/app/globals.css`, `monitoring-web/tests/telemetry.test.mjs`.
**Interfaces:** `projectPositionScenario` scales by scenario leverage / actual leverage; UI renders scenario table and polls every 2 seconds without overlapping fetches.
- [ ] Add failing JS tests proving 2x actual position remains unchanged under 2x scenario at equal capital, while 1x/3x/5x scale correctly.
- [ ] Implement helper fix and scenario-order rows for OPEN positions; use TRADEABLE radar fallback when flat.
- [ ] Change client poll cadence to 2 seconds with in-flight guard and visible freshness.
- [ ] Run frontend tests/lint/build.

### Task 5: Full verification and production cutover
**Files:** Runtime/artifacts only; no secrets committed.
- [ ] Run full Python tests, Ruff, compileall, frontend tests, lint, and build.
- [ ] Snapshot current V14-B state and restart runner on C-compatible code preserving open positions.
- [ ] Restart publisher with `--interval 2` and verify production telemetry updates within a few seconds.
- [ ] Deploy verified web source to the existing Vercel production project and check root, telemetry, unauthorized ingest 401, and runtime errors.
- [ ] Check process health/invariants and scenario UI telemetry fields.
- [ ] Stage only source/docs/tests, scan staged diff for secrets/artifacts, commit one clean V14-C checkpoint.
