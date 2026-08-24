# References — V31

1. Existing V15–V17 source audits and V30 forward-L2 maturity audit.
2. Binance historical futures order-book documentation: `T_DEPTH` is tick-by-tick L2 and may contain gaps; historical download used an authenticated/account-gated workflow rather than ordinary public bulk archives.
3. Binance public-data issue #371: legacy historical futures L2 route removed; ordinary bulk `bookTicker` history does not cover the required recent folds.
4. Tardis Binance Futures documentation: reconstructed depth/top-of-book history with sequence-integrity handling, but arbitrary full history requires service/API access.
5. Cont, Kukanov & Stoikov (2014), *The Price Impact of Order Book Events*.
6. Stoikov (2018), *The micro-price: a high-frequency estimator of future prices*.
