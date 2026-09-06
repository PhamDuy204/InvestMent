# V14 Multi-Asset Leveraged Paper Arbitrage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build V14-B multi-symbol ranked paper arbitrage with an explicit isolated-margin model and a dashboard that explains leverage, margin, and every no-trade decision.

**Architecture:** Keep the live V13 runner untouched while a new V14 runner is tested in the monitoring worktree. Reuse V12/V13 public-book, execution, open/close, and persistence helpers; add only the portfolio risk/accounting required by B. Generalize monitoring in place so the publisher can point at V14 artifacts after switchover.

**Tech Stack:** Python 3.13, CCXT public APIs, pytest, Next.js 16, React 19, TypeScript, Vercel Runtime Cache.

**Spec:** `docs/v14-multi-asset-leverage-design.md`

## Global Constraints

- PAPER / SIMULATION ONLY; no private exchange calls or credentials.
- Initial V14 equity must continue from the current V13 realized equity/history.
- Default `exchange_leverage=2.0`, `gross_leverage_cap=2.0`, `max_open_positions=4`, `single_pair_gross_fraction=0.5`.
- Margin model is `ISOLATED_PAPER_V1`; maintenance margin/liquidation stay unavailable in B.
- Dashboard is PUBLIC · READ ONLY and never controls the runner.
- Do not stop V13 until V14 tests and a dry-run artifact set pass.

---

### Task 1: Venue-tolerant universe discovery

**Files:**
- Modify: `scripts/run_arbitrage_paper_v12.py`
- Test: `tests/test_run_arbitrage_paper_v12.py`

**Interfaces:**
- Produces: `linear_usdt_symbol_venues(clients, *, min_venues=2) -> dict[str, tuple[str, ...]]`
- Existing `common_linear_usdt_symbols` remains behavior-compatible for V12/V13.

- [ ] Add a failing test proving a symbol listed on OKX+MEXC but not Binance is retained by the new helper.
- [ ] Run the focused test and verify RED.
- [ ] Implement the minimal additive helper using `_eligible_linear_usdt_swap` and successful `load_markets()` results.
- [ ] Run V12 tests and verify GREEN.

### Task 2: V14 isolated portfolio risk and runner

**Files:**
- Create: `scripts/run_arbitrage_paper_v14.py`
- Create: `tests/test_arbitrage_v14.py`

**Interfaces:**
- Produces V14 state schema `v14-arbitrage-paper-1`.
- Reuses `_fetch_venue_books`, `_open_position`, `_try_close_position`, `write_state`, `_append_jsonl`, `ExecutionSimulatorV8`, and `best_opportunity`.
- Exposes `run_cycle(...)` for deterministic tests.

- [ ] Write failing tests for: ranked candidates across multiple symbols; max 4 distinct symbols; gross exposure cap; venue margin rejection; modeled initial margin on opens; per-venue realized balance update on close; opportunity radar rejection reasons.
- [ ] Run focused tests and verify RED.
- [ ] Implement minimal V14 state/risk accounting and ranked run cycle.
- [ ] Run focused tests and verify GREEN.
- [ ] Add restart/state invariant test and preserve the public-only safety boundary.

### Task 3: V14 telemetry and publisher compatibility

**Files:**
- Modify: `src/crypto_research/monitoring_v13.py`
- Modify: `scripts/publish_monitoring_v13.py`
- Modify: `tests/test_monitoring_v13.py`
- Modify: `tests/test_publish_monitoring_v13.py`

**Interfaces:**
- Monitoring schema becomes `v14-monitoring-1` when state is V14, while V13 payload building stays supported for safe transition.
- V14 open marks preserve `ISOLATED_PAPER_V1` and modeled margin fields.

- [ ] Write failing tests for V14 portfolio fields, radar sanitization, modeled margin preservation, and V13 backward compatibility.
- [ ] Verify RED.
- [ ] Implement strict allow-list output and conditional schema version.
- [ ] Verify GREEN.

### Task 4: Dashboard always-visible leverage and opportunity radar

**Files:**
- Modify: `monitoring-web/lib/telemetry.ts`
- Modify: `monitoring-web/components/dashboard.tsx`
- Modify: `monitoring-web/app/globals.css`
- Modify: `monitoring-web/tests/telemetry.test.mjs`

**Interfaces:**
- Accepts V14 telemetry fields and V13 transition payloads.
- What-if capacity panel renders even when `open_position_count=0`.

- [ ] Add failing frontend tests for V14 sanitizer and zero-open leverage capacity projection.
- [ ] Verify RED.
- [ ] Implement V14 telemetry types/sanitizer and capacity projection.
- [ ] Render actual V14 risk KPIs plus Opportunity Radar and always-visible $20/$50/$100 × 1/2/3/5x controls.
- [ ] Run tests, lint, and build to GREEN.

### Task 5: V14 dry-run, state migration, switchover, and deployment

**Files:**
- Generated runtime only: `artifacts/arbitrage_v14/*` (gitignored)

**Interfaces:**
- V13 remains fallback until production telemetry proves V14 healthy.

- [ ] Run full Python test suite, Ruff on touched files, compileall, frontend tests/lint/build.
- [ ] Migrate the current closed V13 history only after confirming V13 has zero open positions; copy journal and preserve realized equity/PnL/counts.
- [ ] Run V14 `--once` against separate artifacts and verify at least two venues/universe/radar plus all margin invariants.
- [ ] Start V14 background runner; observe multiple scans without stopping V13.
- [ ] Switch publisher to V14 artifacts and verify local payload/live marks.
- [ ] Deploy the same verified frontend bundle to the existing Vercel project.
- [ ] Verify root 200, unauthorized ingest 401, authorized ingest 200, telemetry 200, V14 risk fields visible, and no Vercel runtime errors.
- [ ] Stop V13 only after V14 production monitoring is healthy.

### Task 6: C promotion evidence checkpoint

**Files:**
- Create: `artifacts/arbitrage_v14/promotion_gate.json` at runtime only.

**Interfaces:**
- Does not activate C; records eligibility evidence.

- [ ] Compute closed trade count, distinct symbols, runtime duration, invariant failures, and telemetry health.
- [ ] Mark `C_ELIGIBLE=false` until all spec gates pass.
- [ ] Reuse `multi_asset_v3` and `leverage_v3` only after the gate becomes true in a later implementation plan.
