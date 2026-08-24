# Methods / Math — V32

The first active L2 feature remains unchanged:

`I_t = (Q_bid,t - Q_ask,t) / (Q_bid,t + Q_ask,t)`.

Sampling for the first diagnostic remains one hourly decision timestamp per symbol. H12 labels overlap heavily at hourly cadence, so recorder snapshots are evidence for feature construction/continuity, not independent H12 observations.

The fixed first test is the V17 chronological-half sign-stability diagnostic with zero fitted parameters.

If a later mechanism is needed, prefer mechanisms with a compact mathematical object and a clear falsification rule, for example:

- microprice/order-flow impact: conditional expectation of future midprice/return from imbalance and depth;
- state-space/change-point regime filtering: latent state probability rather than fold identity;
- cross-sectional residual return: asset return minus a causal common-factor estimate;
- uncertainty-aware decision rule: act only when a predeclared predictive interval excludes the no-edge region;
- simulation: calibrate event arrivals/fills/impact to observed L2 before any RL policy is considered.

These are research directions only, not authorized configurations.
