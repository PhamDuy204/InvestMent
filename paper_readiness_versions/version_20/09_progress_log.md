# Progress Log

## V20 full-range metrics provenance checkpoint — 2026-08-24 Asia/Ho_Chi_Minh

- Preserved and incorporated the pre-existing V19 uncommitted integrity note; no work was overwritten.
- Downloaded/audited 9,912 official Binance USD-M daily metrics files over 472 days x 21 symbols.
- 9,846 file-days clean; 66 anomalies concentrated on six dates; no missing archive files and no parse failures.
- Defined the strict `< decision_time`, <=15m as-of availability rule without outcome access.
- Joined only decision keys (`decision_timestamp`, `symbol`), not H12 outcomes: all 14,308 decisions have 100% availability for all six metrics and fixed one-hour OI change.
- Source rows are exactly t-5m at each decision and t-1h-5m at the one-hour comparison endpoint.
- P0 source-provenance blocker is resolved. Next step is mechanism predeclaration before any outcome read.
- Trial 871 remains unauthorized/unconsumed. `LIVE_NOT_AUTHORIZED`.
