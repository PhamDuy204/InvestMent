# Root Cause Split — V19

## P0 resolved

The V18 economics mismatch was not a mysterious accounting bug. It came from evaluating a regenerated strategy on the wrong causal universe (`in_universe_10`) and bypassing the exact inherited V4/V11 provenance.

Using `in_universe_15` plus the frozen V4 optimizer/overlay reproduces every inherited Ridge decision row and the corrected V11 replay numerically.

## Scientific consequence

Once the comparison is fair, fixed HistGB is worse than Ridge. Increasing model capacity over the same price-only feature family does not solve the alpha failure.

Therefore the next root-cause branch is **new information**, not more model complexity. Official Binance futures `metrics` is promising because it contains historical positioning/open-interest state absent from the retained H12 price-only Ridge core.
