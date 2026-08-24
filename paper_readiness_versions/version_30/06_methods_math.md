# Methods / Math — V30

The already-fixed first microstructure feature is:

`I_t = (Q_bid,t - Q_ask,t) / (Q_bid,t + Q_ask,t)`.

No new transformation is required. The current issue is sample geometry.

An H12 label consumes the next 12 hours. With only about 6.04 hours of pre-cutoff common L2, there is not even one full non-overlapping 12-hour development block wholly supported by this recorder window. Treating thousands of ~7-second snapshots as independent observations would therefore create pseudo-replication rather than genuine chronological evidence.
