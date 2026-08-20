# V9 Paper Readiness Design

## Goal
Upgrade V8 at source SHA `3eaf36efbcc8933bab173df521bb4a4c8897ab60` into an auditable V9 research branch that can truthfully declare either `READY_TO_START_PAPER` or `V9_NOT_READY_FOR_PAPER`, while making live trading impossible by construction.

## Boundary and provenance
V9 begins at the committed prospective boundary in `artifacts/multi_asset_v9/v9_start_manifest.json`. Data eligible before `2026-08-20T10:34:19Z` is development/calibration evidence only. Historical V8 registries and raw data are immutable inputs; V9 stores hashes/pointers and continues trial numbering append-only from 869. Trial 870 is consumed only by one predeclared, materially distinct performance hypothesis that passes both deterministic admission checks and the research council.

## Architecture
Reuse V8/V7 primitives rather than build a new framework. `ExecutionSimulatorV8` remains the observed-book execution model and `ShadowPaperEngine`/`SimulatedBroker` remain the only order-routing path. V9 adds a small governance layer for trial/readiness/freeze validation, a small restartable paper runtime around the existing shadow engine, and a Qwen-only council wrapper that validates JSON locally and fails closed. MiroFish remains an external pinned sidecar and contributes scenario/stress evidence only; if its external requirements are unavailable, V9 records that limitation without blocking deterministic research.

## Scientific gates
Reuse the existing V7 promotion gate, factor admission rules, reliability behavior, selection/evaluation discipline, cost stress, delay stress, wrong-side metrics, and multiple-testing status. No H8 neighborhood search is permitted. A candidate freeze is produced only after an admitted performance candidate exists. A1 starts only after freeze; prior engineering/shadow data never counts toward A1.

## Operational paper runtime
The runtime consumes a frozen candidate manifest when A1-eligible, or an explicitly engineering-only candidate for smoke tests. It rejects stale books before generating a decision, derives idempotent decision IDs through `ShadowPaperEngine`, persists append-only decisions/fills plus a compact state/health snapshot, and restores portfolio/equity state from journals on restart. It imports no private exchange client and exposes no live-order method.

## Council contract
All four roles use one active Qwen model selected from Groq's live model list, preferring `qwen/qwen3.6-27b` when available. Qwen uses JSON Object Mode; outputs are locally schema-validated. At most one same-model repair attempt is allowed for malformed structure; there is no GPT fallback. Stored council artifacts contain final structured outputs only, not hidden reasoning.

## MiroFish contract
Use official `666ghj/MiroFish`, pinned to an exact Git SHA outside InvestMent. No public bind/tunnel. Each actual scenario run is recorded in `mirofish_scenario_registry.jsonl` with source/candidate hashes and role classification. MiroFish may veto/flag or reduce paper risk only under a predeclared deterministic rule; it never increases historical performance, chooses trade direction, or rescues a failing candidate.

## Readiness decision
`paper_readiness.json` evaluates SOURCE_OF_TRUTH, CAUSALITY, SCIENCE, EXECUTION, OPERATIONAL, SAFETY, and FREEZE. Every mandatory category must pass for `READY_TO_START_PAPER`. If science/freeze is absent, the verdict is `V9_NOT_READY_FOR_PAPER` even when the paper engine itself is operational. `LIVE_NOT_AUTHORIZED` is unconditional.
