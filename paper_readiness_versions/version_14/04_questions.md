# Research Questions — V14

1. Do historical Binance USD-M `bookDepth` files pass a fixed cross-fold integrity audit?
2. What exactly do negative and positive `percentage` buckets mean, and can bid/ask side semantics be proven rather than inferred?
3. Is `notional/depth` contemporaneously consistent with an independent market-price series for each bucket/date/symbol?
4. Are missing/duplicate timestamps sparse enough that no outcome-driven repair is required?
5. If P0 passes, does one fixed ±1% depth-asymmetry statistic add causal information across at least two chronological development slices?
6. Does that effect survive realistic costs when mapped to the existing shared replay, without tuning a threshold?
7. If historical `bookDepth` fails integrity, is there another official historical L2 source; otherwise stop and collect rather than manufacture a factor.
8. Which post-boundary rows remain untouched for a future one-shot evaluation? Do not inspect their outcomes during any of the above.
