# Methods / Math — V28

Baseline: `y = beta_0 + beta_price^T x_price + eps`.

Candidate: `y = beta_0 + beta_price^T x_price + beta_OI c + eps`, where `c = sign(ret_4)*log(OI_t/OI_t-1h)` and all inputs are standardized inside the training fold before Ridge `alpha=1.0`.

The candidate coefficient sign check uses the standardized-space Ridge coefficient for `c`; only sign, not magnitude, is gated.
