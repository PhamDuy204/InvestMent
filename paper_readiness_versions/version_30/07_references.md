# References — V30

1. Existing repo V15–V17 audits: Binance historical `bookDepth` failed fixed integrity checks; old public bulk `bookTicker`/historical L2 did not provide adequate 2025–2026 fold coverage under the previously audited paths.
2. Binance `binance-public-data` historical futures order-book download documentation: T_DEPTH is tick-by-tick L2 with possible gaps; historical order-book access has used a separate download workflow rather than the ordinary public klines/aggTrades archive.
3. Cont, Kukanov & Stoikov, *The Price Impact of Order Book Events*, Journal of Financial Econometrics 12(1):47–88 — motivates order-flow/depth imbalance as microstructure information, but does not justify using an insufficiently short sample.
4. Stoikov, *The micro-price: a high-frequency estimator of future prices*, Quantitative Finance 18(12):1959–1966 — motivates top-of-book imbalance/microprice as short-horizon information.
