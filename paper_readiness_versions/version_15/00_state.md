# Version 15 — State Snapshot

## Scientific state

- Branch: `v11-root-cause-paper-readiness`.
- Root cause remains **ALPHA_FAILURE (dominant)**.
- V12: `NO_STABLE_RELATIVE_RANK_EDGE`.
- V13: `NO_MATERIALLY_NEW_EXISTING_CAUSAL_INTERACTION`.
- V14: official historical Binance USD-M `bookDepth` was found as a potentially independent factor family.
- V15: **REJECT_BOOKDEPTH_AS_CROSS_FOLD_DEVELOPMENT_SOURCE** after a fixed integrity audit against independently checksum-verified USD-M 1m mark-price archives.
- 16 symbol/date pairs audited: BTCUSDT, ETHUSDT, SOLUSDT, AAVEUSDT × 2025-04-16, 2025-09-20, 2026-02-24, 2026-07-31.
- 12/16 pairs pass the fixed gate. All four symbols on 2025-04-16 fail; SOLUSDT and AAVEUSDT fail materially on side/implied-price consistency.
- The failure is not a checksum/download problem. Official ZIP checksums matched.
- 2026 files add valid ±0.20% buckets; the audit allows extra buckets and only requires ±1..±5, so the rejection is not caused by schema expansion.
- No historical-date/symbol repair is allowed because that would make source selection outcome/data-quality-period dependent.
- Performance trial max: `870`; trial `871` remains **not authorized, not consumed**.
- Factor admitted: `false`; candidate frozen: `false`.
- `READY_TO_START_PAPER=false`; `A1=NOT_STARTED`; `PAPER_VALIDATED=false`.
- `LIVE_NOT_AUTHORIZED`.
