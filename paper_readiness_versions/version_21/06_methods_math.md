# Methods / Math — V21

At each decision timestamp `t`, for eligible symbols `i`:

`A_i,t = -log(global_long_short_account_ratio_i,t)`.

For each timestamp with at least four symbols, compute cross-sectional Spearman rank correlation between `A_i,t` and realized H12 holding return `r_i,t+12h`.

Also compute a fixed spread:

`spread_t = mean(return of top-2 A) - mean(return of bottom-2 A)`.

Fold statistics are time averages of timestamp IC and spread. No rank bucket/threshold is selected from outcomes.
