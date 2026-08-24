# Fixed Facts — V31

1. No new historical L2 source passed the "already available + auditable + meaningful pre-cutoff coverage" bar.
2. Do not build a new downloader or feature layer. Reuse the existing L2 recorder and `top_of_book_imbalance`.
3. The new DEVELOPMENT start is prospectively fixed at `2026-08-24T06:00:00Z`, after this checkpoint was designed and before corresponding outcomes exist.
4. DEVELOPMENT requires 7 contiguous days under the existing V17 continuity rules and ends at `2026-08-31T06:00:00Z` only if no common outage >15 minutes resets the clock.
5. Preserve a 12-hour H12 purge gap after DEVELOPMENT.
6. The untouched block is fixed to `2026-08-31T18:00:00Z`–`2026-09-07T18:00:00Z`, subject to continuity rules and must remain unread during development analysis.
7. Existing post-2026-08-20 L2 before the new start remains quarantined/reserved; it is not retroactively converted into development evidence.
8. No L2 performance result is authorized until the development block is complete and continuity/coverage gates pass.
9. `DEVELOPMENT_CONFIGURATION_COUNT=10`; trial 871 is not consumed.
