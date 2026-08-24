# State — Version 30

V30 resolves the V29 forward-L2 maturity question without opening reserved outcomes.

The existing recorder and schema are healthy enough for future microstructure research, but the **DEVELOPMENT-eligible sample is not mature enough for an H12 test**.

- 3,675 parquet files; all checked SHA-256 sidecars match.
- 220,500 snapshots total across all 21 expected symbols; exactly 10,500 snapshots per symbol in the audited files.
- Median capture cadence is about 7.35 seconds; there are no same-day gaps >20 seconds and the largest same-day gap is about 10.03 seconds.
- Schema already contains the V17-fixed `top_of_book_imbalance`, microprice, spread and depth-5/10/20 fields. No feature/downloader code is needed.
- Only 2026-08-20 10:46:53Z–16:49:18Z lies on or before the fixed DEVELOPMENT cutoff, giving about **6.04 common hours across all 21 symbols**.
- Later L2 begins 2026-08-23 13:07:32Z and is reserved. Metadata/continuity were inspected, but no post-cutoff return/outcome was opened.
- There is a roughly 68-hour recorder hole between the 2026-08-20 and 2026-08-23 windows, so these observations cannot be represented as one continuous sample.

Therefore no L2 predictive test, portfolio replay, model fit, threshold, or new DEVELOPMENT configuration is authorized in V30. Development configuration count remains 10. Trial 871 remains untouched.

`READY_TO_START_PAPER=false`; `A1=NOT_STARTED`; `PAPER_VALIDATED=false`; `LIVE_NOT_AUTHORIZED`.
