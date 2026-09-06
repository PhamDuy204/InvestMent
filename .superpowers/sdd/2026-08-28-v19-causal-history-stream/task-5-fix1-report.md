# Task 5 review fix round 1 report — V19 terminal funnel telemetry

## Result

COMPLETE

- BASE: `ab8834d09a4a80c974a7dda29024caf5adcb57a3`
- Commit subject: `fix: reconcile v19 terminal funnel telemetry`
- Scope: Task 5 review findings only

## TDD evidence

### RED

- `PYTHONPATH=.:src pytest -q tests/test_arbitrage_v19.py -k 'market_data_timeout_counts or post_fill_rejection_counts or paired_open_counts'`
  - 1 failed, 2 passed, 22 deselected.
  - The missing-market-data timeout removed the zero-fill pending entry but left `candidate_funnel_counts["no_causal_fill"] == 0`.
- `node --test monitoring-web/tests/telemetry.test.mjs`
  - 18 passed, 1 failed.
  - V19 telemetry validation accepted an invalid required counter.

### GREEN

- Added the single missing `no_causal_fill` increment directly beside the existing `MARKET_DATA_TIMEOUT` terminal cancel branch.
- Required V19 cause and funnel counters now must be nonnegative integers before telemetry is accepted.
- Added behavioral terminal accounting regressions for:
  - missing-market-data no-causal-fill timeout, including a second processing call proving exactly-once accounting;
  - post-fill rejection and abort;
  - paired position open.
- Removed the inherited V18 dashboard source-string assertion and its unused file-read import. The telemetry suite now tests Task 5 telemetry behavior without depending on uncommitted `dashboard.tsx` lineage.

## Verification

- Focused backend:
  - `PYTHONPATH=.:src pytest -q tests/test_arbitrage_v19.py tests/test_monitoring_v13.py tests/test_publish_monitoring_v13.py`
  - 50 passed in 5.70s.
- Frontend:
  - `npm --prefix monitoring-web test`
  - 19 passed, 0 failed.
- Ruff:
  - `ruff check scripts/run_arbitrage_paper_v19.py tests/test_arbitrage_v19.py`
  - PASS.
- `git diff --check`
  - PASS.
- Clean committed-worktree frontend verification:
  - Detached committed HEAD had an empty status before the test.
  - `npm --prefix monitoring-web test`: 19 passed, 0 failed.
  - The temporary worktree was removed after verification.

## Boundaries preserved

- No gate, EV, fill, margin, PnL, or position-accounting economics changed.
- V17 and V18 behavior remains unchanged.
- Paper/public-only boundaries remain unchanged.
- No dependencies or runtime abstractions were added.
- No runner or publisher process was started or stopped.
- Pre-existing dirty dashboard and earlier-runner lineage was not staged.
