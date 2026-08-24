# State — Version 19

V19 resolves V18 P0 and corrects one provenance mistake in the initial V18 model probe.

- Exact historical V4/V11 reproduction requires the causal universe column **`in_universe_15`**, not `in_universe_10`.
- With `in_universe_15`, regenerated Ridge V4 decisions match the inherited V4 decision log exactly in all 14,308 keys; maximum target-weight difference is `8.70e-15` and score/label differences are numerical noise only.
- Replaying the regenerated Ridge through the exact V11 70/30 fold partition + drift/funding/cost/final-unwind flow reproduces aggregate V11 net `-0.035286447021` and Sharpe `-0.699873546093`.
- Fixed HistGradientBoosting under the **same** corrected flow is worse: aggregate net `-0.070824194959`, Sharpe `-1.553732827252`, wrong-side economic damage `1.581617566221` versus Ridge `1.218541324641`.
- HistGB improves net in only `1/3` chronological held-out development slices and wrong-side economic damage in only `1/3`; it is rejected as a price-only nonlinear rescue.
- No stacking, Optuna, or RL follow-up is justified from this result.
- A materially new official Binance USD-M `metrics` family is historically available at 5-minute cadence. Availability audit found all 21 V11 symbols with exactly 288 rows/day on four representative dates spanning the old folds (`2025-04-16`, `2025-09-20`, `2026-02-24`, `2026-07-31`). Fields include open interest, top-trader long/short ratios, global long/short ratio, and taker long/short volume ratio.
- This availability audit inspected timestamps/schema only, not return outcomes.
- Trial 871 remains unauthorized/unconsumed; `READY_TO_START_PAPER=false`; `A1=NOT_STARTED`; `LIVE_NOT_AUTHORIZED`.
