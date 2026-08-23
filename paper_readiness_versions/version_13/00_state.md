# Version 13 — State Snapshot

## Scientific state

- Branch: `v11-root-cause-paper-readiness`
- Root cause: **ALPHA_FAILURE (dominant)**
- V12: `NO_STABLE_RELATIVE_RANK_EDGE` — rank-only H12 rescue rejected.
- V13: **NO_MATERIALLY_NEW_EXISTING_CAUSAL_INTERACTION** — the compact existing-variable scan found no causal variable that is both directionally stable enough to justify follow-up and materially distinct from the retained H12 feature set / prior H4-H8/V10 mechanisms.
- Decision: **retire further H12 filter/rank/regime rescue on the currently observed feature family**. Future work must start from a materially new causal factor family or new independent evidence, not another transformation of saturated H12 inputs.
- Performance trial max: `870`
- Trial `871`: **not authorized, not consumed**
- Factor admitted: `false`
- Candidate frozen: `false`
- `READY_TO_START_PAPER=false`
- `A1=NOT_STARTED`
- `PAPER_VALIDATED=false`
- `LIVE_NOT_AUTHORIZED`

## Key V13 evidence

On the chronological 70% selection partition of each outer fold, row-level Spearman correlation with `sign(effective_score) * holding_return_label` was:

- `lag_return_1h`: `+0.03855, +0.04034, +0.01473` across folds 0/1/2.
- `trade_count_z24`: `-0.01396, -0.03352, -0.03218`.
- `quote_volume_z24`: `-0.01211, -0.02593, -0.02844`.
- `taker_imbalance`: `-0.02561, -0.04374, -0.01455`.
- `funding_rate`: `-0.00718, -0.06636, -0.01161`.
- `realized_vol_24`: `-0.03766, -0.00764, -0.04558`.

These are diagnostic associations only. The apparently stable variables are not materially new: the retained H12 `FACTOR_COLUMNS` already include volatility, volume/activity, taker imbalance, funding, market/asset returns, sessions, breadth and lagged BTC/ETH returns; `lag_return_1h` has also been used as a control/input in prior H4/H8 research. No performance candidate was created.
