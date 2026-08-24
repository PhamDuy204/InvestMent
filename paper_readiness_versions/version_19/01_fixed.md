# Fixed Facts — V19

1. V18's initial `in_universe_10` model-capacity probe is superseded for economic comparison because it did not reproduce the inherited V4/V11 universe.
2. Correct V4/V11 causal universe is `in_universe_15`; it generates exactly 14,308 decision rows across 942 decision timestamps and 21 symbols, matching the inherited decision log.
3. Corrected Ridge replay reproduces V11 aggregate net and Sharpe to floating-point precision.
4. Fixed HistGB does not repair H12 under corrected execution semantics: net and Sharpe worsen, economic wrong-side damage rises, and only one of three folds improves.
5. Do not tune HistGB or revisit naive stacking on the same price-only features.
6. The next defensible research direction must use materially new causal information rather than more capacity over the saturated H12 feature set.
7. Binance public USD-M daily `metrics` archives are a candidate new family and contain 5-minute `sum_open_interest`, `sum_open_interest_value`, top-trader long/short ratios, global long/short ratio, and taker long/short volume ratio.
8. Representative coverage is complete for all 21 V11 symbols on four dates spanning the historical folds; full-range continuity is not yet proven.
9. All data/outcomes after 2026-08-20 remain reserved from V19 model selection.
10. Trial 871 and live trading remain blocked.
