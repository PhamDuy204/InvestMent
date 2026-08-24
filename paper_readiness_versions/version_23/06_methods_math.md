# Methods / Math — V23

`C_t = sign(ret_4,t) * log(OI_t / OI_{t-1h})`, using the already-fixed V20 causal OI endpoints.

Positive `C` means OI expanded in the direction of recent 4h price movement; negative means OI expansion conflicts with that direction or OI contracted. The predeclared expectation is a positive cross-sectional relationship with subsequent H12 return.
