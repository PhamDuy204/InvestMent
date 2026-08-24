# Open Problems — Ordered by Leverage

## P0 — Validate historical `bookDepth` before using it

A potentially independent historical source now exists, so the immediate blocker is no longer “find any data”. It is **prove the data semantics and integrity are good enough for one causal development diagnostic**.

Smallest falsifiable question:
> Across representative symbols/dates in each historical fold, are Binance USD-M `bookDepth` timestamps, ±1% depth/notional buckets, availability, and implied price/depth relationships internally consistent enough to construct one deterministic depth-asymmetry/liquidity statistic without hindsight repair?

Minimum checks before research use:
- official file/checksum provenance;
- timestamps strictly parseable and monotone after sorting;
- all required ±1..±5 buckets present at a high rate;
- depth/notional finite and non-negative;
- no symbol/date-level implausible implied-price mismatch versus independent contemporaneous market price;
- quantify missing/duplicate timestamps rather than silently filling;
- use the same fixed validation rule across folds/symbols.

Known risk: Binance public-data issues report possible `bookDepth` misalignment on some USD-M files. If integrity fails materially, reject this source rather than patching around bad dates.

## P1 — One parameter-light L2/depth mechanism, development only

Only if P0 passes, test one mechanism. Preferred first diagnostic:

`depth_asymmetry_1pct = (bid_notional_1pct - ask_notional_1pct) / (bid_notional_1pct + ask_notional_1pct)`

where side semantics must first be proven from source documentation/data. Do not threshold-search. Evaluate association/economics only on historical development partitions; keep V11 post-boundary outcomes unopened.

Order-flow imbalance and micro-price literature provide economic motivation for order-book imbalance as short-horizon information, but Binance historical `bookDepth` is an aggregated percentage-depth dataset, not the same object as tick-level OFI or the local top-of-book recorder. Do not claim equivalence.

## P2 — Untouched post-boundary evidence

Boundary remains `2026-08-23T17:16:03.853710+00:00`. Do not use reserved post-boundary outcomes to design or validate P0/P1. Trial 871 remains blocked.

## P3 — Positioning

Keep collecting but do not use it for historical-fold development unless an independently verifiable historical public source is found. Current recorder provenance is `FORWARD_ONLY_FIRST_SEEN`.

## P4 — Runtime/environment reproducibility

V9 venv is source-stale for importing V11. Reconcile only when an actual V11 project replay/code run is required. Data-only inspection may use its installed pandas/numpy without importing project modules.

## P5 — Multiple testing / paper readiness

DSR/PBO/CSCV/CPCV remain not computable for a promoted candidate. SCIENCE and FREEZE still block paper start. Reuse existing execution/paper infrastructure; do not rewrite it.
