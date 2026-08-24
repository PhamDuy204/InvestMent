# Methods / Math — V25

The raw mapping `mu=sign(ret_4)*dlog(OI_1h)` creates targets through the frozen optimizer that change too aggressively as `mu` varies. Its turnover is ~6.24x the corrected H12 baseline.

A reliability mapping can instead preserve baseline H12 target direction/magnitude and use only the sign of the independent H21-C state to decide whether a *new/increased* exposure is trustworthy.
