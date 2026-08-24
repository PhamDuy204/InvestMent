# Open Problems — Ordered by Leverage

## P0 — Find a different historical causal microstructure source, or stop historical rescue

Binance USD-M historical `bookDepth` cannot be used as the cross-fold source because the same fixed audit fails materially in the earliest fold. Do not exclude Apr-2025 or repair symbols after seeing the defect.

Smallest falsifiable question:
> Is there another public historical order-book/top-of-book source with timestamped coverage across all three old H12 development folds and fixed, independently auditable semantics for the required symbols?

Preference order:
1. Existing repo/local archive already collected before outcomes, if any.
2. Official Binance historical top-of-book/order-book archive with stable schema and actual fold coverage.
3. Another reputable public source only if provenance/licensing/causal timestamps can be verified.
4. If none exists, stop historical microstructure rescue and continue forward L2 collection rather than fabricate backfill.

Do not pay for/newly architect a large data pipeline until availability is proven with a few HEAD/checksum/schema probes.

## P1 — Forward-only L2 research path

Local L2 recorder remains valid for future prospective research but cannot be retrofitted into 2025–2026 old folds. Keep collecting without inspecting reserved future outcomes during factor design. A future version may define a new prospective research boundary rather than force comparability with the old H12 panel.

## P2 — Untouched post-boundary evidence

V11 boundary remains `2026-08-23T17:16:03.853710+00:00`. Do not use reserved post-boundary outcomes to design a replacement factor. Trial 871 remains blocked.

## P3 — Runtime/environment reproducibility

V9 venv remains source-stale for V11 imports. Reconcile only when an actual project replay/integration is justified by a surviving development mechanism.

## P4 — Multiple testing / paper readiness

DSR/PBO/CSCV/CPCV remain not computable for a promoted candidate. SCIENCE and FREEZE still block paper start. Reuse the existing execution/paper infrastructure if readiness is eventually reached.
