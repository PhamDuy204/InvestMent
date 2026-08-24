# Fixed Facts — V20

1. Exact V11 decision population: 14,308 rows, 942 timestamps, 21 symbols.
2. Full metrics archive audit range: 2025-04-16 through 2026-07-31, 472 days, 9,912 symbol-day files.
3. Missing files: 0. Parse/network failures after retries: 0. Duplicate timestamp rows in this exact range: 0.
4. Source anomalies: 66 file-days across only six dates; none prevents metric availability at an actual V11 decision timestamp under the fixed causal rule.
5. Decision-time coverage is 100% for `sum_open_interest`, `sum_open_interest_value`, top-trader account/position ratios, global long/short ratio, taker long/short volume ratio and `oi_log_change_1h`.
6. Latest source observation at every decision is t-5m; the one-hour comparison source is also exactly five minutes before t-1h.
7. Do not interpolate missing archive values and do not use a source row timestamped at or after the decision endpoint.
8. Historical data through 2026-08-20 remains DEVELOPMENT; later outcomes remain reserved.
9. Trial 871 and live trading remain blocked.
