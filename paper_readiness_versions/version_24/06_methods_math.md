# Methods / Math — V24

Raw directional score:

`mu_i,t = sign(ret_4,i,t) * log(OI_i,t / OI_i,t-1h)`.

Both OI observations follow the V20 strict causal as-of rule.

The first economic replay must feed `mu` directly into the inherited frozen V4 optimizer and execution/accounting path. This deliberately avoids learning a post-outcome scale from the development results.
