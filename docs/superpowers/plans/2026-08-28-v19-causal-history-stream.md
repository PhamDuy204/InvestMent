# V19 Causal History and Stream Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a paper-only V19 that fixes per-symbol history starvation, reduces cache/query load, makes WebSocket rejection reasons observable, and preserves conservative post-fill economics.

**Architecture:** Keep V17/V18 defaults backward compatible and add narrow opt-in parameters used by a versioned V19 runner. Reuse the latest-only cache and maker/route helpers, materialize only discovery and active symbols, and expose V19 through the existing sanitized monitoring pipeline.

**Tech Stack:** Python 3.13 stdlib, SQLite, installed ccxt/ccxt.pro 4.5.76, pytest, Ruff, Next.js monitoring app.

**Spec:** `docs/superpowers/specs/2026-08-28-v19-causal-history-stream-design.md`

## Global Constraints

- Public market data and paper simulation only.
- Never call private/authenticated trading, transfer, deposit, or withdrawal endpoints.
- Do not fabricate fills, PnL, profitability, execution, or WebSocket events.
- Preserve V18 defaults and artifacts; V19 behavior must be opt-in.
- Do not lower fee, depth, EV, adverse-selection, safety, or post-fill gates.
- Use the current host envelope: 1,200 MB high-water and 1,500 MB hard stop; allow CLI values up to 3,000 MB only on a larger host.
- Do not run V18 and V19 full 350-stream runners concurrently.
- No new dependency.

---

### Task 1: Per-symbol history and indexed seven-minute readiness

**Files:**
- Modify: `src/crypto_research/route_v16.py:15-33`
- Modify: `src/crypto_research/maker_v17.py:137-194`
- Modify: `scripts/run_arbitrage_paper_v17.py:850-1040`
- Test: `tests/test_route_v16.py`
- Test: `tests/test_maker_v17.py`
- Create: `tests/test_arbitrage_v19.py`

**Interfaces:**
- Extend `multi_horizon_route_features(..., minimum_span_ms: int = 600_000)`.
- Extend `run_cycle_v17(..., per_symbol_history_sampling: bool = False, minimum_history_span_ms: int = 600_000, strict_maker_price_through: bool = False)`.
- Persist V19 sampling stamps in `state["last_history_sample_ms_by_symbol"]: dict[str, int]`.
- Create SQLite index `idx_route_history_v16_route_time` on `(symbol, buy_venue, sell_venue, observed_at_ms)`.

- [ ] **Step 1: Create the V19 branch without disturbing dirty V15-V18 work**

Run:

```bash
git switch -c v19-causal-history-stream
git status --short --branch
```

Expected: branch is `v19-causal-history-stream`; existing modified and untracked files remain present.

- [ ] **Step 2: Write failing index and seven-minute feature tests**

Add:

```python
def test_route_history_has_route_time_index(tmp_path):
    import sqlite3
    db = tmp_path / "history.sqlite"
    record_route_snapshots(db, 1_000, [_row(1.0)])
    with sqlite3.connect(db) as connection:
        names = {row[1] for row in connection.execute("PRAGMA index_list(route_history_v16)")}
    assert "idx_route_history_v16_route_time" in names


def test_multi_horizon_features_accept_opt_in_seven_minute_span(tmp_path):
    db = tmp_path / "history.sqlite"
    start = 1_000_000
    for i in range(12):
        record_route_snapshots(db, start + i * 40_000, [{
            "symbol": "AAA/USDT:USDT",
            "buy_venue": "okx",
            "sell_venue": "bybit",
            "gross_edge_bps": 5.0,
            "reference_mid_price": 100.0,
        }])
    now = start + 12 * 40_000
    assert multi_horizon_route_features(
        db, "AAA/USDT:USDT", "okx", "bybit", now_ms=now
    ) is None
    assert multi_horizon_route_features(
        db,
        "AAA/USDT:USDT",
        "okx",
        "bybit",
        now_ms=now,
        minimum_span_ms=420_000,
    ) is not None
```

- [ ] **Step 3: Write the failing independent-symbol sampling regression**

Use existing `FakePublicClient`/book helpers. Pre-seed stable route history, run two one-symbol batches less than five seconds apart with `per_symbol_history_sampling=True`, then query both symbols:

```python
def test_v19_history_clock_is_per_symbol(tmp_path):
    state = _default_state_v17(["cheap", "rich"])
    state["history_sample_interval_ms"] = 5_000
    run_cycle_v17(..., symbols=["A/USDT:USDT"], now_ms=1_000_000,
                  per_symbol_history_sampling=True,
                  minimum_history_span_ms=420_000)
    run_cycle_v17(..., symbols=["B/USDT:USDT"], now_ms=1_001_000,
                  per_symbol_history_sampling=True,
                  minimum_history_span_ms=420_000)
    assert state["last_history_sample_ms_by_symbol"] == {
        "A/USDT:USDT": 1_000_000,
        "B/USDT:USDT": 1_001_000,
    }
```

- [ ] **Step 4: Run the new tests and verify RED**

Run:

```bash
pytest -q tests/test_route_v16.py::test_route_history_has_route_time_index   tests/test_maker_v17.py::test_multi_horizon_features_accept_opt_in_seven_minute_span   tests/test_arbitrage_v19.py::test_v19_history_clock_is_per_symbol
```

Expected: failures for missing index/parameters/map.

- [ ] **Step 5: Implement the minimal shared changes**

In both route database connection helpers, execute:

```python
connection.execute(
    "CREATE INDEX IF NOT EXISTS idx_route_history_v16_route_time "
    "ON route_history_v16(symbol, buy_venue, sell_venue, observed_at_ms)"
)
```

In `multi_horizon_route_features`, validate a positive `minimum_span_ms` and replace the fixed ten-minute comparison with that parameter.

In `run_cycle_v17`, preserve the old global branch by default. For the opt-in branch:

```python
last_by_symbol = state.setdefault("last_history_sample_ms_by_symbol", {})
sample_symbols = {
    symbol
    for symbol in symbols
    if now_ms - int(last_by_symbol.get(symbol, 0)) >= history_interval
}
```

Record only rows belonging to `sample_symbols`, and set each map entry only after its rows are persisted. Pass `minimum_history_span_ms` to every feature recomputation, including reprice validation.

- [ ] **Step 6: Run focused and compatibility tests**

Run:

```bash
pytest -q tests/test_route_v16.py tests/test_maker_v17.py   tests/test_arbitrage_v17.py tests/test_arbitrage_v18.py tests/test_arbitrage_v19.py
```

Expected: PASS; V17/V18 tests keep ten-minute/global defaults.

- [ ] **Step 7: Commit Task 1**

```bash
git add src/crypto_research/route_v16.py src/crypto_research/maker_v17.py   scripts/run_arbitrage_paper_v17.py tests/test_route_v16.py   tests/test_maker_v17.py tests/test_arbitrage_v19.py
git commit -m "fix: sample route history per symbol for v19"
```

---

### Task 2: Selective immutable snapshots and stream-cause telemetry

**Files:**
- Modify: `src/crypto_research/stream_v18.py:15-184,270-299`
- Test: `tests/test_stream_v18.py`

**Interfaces:**
- Extend `LatestBookCache.snapshot(..., selected_symbols: set[str] | None = None, require_connected: bool = False)`.
- Add `LatestBookCache.record_stream_error(venue: str, symbol: str, exc: Exception)`.
- Successful `update` marks the stream connected again.
- Return aggregate metrics plus `age_expired_book_count`, `skew_rejected_book_count`, `disconnected_book_count`, `stream_error_counts`, and `stream_error_counts_by_venue`.
- Keep V18 behavior when new arguments are omitted.

- [ ] **Step 1: Write failing snapshot-selection tests**

Add books for 50 symbols across seven venues, then assert metrics describe all 350 entries while clients contain only selected symbols:

```python
def test_snapshot_materializes_only_selected_symbols_but_counts_full_cache():
    cache = LatestBookCache(depth_limit=2, max_entries=400)
    for index in range(50):
        for venue in ("a", "b", "c", "d", "e", "f", "g"):
            cache.update(venue, f"S{index}", _book(), received_at_ms=10_000,
                         received_mono_ms=10_000)
    clients, metrics = cache.snapshot(
        now_ms=10_100,
        now_mono_ms=10_100,
        max_age_ms=5_000,
        max_skew_ms=None,
        selected_symbols={"S1", "S2"},
    )
    assert metrics["cache_entry_count"] == 350
    assert metrics["fresh_book_count"] == 350
    assert sum(len(client.symbols) for client in clients.values()) == 14
```

Add tests proving a healthy bounded-age book is accepted despite last-change skew and a recorded stream error is classified separately from age expiry.

- [ ] **Step 2: Run stream tests and verify RED**

Run:

```bash
pytest -q tests/test_stream_v18.py
```

Expected: failures for unsupported selection/health arguments and missing cause metrics.

- [ ] **Step 3: Remove duplicate deep copies**

Under the cache lock, take a shallow dictionary snapshot because `update` replaces normalized book objects rather than mutating them. Deep-copy only accepted selected rows into `CachedPublicClient`. Change `CachedPublicClient.__init__` to retain the already-isolated mapping; keep `fetch_order_book` returning a copy to callers.

Track health in a bounded dictionary keyed by `(venue, symbol)`. Normalize error keys to `type(exc).__name__`, capped to known string sizes; never store unbounded traceback objects.

- [ ] **Step 4: Pass exact errors from watcher to cache**

Replace the broad anonymous handler with:

```python
except Exception as exc:
    cache.record_stream_error(venue, symbol, exc)
    ...
```

A subsequent valid `cache.update` clears the disconnected flag but does not erase cumulative counters.

- [ ] **Step 5: Run tests and a 350-book microbenchmark**

Run:

```bash
pytest -q tests/test_stream_v18.py
PYTHONPATH=.:src python - <<'PY'
import time
from src.crypto_research.stream_v18 import LatestBookCache
cache = LatestBookCache(depth_limit=20, max_entries=400)
book = {"bids": [[100-i*.01, 1] for i in range(20)],
        "asks": [[100+i*.01, 1] for i in range(20)]}
for i in range(50):
    for venue in "abcdefg":
        cache.update(venue, f"S{i}", book)
start = time.perf_counter()
for _ in range(100):
    cache.snapshot(max_age_ms=5_000, max_skew_ms=None,
                   selected_symbols={"S1", "S2"})
elapsed = (time.perf_counter() - start) * 10
assert elapsed < 25, elapsed
print({"snapshot_mean_ms": elapsed})
PY
```

Expected: tests PASS and mean selective snapshot below 25 ms on the sandbox.

- [ ] **Step 6: Commit Task 2**

```bash
git add src/crypto_research/stream_v18.py tests/test_stream_v18.py
git commit -m "perf: materialize only active public books"
```

---

### Task 3: Honest strict price-through paper fills

**Files:**
- Modify: `src/crypto_research/maker_v17.py:90-127`
- Modify: `scripts/run_arbitrage_paper_v17.py`
- Modify: `scripts/run_arbitrage_paper_v18.py:248-519`
- Test: `tests/test_maker_v17.py`
- Test: `tests/test_arbitrage_v18.py`
- Test: `tests/test_arbitrage_v19.py`

**Interfaces:**
- Extend `passive_limit_filled(..., strict_price_through: bool = False)`.
- Propagate `strict_maker_price_through` from `run_cycle_v17` into entry, exit, and probe processors.
- V17/V18 defaults remain touch-compatible; V19 passes `True`.

- [ ] **Step 1: Write the failing strict-fill test**

```python
def test_strict_paper_fill_requires_price_through_not_touch():
    touched_buy = {"bids": [[99.9, 1]], "asks": [[100.0, 1]],
                   "received_at_ms": 1_001}
    crossed_buy = {"bids": [[99.8, 1]], "asks": [[99.9, 1]],
                   "received_at_ms": 1_001}
    assert passive_limit_filled(
        "buy", 100.0, touched_buy, placed_at_ms=1_000,
        strict_price_through=True,
    ) is False
    assert passive_limit_filled(
        "buy", 100.0, crossed_buy, placed_at_ms=1_000,
        strict_price_through=True,
    ) is True
```

Mirror it for sell. Add an entry-processing test showing touch remains pending in V19 mode.

- [ ] **Step 2: Run strict-fill tests and verify RED**

Run:

```bash
pytest -q tests/test_maker_v17.py::test_strict_paper_fill_requires_price_through_not_touch   tests/test_arbitrage_v19.py -k strict
```

Expected: unsupported parameter or touch incorrectly fills.

- [ ] **Step 3: Implement one conditional comparison**

After the existing causal timestamp guard:

```python
if side == "buy":
    return best_ask < limit_price if strict_price_through else best_ask <= limit_price
return best_bid > limit_price if strict_price_through else best_bid >= limit_price
```

Propagate the flag; do not change price, fee, quantity, fill-probability, or PnL formulas.

- [ ] **Step 4: Run maker/execution compatibility tests**

Run:

```bash
pytest -q tests/test_maker_v17.py tests/test_maker_v18.py   tests/test_arbitrage_v17.py tests/test_arbitrage_v18.py tests/test_arbitrage_v19.py
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/crypto_research/maker_v17.py scripts/run_arbitrage_paper_v17.py   scripts/run_arbitrage_paper_v18.py tests/test_maker_v17.py   tests/test_arbitrage_v18.py tests/test_arbitrage_v19.py
git commit -m "fix: require strict price-through for v19 paper fills"
```

---

### Task 4: Versioned V19 runner, bounded batch five, and resource checks

**Files:**
- Create: `scripts/run_arbitrage_paper_v19.py`
- Modify: `tests/test_arbitrage_v19.py`

**Interfaces:**
- Schema `v19-arbitrage-paper-1`.
- Strategy/portfolio `WS_CAUSAL_POST_FILL_EV_V2`.
- History file `history_v19.sqlite`.
- Defaults: batch 5, book idle 5,000 ms, no receive skew, history span 420,000 ms, memory 1,200/1,500 MB.
- Reuse V18 cycle/post-fill/accounting helpers and shared stream cache.

- [ ] **Step 1: Write failing state/parser tests**

```python
def test_v19_defaults_are_bounded_and_paper_only():
    state = _default_state_v19(["binance", "okx"])
    args = _parser().parse_args([])
    assert state["schema_version"] == "v19-arbitrage-paper-1"
    assert state["last_history_sample_ms_by_symbol"] == {}
    assert args.scan_batch_size == 5
    assert args.max_book_age_ms == 5_000
    assert args.max_book_skew_ms is None
    assert args.memory_high_water_mb == 1_200
    assert args.memory_hard_limit_mb == 1_500
```

Add parser validation: positive limits, high-water below hard-stop, and hard-stop at most 3,000 MB.

- [ ] **Step 2: Run and verify RED**

Run:

```bash
pytest -q tests/test_arbitrage_v19.py
```

Expected: module/import failure.

- [ ] **Step 3: Create the versioned runner using the existing V18 pattern**

Copy the V18 runner once, then change only version constants, defaults, history filename, loader validation, and V19 opt-in arguments. In the main loop choose the discovery batch before calling `cache.snapshot` and union it with active symbols:

```python
active_symbols = {
    str(row["symbol"])
    for key in ("pending_entries", "pending_exits", "maker_probes", "open_positions")
    for row in state.get(key, [])
    if isinstance(row, dict) and row.get("symbol")
}
selected_symbols = set(discovery_symbols) | active_symbols
snapshot_clients, metrics = cache.snapshot(
    now_ms=now_ms,
    now_mono_ms=now_mono_ms,
    max_age_ms=args.max_book_age_ms,
    max_skew_ms=None,
    selected_symbols=selected_symbols,
    require_connected=True,
)
```

Call the shared cycle with:

```python
per_symbol_history_sampling=True
minimum_history_span_ms=420_000
strict_maker_price_through=True
```

The seed default is `artifacts/arbitrage_v18/history_v18.sqlite`; never copy V18 state/PnL.

- [ ] **Step 4: Add memory and invariant validation tests**

Test that invalid memory pairs terminate before clients are constructed and that V19's fake clients contain no callable private order method. Keep the existing one-leg APT accounting regression unchanged.

- [ ] **Step 5: Run focused V19 tests**

Run:

```bash
pytest -q tests/test_arbitrage_v19.py tests/test_stream_v18.py   tests/test_maker_v17.py tests/test_maker_v18.py
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add scripts/run_arbitrage_paper_v19.py tests/test_arbitrage_v19.py
git commit -m "feat: add v19 causal public-stream runner"
```

---

### Task 5: Candidate funnel and V19 monitoring allow-list

**Files:**
- Modify: `scripts/run_arbitrage_paper_v17.py`
- Modify: `scripts/run_arbitrage_paper_v19.py`
- Modify: `src/crypto_research/monitoring_v13.py`
- Modify: `scripts/publish_monitoring_v13.py`
- Modify: `tests/test_arbitrage_v19.py`
- Modify: `tests/test_monitoring_v13.py`
- Modify: `tests/test_publish_monitoring_v13.py`
- Modify: `monitoring-web/lib/telemetry.ts`
- Modify: `monitoring-web/tests/telemetry.test.mjs`

**Interfaces:**
- State map `candidate_funnel_counts: dict[str, int]` with fixed keys from the spec.
- Payload schema `v19-monitoring-1`.
- Publisher reads `history_v19.sqlite` and skips separate REST marking for V19.

- [ ] **Step 1: Write failing funnel reconciliation tests**

Create one candidate for each existing rejection branch—duplicate, cooldown, max positions, gross cap, venue margin, execution depth, reprice EV—and assert the corresponding fixed counter increments. For a created pending order:

```python
counts = state["candidate_funnel_counts"]
assert counts["ev_qualified_occurrence"] >= 1
assert counts["pending_created"] == 1
assert sum(counts[key] for key in (
    "duplicate_rejected", "cooldown_rejected", "capacity_rejected",
    "margin_rejected", "depth_rejected", "reprice_ev_rejected",
    "pending_created",
)) <= counts["ev_qualified_occurrence"]
```

- [ ] **Step 2: Write failing monitoring/publisher tests**

Build a V19 state with stream-cause and funnel counters. Assert sanitized V19 payload values, `history_v19.sqlite` selection, and no call to `make_public_clients`.

- [ ] **Step 3: Run and verify RED**

Run:

```bash
pytest -q tests/test_arbitrage_v19.py tests/test_monitoring_v13.py   tests/test_publish_monitoring_v13.py
node --test monitoring-web/tests/telemetry.test.mjs
```

Expected: missing schema/counters/history mapping.

- [ ] **Step 4: Increment counters at existing decisions**

Use one fixed map initialized in V19 state. Increment directly beside the existing branch that assigns each radar decision; do not add a second optimizer or event bus. Preserve the legacy qualified counter.

- [ ] **Step 5: Extend monitoring allow-lists**

Add V19 schema constants and recognize V19 anywhere V18 already uses causal persisted marks. Allow-list only bounded numeric maps and fixed error-reason keys; do not expose exception messages or exchange payloads.

- [ ] **Step 6: Run backend/frontend focused tests**

Run:

```bash
pytest -q tests/test_arbitrage_v19.py tests/test_monitoring_v13.py   tests/test_publish_monitoring_v13.py
npm --prefix monitoring-web test
```

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

```bash
git add scripts/run_arbitrage_paper_v17.py scripts/run_arbitrage_paper_v19.py   src/crypto_research/monitoring_v13.py scripts/publish_monitoring_v13.py   tests/test_arbitrage_v19.py tests/test_monitoring_v13.py   tests/test_publish_monitoring_v13.py monitoring-web/lib/telemetry.ts   monitoring-web/tests/telemetry.test.mjs
git commit -m "feat: expose honest v19 candidate and stream telemetry"
```

---

### Task 6: Full verification and controlled production switchover

**Files:**
- Runtime create: `artifacts/arbitrage_v19/`
- No source change unless a verification failure is reproduced by a new focused test.

**Interfaces:**
- V19 runner command uses 50 symbols, batch five, public WebSockets, and V18 history seed.
- Existing web server/tunnel remain running.
- Publisher switches artifacts only after V19 health is valid.

- [ ] **Step 1: Run complete static/backend verification**

```bash
PYTHONPATH=.:src pytest -q
ruff check .
python -m compileall -q scripts src
git diff --check
```

Expected: all tests PASS, Ruff/compile/diff checks exit 0.

- [ ] **Step 2: Run complete frontend verification**

```bash
npm --prefix monitoring-web test
npm --prefix monitoring-web run lint
npm --prefix monitoring-web run build
```

Expected: tests, lint, and production build PASS.

- [ ] **Step 3: Capture rollback evidence**

Record current V18 job IDs, command, state/health hashes, open/pending position counts, RSS, and current Git status. Assert no open or pending V18 exposure before termination; if exposure exists, wait for the existing paper state machine rather than deleting it.

- [ ] **Step 4: Stop only the V18 runner and start V19**

Use the Eztech task API to TERM job `51f76f6e63ce`. Do not stop the web server or tunnel. Start:

```bash
PYTHONPATH=.:src python -u scripts/run_arbitrage_paper_v19.py   --symbols 50   --scan-batch-size 5   --artifacts-dir artifacts/arbitrage_v19   --seed-history-db artifacts/arbitrage_v18/history_v18.sqlite
```

Expected: one V19 job, no concurrent V18 runner.

- [ ] **Step 5: Observe bounded runtime gates**

For at least ten minutes, sample every 30–60 seconds:

- process alive and health `HEALTHY`;
- RSS below 1,200 MB normally and never at 1,500 MB;
- cache entries at or below configured venue-symbol bound;
- each rotating symbol receives independent history;
- feature-ready route count rises rather than collapsing to zero;
- loop and heartbeat remain responsive;
- stream failures are classified;
- invariant failure count remains zero;
- journal contains only supported paper event types.

If any hard gate fails, TERM V19 and restart the preserved V18 command.

- [ ] **Step 6: Switch the publisher**

TERM only the current publisher job and restart `publish_monitoring_v13.py --interval 2 --artifacts-dir artifacts/arbitrage_v19` with the existing local ingest token. Verify the dashboard timestamp, V19 schema, state equity, paired closed counts, and one-leg abort semantics.

- [ ] **Step 7: Produce the evidence report**

Report tests/build results, job IDs, memory/loop/history/freshness measurements, exact source commit, artifact paths, dashboard status, and any remaining limitations. Do not claim the $0.50/hour benchmark from smoke duration or a small trade sample.

- [ ] **Step 8: Commit only source/test changes still required by reproduced failures**

If no source change occurred during rollout, make no empty commit.
