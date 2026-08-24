# Open Problems — Ordered by Leverage

## P0 — Accumulate enough contiguous forward L2 evidence

The feature and boundary rule are now fixed without outcome access. The current blocker is simply insufficient contiguous data.

Predeclared development eligibility:
- use the existing 21-symbol recorder universe;
- use one hourly decision timestamp per symbol, not every ~7s snapshot as an independent observation;
- require 7 contiguous calendar days after the latest common restart;
- each UTC hour must have usable L2 for at least 20/21 symbols and each symbol must be present in at least 95% of eligible hourly timestamps;
- any common outage >15 minutes breaks continuity and restarts the 7-day clock;
- feature is fixed to existing `top_of_book_imbalance`; no threshold search.

Once 7 days exist, split development chronologically into two equal halves and only then inspect H12 outcomes for development diagnostics.

## P1 — Reserve untouched evaluation before development outcome inspection

After the 7-day development block closes, reserve a 12h purge gap for the H12 label horizon, then a separate 7-day untouched block. The untouched block must remain unread during development design.

## P2 — Runtime/environment reproducibility

V9 venv remains stale for V11 imports. Reconcile only if the forward L2 mechanism survives development diagnostics and integration/replay becomes necessary. The V9 venv may be used only as a parquet reader for metadata/schema inspection; it is not the V11 scientific runtime.

## P3 — Trial 871 / paper readiness

Trial 871 remains blocked behind candidate freeze, predeclaration, untouched eligibility, deterministic audit, council methodology check and exact local==remote SHA. SCIENCE and FREEZE remain failing readiness categories.
