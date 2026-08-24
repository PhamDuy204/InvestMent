# Methods / Math — V27

Proposed future model, not yet authorized:

`y_H12 = beta_0 + beta_price^T x_price + beta_OI * [sign(ret_4) * dlog(OI_1h)] + epsilon`

with StandardScaler and Ridge `alpha=1.0` exactly as inherited H12. `beta_OI` must be estimated only inside each chronological training fold.
