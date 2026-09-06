# V13 Monitoring Dashboard Design

## Goal

Build and deploy a public, read-only monitoring website for the V13 cross-exchange paper-trading runner so the user can quickly see whether the virtual $20 account is profitable and whether the strategy is operationally effective.

## Safety Boundary

- The dashboard is monitoring-only. It must not expose order placement, exchange credentials, private exchange endpoints, or live-trading controls.
- The V13 runner remains the source of truth for trading state and accounting.
- Monitoring failures must never stop, restart, or mutate the V13 runner.
- The telemetry publisher may read only V13 monitoring artifacts and may only send an allow-listed payload.
- No exchange API key, secret, environment dump, stack trace containing credentials, or raw private exchange response may be sent to Vercel.

## Architecture

The existing Python V13 paper runner continues to run in the Eztech sandbox. A new standalone Python telemetry publisher reads `artifacts/arbitrage_v13/state.json`, `health.json`, and `positions.jsonl` when present, computes monitoring summaries, and POSTs a filtered payload to a Vercel Next.js Route Handler.

The Vercel app validates an `Authorization: Bearer <INGEST_TOKEN>` header and the telemetry schema before persisting the latest payload in Vercel Blob. The public dashboard reads only the stored telemetry. Vercel Blob is used as lightweight durable state, not as the trading source of truth.

Publisher failures are isolated: network/API/storage errors are logged and retried on the next interval without affecting V13. If telemetry stops arriving, the web UI changes from HEALTHY to STALE based on `updated_at` age.

## Telemetry Schema

Top-level fields:

- `schema_version`: `v13-monitoring-1`
- `updated_at_utc`: publisher timestamp
- `runner_health`: `HEALTHY`, `DEGRADED`, or `UNKNOWN`
- `runner_error`: nullable sanitized short error string
- `initial_equity`
- `equity`
- `realized_pnl`
- `return_pct`
- `scan_count`
- `opened_position_count`
- `closed_position_count`
- `open_position_count`
- `open_positions`: allow-listed position details only
- `closed_positions`: bounded recent close history, maximum 200 entries
- `metrics`: derived effectiveness metrics

Derived metrics:

- `win_rate_pct`
- `profit_factor`
- `avg_win`
- `avg_loss`
- `fee_drag`
- `avg_holding_seconds`
- `max_drawdown_pct`
- `opportunity_to_trade_pct` when a valid denominator is available, otherwise null
- `closed_trade_count`

Metrics that do not have enough evidence must be `null`, never fabricated or shown as zero unless zero is semantically correct.

## Dashboard UX

The dashboard is a dark, restrained financial monitoring surface rather than a trading terminal. It uses strong typography, generous spacing, clear hierarchy, subtle borders, and restrained positive/negative status colors.

Top bar:

- product title `InvestMent · V13 Paper Monitor`
- public read-only badge
- health chip: HEALTHY / STALE / DEGRADED / WAITING
- last update age

Primary KPI grid:

- Current Equity
- Realized PnL in dollars and percent
- Max Drawdown
- Win Rate
- Closed Trades
- Open Positions

Main visual area:

- equity curve reconstructed from initial equity plus realized close events
- cumulative realized PnL curve
- clear empty state before the first closed position

Effectiveness panel:

- Profit Factor
- Avg Win
- Avg Loss
- Fee Drag
- Avg Holding Time
- Scan Count
- evidence warning when there are too few closed trades

Recent positions table:

- symbol
- long venue / short venue
- quantity
- entry / exit summary when present
- hold time
- fees
- close reason
- net PnL

Mobile layout collapses into readable KPI cards and horizontally scrollable recent-trade details.

## Status Rules

- `DEGRADED`: runner health explicitly reports an error/non-healthy state.
- `STALE`: latest telemetry is older than 120 seconds.
- `HEALTHY`: telemetry is fresh and runner health is HEALTHY.
- `WAITING`: no telemetry is stored yet.

## Storage

Use Vercel Blob `telemetry/latest.json` with overwrite enabled. The dashboard reads it through a server Route Handler and returns `Cache-Control: no-store`. The ingest token and Blob read-write token are server-only Vercel environment variables.

A 60-second Blob cache propagation delay is acceptable for this paper-monitoring use case. The publisher default interval is 30 seconds, while the UI displays the actual telemetry age rather than pretending to be tick-level real time.

## Testing

Python:

- payload construction from empty artifacts
- payload construction with open positions
- metrics from wins/losses
- max drawdown calculation
- secret/redaction boundary: output contains only allow-listed keys
- publisher network failures do not mutate artifacts or raise out of the continuous loop

Web:

- pure metric/presentation helpers with empty and populated telemetry
- ingest rejects missing/incorrect bearer token
- ingest rejects malformed schema
- empty dashboard renders WAITING / not-enough-data states
- production build succeeds

Integration:

- run publisher in `--once --dry-run` against the live V13 artifacts
- deploy web app
- POST one real filtered telemetry payload to production ingest endpoint
- fetch production dashboard/API and verify the same equity/scan count are visible

## Git and Deployment

Development happens on `v13-monitoring-dashboard` in an isolated worktree. Do not modify historical V7-V13 research boundaries or V13 trading logic unless a read-only telemetry bug requires it. Keep deployment code under `monitoring-web/` and publisher code under `scripts/`.

Deployment should target the user's connected Vercel Hobby team. Remote Git branches are not changed unless deployment requires Git source; if Git is required, push only `v13-monitoring-dashboard` and do not merge or force-push any existing branch.
