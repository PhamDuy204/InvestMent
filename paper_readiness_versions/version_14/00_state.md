# Version 14 — State Snapshot

## Scientific state

- Branch: `v11-root-cause-paper-readiness`
- Root cause: **ALPHA_FAILURE (dominant)**.
- V12 rejected H12 rank rescue: `NO_STABLE_RELATIVE_RANK_EDGE`.
- V13 rejected further rescue inside the saturated H12 feature family: `NO_MATERIALLY_NEW_EXISTING_CAUSAL_INTERACTION`.
- V14 provenance result: **HISTORICAL_PUBLIC_DEPTH_SOURCE_FOUND**.
- Local forward-only L2/positioning data do not overlap the old H12 development panel, but Binance Data Vision has historical USD-M `bookDepth` files spanning representative dates in all three historical folds.
- This historical `bookDepth` family is a materially different source from bar-volume/funding/return features, but it is **not yet an admitted factor**. Dataset semantics/quality must be validated before any development diagnostic.
- Performance trial max: `870`.
- Trial `871`: **not authorized, not consumed**.
- Factor admitted: `false`.
- Candidate frozen: `false`.
- `READY_TO_START_PAPER=false`.
- `A1=NOT_STARTED`.
- `PAPER_VALIDATED=false`.
- `LIVE_NOT_AUTHORIZED`.

## Provenance facts

- Historical H12/execution panel: `2025-04-16 12:00 UTC` through `2026-07-31 08:00 UTC`, 14,308 rows, 21 symbols, 3 folds.
- Local L2 starts only `2026-08-20 10:46:51 UTC`; it therefore cannot explain historical folds by direct join.
- Local L2 pre-boundary coverage is only two short sessions: about 6h on 2026-08-20 and about 4h before the V11 boundary on 2026-08-23.
- Local positioning is explicitly `FORWARD_ONLY_FIRST_SEEN`; historical backfill is marked `DATA_LIMITATION`.
- Binance Data Vision historical USD-M `bookDepth` returned HTTP 200 on representative BTCUSDT dates `2025-04-16`, `2025-09-20`, `2026-02-24`, and `2026-07-31`.
- Sample schema is `timestamp,percentage,depth,notional`, with ±1..±5 percentage buckets.
- Historical `bookTicker` on `2025-04-16` returned HTTP 404, so do not assume historical top-of-book quantity is available from that path.
