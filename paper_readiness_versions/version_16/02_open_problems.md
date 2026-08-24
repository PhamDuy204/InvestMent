# Open Problems — Ordered by Leverage

## P0 — Define a forward-only L2 research boundary without outcome leakage

Historical microstructure rescue is closed. The next smallest falsifiable question is:

> Can the existing local L2 recorder support one parameter-light, causal imbalance feature under a new forward research boundary, with enough timestamp/symbol coverage to create chronological development slices before any reserved outcomes are opened?

First answer this from recorder schema, timestamps and counts only. Do not inspect future return outcomes while designing the feature or boundary.

Preferred feature family: reuse the existing normalized top-book/depth fields from `l2_shadow_v8.py`; do not invent a new downloader or order-book reconstruction framework.

## P1 — Prospective design/sample sufficiency

Define a sample sufficiency rule **before** outcome inspection. Prefer time coverage + independent decision timestamps + symbol coverage over a tuned numeric performance threshold. The rule should distinguish development data from a later untouched evaluation block.

## P2 — Runtime/environment reproducibility

V9 venv remains stale for V11 imports. Reconcile only if a forward L2 mechanism survives data-level development diagnostics and integration/replay becomes necessary.

## P3 — Trial 871 / paper readiness

Trial 871 remains blocked behind candidate freeze, predeclaration, untouched eligibility, deterministic audit, council methodology check and exact local==remote SHA. SCIENCE and FREEZE remain failing readiness categories.
