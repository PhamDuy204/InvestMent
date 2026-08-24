# State — Version 31

V31 resolves V30's evidence-boundary question without opening any reserved L2 outcomes and without adding code.

A fresh search did not identify a new free/public historical microstructure source that overturns the V15–V16 conclusion:

- Binance ordinary public bulk `bookTicker` still does not cover the required 2025–2026 period.
- Binance historical `bookDepth` remains rejected by the existing fixed integrity/semantics audit.
- Binance's older first-party historical futures order-book workflow exists/documented as tick-level `T_DEPTH`, but access is signed/account-gated rather than an ordinary public bulk archive, and Binance explicitly notes gaps. It is therefore not adopted as a silent replacement source.
- Tardis remains technically suitable but requires service/API access for arbitrary history; no new paid historical pipeline is justified here.

The lowest-complexity scientifically clean path is to reuse the already-existing V17 forward-L2 boundary rules and reset them **prospectively** at the next untouched UTC-hour boundary, before corresponding outcomes exist.

## Prospective boundary

- DEVELOPMENT L2 starts: `2026-08-24T06:00:00Z`.
- DEVELOPMENT L2 ends: `2026-08-31T06:00:00Z` (7 contiguous calendar days).
- H12 purge gap: `2026-08-31T06:00:00Z` through `2026-08-31T18:00:00Z`.
- UNTOUCHED L2 starts: `2026-08-31T18:00:00Z`.
- UNTOUCHED L2 ends: `2026-09-07T18:00:00Z` (7 days).

The V17 continuity/coverage rules are reused exactly: one hourly decision timestamp, >=20/21 symbols per hour, >=95% hourly presence per symbol, and any common outage >15 minutes resets the development clock. The fixed first feature remains `top_of_book_imbalance`; no threshold or new transformation is selected.

No post-cutoff return/outcome label was inspected in V31. Existing 2026-08-23/24 pre-boundary L2 remains reserved/quarantined and is not repurposed into this new DEVELOPMENT block.

`DEVELOPMENT_CONFIGURATION_COUNT=10`; trial 871 remains untouched; `READY_TO_START_PAPER=false`; `A1=NOT_STARTED`; `PAPER_VALIDATED=false`; `LIVE_NOT_AUTHORIZED`.
