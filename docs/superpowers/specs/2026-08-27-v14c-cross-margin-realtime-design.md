# V14-C Cross-Margin Portfolio + Realtime Monitor Design

## Goal
Upgrade V14-B paper arbitrage into V14-C with per-venue shared cross-margin accounting, portfolio-wide opportunity allocation, near-real-time monitoring, and scenario controls that visibly project each order/position for $20/$50/$100 and 1x/2x/3x/5x.

## Safety boundary
- PAPER / SIMULATION ONLY.
- Public market data only; no exchange credentials, private endpoints, or create_order.
- Monitoring remains PUBLIC · READ ONLY and cannot mutate runner state.
- Never claim exact liquidation unless public venue tier data is actually modeled. Cross-margin risk uses a clearly labeled conservative maintenance stress rate, not an exchange liquidation quote.

## C margin model
Use `CROSS_MARGIN_PAPER_V1` per venue. Collateral is shared by all positions on the same venue, but never shared across exchanges. For each venue compute account equity from realized venue balance plus current paper unrealized leg PnL, current gross notional, initial-margin requirement at configured leverage, maintenance-stress requirement, available initial-margin capacity, and a stress margin ratio. Candidate entry is rejected when the venue would exceed its configurable margin-utilization cap or maintenance-stress buffer.

The default maintenance stress rate is 5% because public MMR tiers vary by symbol and venue. It is a conservative paper stress parameter, not an exact venue liquidation model. Exact tier-aware liquidation remains `Unavailable` until tier adapters are implemented.

## Portfolio optimizer
Evaluate all tradeable opportunities together. Size each candidate from its positive executable net edge, cap each pair at the existing single-pair gross fraction, enforce portfolio gross leverage, max positions, and per-venue cross-margin capacity. Add a venue concentration penalty so the optimizer prefers a diversified set of routes instead of exhausting one venue on the first candidate. Existing open positions remain first-class constraints.

No negative-net signal may become a trade. WATCH remains observational only.

## Realtime monitoring
Runner keeps its 5-second scan cadence. Publisher changes from 30 seconds to 2 seconds because it only marks currently open positions. Dashboard polls `/api/telemetry` every 2 seconds with `cache: no-store`, prevents overlapping requests, and displays mark freshness. Open-position executable PnL can therefore move between runner scans while Opportunity Radar updates on the runner cadence.

## Scenario controls
Scenario selection is hypothetical/read-only. It never changes live paper positions.

For an open position, scenario scale is:
`capital_ratio * (scenario_leverage / actual_position_leverage)`.
This fixes the current double-counting bug where a 2x scenario multiplied an already-2x paper position by another 2.

The UI will render a `Scenario orders` table. For every current open position it shows route, projected long/short notional, projected gross exposure, projected initial margin, linearized close-now net PnL, PnL as % of selected capital, and selected leverage. If there are no open positions, current TRADEABLE Opportunity Radar rows are used to construct hypothetical pair orders from current edge and configured pair allocation; these remain labeled hypothetical.

## Telemetry
Keep existing V14 schema compatibility and add C fields rather than break production ingestion unnecessarily: `portfolio_model`, cross-margin per-venue summaries, maintenance stress rate, margin utilization cap, optimizer allocations/rejections, and realtime publisher timestamp. Dashboard title changes to `V14-C Cross-Margin Paper Monitor` when `portfolio_model` is C.

## Definition of done
- New C tests pass, plus full Python/frontend/lint/build suites.
- V14-B state migrates in place with current open positions preserved.
- Continuous runner reports `CROSS_MARGIN_PAPER_V1`, zero invariant failures, and continues paper-only operation.
- Publisher interval is 2 seconds and production telemetry freshness changes within a few seconds.
- Scenario buttons visibly change per-order notional/margin/projected PnL.
- Production Vercel dashboard serves V14-C fields with no runtime errors.
- Git checkpoint is clean and contains no token/artifact/secrets.
