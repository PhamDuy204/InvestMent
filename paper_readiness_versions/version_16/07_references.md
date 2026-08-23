# References — V16

1. Binance public-data README — official bulk public data scope and archive formats.
2. Binance public-data issue #371 — historical futures L2 download path removed; public `bookTicker` listing lacks pre-May-2023 history in the reported path.
3. Binance public-data issues #372/#380 — futures `bookTicker` bulk data stopped updating around March 2024, so it cannot cover the 2025–2026 H12 folds.
4. Binance public-data issue #431 — `bookDepth` misalignment report; independently reproduced by V15's fixed audit.
5. Tardis Binance USDT Futures documentation — coverage since 2019-11-17; captures `depth`, `bookTicker`, generated depth snapshots and validates incremental-book sequence continuity.
6. Tardis downloadable CSV documentation — free downloadable samples are limited; full arbitrary historical periods use API/service access.
7. Cont, Kukanov & Stoikov — *The Price Impact of Order Book Events*, JFE 12(1):47–88; arXiv:1011.6402.
8. Stoikov — *The micro-price: a high-frequency estimator of future prices*, Quantitative Finance 18(12):1959–1966.
