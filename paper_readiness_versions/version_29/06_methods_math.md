# Methods / Math — V29

V29 candidate model:

`y = beta_0 + beta_price^T x_price + beta_OI c + eps`,

`c = sign(ret_4) * log(OI_t/OI_t-1h)`,

with StandardScaler and Ridge `alpha=1.0`.

Although `beta_OI > 0` in all three folds and mean IC improves by approximately `1.05e-4`, corrected economics worsen materially. This demonstrates that small predictive metric improvements are not sufficient promotion evidence for a cost-sensitive portfolio.

Future feature families must first show stable chronological predictive structure and then survive the exact corrected execution/accounting flow without post-hoc parameter selection.
