# V20 Execution-Aware Paper Arbitrage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop V19 one-leg execution leakage with a conservative single-maker account-EV gate, preserve causal public-data paper execution, then expose account-level telemetry needed to optimize toward +$0.05/hour.

**Architecture:** Reuse V17/V19 scanner, public WS cache, causal fill detector, post-fill EV, margin, exit, and monitoring. Add one focused V20 math/stat module, two optional V17 cycle hooks so V20 can supply its route decision and shadow-probe processor without duplicating the runner, and a thin V20 runner. Keep the existing V19 background runner/publisher/web/tunnel untouched and smoke V20 in a separate artifacts directory.

**Tech Stack:** Python 3, stdlib sqlite3/statistics/math, existing ccxt.pro, existing pytest/Ruff, existing Next.js monitoring web.

**Spec:** `docs/v20-execution-aware-design.md`

## Global Constraints

- PAPER / simulation only; public REST/WS only; no keys, private/authenticated endpoints, real orders, transfers, deposits, or withdrawals.
- Do not fake fills, PnL, latency, depth, or WS updates.
- $100 initial paper capital; only 20x/30x/40x simulated leverage; leverage cannot change EV sign.
- Account realized net PnL/hour is authoritative; paired win rate is not profitability.
- Do not stop/restart the existing V19 runner, publisher, dashboard web process, or Cloudflare tunnel.
- No new dependency.
- Do not clean/reset unrelated modified/untracked files.

---

### Task 1: Execution outcome calibration and attempt EV

**Files:**
- Create: `src/crypto_research/maker_v20.py`
- Create/Test: `tests/test_maker_v20.py`

**Interfaces:**
- `record_v20_execution_outcome(db_path, *, venue, side, accepted, reject_net_bps=None) -> None`
- `seed_v20_execution_outcomes(db_path, journal_path) -> int`
- `v20_execution_calibration(db_path, *, venue, side) -> dict[str, float|int|bool]`
- `single_maker_attempt_ev(*, pair_capture_bps, maker_fee_bps, hedge_taker_fee_bps, expected_exit_fee_bps, expected_exit_price_improvement_bps, maker_quote_improvement_bps, adverse_selection_bps, safety_buffer_bps, fill_probability, calibration) -> dict[str, float|bool|str]`

- [ ] Write tests proving seed is idempotent, rejected outcomes include negative abort bps, sparse local evidence shrinks toward global evidence, and a candidate with legacy-positive paired economics is rejected when calibrated abort expectancy makes account EV negative.
- [ ] Run focused tests and verify they fail before implementation.
- [ ] Implement one SQLite aggregate table plus one seed-marker table; validate finite/range inputs at the boundary.
- [ ] Implement conservative accept probability using global shrinkage and a one-standard-error downward adjustment; implement reject loss as a conservative negative global/local shrunk mean.
- [ ] Implement attempt EV as `p_fill * (q_accept * pair_value + (1-q_accept) * reject_net_bps)` and require sufficient evidence plus positive/minimum expected attempt EV.
- [ ] Run focused tests to pass.

### Task 2: Reuse V17 cycle with V20 decision/probe hooks

**Files:**
- Modify: `scripts/run_arbitrage_paper_v17.py`
- Modify/Test: `tests/test_arbitrage_v17.py` or existing V17 test file

**Interfaces:**
- Add optional `route_decider` defaulting to `_v17_route_decision`.
- Add optional `maker_probe_processor` defaulting to `_process_maker_probes`.

- [ ] Add failing regression test showing both first-pass candidate scoring and exact-notional reprice use the supplied route decider.
- [ ] Add failing regression test showing the supplied maker-probe processor is invoked with the existing causal probe inputs.
- [ ] Replace only the two hard-coded route-decider calls and one probe-processor call with local hook variables; default behavior must be byte-for-byte equivalent for existing callers.
- [ ] Run V17/V19 focused tests.

### Task 3: Single-maker V20 pending execution

**Files:**
- Create: `scripts/run_arbitrage_paper_v20.py`
- Modify: `scripts/run_arbitrage_paper_v17.py` only to preserve selected V20 decision metadata in pending records.
- Modify: `scripts/run_arbitrage_paper_v19.py` only if a tiny generic `_run(..., cycle_runner=...)` hook is required; V19 default behavior remains unchanged.
- Create/Test: `tests/test_arbitrage_v20.py`

**Interfaces:**
- `STRATEGY_ID = "WS_EXECUTION_AWARE_SINGLE_MAKER_V1"`
- `_v20_route_decision(...)` evaluates LONG-maker and SHORT-maker actions and chooses the higher conservative account-EV action.
- `_process_pending_entries_v20(...)` uses only `pending["maker_side"]` as causal maker evidence, then reuses current V19 post-fill EV and taker hedge/unwind math.
- `run_cycle_v20(...)` delegates to `run_cycle_v17` with V19 history/exit/invariant behavior plus V20 hooks.

- [ ] Write a failing test that a V20 pending LONG-maker cannot be opened by a SHORT maker touch, and vice versa.
- [ ] Write a failing test that post-fill reject records exactly one calibration reject with realized abort bps and paired accept records exactly one calibration accept.
- [ ] Write a failing test that a route with no execution calibration remains shadow-only/not tradeable instead of guessing.
- [ ] Implement the minimum V20 wrapper and selected-maker processing by reusing V19 helpers.
- [ ] Preserve journal metadata: maker side, calibrated accept probability, calibrated reject bps, attempt EV bps/dollars, post-fill EV, leverage, and latency.
- [ ] Run V20 focused tests.

### Task 4: Enrich causal shadow probes without equity mutation

**Files:**
- Modify: `scripts/run_arbitrage_paper_v20.py`
- Test: `tests/test_arbitrage_v20.py`

**Interfaces:**
- `_process_maker_probes_v20(...)` wraps the existing V17 causal probe processor, identifies terminal causal fills from the pre-call probe snapshot, computes hypothetical opposite taker depth/post-fill decision, and records accept/reject economics only in V20 calibration SQLite.

- [ ] Write failing test that a causal shadow fill updates calibration while equity/realized PnL/open positions remain unchanged.
- [ ] Write failing test that no-fill/timeout shadow probe does not create a fake execution outcome.
- [ ] Implement by reusing `passive_limit_filled`, `_market_fill`, V18 `post_fill_entry_ev`, and V19 freshness/strict-price-through semantics.
- [ ] Run V20 focused tests.

### Task 5: Fee model and optional Kraken public stream support

**Files:**
- Modify: `src/crypto_research/maker_v17.py` (Gate maker only)
- Modify: `scripts/run_arbitrage_paper_v12.py` / V20 fee overlay only as justified
- Modify: `src/crypto_research/stream_v18.py` only if Kraken is enabled generically; otherwise define V20 client factory in V20 runner.
- Test: existing fee/client tests plus V20 tests.

- [ ] Update Gate VIP0 maker assumption from 5 bps fallback to officially verified 2 bps; keep taker 5 bps.
- [ ] Keep MEXC API Futures at 6/8, Bybit 2/5.5, Bitget 2/6, OKX 2/5, KuCoin 2/6.
- [ ] Keep Binance conservative until an exact current official USD-M base table is verified; do not assume VIP/BNB discounts.
- [ ] Add Kraken Futures 2/5 only to V20 public client/fee maps if installed CCXT Pro reports `krakenfutures` + public `watchOrderBook`; no private calls.
- [ ] Run client construction test without credentials and a one-shot coverage check; reject Kraken if public market metadata/linear-USDT overlap is inadequate.

### Task 6: Account-level telemetry and dashboard truthfulness

**Files:**
- Modify: `src/crypto_research/monitoring_v13.py`
- Modify: `tests/test_monitoring_v13.py`
- Modify: `monitoring-web/lib/telemetry.ts`
- Modify: `monitoring-web/components/dashboard.tsx`
- Modify frontend tests as existing project pattern requires.

**Interfaces:**
- Preserve `win_rate_pct` for compatibility but label it `Paired Win Rate`.
- Add metrics computed from journal/state: `account_realized_pnl_per_hour`, `paired_realized_pnl`, `paired_realized_pnl_per_hour`, `non_paired_execution_pnl`, `non_paired_execution_pnl_per_hour`, abort gross/fees/net/count, total/paired/non-paired fee drag, paired trades/hour, rolling account PnL 1h/3h/6h, median/p95 entry gap.

- [ ] Add backend tests with paired winner + one-leg abort fixture proving account PnL reconciles and paired win rate is not reused as account profitability.
- [ ] Implement metrics by reusing journal rows already loaded by monitoring; no second event store.
- [ ] Add frontend schema fields and KPI labels; show `Paired Win Rate` explicitly.
- [ ] Run frontend tests/lint/build.

### Task 7: Verification and sidecar V20 paper smoke

**Files:** no production source beyond prior tasks.

- [ ] Run focused Python tests.
- [ ] Run full `pytest`.
- [ ] Run `ruff check` on changed Python files / project command.
- [ ] Run `python -m compileall` on changed Python modules.
- [ ] Run `git diff --check`.
- [ ] Run frontend tests/lint/build if UI changed.
- [ ] Confirm V19 runner/publisher/web/tunnel job IDs are still alive before starting V20.
- [ ] Start V20 with a separate `artifacts/arbitrage_v20_live` directory and a separate history DB seed; never reuse/reset V19 equity.
- [ ] Observe a short smoke for public WS health, memory, causal probes, calibration, no invariant failures, and exact account-PnL reconciliation. Do not claim +$0.05/hour from the short smoke.
- [ ] Leave V19 expose alive; only publish V20 publicly after local V20 telemetry is valid and without killing the existing Cloudflare tunnel.
