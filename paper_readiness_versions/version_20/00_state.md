# State — Version 20

V20 resolves the V19 full-range Binance USD-M metrics provenance blocker.

- Audited every daily metrics archive for the exact V11 21-symbol universe from 2025-04-16 through 2026-07-31: 9,912 expected files, 9,912 present and parseable.
- 9,846 file-days are perfectly clean; 66 have source anomalies concentrated on six dates.
- The anomalies are sparse/common-source issues rather than long missing history: 2025-07-21/22 ratio NaNs, 2025-08-29 three common missing 5-minute slots, two isolated taker-ratio NaN dates, and one 1000SHIB timestamp shifted from 2026-06-28 00:00 to 2026-06-29 00:00.
- Fixed causal availability rule: for decision time `t`, use only the latest completed metrics row with `create_time < t` and age <=15m; never forward/back-fill beyond this as-of rule. For one-hour OI change, compare latest row `<t` with latest row `<t-1h`, each with the same <=15m tolerance.
- Under that pre-outcome rule, all 14,308 inherited V4/V11 decision rows have all six metrics available and `oi_log_change_1h` available. Both current and t-1h rows are exactly 5 minutes old at every decision.
- No H12 return/outcome column was read to establish this coverage.
- Therefore Binance metrics is accepted as a usable historical DEVELOPMENT source with explicit sparse-source anomaly handling by unavailability, not fabricated repair.
- Trial 871 remains unauthorized/unconsumed; `READY_TO_START_PAPER=false`; `LIVE_NOT_AUTHORIZED`.
