# State — Version 21

V21 is a pre-outcome scientific predeclaration checkpoint.

The Binance metrics source passed V20 provenance/decision-coverage audit. V21 fixes an ordered mechanism ladder before opening historical H12 outcomes.

### H21-A — Global crowd-short contrarian positioning (test first)

`crowd_short_contrarian = -log(count_long_short_ratio)` using the latest causal metrics row `< decision_time`.

Fixed sign expectation: larger values (more accounts net-short relative to net-long) predict higher subsequent H12 return. This is motivated by published evidence that more net-short speculative futures behavior can predict higher crypto returns, but Binance global account ratio is not assumed identical to the paper's trader classification.

### H21-B — Top-trader versus global positioning divergence (only if A fails)

`smart_crowd_divergence = log(sum_toptrader_long_short_ratio) - log(count_long_short_ratio)`.

Fixed sign expectation: top-trader position ratio being more long-biased than the global account ratio predicts higher subsequent H12 return.

### H21-C — Open-interest trend confirmation (only if A and B fail)

`oi_trend_confirmation = sign(ret_4) * oi_log_change_1h`.

Fixed sign expectation: positive values predict positive subsequent H12 return and negative values predict negative subsequent H12 return. This encodes the classic hypothesis that expanding OI confirms the current price direction, while contracting OI weakens/reverses that confirmation.

No threshold, quantile cut, model fitting, hyperparameter search, Optuna, stacking, or RL is permitted at this stage.
