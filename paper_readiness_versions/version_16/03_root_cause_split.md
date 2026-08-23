# Root Cause Split — V16

## What changed

The root cause did not change. The research path did.

- Existing H12 information family: saturated/rejected.
- Binance `bookDepth`: historical integrity failure in earliest fold.
- Other Binance public top-of-book/L2 bulk archives: insufficient old-fold coverage.
- Tardis: technically viable but would require paid/full API access and a new historical data path.
- Existing local L2: already collected, causal from first-seen timestamps, no new dependency or pipeline needed.

## Simplest path

1. Stop trying to retrofit microstructure into old folds.
2. Preserve old H12 results as observed historical evidence only.
3. Define a new forward-only research boundary using the recorder already running.
4. Use an existing normalized L2 field/one simple imbalance statistic first.
5. Reserve a later block untouched before any performance evaluation.
6. Only after a development mechanism survives do runtime reconciliation and one-shot held-out authorization become relevant.
