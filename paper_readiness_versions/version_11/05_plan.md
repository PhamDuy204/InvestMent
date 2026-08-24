# Minimal Plan Toward Paper Readiness

## Stage 1 — Diagnose information form, no new trial

- Reuse current V11 replay/attribution output.
- Test whether H12 contains stable cross-sectional rank information despite negative absolute direction.
- Use only observed/development evidence.
- Keep parameters fixed to natural choices already present in repo (rank/quantiles) unless a parameter is economically required.

Exit:
- `NO_EDGE`: retire H12 directional family for now; seek materially new causal source.
- `RELATIVE_EDGE_ONLY`: formulate one small causal relative mechanism and development-test it.
- `LOW_DIMENSIONAL_REGIME_EDGE`: formulate one single interaction and development-test it.

## Stage 2 — Development screen

For exactly one selected mechanism:
- chronological folds;
- purge/embargo only if label windows overlap;
- log every actual configuration;
- compare 0/10/20bps;
- relevant delay stress;
- require >=2 temporal development folds improve net and aggregate development net > baseline.

If it fails: record and stop. No local parameter rescue.

## Stage 3 — Untouched evidence audit

- inventory post-boundary data;
- prove no design-time outcome access;
- predeclare exact evaluation period/folds/cost/delay/promotion gates;
- deterministic methodology audit;
- Qwen council only at the actual trial gate.

If evidence is insufficient: stop with `NEED_MORE_UNTOUCHED_EVIDENCE`.

## Stage 4 — Trial 871, at most once

Only after all authorization gates pass:
- commit/push predeclaration;
- local SHA == remote SHA;
- atomically create access marker;
- evaluate once;
- no tuning afterward.

## Stage 5 — Freeze then paper

Only if 871 and robustness pass:
- immutable candidate freeze/hash;
- readiness categories all PASS;
- start existing `SimulatedBroker` + `ExecutionSimulatorV8` paper path;
- keep `PAPER_VALIDATED=false` until prospective paper evidence accumulates;
- `LIVE_NOT_AUTHORIZED` forever in this research line.
