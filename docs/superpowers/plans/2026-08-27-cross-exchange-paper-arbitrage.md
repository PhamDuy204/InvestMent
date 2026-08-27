# Cross-Exchange Paper Arbitrage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a credential-free, simulated-only Binance/OKX/MEXC perpetual-futures arbitrage scanner using a 20 USD virtual account.

**Architecture:** Keep network I/O in one runner and all arbitrage math in one pure module. Reuse `ExecutionSimulatorV8` for depth-aware fills and the existing CCXT dependency; write JSONL/JSON artifacts only, with no authenticated exchange methods.

**Tech Stack:** Python 3.11+, CCXT, existing `ExecutionSimulatorV8`, pytest, stdlib JSON/pathlib.

**Spec:** `docs/superpowers/specs/2026-08-27-cross-exchange-paper-arbitrage-design.md`

## Global Constraints

- No API keys or authenticated endpoints.
- No live order method in the V1 code path.
- Initial virtual equity defaults to exactly 20.0 USD.
- Binance, OKX, and MEXC USDT linear perpetuals only.
- No new dependency.
- Reject partial fills and invalid/crossed books.

---

### Task 1: Pure arbitrage decision logic

**Files:**
- Create: `tests/test_arbitrage_v12.py`
- Create: `src/crypto_research/arbitrage_v12.py`

**Interfaces:**
- `VenueBook(name: str, book: dict[str, object], fee_bps: float)`
- `ArbitrageOpportunity(symbol, buy_venue, sell_venue, target_notional, buy_vwap, sell_vwap, gross_edge_bps, total_fee_bps, safety_buffer_bps, net_edge_bps)`
- `evaluate_pair(symbol, buy, sell, target_notional, safety_buffer_bps=0.0) -> ArbitrageOpportunity | None`
- `best_opportunity(symbol, venues, target_notional, min_net_edge_bps, safety_buffer_bps=0.0) -> ArbitrageOpportunity | None`

- [ ] **Step 1: Write failing tests** proving cost rejection, profitable acceptance, depth rejection, best-pair selection, and crossed-book rejection.
- [ ] **Step 2: Run** `python -m pytest -q tests/test_arbitrage_v12.py` and confirm failure is because `crypto_research.arbitrage_v12` does not exist.
- [ ] **Step 3: Implement minimal pure logic** by calling `ExecutionSimulatorV8(fee_bps=venue.fee_bps).simulate_market_order(...)` for each leg, rejecting `unfilled_notional > 1e-9`, and computing `gross_edge_bps = (sell.vwap - buy.vwap) / ((sell.vwap + buy.vwap) / 2) * 10_000`, then `net_edge_bps = gross_edge_bps - buy.fee_bps - sell.fee_bps - safety_buffer_bps`.
- [ ] **Step 4: Run** `python -m pytest -q tests/test_arbitrage_v12.py` and then full `python -m pytest -q`.
- [ ] **Step 5: Run** `ruff check src tests` and `python -m compileall -q src tests scripts`.

### Task 2: Public-data paper runner

**Files:**
- Create: `scripts/run_arbitrage_paper_v12.py`
- Create: `tests/test_run_arbitrage_paper_v12.py`

**Interfaces:**
- `make_public_clients() -> dict[str, Any]` creates `ccxt.binanceusdm`, `ccxt.okx`, and `ccxt.mexc` with `defaultType='swap'` and rate limiting.
- `common_linear_usdt_symbols(clients, limit) -> list[str]` intersects active linear USDT swap symbols.
- `run_scan(clients, symbols, equity, target_fraction, min_net_edge_bps, safety_buffer_bps, depth_limit) -> list[ArbitrageOpportunity]` fetches public books and returns accepted opportunities.
- `load_state(path, initial_equity=20.0) -> dict` and `write_state(path, state) -> None` provide restartable paper state.

- [ ] **Step 1: Write failing tests** with tiny fake public clients to prove symbol intersection, no private order calls, and state recovery.
- [ ] **Step 2: Run** the new test file and confirm red.
- [ ] **Step 3: Implement the minimal runner** using only `load_markets`, `fetch_order_book`, and optional `fetch_funding_rate` public calls; no exchange credentials.
- [ ] **Step 4: CLI defaults:** `--initial-equity 20`, `--target-fraction 0.25`, `--symbols 20`, `--interval 5`, `--depth 20`, `--once` for smoke testing, and artifacts under `artifacts/arbitrage_v12/`.
- [ ] **Step 5: Verify targeted tests, full tests, ruff, and compileall.**

### Task 3: Verification and handoff

**Files:**
- Modify only if needed: `.github/workflows/ci.yml` (prefer no change).

- [ ] **Step 1:** Confirm existing CI runs on the branch and reports pytest/ruff/compileall success.
- [ ] **Step 2:** Review branch diff against `v11-root-cause-paper-readiness`; confirm there is no `create_order`, API key, secret, or authenticated endpoint in added code.
- [ ] **Step 3:** If public network access is available, run one-shot `python scripts/run_arbitrage_paper_v12.py --once`; otherwise report that runtime smoke testing remains blocked by the PC connector/network and do not claim it ran.
- [ ] **Step 4:** Open a draft PR from `v12-cross-exchange-paper-arbitrage` to `v11-root-cause-paper-readiness` only after CI is green.
