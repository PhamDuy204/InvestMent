# V7 Research Council and Escalation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the bounded V7 escalation layer that turns unresolved first-line error buckets into auditable factor-family hypotheses, uses a structured Groq research council and append-only blackboard, tests only independently supported factor families, permits one small nonlinear reliability challenger when justified, and integrates an isolated MiroFish/OASIS-style scenario sidecar only as event/risk evidence.

**Architecture:** This plan never replaces the V7 H12 trading core with an LLM trader. Agents communicate through typed evidence cards on an append-only research blackboard; deterministic validators decide whether a hypothesis may consume a trial. Factor families enter one at a time, then a small nonlinear reliability model may combine only factor families that already showed incremental information. Scenario swarm output is an optional sidecar feature family and cannot create direct LONG/SHORT instructions.

**Tech Stack:** Python 3, pandas, NumPy, existing scikit-learn stack already used by the project, Groq Python client/runtime model discovery, JSON/JSONL/CSV artifacts, standard-library HTTP for an optional local scenario sidecar, pytest, Ruff.

## Global Constraints

- Execute this plan only when `artifacts/multi_asset_v7/v7_protocol.json` or the core-cycle result says `escalation_required=true`.
- Continue the same V7 trial counter created by `V7TrialRegistry`; never reset or create a separate hidden counter.
- Total V7 performance-bearing configurations remain capped at 60; because first-line is capped at 24, escalation can consume at most 36 additional inspected performance configurations.
- Every factor-family performance inspection counts as a V7 trial, including ML challengers and scenario-derived strategy tests.
- LLM-only brainstorming that does not inspect strategy performance is logged in `hypothesis_registry.jsonl` but does not consume a performance trial until an approved backtest result is inspected.
- Agents may retrieve evidence, propose hypotheses, preserve dissent, audit methodology, and construct experiment manifests. They may not generate executable LONG/SHORT orders or bypass deterministic promotion code.
- Agent context must exclude keys/values whose semantic role is forward, future, oracle, V7 untouched forward result, secret, token, password, authorization, or API-key material.
- `GROQ_API_KEY` is loaded only from environment/secret storage. Its value is never printed, persisted, copied into prompts, or committed.
- No live exchange order/cancel/withdraw/transfer/leverage-change tool is implemented or exposed.
- Factor observation does not imply alpha promotion. Each family must pass source-quality, causal-availability, stability, target-error association, and incremental after-cost gates.
- A factor rejected for a mechanism recorded in `do_not_repeat.json` may re-enter only with materially new independent evidence or a genuinely different mechanism.
- Nonlinear models may use only factor families already individually admitted by deterministic evidence gates. The first challenger is small tree/histogram boosting; deep sequence models are outside this V7 plan unless a later spec explicitly authorizes them.
- MiroFish/OASIS is treated as a scenario/narrative simulator, not a proven native price/order-book forecasting engine.
- Scenario output may enter a performance trial only after a causal event-study artifact shows incremental information; it still cannot directly set trade direction.

---

## File Structure

Create:

- `src/crypto_research/research_blackboard_v7.py` — typed `EvidenceCard`, append-only JSONL storage, dissent preservation.
- `src/crypto_research/hypotheses_v7.py` — hypothesis schema, deterministic validator, experiment manifest, do-not-repeat integration.
- `src/crypto_research/groq_v7.py` — runtime Groq role discovery/orchestration and strict context sanitization.
- `src/crypto_research/factor_observatory_v7.py` — factor-family evidence registry and admission gates.
- `src/crypto_research/reliability_ml_v7.py` — small nonlinear reliability challenger with walk-forward fit/predict separation.
- `src/crypto_research/scenario_v7.py` — scenario request/result schema, disabled simulator, optional local MiroFish/OASIS sidecar adapter.
- `src/crypto_research/run_v7_research.py` — event-driven research council loop and bounded escalation orchestration.
- `skills/v7-research-scientist/SKILL.md`
- `skills/v7-methodology-auditor/SKILL.md`

Modify:

- `src/crypto_research/run_v7.py` — call escalation only before V7 freeze and only when the core cycle requests it.
- `src/crypto_research/v7_cycle.py` — full artifact status and escalation handoff.

Tests:

- `tests/test_research_blackboard_v7.py`
- `tests/test_hypotheses_v7.py`
- `tests/test_groq_v7.py`
- `tests/test_factor_observatory_v7.py`
- `tests/test_reliability_ml_v7.py`
- `tests/test_scenario_v7.py`
- `tests/test_run_v7_research.py`

---

### Task 1: Implement the append-only Research Blackboard

**Files:**
- Create: `src/crypto_research/research_blackboard_v7.py`
- Test: `tests/test_research_blackboard_v7.py`

**Interfaces:**
- Produces frozen dataclass `EvidenceCard` with fields:
  - `card_id: str`
  - `author_agent: str`
  - `claim: str`
  - `source_ids: tuple[str, ...]`
  - `timestamp_utc: str`
  - `data_cutoff_utc: str`
  - `causal: bool`
  - `target_error: str`
  - `expected_mechanism: str`
  - `confidence: float`
  - `supporting_evidence: tuple[str, ...]`
  - `contradictory_evidence: tuple[str, ...]`
  - `data_required: tuple[str, ...]`
  - `recommended_action: str`
- Produces: `append_evidence_card(card: EvidenceCard, path: str | Path) -> None`
- Produces: `load_evidence_cards(path: str | Path) -> list[EvidenceCard]`

- [ ] **Step 1: Write schema validation tests**

```python
def test_evidence_card_requires_bounded_confidence():
    with pytest.raises(ValueError, match="confidence"):
        EvidenceCard(..., confidence=1.5, ...)
```

Require a non-empty `claim`, `author_agent`, `target_error`, and ISO-like UTC timestamp fields.

- [ ] **Step 2: Write append-only/dissent test**

Append a support card and a contradictory card about the same hypothesis, reload the file, and assert both remain present in original order.

- [ ] **Step 3: Run tests and verify failure**

Run: `pytest tests/test_research_blackboard_v7.py -v`

- [ ] **Step 4: Implement JSONL serialization with deterministic card IDs**

If `card_id` is not externally supplied, derive it from canonical JSON of author, claim, sources, data cutoff, target error, and mechanism. Never rewrite an existing line; append only.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/test_research_blackboard_v7.py -v
git add src/crypto_research/research_blackboard_v7.py tests/test_research_blackboard_v7.py
git commit -m "feat: add V7 append-only research blackboard"
```

---

### Task 2: Implement hypothesis and experiment-manifest governance

**Files:**
- Create: `src/crypto_research/hypotheses_v7.py`
- Test: `tests/test_hypotheses_v7.py`

**Interfaces:**
- Produces frozen dataclass `ResearchHypothesis` with fields: `hypothesis_id`, `target_error`, `observation`, `causal_inputs`, `expected_mechanism`, `single_change`, `expected_effect`, `cost_risk`, `invalidation_condition`, `required_test`, `factor_family`, `source_ids`, `materially_new_evidence`.
- Produces frozen dataclass `ExperimentManifest` with fields: `hypothesis_id`, `trial_phase`, `causal_inputs`, `train_window`, `evaluation_window`, `metrics`, `cost_bps`, `delay_minutes`, `allowed_actions`.
- Produces: `validate_hypothesis(h: ResearchHypothesis, *, blocked_fingerprints: set[str]) -> ResearchHypothesis`
- Produces: `build_experiment_manifest(h: ResearchHypothesis, *, train_window: tuple[str, str], evaluation_window: tuple[str, str]) -> ExperimentManifest`

- [ ] **Step 1: Write direct-direction rejection tests**

Reject hypothesis text/action fields containing an LLM-created direct direction mechanism such as `go long`, `go short`, `buy BTC`, `sell ETH`, `direct directional alpha`, or `flip H12`.

- [ ] **Step 2: Write multi-change rejection test**

`single_change` must describe exactly one primary mechanism. Reject manifests whose requested actions include both a new alpha source and a leverage increase, or a factor addition plus execution-mode change.

- [ ] **Step 3: Write do-not-repeat integration test**

Compute the same mechanism fingerprint used by `diagnostics_v7.py` and reject it unless `materially_new_evidence=True`.

- [ ] **Step 4: Implement exact allowed actions**

Allowed research actions are a subset of:

```python
{"veto_entry", "veto_increase", "scale_increase", "reliability_score", "risk_context", "event_risk_context"}
```

No experiment manifest may contain an exchange/order action.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/test_hypotheses_v7.py -v
git add src/crypto_research/hypotheses_v7.py tests/test_hypotheses_v7.py
git commit -m "feat: govern V7 hypotheses and experiment manifests"
```

---

### Task 3: Write the local V7 research skills

**Files:**
- Create: `skills/v7-research-scientist/SKILL.md`
- Create: `skills/v7-methodology-auditor/SKILL.md`
- Test: `tests/test_hypotheses_v7.py`

**Interfaces:**
- Research Scientist output maps one evidence gap/failure to the `ResearchHypothesis` schema.
- Methodology Auditor output is a JSON-like object with `decision`, `risks`, `causal_findings`, `cost_findings`, `duplicate_mechanism`, and `required_controls`.

- [ ] **Step 1: Write static skill-content tests**

Read both files in the test and assert they explicitly contain:
- research/backtest only;
- no direct LONG/SHORT order generation;
- future/oracle/forward data prohibition;
- one mechanism per hypothesis;
- invalidation condition requirement;
- transaction-cost realism;
- do-not-repeat check.

- [ ] **Step 2: Create the Research Scientist skill**

Its process must be:

`read unresolved error -> read blackboard evidence -> read do-not-repeat -> formulate one mechanism -> specify causal inputs -> specify falsification -> emit schema only`.

It must prefer no hypothesis over a weak or duplicate hypothesis.

- [ ] **Step 3: Create the Methodology Auditor skill**

Its process must independently check causal timing, leakage, duplicate mechanism, parameter expansion, source quality, cost/execution realism, and whether the claimed factor could simply be reacting to price.

- [ ] **Step 4: Run tests and commit**

```bash
pytest tests/test_hypotheses_v7.py -v
git add skills/v7-research-scientist/SKILL.md skills/v7-methodology-auditor/SKILL.md tests/test_hypotheses_v7.py
git commit -m "docs: add V7 research scientist and auditor skills"
```

---

### Task 4: Implement the structured Groq research council

**Files:**
- Create: `src/crypto_research/groq_v7.py`
- Test: `tests/test_groq_v7.py`

**Interfaces:**
- Reuses: `groq_v6.list_model_ids` logic but does not mutate V6.
- Produces: `sanitize_v7_context(value: Any) -> Any`
- Produces: `select_v7_role_models(ids: set[str]) -> dict[str, str]`
- Produces: `run_v7_research_council(context: dict[str, Any], *, client: Any) -> dict[str, Any]`
- Logical roles: `evidence_scout`, `error_scientist`, `methodology_auditor`, `research_judge`.

- [ ] **Step 1: Write context-sanitization tests**

```python
def test_v7_context_strips_forward_oracle_and_secret_fields():
    clean = sanitize_v7_context({
        "api_key": "x",
        "forward_results": {"net": 9},
        "oracle_direction": 1,
        "future_return": 0.5,
        "error_ledger": {"WRONG_SIDE": 10},
    })
    assert "api_key" not in clean
    assert "forward_results" not in clean
    assert "oracle_direction" not in clean
    assert "future_return" not in clean
    assert clean["error_ledger"]["WRONG_SIDE"] == 10
```

- [ ] **Step 2: Write model-discovery tests**

At runtime select available models with deterministic preferences:
- evidence/error roles: Qwen when available, otherwise an available fallback;
- methodology auditor: `openai/gpt-oss-120b` then `openai/gpt-oss-20b`;
- judge: `openai/gpt-oss-20b` then auditor fallback.

Never hard-fail solely because one preferred model ID was deprecated if another discovered model is available.

- [ ] **Step 3: Write structured-role tests using a fake client**

The fake Evidence Scout returns evidence cards, Error Scientist returns hypotheses, Auditor rejects one duplicate/leaky hypothesis, Judge ranks only auditor-approved hypotheses. Assert the local deterministic validator still removes any direct-direction proposal even when the LLM auditor says `test`.

- [ ] **Step 4: Implement council orchestration**

Use temperature 0 where supported. Each role sees only the minimum preceding artifacts it requires. Preserve raw dissent/audit findings in the returned result instead of replacing them with judge output.

- [ ] **Step 5: Explicitly omit trading tools**

The Groq role prompt/tool allowlist may mention research functions such as `search_literature`, `query_error_ledger`, `query_factor_observatory`, and `build_experiment_manifest`; it must not define or expose order/cancel/withdraw/transfer tools.

- [ ] **Step 6: Run tests and commit**

```bash
pytest tests/test_groq_v7.py -v
git add src/crypto_research/groq_v7.py tests/test_groq_v7.py
git commit -m "feat: add structured Groq V7 research council"
```

---

### Task 5: Implement the Factor Observatory

**Files:**
- Create: `src/crypto_research/factor_observatory_v7.py`
- Test: `tests/test_factor_observatory_v7.py`

**Interfaces:**
- Produces frozen dataclass `FactorEvidence` with fields: `factor_family`, `feature_name`, `source_ids`, `coverage_fraction`, `causal_available`, `source_quality`, `stability_score`, `target_error`, `association_value`, `incremental_net_bps`, `incremental_sharpe_delta`, `turnover_delta`, `evaluation_fold_count`, `status`.
- Produces: `admit_factor(evidence: FactorEvidence) -> bool`
- Produces: `write_factor_observatory(rows: list[FactorEvidence], path: str | Path) -> Path`

- [ ] **Step 1: Write admission-gate tests**

Reject when `causal_available=False`, coverage is too sparse to evaluate, source quality is `unverified_blog_only`, evaluation evidence exists in only one fold, or incremental after-cost value is non-positive.

- [ ] **Step 2: Define factor families as data, not code branches**

Use a stable set of names including `microstructure`, `derivatives`, `cross_asset_macro`, `on_chain`, `news_event`, `attention_sentiment`, `cross_sectional`, `execution_risk`, `scenario_swarm`.

- [ ] **Step 3: Implement machine-readable observatory output**

Write `factor_observatory.json` with all observed rows, including rejected rows and exact rejection reasons. Observation is not promotion.

- [ ] **Step 4: Add reverse-causality flagging**

`attention_sentiment` entries must carry a `reverse_causality_checked` metadata field in the serialized artifact; admission fails if that check is false.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/test_factor_observatory_v7.py -v
git add src/crypto_research/factor_observatory_v7.py tests/test_factor_observatory_v7.py
git commit -m "feat: add V7 factor observatory admission gates"
```

---

### Task 6: Implement one-factor-at-a-time escalation orchestration

**Files:**
- Create: `src/crypto_research/run_v7_research.py`
- Test: `tests/test_run_v7_research.py`

**Interfaces:**
- Produces: `run_factor_family_challenge(context: dict[str, Any], hypothesis: ResearchHypothesis, *, registry: V7TrialRegistry, backtest_runner: Callable[..., dict[str, Any]], artifact_root: str | Path) -> dict[str, Any]`
- Produces: `run_research_event_loop(context: dict[str, Any], *, client: Any, backtest_runner: Callable[..., dict[str, Any]], artifact_root: str | Path) -> dict[str, Any]`

- [ ] **Step 1: Write event-trigger tests**

The loop runs only when one of these is present: unresolved error bucket, failed experiment, new materially distinct evidence, or explicit evidence gap. With an empty trigger set it returns `NO_RESEARCH_TRIGGER` and does not call Groq.

- [ ] **Step 2: Write budget test**

If the shared registry has already reached total trial 917 (`857 + 60`), the loop returns `V7_TRIAL_BUDGET_EXHAUSTED` before any performance backtest.

- [ ] **Step 3: Write one-family test**

An approved hypothesis for `derivatives` must result in exactly one new performance configuration before any second derivatives threshold/model is allowed. New variants require a newly registered mechanism or evidence card.

- [ ] **Step 4: Implement the loop**

Flow:

`load failure memory -> council -> deterministic hypothesis validation -> blackboard append -> build manifest -> one approved backtest -> factor evidence -> admit/reject -> failure ledger update`.

All Groq outputs are archived in `agent_research_log.jsonl`; all hypotheses including rejected ones are archived in `hypothesis_registry.jsonl`.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/test_run_v7_research.py tests/test_groq_v7.py tests/test_factor_observatory_v7.py -v
git add src/crypto_research/run_v7_research.py tests/test_run_v7_research.py
git commit -m "feat: add bounded V7 research event loop"
```

---

### Task 7: Implement the small nonlinear reliability challenger

**Files:**
- Create: `src/crypto_research/reliability_ml_v7.py`
- Test: `tests/test_reliability_ml_v7.py`

**Interfaces:**
- Produces frozen dataclass `ReliabilityModelConfig` with `feature_names: tuple[str, ...]`, `max_iter: int = 100`, `max_leaf_nodes: int = 15`, `learning_rate: float = 0.05`, `random_state: int = 42`.
- Produces: `fit_reliability_model(train: pd.DataFrame, config: ReliabilityModelConfig) -> object`
- Produces: `predict_reliability(model: object, frame: pd.DataFrame, config: ReliabilityModelConfig) -> np.ndarray`
- Preferred implementation: `sklearn.ensemble.HistGradientBoostingClassifier` using the project’s existing scikit-learn dependency.

- [ ] **Step 1: Write feature-admission test**

Reject a config whose feature list contains a factor family/feature not marked admitted in `factor_observatory.json`.

- [ ] **Step 2: Write train/evaluation isolation test**

Fit on training rows only. Mutating evaluation labels must not change model parameters or training predictions.

- [ ] **Step 3: Define the target**

Use a binary reliability target derived post-hoc on the training fold: `1` when the inherited H12 sign produced positive after-cost directional contribution for the evaluation horizon, otherwise `0`. Do not train on untouched V7 forward evidence.

- [ ] **Step 4: Implement fixed hyperparameters only**

Do not grid-search depth, leaves, learning rate, or number of iterations in V7. One ML challenger configuration consumes one trial when its strategy-level performance is inspected.

- [ ] **Step 5: Convert probability to a reliability modifier, not direction**

The strategy may use probability only to veto/scale exposure increases. For example, predeclare one rule `p_reliable < 0.50 -> veto increase`; do not optimize the threshold in V7 and do not flip the H12 sign.

- [ ] **Step 6: Run tests and commit**

```bash
pytest tests/test_reliability_ml_v7.py -v
git add src/crypto_research/reliability_ml_v7.py tests/test_reliability_ml_v7.py
git commit -m "feat: add bounded nonlinear V7 reliability challenger"
```

---

### Task 8: Integrate ML challenger with shared trial/error governance

**Files:**
- Modify: `src/crypto_research/run_v7_research.py`
- Test: `tests/test_run_v7_research.py`

**Interfaces:**
- Produces: `run_nonlinear_challenger(...) -> dict[str, Any]`

- [ ] **Step 1: Write eligibility tests**

Do not run ML if fewer than two factor features/families have passed independent observatory admission, or if first-line/simple candidate is already selected for freeze with no unresolved reliability gap.

- [ ] **Step 2: Write single-config trial test**

Exactly one ML performance configuration is registered with the fixed model config. No automatic hyperparameter loop is permitted.

- [ ] **Step 3: Apply the same promotion/stress/error gates as simple candidates**

The ML challenger must improve the target error/economic profile after costs and survive 20 bps/+1h checks; model AUC/accuracy alone is not sufficient.

- [ ] **Step 4: Persist model metadata, not secret/runtime internals**

Write feature names, fixed hyperparameters, train/evaluation windows, and model hash/serialization path. Do not serialize LLM prompts into the model file.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/test_run_v7_research.py tests/test_reliability_ml_v7.py -v
git add src/crypto_research/run_v7_research.py tests/test_run_v7_research.py
git commit -m "feat: integrate nonlinear V7 challenger governance"
```

---

### Task 9: Implement the MiroFish/OASIS scenario sidecar boundary

**Files:**
- Create: `src/crypto_research/scenario_v7.py`
- Test: `tests/test_scenario_v7.py`

**Interfaces:**
- Produces frozen dataclass `ScenarioRequest` with `event_id`, `event_timestamp_utc`, `event_text`, `causal_context`, `participant_roles`.
- Produces frozen dataclass `ScenarioResult` with `event_id`, `consensus_strength`, `scenario_disagreement`, `tail_risk_bucket`, `liquidity_stress_bucket`, `narrative_polarity`, `confidence`, `source="MIROFISH_OASIS_SIDECAR"`.
- Produces protocol-like interface `ScenarioSimulator.run(request: ScenarioRequest) -> ScenarioResult`.
- Produces `DisabledScenarioSimulator` and `MiroFishSidecarClient(endpoint: str, *, timeout_seconds: float = 30.0)`.

- [ ] **Step 1: Write schema/range tests**

`consensus_strength`, `scenario_disagreement`, `confidence` must be in `[0,1]`; narrative polarity must be in `[-1,1]`; tail/liquidity buckets use a finite enum such as `low`, `medium`, `high`, `extreme`.

- [ ] **Step 2: Write no-direction-output test**

Assert `ScenarioResult` has no `side`, `position`, `buy`, `sell`, `long`, or `short` field.

- [ ] **Step 3: Implement disabled-by-default simulator**

Without `V7_SCENARIO_SIDECAR_URL`, the system returns status `SCENARIO_SIMULATOR_NOT_CONFIGURED` and does not consume a performance trial.

- [ ] **Step 4: Implement isolated local HTTP adapter with standard library**

Use `urllib.request` to POST canonical JSON to a configured local/research endpoint. Parse only the strict `ScenarioResult` schema. The adapter has no exchange credential access and no ability to place orders.

- [ ] **Step 5: Add deterministic response validation**

Reject extra fields that attempt direct direction/action output.

- [ ] **Step 6: Run tests and commit**

```bash
pytest tests/test_scenario_v7.py -v
git add src/crypto_research/scenario_v7.py tests/test_scenario_v7.py
git commit -m "feat: add isolated V7 scenario swarm sidecar boundary"
```

---

### Task 10: Add causal event-study gate before scenario output can affect research candidates

**Files:**
- Modify: `src/crypto_research/scenario_v7.py`
- Modify: `src/crypto_research/factor_observatory_v7.py`
- Test: `tests/test_scenario_v7.py`
- Test: `tests/test_factor_observatory_v7.py`

**Interfaces:**
- Produces: `build_scenario_event_study(events: pd.DataFrame, scenario_results: pd.DataFrame, outcomes: pd.DataFrame) -> dict[str, object]`

- [ ] **Step 1: Write timing test**

Scenario inputs for an event may use only event text/context known at the event timestamp and pre-event causal context. Later price response can appear only in the outcomes side of the post-hoc event study.

- [ ] **Step 2: Write minimum-evidence test**

Do not admit `scenario_swarm` from one anecdotal event. Require multiple historical events and evaluation across more than one temporal fold before it can be marked `ADMITTED_FOR_CHALLENGE`.

- [ ] **Step 3: Implement association/incremental evidence artifact**

Report whether disagreement/tail-risk/liquidity-stress outputs add information about the target error/economic outcome beyond the inherited H12 score and simple event metadata. This artifact is evidence only; it does not automatically alter target weights.

- [ ] **Step 4: Feed the result into normal Factor Observatory admission**

Only an admitted `scenario_swarm` feature can later enter the single nonlinear challenger or a separately registered simple risk-context experiment.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/test_scenario_v7.py tests/test_factor_observatory_v7.py -v
git add src/crypto_research/scenario_v7.py src/crypto_research/factor_observatory_v7.py tests/test_scenario_v7.py tests/test_factor_observatory_v7.py
git commit -m "feat: gate scenario swarm evidence with causal event studies"
```

---

### Task 11: Wire escalation into V7 only before freeze

**Files:**
- Modify: `src/crypto_research/run_v7.py`
- Modify: `src/crypto_research/v7_cycle.py`
- Modify: `src/crypto_research/run_v7_research.py`
- Test: `tests/test_run_v7_research.py`
- Test: `tests/test_forward_v7.py`

**Interfaces:**
- Produces: `maybe_run_v7_escalation(core_result: dict[str, Any], *, freeze_exists: bool, ...) -> dict[str, Any]`

- [ ] **Step 1: Write freeze-block test**

If `forward_freeze.json` already exists and verifies, `maybe_run_v7_escalation` must return `V7_FROZEN_NO_RETUNING` and must not call Groq, run a factor backtest, or register a new trial.

- [ ] **Step 2: Write simple-first skip test**

If core result says a simple candidate is selected for freeze and `escalation_required=false`, do not invoke escalation.

- [ ] **Step 3: Implement bounded escalation ordering**

Order is fixed:
1. Factor-family challenge(s), one family/mechanism at a time.
2. Optional fixed nonlinear reliability challenger if admitted factor evidence justifies it.
3. Optional scenario event-study/factor challenge if event data and a configured sidecar exist.

No later tier runs merely because earlier tiers exist; each needs an unresolved evidence gap.

- [ ] **Step 4: Update artifact status**

Populate `literature_registry.json`, `hypothesis_registry.jsonl`, `agent_research_log.jsonl`, `research_blackboard.jsonl`, and `factor_observatory.json` with real research state instead of `NOT_RUN_CORE_ONLY` placeholders.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/test_run_v7_research.py tests/test_forward_v7.py -v
git add src/crypto_research/run_v7.py src/crypto_research/v7_cycle.py src/crypto_research/run_v7_research.py tests/test_run_v7_research.py
git commit -m "feat: wire bounded V7 escalation before freeze"
```

---

### Task 12: Full council/escalation verification and research handoff

**Files:**
- No production file unless root-cause fixes are required.
- Tests: all V7 council/escalation tests plus full project suite.

**Interfaces:**
- Produces a verified escalation checkpoint that can feed candidate selection but cannot bypass the existing V7 freeze/A1 gate.

- [ ] **Step 1: Run targeted council/escalation suite**

```bash
pytest tests/test_research_blackboard_v7.py tests/test_hypotheses_v7.py tests/test_groq_v7.py tests/test_factor_observatory_v7.py tests/test_reliability_ml_v7.py tests/test_scenario_v7.py tests/test_run_v7_research.py -v
```

Expected: PASS.

- [ ] **Step 2: Run full project regression**

```bash
pytest -q
ruff check src tests
python -m compileall -q src tests
```

Expected: all succeed.

- [ ] **Step 3: Run explicit agent-safety tests**

Verify:
- forward/future/oracle keys are absent from role contexts;
- direct LLM BUY/SELL/LONG/SHORT hypotheses are rejected locally;
- dissent cards survive synthesis;
- repeated failed mechanisms are rejected;
- no performance backtest runs after a valid V7 freeze;
- no order/cancel/withdraw/transfer function exists in V7 tool registries.

- [ ] **Step 4: Verify trial budget across core + escalation**

Load one shared `experiment_registry.csv` and assert first trial 858, no duplicate trial numbers, total inspected V7 configurations <= 60, and no separate hidden ML/scenario trial registry exists.

- [ ] **Step 5: Verify secret hygiene**

Search V7 branch changes for credential values. `GROQ_API_KEY` identifier and dummy test keys are allowed only where tests explicitly assert sanitization; real `gsk_...` values, bearer tokens, private keys, exchange secrets, and OTP data must not appear.

- [ ] **Step 6: Verify scenario isolation**

With no sidecar URL, the V7 core/council still runs and reports scenario research unavailable instead of failing. With a fake local sidecar in tests, only strict scenario evidence fields are accepted.

- [ ] **Step 7: Produce escalation conclusion**

If an escalation candidate clears deterministic discovery/evaluation gates, hand its exact config to the existing `freeze_v7_candidate` path. If none clears, finish V7 with `NEEDS_MORE_RESEARCH`; do not extend the search beyond the 60-trial cap.

---

## Escalation Completion Gate

This plan is complete when the research council is structured and auditable, all agent communication is persisted through typed evidence/hypothesis artifacts, factor families are admitted one at a time, at most one fixed nonlinear reliability challenger is available after factor admission, scenario simulation is isolated and evidence-gated, the shared V7 trial budget is enforced, and no agent can alter a frozen V7 candidate or produce direct executable trading direction.

After completion, candidate selection flows back into the core plan’s immutable freeze and A1 readiness gate. No council/ML/scenario result can directly produce `READY_FOR_PAPER_TRADING`; only `readiness_gate.json` after untouched A1 evidence can do that.