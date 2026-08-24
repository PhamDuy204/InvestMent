# Methods and Minimal Mathematics

Use these only when their assumptions match the available provenance. Do not implement a method solely because it sounds sophisticated.

## 1. Economic decomposition

For decision periods `t=1..T`:

`r_net,t = w_t * r_asset,t + r_funding,t - c_t`

With linear turnover cost:

`c_t = k * |w_t - w_(t-1)|`

where `k` is one-way cost. This makes the first diagnostic simple: if `sum(w_t*r_asset,t + funding_t) <= 0`, cost reduction is not the root-cause fix.

## 2. Direction vs ranking

Let `s_i,t` be H12 score and `r_i,t+h` future return.

Absolute directional information asks whether:

`E[sign(s_i,t) * r_i,t+h] > 0`.

Relative/ranking information asks whether future returns increase with score rank, e.g. whether

`E[r | rank(s) in top] - E[r | rank(s) in bottom] > 0`

consistently across chronological development folds.

This distinction is useful because fold-1 may invalidate market-direction prediction while a cross-sectional ordering could still exist. It must be tested, not assumed.

## 3. Conditional sign stability

For a causal regime `z_t`, define

`mu_z = E[sign(s_t) * r_(t+h) | z_t=z]`.

A regime interaction is defensible only if the sign/magnitude of `mu_z` is reasonably consistent across separate chronological development slices. A rule chosen because one already-observed fold looks bad is not evidence.

## 4. Purging overlapping labels

If observation `i` uses an outcome interval `[t_i0, t_i1]` and the test interval is `[T0,T1]`, purge a training observation when intervals overlap:

`(t_i0 <= T1) and (t_i1 >= T0)`.

Embargo may be added after a test block when serial dependence makes immediate post-test training unsafe. Use only when overlap/dependence actually requires it.

## 5. Deflated Sharpe Ratio intuition

A high observed Sharpe selected from many tried strategies is biased upward. DSR compares observed Sharpe against an elevated benchmark implied by the number/distribution of trials and adjusts for non-normal return moments. It needs defensible trial/return provenance; a count plus one scalar Sharpe is not enough for this project's readiness decision.

## 6. PBO / CSCV intuition

CSCV forms multiple symmetric train/test combinations over aligned strategy return paths and asks how often the in-sample winner underperforms out of sample. PBO therefore requires an aligned matrix of genuinely tried strategy returns. If that matrix does not exist, report `NOT_COMPUTABLE_WITH_CURRENT_PROVENANCE`.
