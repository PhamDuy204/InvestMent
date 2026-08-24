# Open Problems — Ordered by Leverage

## P0 — Identify one materially new causal factor family

The current H12 feature family is saturated and its rescue paths are exhausted enough to stop local filtering. Do **not** add another transform/threshold/interaction over volatility, volume/activity, taker imbalance, funding, market/asset returns, sessions, breadth, dispersion, lag-return, lag-RV, or prior flat-trend logic unless genuinely independent evidence changes the mechanism.

Smallest next question:
> Is there one new pre-decision causal information source, not already embedded in H12/H1-H8/V10, with a clear economic mechanism and data provenance that can be evaluated on development data without touching post-boundary outcomes?

Prefer already-recorded but scientifically independent data before collecting/building anything new. Candidate families may include public L2 microstructure or positioning only if timestamp provenance and pre-boundary/development availability make the test legal; post-boundary reserved outcomes must remain untouched.

Before any performance trial require: materially distinct mechanism, deterministic single-change specification, causal availability, development support in >=2 chronological slices, positive aggregate development economics after realistic costs, and no outcome-driven threshold selection.

## P1 — Establish enough untouched post-boundary evidence

Boundary remains `2026-08-23T17:16:03.853710+00:00`. Recorder continuity remains healthy, but no claim of sufficient matured H12 evaluation sample/provenance has been made. Until independently proven: `NEED_MORE_UNTOUCHED_EVIDENCE`; do not consume 871.

## P2 — Development dataset for a new factor

If a materially new factor is found, first prove that historical/pre-boundary data exists for development. Do not use reserved post-boundary outcomes to invent or tune the mechanism.

## P3 — Runtime/environment reproducibility

The V9 venv is source-stale for importing V11. Reconcile only when an actual V11 code/replay run is required. Standalone data diagnostics may reuse its installed pandas/numpy without importing project modules.

## P4 — Multiple-testing provenance

DSR/PBO/CSCV/CPCV remain `NOT_COMPUTABLE_WITH_CURRENT_PROVENANCE`. Build aligned candidate-return provenance only when genuine candidate paths exist.

## P5 — Paper readiness

Still blocked by SCIENCE and FREEZE. Reuse existing execution/paper infrastructure; do not rewrite it.
