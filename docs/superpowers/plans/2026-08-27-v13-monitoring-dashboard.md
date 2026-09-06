# V13 Monitoring Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a public read-only Vercel dashboard that receives sanitized V13 paper-trading telemetry and shows profitability, health, and effectiveness from the virtual $20 account.

**Architecture:** A standalone Python publisher reads V13 artifacts and POSTs an allow-listed telemetry payload to a Next.js ingest Route Handler. The web app stores the latest payload in Vercel Blob and renders a responsive dashboard from that durable monitoring snapshot; monitoring is fully isolated from the paper runner.

**Tech Stack:** Python 3.11 stdlib, pytest, Next.js App Router, React, TypeScript, CSS, `@vercel/blob`, Node built-in test runner, Vercel Functions, Vercel Blob.

**Spec:** `docs/superpowers/specs/2026-08-27-v13-monitoring-dashboard-design.md`

## Global Constraints

- Public read-only dashboard.
- Initial paper capital remains $20 virtual unless V13 state says otherwise.
- Never add live order placement or private exchange calls.
- Never transmit exchange credentials or arbitrary environment variables.
- V13 state remains the accounting source of truth.
- Publisher/storage/dashboard failure must not affect the paper runner.
- Missing evidence renders as null/not-enough-data, never fabricated metrics.
- No merge or force-push of existing remote branches.

---

### Task 1: Telemetry metric and payload builder

**Files:**
- Create: `src/crypto_research/monitoring_v13.py`
- Create: `tests/test_monitoring_v13.py`

**Interfaces:**
- Consumes: V13 `state.json`, `health.json`, optional `positions.jsonl` dictionaries.
- Produces: `build_monitoring_payload(state, health, position_events, updated_at_utc=None) -> dict` and `calculate_effectiveness(initial_equity, closed_positions, scan_count) -> dict`.

- [ ] **Step 1: Write failing tests for empty and populated monitoring payloads**

```python
from crypto_research.monitoring_v13 import build_monitoring_payload


def test_payload_keeps_zero_trade_metrics_unknown():
    payload = build_monitoring_payload(
        {
            "initial_equity": 20.0,
            "equity": 20.0,
            "realized_pnl": 0.0,
            "scan_count": 100,
            "opened_position_count": 0,
            "closed_position_count": 0,
            "open_positions": [],
        },
        {"status": "HEALTHY", "error": None},
        [],
        updated_at_utc="2026-08-27T09:30:00+00:00",
    )
    assert payload["return_pct"] == 0.0
    assert payload["metrics"]["win_rate_pct"] is None
    assert payload["metrics"]["profit_factor"] is None
    assert set(payload) == {
        "schema_version", "updated_at_utc", "runner_health", "runner_error",
        "initial_equity", "equity", "realized_pnl", "return_pct", "scan_count",
        "opened_position_count", "closed_position_count", "open_position_count",
        "open_positions", "closed_positions", "metrics",
    }
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m pytest tests/test_monitoring_v13.py -q`
Expected: FAIL because `crypto_research.monitoring_v13` does not exist.

- [ ] **Step 3: Implement allow-listed payload construction and effectiveness calculations**

Implementation requirements:

```python
MAX_CLOSED_POSITIONS = 200
PAYLOAD_SCHEMA_VERSION = "v13-monitoring-1"
```

Recognize close events from `positions.jsonl` only when they contain a realized PnL field (`realized_net_pnl` or `net_pnl`). Normalize to allow-listed keys. Compute win rate, avg win/loss, profit factor, fee drag, average holding time, and an equity-path max drawdown. Return `None` when the denominator/evidence does not exist.

- [ ] **Step 4: Add tests for win/loss metrics, drawdown, and allow-list redaction**

Include an event containing fake keys such as `apiKey`, `secret`, and `raw_exchange_response`; assert none appear recursively in the returned payload.

- [ ] **Step 5: Run tests GREEN**

Run: `python -m pytest tests/test_monitoring_v13.py -q`
Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/crypto_research/monitoring_v13.py tests/test_monitoring_v13.py
git commit -m "feat: add V13 monitoring telemetry model"
```

### Task 2: Isolated telemetry publisher CLI

**Files:**
- Create: `scripts/publish_monitoring_v13.py`
- Create: `tests/test_publish_monitoring_v13.py`

**Interfaces:**
- Consumes: `build_monitoring_payload`, V13 artifacts directory, `MONITOR_INGEST_URL`, `MONITOR_INGEST_TOKEN`.
- Produces: `load_payload(artifacts_dir) -> dict`, `publish_once(...) -> bool`, CLI `--once`, `--dry-run`, `--interval`.

- [ ] **Step 1: Write failing tests for artifact loading and dry-run**

Create temporary state/health files, omit `positions.jsonl`, call `load_payload`, and assert the current equity/health are preserved.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_publish_monitoring_v13.py -q`
Expected: FAIL because publisher module is absent.

- [ ] **Step 3: Implement publisher with Python stdlib only**

Use `urllib.request.Request` for POST. Send JSON with headers:

```text
Authorization: Bearer <token>
Content-Type: application/json
User-Agent: InvestMent-V13-Monitor/1
```

CLI defaults:

```text
--artifacts-dir artifacts/arbitrage_v13
--interval 30
```

`--dry-run` prints sanitized JSON and performs no network call. Continuous mode catches network/HTTP errors, writes a short stderr message, sleeps, and retries; it never writes to the V13 artifacts directory.

- [ ] **Step 4: Test network failure isolation**

Monkeypatch the URL opener to raise an error and assert `publish_once` returns `False` without changing source artifact checksums.

- [ ] **Step 5: Run publisher tests GREEN and dry-run against live artifacts**

Run:

```bash
python -m pytest tests/test_publish_monitoring_v13.py -q
python scripts/publish_monitoring_v13.py --once --dry-run --artifacts-dir /root/workspace/projects/InvestMent/artifacts/arbitrage_v13
```

Expected: tests pass and JSON shows current V13 equity/scan count with no secrets.

- [ ] **Step 6: Commit Task 2**

```bash
git add scripts/publish_monitoring_v13.py tests/test_publish_monitoring_v13.py
git commit -m "feat: add isolated V13 telemetry publisher"
```

### Task 3: Next.js monitoring app, ingest API, and dashboard

**Files:**
- Create: `monitoring-web/package.json`
- Create: `monitoring-web/tsconfig.json`
- Create: `monitoring-web/next.config.ts`
- Create: `monitoring-web/app/layout.tsx`
- Create: `monitoring-web/app/page.tsx`
- Create: `monitoring-web/app/globals.css`
- Create: `monitoring-web/app/api/ingest/route.ts`
- Create: `monitoring-web/app/api/telemetry/route.ts`
- Create: `monitoring-web/lib/telemetry.ts`
- Create: `monitoring-web/components/dashboard.tsx`
- Create: `monitoring-web/components/equity-chart.tsx`
- Create: `monitoring-web/tests/telemetry.test.mjs`
- Create: `monitoring-web/.env.example`

**Interfaces:**
- `POST /api/ingest`: authenticated telemetry write.
- `GET /api/telemetry`: public latest telemetry read with `no-store`.
- `getDisplayStatus(telemetry, now) -> HEALTHY | STALE | DEGRADED | WAITING`.

- [ ] **Step 1: Scaffold minimal Next.js dependencies**

`package.json` dependencies: `next`, `react`, `react-dom`, `@vercel/blob`; dev dependencies: `typescript`, React/Node type packages, `eslint`, `eslint-config-next`.

- [ ] **Step 2: Write Node tests for display status and equity-series helpers**

Test WAITING with null telemetry, STALE above 120 seconds, DEGRADED from runner health, and a three-close equity sequence.

- [ ] **Step 3: Run Node tests RED**

Run: `cd monitoring-web && npm install && npm test`
Expected: FAIL until `lib/telemetry.mjs` exists.

- [ ] **Step 4: Implement telemetry validation/storage helpers and APIs**

Ingest requirements:

- constant-time-ish token comparison using Node `crypto.timingSafeEqual` after equal-length check
- 401 on missing/bad token
- 400 on invalid schema/version/numeric fields
- Blob `put('telemetry/latest.json', JSON.stringify(payload), {access:'public', allowOverwrite:true, cacheControlMaxAge:60, contentType:'application/json'})`
- do not return or log secrets

Read requirements:

- `list({prefix:'telemetry/latest.json', limit:1})`
- return 404 `{status:'WAITING'}` if absent
- fetch blob URL with a cache-busting query and return JSON with `Cache-Control: no-store`

- [ ] **Step 5: Implement premium read-only dashboard**

Use semantic HTML, responsive CSS, no trading controls. Build KPI cards, inline SVG equity chart, effectiveness cards, health/age indicators, empty-state evidence messaging, and recent-position table. Auto-refresh `/api/telemetry` every 30 seconds in a client dashboard component.

- [ ] **Step 6: Run frontend tests, lint, and production build**

Run:

```bash
cd monitoring-web
npm test
npm run lint
npm run build
```

Expected: all pass.

- [ ] **Step 7: Commit Task 3**

```bash
git add monitoring-web
git commit -m "feat: add V13 Vercel monitoring dashboard"
```

### Task 4: Full verification, Vercel deployment, and live publisher

**Files:**
- Modify only if verification reveals a defect in files created by Tasks 1-3.
- Create runtime publisher log outside Git: `/tmp/investment-v13-monitor-publisher.log`.

**Interfaces:**
- Production public dashboard URL.
- Production `POST /api/ingest` and `GET /api/telemetry`.

- [ ] **Step 1: Run full repository verification**

```bash
python -m pytest -q
python -m ruff check src tests scripts
python -m compileall -q src tests scripts
cd monitoring-web && npm test && npm run lint && npm run build
```

- [ ] **Step 2: Create deployment secrets**

Generate a high-entropy ingestion token locally. Configure `INGEST_TOKEN` and `BLOB_READ_WRITE_TOKEN` only in Vercel server environment; never commit them.

- [ ] **Step 3: Deploy `monitoring-web` to connected Vercel account**

Use the connected Vercel deployment tool. If it requires Git-backed source, push only branch `v13-monitoring-dashboard`; do not merge or force-push other branches.

- [ ] **Step 4: Verify production before wiring publisher**

Fetch `/`, `/api/telemetry`, and deployment build/runtime errors. Dashboard should render WAITING before first ingest and no production build errors should exist.

- [ ] **Step 5: Send one real sanitized telemetry payload**

Configure publisher process environment with only `MONITOR_INGEST_URL` and `MONITOR_INGEST_TOKEN`, then run `--once`. Verify production API shows the same `initial_equity`, `equity`, and `scan_count` as the local source artifacts.

- [ ] **Step 6: Start continuous publisher as an independent background task**

Run every 30 seconds from the original V13 checkout context. Verify both V13 runner and publisher are alive independently.

- [ ] **Step 7: Final verification and local-only commit if fixes were needed**

Confirm worktree clean and report exact deployment URL, current virtual equity, health, publisher status, and Git commit SHAs. Do not claim completion without fresh outputs from tests/build and production fetch.
