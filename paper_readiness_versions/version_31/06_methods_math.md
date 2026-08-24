# Methods / Math — V31

The feature remains unchanged:

`I_t = (Q_bid,t - Q_ask,t) / (Q_bid,t + Q_ask,t)`.

Sampling remains one hourly decision timestamp per symbol. H12 labels overlap heavily at hourly cadence, so statistical interpretation must be chronological rather than treating each hour as independent. The V17 two-half sign-stability check remains the first diagnostic and is intentionally parameter-free.

The seven-day block is an evidence-collection rule, not a claim of statistical sufficiency for production. It provides enough market-time diversity to avoid the obviously invalid ~6-hour V30 sample while keeping the first test bounded and simple.
