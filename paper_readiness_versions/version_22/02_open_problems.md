# Open Problems — V22

## P0 — Test predeclared H21-B exactly once

Use the V21-fixed feature and sign without modification:

`smart_crowd_divergence = log(sum_toptrader_long_short_ratio) - log(count_long_short_ratio)`.

Apply the same fixed gate as H21-A: positive mean timestamp IC in >=2/3 folds, positive top2-bottom2 mean spread in >=2/3 folds, and aggregate mean timestamp IC > 0.

If it fails, record rejection before opening H21-C.

## P1 — Economic replay

Only a mechanism passing P0 may enter corrected V11 economics.

## P2 — Untouched validation / trial 871

Remain blocked; post-2026-08-20 outcomes stay reserved.
