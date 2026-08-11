# V7 Core Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the simple-first V7 research core that tests H1 quarter-hour conflict veto, H2 high-dispersion exposure gate, and H3 weak-edge veto, records every inspected configuration from trial 858 onward, attributes failures by error class, freezes one immutable candidate, and evaluates the strict A1 readiness gate without adding any live trading path.

**Architecture:** Reuse the V6 replay, account simulation, H12 direction, hysteresis, MARKET execution, 1x exposure, and cost/account primitives. Add focused V7 modules for causal reliability features, fold-fitted gate parameters, failure memory, bounded trial accounting, freeze/readiness, and the artifact contract. V7 modules may reduce/veto new exposure but must never create an opposite direction to the retained H12 core.

**Tech Stack:** Python 3, pandas, NumPy, existing scikit-learn/Ridge research stack, pytest, Ruff, existing V3/V6 portfolio/account simulators, JSON/CSV/GZip artifacts.

## Global Constraints

- Base branch/work starts from `v7-factor-observatory`, whose parent V6 head is `46212f4c9eef07001341a87dffea40cd223cfa84`.
- V6 frozen candidate hash remains `be84d12f86df294fc7eaf30affe5cf6d89df99cb1092e7856f2dbfd016b3ec92` and is never rewritten.
- Starting trial count is exactly 857; first inspected V7 performance configuration is trial 858.
- First-line V7 performance configurations are capped at 24.
- Total V7 performance-bearing configurations, including escalation handled by the companion plan, are capped at 60.
- H1/H2/H3 may veto or reduce new exposure only; they may not flip H12 direction, increase leverage, force a new opposite position, or replace MARKET/1x as the inherited baseline.
- Thresholds are fit only on the corresponding training/inner fold and applied unchanged to its evaluation fold.
- 2021-2023 and Aug 1-10, 2026 evidence remain locked and cannot be used for V7 parameter selection.
- `READY_FOR_PAPER_TRADING` requires at least 30 untouched calendar days AND at least 40 eligible H12 observations after the V7 freeze.
- A1 additionally requires net return > 0 at 10 bps, PF > 1.10, Sharpe > 0.50, net return >= 0 at 20 bps, net return >= 0 with +1h delay, zero liquidation, zero exposure/margin violations, unchanged candidate hash, and zero forward-driven retuning.
- No live exchange order, cancellation, transfer, withdrawal, OTP, or exchange-side leverage mutation capability may be added.
- `GROQ_API_KEY` is not needed for this core plan and its value must never appear in code, logs, artifacts, diffs, or tests.

---

## File Structure

Create these focused modules:

- `src/crypto_research/features_v7.py` — causal H1 quarter-hour imbalance and H2 cross-sectional dispersion primitives.
- `src/crypto_research/reliability_v7.py` — fold-fitted H1/H2/H3 gate state and target-weight transformation.
- `src/crypto_research/trials_v7.py` — monotonic V7 trial registry with first-line/total budget enforcement.
- `src/crypto_research/diagnostics_v7.py` — failure ledger records, economic/error attribution, and do-not-repeat fingerprints.
- `src/crypto_research/forward_v7.py` — V7 freeze payload/hash verification and strict A1 readiness evaluation.
- `src/crypto_research/v7_cycle.py` — required artifact contract and fixed H1/H2/H3 experiment sequence.
- `src/crypto_research/run_v7.py` — orchestration that reuses V6 replay/account primitives and emits V7 artifacts.

Modify only where reuse is necessary:

- `src/crypto_research/decision_diagnostics.py` — add V7 causal/label column constants without changing V6 semantics.
- `src/crypto_research/run_v6.py` — avoid behavior changes; only expose/reuse helpers if a clean import is impossible.

Tests:

- `tests/test_features_v7.py`
- `tests/test_reliability_v7.py`
- `tests/test_trials_v7.py`
- `tests/test_diagnostics_v7.py`
- `tests/test_forward_v7.py`
- `tests/test_v7_cycle.py`
- `tests/test_run_v7.py`
- extend `tests/test_decision_log_v6.py` only if needed to prove V6 remains unchanged.

---

### Task 1: Lock V7 trial accounting and artifact contract

**Files:**
- Create: `src/crypto_research/trials_v7.py`
- Create: `src/crypto_research/v7_cycle.py`
- Test: `tests/test_trials_v7.py`
- Test: `tests/test_v7_cycle.py`

**Interfaces:**
- Produces: `V7TrialRegistry(path: str | Path, prior_count: int = 857, first_line_cap: int = 24, total_cap: int = 60)`
- Produces: `record(stage: str, hypothesis: str, status: str, *, config: dict[str, object] | None = None, metrics: dict[str, object] | None = None, phase: str = "first_line") -> dict[str, object]`
- Produces: `REQUIRED_V7_ARTIFACTS: set[str]`
- Produces: `ensure_v7_artifact_contract(root: str | Path) -> list[str]`

- [ ] **Step 1: Write failing tests for trial 858, persistence, and budgets**

```python
from crypto_research.trials_v7 import V7TrialRegistry


def test_v7_registry_starts_at_858_and_persists(tmp_path):
    path = tmp_path / "experiment_registry.csv"
    registry = V7TrialRegistry(path)
    row = registry.record("A", "exact_v6_control", "CONTROL", phase="first_line")
    assert row["trial_number"] == 858
    registry.to_csv()
    loaded = V7TrialRegistry(path)
    assert loaded.total_count == 858


def test_v7_first_line_budget_rejects_25th_configuration(tmp_path):
    registry = V7TrialRegistry(tmp_path / "registry.csv", first_line_cap=24)
    for i in range(24):
        registry.record("H", f"h-{i}", "INSPECTED", phase="first_line")
    with pytest.raises(RuntimeError, match="first-line"):
        registry.record("H", "overflow", "INSPECTED", phase="first_line")
```

- [ ] **Step 2: Run the new registry tests and confirm failure**

Run: `pytest tests/test_trials_v7.py -v`

Expected: FAIL because `crypto_research.trials_v7` does not exist.

- [ ] **Step 3: Implement the minimal registry by adapting V6 registry semantics**

Use the V6 CSV columns and add `phase` plus immutable V7 trial IDs:

```python
trial_number = self.prior_count + len(self.rows) + 1
trial_id = f"v7-{trial_number:04d}-{config_hash[:10]}"
```

Count rows with `phase == "first_line"` before accepting a first-line record; reject any row once `len(self.rows) >= total_cap`.

- [ ] **Step 4: Write the artifact-contract test**

```python
from crypto_research.v7_cycle import REQUIRED_V7_ARTIFACTS


def test_v7_required_artifacts_cover_core_contract():
    required = {
        "v7_protocol.json",
        "experiment_registry.csv",
        "failure_ledger.csv.gz",
        "do_not_repeat.json",
        "qh_imbalance_results.json",
        "dispersion_results.json",
        "weak_edge_results.json",
        "combination_results.json",
        "error_attribution.json",
        "stress_results.json",
        "dsr_results.json",
        "pbo_results.json",
        "final_candidate.json",
        "forward_freeze.json",
        "forward_observations.csv.gz",
        "readiness_gate.json",
        "final_report.md",
    }
    assert required.issubset(REQUIRED_V7_ARTIFACTS)
```

- [ ] **Step 5: Implement `REQUIRED_V7_ARTIFACTS` and `ensure_v7_artifact_contract`**

Include the full design contract, including `literature_registry.json`, `hypothesis_registry.jsonl`, `agent_research_log.jsonl`, `research_blackboard.jsonl`, and `factor_observatory.json`; these research-council files may initially contain a machine-readable `NOT_RUN_CORE_ONLY` state until the companion escalation plan runs.

- [ ] **Step 6: Run tests and commit**

Run: `pytest tests/test_trials_v7.py tests/test_v7_cycle.py -v`

Expected: PASS.

```bash
git add src/crypto_research/trials_v7.py src/crypto_research/v7_cycle.py tests/test_trials_v7.py tests/test_v7_cycle.py
git commit -m "feat: lock V7 trial budgets and artifact contract"
```

---

### Task 2: Implement causal quarter-hour imbalance H1

**Files:**
- Create: `src/crypto_research/features_v7.py`
- Test: `tests/test_features_v7.py`

**Interfaces:**
- Produces: `signed_aggressor_volume(quantity: float, is_buyer_maker: bool) -> float`
- Produces: `previous_completed_quarter_open(decision_timestamp: pd.Timestamp) -> pd.Timestamp`
- Produces: `build_qh_opening_imbalance(trades: pd.DataFrame, decisions: pd.DataFrame, *, opening_seconds: int = 10) -> pd.DataFrame`
- Output columns: `decision_timestamp`, `symbol`, `qh_window_start`, `qh_window_end`, `qh_order_imbalance`, `qh_abs_order_imbalance`, `qh_trade_count`.

- [ ] **Step 1: Write sign-mapping and strict-timing tests**

```python
from crypto_research.features_v7 import signed_aggressor_volume, previous_completed_quarter_open


def test_is_buyer_maker_true_is_sell_aggressor():
    assert signed_aggressor_volume(3.0, True) == -3.0
    assert signed_aggressor_volume(3.0, False) == 3.0


def test_decision_on_quarter_boundary_uses_previous_quarter():
    decision = pd.Timestamp("2026-01-01T04:00:00Z")
    assert previous_completed_quarter_open(decision) == pd.Timestamp("2026-01-01T03:45:00Z")
```

- [ ] **Step 2: Add the leakage regression**

Construct trades at `03:45:00`, `03:45:09`, `04:00:00`, and `04:00:09`; a `04:00:00` decision must use only the first two rows.

```python
def test_qh_feature_never_uses_current_or_future_quarter():
    out = build_qh_opening_imbalance(trades, decisions, opening_seconds=10)
    row = out.iloc[0]
    assert row["qh_window_start"] == pd.Timestamp("2026-01-01T03:45:00Z")
    assert row["qh_window_end"] == pd.Timestamp("2026-01-01T03:45:09Z")
    assert row["qh_trade_count"] == 2
```

- [ ] **Step 3: Run tests and verify failure**

Run: `pytest tests/test_features_v7.py -v`

Expected: FAIL because the module/functions are absent.

- [ ] **Step 4: Implement the minimal causal feature**

The imbalance for a symbol/window is:

```python
signed = sum(signed_aggressor_volume(qty, flag) for qty, flag in rows)
total = sum(abs(qty) for qty in rows)
imbalance = signed / total if total > 0 else 0.0
```

Use UTC timestamps, explicit `[window_start, window_start + 10 seconds)` selection, and never use `merge_asof(... direction="forward")`.

- [ ] **Step 5: Mutate future trades and prove prior feature stability**

Add a test that changes all trades at or after `decision_timestamp` by 1,000x and asserts the pre-decision output is byte-for-byte equal for the same decision.

- [ ] **Step 6: Run tests and commit**

Run: `pytest tests/test_features_v7.py -v`

Expected: PASS.

```bash
git add src/crypto_research/features_v7.py tests/test_features_v7.py
git commit -m "feat: add causal quarter-hour imbalance feature"
```

---

### Task 3: Implement H2 causal dispersion state

**Files:**
- Modify: `src/crypto_research/features_v7.py`
- Test: `tests/test_features_v7.py`

**Interfaces:**
- Produces: `build_cross_sectional_dispersion(panel: pd.DataFrame, *, return_col: str = "ret_12", eligible_col: str = "in_universe") -> pd.DataFrame`
- Output columns: `decision_timestamp`, `dispersion_iqr`, `eligible_symbol_count`.

- [ ] **Step 1: Write the IQR/universe test**

```python
def test_dispersion_uses_only_current_causal_universe():
    out = build_cross_sectional_dispersion(panel)
    row = out.loc[out["decision_timestamp"] == pd.Timestamp("2026-01-01T00:00Z")].iloc[0]
    expected = np.quantile([0.01, 0.02, 0.05], 0.75) - np.quantile([0.01, 0.02, 0.05], 0.25)
    assert row["dispersion_iqr"] == pytest.approx(expected)
    assert row["eligible_symbol_count"] == 3
```

Include one large-return row with `in_universe=False` and assert it does not affect the result.

- [ ] **Step 2: Run the test and confirm failure**

Run: `pytest tests/test_features_v7.py::test_dispersion_uses_only_current_causal_universe -v`

- [ ] **Step 3: Implement group-by-decision IQR**

Use only rows where `eligible_col` is true and finite `return_col` is available at the decision timestamp. Return `NaN` when fewer than two eligible finite values exist; the gate will treat missing dispersion as inactive rather than high risk.

- [ ] **Step 4: Add future-mutation stability test**

Change returns only at later decision timestamps and prove earlier dispersion rows are unchanged.

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/test_features_v7.py -v`

```bash
git add src/crypto_research/features_v7.py tests/test_features_v7.py
git commit -m "feat: add causal cross-sectional dispersion feature"
```

---

### Task 4: Implement fold-fitted H1/H2/H3 reliability gates

**Files:**
- Create: `src/crypto_research/reliability_v7.py`
- Test: `tests/test_reliability_v7.py`

**Interfaces:**
- Produces immutable dataclass `ReliabilityGateConfig` with fields:
  - `qh_abs_threshold: float | None`
  - `dispersion_threshold: float | None`
  - `weak_score_threshold: float | None`
  - `weak_score_veto_enabled: bool`
  - `high_dispersion_scale: float = 0.5`
- Produces: `fit_reliability_gates(train: pd.DataFrame, *, score_col: str = "effective_score") -> ReliabilityGateConfig`
- Produces: `apply_reliability_gates(row: Any, previous_weight: float, base_target_weight: float, config: ReliabilityGateConfig) -> dict[str, object]`

- [ ] **Step 1: Write train-only threshold tests**

```python
def test_fit_reliability_gates_uses_fixed_percentiles():
    cfg = fit_reliability_gates(train)
    assert cfg.qh_abs_threshold == pytest.approx(train["qh_abs_order_imbalance"].median())
    assert cfg.dispersion_threshold == pytest.approx(train["dispersion_iqr"].quantile(0.80))
    assert cfg.weak_score_threshold == pytest.approx(train["effective_score"].abs().quantile(0.20))
```

The weak-score veto is enabled only when the training weak bucket has mean `realized_net_contribution <= 0`.

- [ ] **Step 2: Write action semantics tests**

```python
def test_h1_conflict_veto_blocks_new_entry_but_not_existing_exit():
    out = apply_reliability_gates(conflict_row, 0.0, 0.25, cfg)
    assert out["target_weight"] == 0.0
    assert out["h1_veto"] is True


def test_h2_high_dispersion_scales_only_exposure_increase():
    out = apply_reliability_gates(high_dispersion_row, 0.10, 0.25, cfg)
    assert out["target_weight"] == pytest.approx(0.125)
    reduced = apply_reliability_gates(high_dispersion_row, 0.25, 0.10, cfg)
    assert reduced["target_weight"] == pytest.approx(0.10)


def test_gates_never_flip_h12_direction():
    for base in (-0.25, 0.25):
        out = apply_reliability_gates(row, 0.0, base, cfg)
        assert np.sign(out["target_weight"]) in {0.0, np.sign(base)}
```

- [ ] **Step 3: Run tests and verify failure**

Run: `pytest tests/test_reliability_v7.py -v`

- [ ] **Step 4: Implement H1 exactly**

H1 is active only when both values are finite and:

```python
conflict = np.sign(qh_order_imbalance) != np.sign(effective_score)
strong = abs(qh_order_imbalance) > config.qh_abs_threshold
```

When active, veto only a new position or an absolute exposure increase. Preserve reductions/exits.

- [ ] **Step 5: Implement H2 exactly**

If `dispersion_iqr > config.dispersion_threshold`, multiply only the incremental increase in absolute exposure by 0.5. For example, previous `+0.10`, base target `+0.25` becomes `+0.175`, not `+0.125`:

```python
increment = max(abs(base_target) - abs(previous), 0.0)
new_abs = abs(previous) + 0.5 * increment
```

Use the base sign. Reductions/exits pass through unchanged.

- [ ] **Step 6: Implement H3 exactly**

If the training weak bucket was non-positive and `abs(score) <= weak_score_threshold`, veto only new exposure/increases; reductions/exits pass through.

- [ ] **Step 7: Add fold-isolation regression**

Fit config on a train frame, mutate all evaluation features/labels, and assert the fitted config does not change.

- [ ] **Step 8: Run tests and commit**

Run: `pytest tests/test_reliability_v7.py -v`

```bash
git add src/crypto_research/reliability_v7.py tests/test_reliability_v7.py
git commit -m "feat: add fold-fitted V7 reliability gates"
```

---

### Task 5: Add V7 failure ledger and do-not-repeat fingerprints

**Files:**
- Create: `src/crypto_research/diagnostics_v7.py`
- Test: `tests/test_diagnostics_v7.py`

**Interfaces:**
- Produces: `mechanism_fingerprint(target_error: str, expected_mechanism: str, causal_inputs: list[str], action: str) -> str`
- Produces: `build_failure_record(...) -> dict[str, object]`
- Produces: `append_failure_ledger(records: list[dict[str, object]], path: str | Path) -> Path`
- Produces: `load_do_not_repeat(path: str | Path) -> set[str]`
- Produces: `reject_repeated_mechanism(fingerprint: str, blocked: set[str], *, materially_new_evidence: bool = False) -> None`

- [ ] **Step 1: Write deterministic-fingerprint tests**

```python
def test_mechanism_fingerprint_ignores_threshold_wording_noise():
    a = mechanism_fingerprint("WRONG_SIDE", "QH conflict veto", ["qh_order_imbalance", "h12_score"], "veto_increase")
    b = mechanism_fingerprint("WRONG_SIDE", " qh conflict veto ", ["h12_score", "qh_order_imbalance"], "veto_increase")
    assert a == b
```

- [ ] **Step 2: Write duplicate-rejection test**

```python
def test_repeated_failed_mechanism_requires_new_evidence():
    with pytest.raises(ValueError, match="do-not-repeat"):
        reject_repeated_mechanism("abc", {"abc"})
    reject_repeated_mechanism("abc", {"abc"}, materially_new_evidence=True)
```

- [ ] **Step 3: Write failure-record completeness test**

Require exactly these research fields in addition to IDs/timestamps: `target_error`, `expected_mechanism`, `actual_error_delta`, `net_effect_bps`, `turnover_effect`, `drawdown_effect`, `damaged_regime`, `helped_regime`, `assumption_status`, `failure_reason`, `do_not_repeat_fingerprint`, `next_allowed_question`.

- [ ] **Step 4: Implement JSON-normalized SHA-256 fingerprint and append-only GZip CSV**

Normalize mechanism text with lowercase/trim/collapsed whitespace and sort causal inputs before hashing.

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/test_diagnostics_v7.py -v`

```bash
git add src/crypto_research/diagnostics_v7.py tests/test_diagnostics_v7.py
git commit -m "feat: add V7 failure memory and fingerprints"
```

---

### Task 6: Add V7 causal/label schema without changing V6 diagnostics

**Files:**
- Modify: `src/crypto_research/decision_diagnostics.py`
- Test: `tests/test_diagnostics_v7.py`
- Regression: `tests/test_decision_log_v6.py`

**Interfaces:**
- Produces: `V7_CAUSAL_COLUMNS`
- Produces: `V7_LABEL_COLUMNS`

- [ ] **Step 1: Write the schema separation test**

```python
def test_v7_oracle_and_realized_fields_are_label_only():
    assert not set(V7_CAUSAL_COLUMNS) & set(V7_LABEL_COLUMNS)
    for name in ("realized_return", "oracle_direction", "WRONG_SIDE"):
        assert name in V7_LABEL_COLUMNS
        assert name not in V7_CAUSAL_COLUMNS
```

Include `qh_order_imbalance`, `qh_abs_order_imbalance`, `dispersion_iqr`, and the frozen fold thresholds in causal metadata; never include `holding_return_label`, future PnL, oracle labels, or readiness-forward results.

- [ ] **Step 2: Run the new schema test and confirm failure**

- [ ] **Step 3: Add constants only; do not rewrite V6 constants/functions**

- [ ] **Step 4: Run V6 and V7 diagnostics tests**

Run: `pytest tests/test_decision_log_v6.py tests/test_diagnostics_v7.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/crypto_research/decision_diagnostics.py tests/test_diagnostics_v7.py
git commit -m "feat: define V7 causal diagnostic schema"
```

---

### Task 7: Build fixed first-line V7 replay sequence

**Files:**
- Create: `src/crypto_research/run_v7.py`
- Modify: `src/crypto_research/v7_cycle.py`
- Test: `tests/test_run_v7.py`

**Interfaces:**
- Produces: `split_selection_evaluation(decision_log: pd.DataFrame, *, selection_fraction: float = 0.70) -> tuple[pd.DataFrame, pd.DataFrame]`
- Produces: `run_v7_first_line(decision_log: pd.DataFrame, qh_features: pd.DataFrame, dispersion: pd.DataFrame, *, artifact_root: str | Path, prior_trials: int = 857, round_trip_cost_bps: float = 10.0) -> dict[str, object]`
- Reuses: `run_v6.replay_weight_overlay` and `run_v3.stateful_summary`.

- [ ] **Step 1: Write a toy-data sequence test**

Assert the registry rows appear in fixed order: exact V6 control, H1, H2, H3, and only one combination if at least two individual hypotheses pass.

```python
def test_first_line_sequence_is_fixed_and_starts_at_858(tmp_path):
    result = run_v7_first_line(...)
    registry = pd.read_csv(tmp_path / "experiment_registry.csv")
    assert registry.iloc[0]["trial_number"] == 858
    assert registry.iloc[0]["hypothesis"] == "exact_v6_control"
    assert registry["hypothesis"].tolist()[:4] == ["exact_v6_control", "H1_qh_conflict_veto", "H2_high_dispersion_gate", "H3_weak_edge_veto"]
```

- [ ] **Step 2: Write a no-combination test**

If fewer than two hypotheses pass the deterministic promotion gate, write `combination_results.json` with status `NOT_RUN_FEWER_THAN_TWO_PROMOTED` and do not spend a combination performance trial.

- [ ] **Step 3: Run tests and confirm failure**

Run: `pytest tests/test_run_v7.py -v`

- [ ] **Step 4: Implement exact control replay**

Merge causal H1/H2 features into the discovery decision log with `validate="one_to_one"` on `[decision_timestamp, symbol]` where applicable. Recompute control through `replay_weight_overlay(..., scale_fn=lambda row: 1.0)` so the control is numerically comparable to V7 candidates.

- [ ] **Step 5: Implement per-fold gate fitting and candidate replay**

Fit `ReliabilityGateConfig` on selection only. For H1/H2/H3-alone runs, disable the other gates by setting their thresholds to `None`/flags false. For the single combination, enable only individually promoted modules using the same already-fit thresholds; do not refit the combination.

- [ ] **Step 6: Implement deterministic promotion checks**

Require 10 bps net improvement versus control plus no material Sharpe/DD damage, target-error improvement, non-collapse at 20 bps and +1h delay, and no single-fold-only effect. Record the exact reasons in each result artifact.

- [ ] **Step 7: Write H1/H2/H3 artifacts and registry**

Write:
- `qh_imbalance_results.json`
- `dispersion_results.json`
- `weak_edge_results.json`
- `combination_results.json`
- `experiment_registry.csv`

- [ ] **Step 8: Run tests and commit**

Run: `pytest tests/test_run_v7.py tests/test_reliability_v7.py tests/test_trials_v7.py -v`

```bash
git add src/crypto_research/run_v7.py src/crypto_research/v7_cycle.py tests/test_run_v7.py
git commit -m "feat: add fixed V7 first-line experiment cycle"
```

---

### Task 8: Add error attribution and failure-led artifact generation

**Files:**
- Modify: `src/crypto_research/run_v7.py`
- Modify: `src/crypto_research/diagnostics_v7.py`
- Test: `tests/test_run_v7.py`
- Test: `tests/test_diagnostics_v7.py`

**Interfaces:**
- Produces: `attribute_candidate_errors(base_log: pd.DataFrame, candidate_decisions: pd.DataFrame, *, round_trip_cost_bps: float) -> dict[str, object]`

- [ ] **Step 1: Write the economic-attribution test**

The result must report, per target error class, baseline count, candidate count, count delta, avoided-loss bps, lost-correct-trade bps, and net bps effect.

- [ ] **Step 2: Implement attribution using existing `classify_error` semantics**

Do not invent a new oracle definition. Use the V5/V6 decision diagnostics to classify post-hoc realized outcomes and compare the base versus candidate target weights.

- [ ] **Step 3: Emit failure ledger records for every rejected inspected candidate**

A failed H1/H2/H3 record must state the hypothesis assumption as `falsified` or `not_supported`; promoted candidates receive `supported_inner_not_forward_confirmed` rather than a success claim.

- [ ] **Step 4: Write `error_attribution.json`, `failure_ledger.csv.gz`, and `do_not_repeat.json`**

`do_not_repeat.json` contains sorted unique fingerprints plus human-readable mechanism summaries.

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/test_diagnostics_v7.py tests/test_run_v7.py -v`

```bash
git add src/crypto_research/run_v7.py src/crypto_research/diagnostics_v7.py tests/test_run_v7.py tests/test_diagnostics_v7.py
git commit -m "feat: attribute V7 errors and persist failure memory"
```

---

### Task 9: Reuse V6 stress/account machinery for final contenders

**Files:**
- Modify: `src/crypto_research/run_v7.py`
- Test: `tests/test_run_v7.py`

**Interfaces:**
- Produces: `run_v7_stress_suite(periods: pd.DataFrame, market: pd.DataFrame) -> dict[str, object]`
- Reuses: `run_leverage_v3.run_grid`, `run_leverage_v3.shock_grid`, existing bootstrap/PBO/DSR helpers already used by V6.

- [ ] **Step 1: Write stress contract tests**

Require named outputs for base 10 bps, 20 bps, +1h delay, funding x3, slippage 5 bps/way, maintenance margin 2% and 5%, and correlation-one adverse shock.

- [ ] **Step 2: Implement wrappers only; do not clone account logic**

The final V7 candidate remains 1x unless the spec is changed in a future cycle. Higher leverage is stress evidence only and cannot become a V7 alpha promotion path.

- [ ] **Step 3: Recompute CSCV/PBO and approximate DSR with the V7 aligned candidate matrix**

Keep the status explicit if the historical all-trial Sharpe distribution remains incomplete. Do not call CSCV/PBO CPCV.

- [ ] **Step 4: Write `stress_results.json`, `dsr_results.json`, and `pbo_results.json`**

- [ ] **Step 5: Run tests and commit**

```bash
git add src/crypto_research/run_v7.py tests/test_run_v7.py
git commit -m "feat: add V7 contender stress and multiple-testing reports"
```

---

### Task 10: Implement immutable V7 freeze and strict A1 readiness gate

**Files:**
- Create: `src/crypto_research/forward_v7.py`
- Test: `tests/test_forward_v7.py`

**Interfaces:**
- Produces: `freeze_v7_candidate(config: dict[str, object], *, artifact_root: str | Path, timestamp: str, total_trial_count: int, source_sha: str, causal_schema_version: str) -> dict[str, object]`
- Produces: `verify_v7_freeze(path: str | Path) -> bool`
- Produces: `evaluate_a1_readiness(forward: pd.DataFrame, freeze: dict[str, object], *, candidate_hash: str, ret_10bps: float, profit_factor: float, sharpe: float, ret_20bps: float, delay_1h_return: float, liquidation_count: int, exposure_violation_count: int, margin_violation_count: int, forward_driven_retuning: bool) -> dict[str, object]`

- [ ] **Step 1: Write freeze mutation tests**

Hash the canonical object containing `candidate_config`, `source_sha`, `causal_schema_version`, and `total_trial_count_at_freeze`. Mutating any one must make verification fail.

- [ ] **Step 2: Write A1 volume-gate tests**

```python
def test_a1_cannot_be_ready_before_30_days_and_40_observations():
    result = evaluate_a1_readiness(forward_29_days_50_rows, freeze, ...all_metrics_passing...)
    assert result["verdict"] == "NEEDS_MORE_RESEARCH"
    assert "minimum_calendar_days" in result["failed_gates"]

    result = evaluate_a1_readiness(forward_31_days_39_rows, freeze, ...all_metrics_passing...)
    assert result["verdict"] == "NEEDS_MORE_RESEARCH"
    assert "minimum_h12_observations" in result["failed_gates"]
```

- [ ] **Step 3: Write hard-metric tests**

A negative 20 bps return or negative +1h delay return must make READY impossible even when all other metrics pass.

- [ ] **Step 4: Write hash/retuning tests**

A candidate hash mismatch or `forward_driven_retuning=True` must force `NEEDS_MORE_RESEARCH`.

- [ ] **Step 5: Implement freeze/readiness functions**

Use exact verdict strings only: `NEEDS_MORE_RESEARCH` or `READY_FOR_PAPER_TRADING`. Do not introduce intermediate READY-like labels.

- [ ] **Step 6: Run tests and commit**

Run: `pytest tests/test_forward_v7.py -v`

```bash
git add src/crypto_research/forward_v7.py tests/test_forward_v7.py
git commit -m "feat: add immutable V7 freeze and A1 readiness gate"
```

---

### Task 11: Assemble core V7 artifacts and report

**Files:**
- Modify: `src/crypto_research/run_v7.py`
- Modify: `src/crypto_research/v7_cycle.py`
- Test: `tests/test_v7_cycle.py`
- Test: `tests/test_run_v7.py`

**Interfaces:**
- Produces: `run_v7_core_cycle(...) -> dict[str, object]`

- [ ] **Step 1: Write an end-to-end toy artifact-contract test**

Run the core cycle into `tmp_path`, create a frozen candidate, append a synthetic forward-observation file, and assert `ensure_v7_artifact_contract(tmp_path)` is empty once all core artifacts plus explicit `NOT_RUN_CORE_ONLY` council placeholders are written.

- [ ] **Step 2: Implement `v7_protocol.json`**

Record exact H1/H2/H3 formulas, split rule, trial budgets, locked evidence, cost assumptions, 1x/MARKET inheritance, and A1 requirements.

- [ ] **Step 3: Implement `final_candidate.json` and `final_report.md` generation**

The report must distinguish discovery/evaluation evidence from untouched forward evidence and must never output `READY_FOR_PAPER_TRADING` unless `readiness_gate.json` says READY.

- [ ] **Step 4: Add explicit escalation handoff state**

If first-line modules do not produce sufficient directional/error improvement, write `escalation_required=true` and the target unresolved error buckets so the companion research-council plan can start without modifying the already-recorded first-line trials.

- [ ] **Step 5: Run end-to-end core tests and commit**

Run: `pytest tests/test_v7_cycle.py tests/test_run_v7.py tests/test_forward_v7.py -v`

```bash
git add src/crypto_research/run_v7.py src/crypto_research/v7_cycle.py tests/test_v7_cycle.py tests/test_run_v7.py
git commit -m "feat: assemble V7 core research artifacts"
```

---

### Task 12: Full regression, leakage, security, and branch checkpoint

**Files:**
- No new production file unless a failing regression exposes a root-cause bug.
- Tests: full `tests/` suite.

**Interfaces:**
- Produces a verified core checkpoint suitable for deciding whether to execute the companion escalation plan.

- [ ] **Step 1: Run targeted V7 suite**

Run:

```bash
pytest tests/test_features_v7.py tests/test_reliability_v7.py tests/test_trials_v7.py tests/test_diagnostics_v7.py tests/test_forward_v7.py tests/test_v7_cycle.py tests/test_run_v7.py -v
```

Expected: PASS.

- [ ] **Step 2: Run full regression**

Run: `pytest -q`

Expected: PASS, including all V3-V6 tests.

- [ ] **Step 3: Run lint and compile checks**

```bash
ruff check src tests
python -m compileall -q src tests
```

Expected: both commands succeed.

- [ ] **Step 4: Run explicit leakage checks**

Execute the future-mutation tests from H1/H2 and fold-isolation tests from H3, plus V6 causal-state regressions:

```bash
pytest tests/test_features_v7.py tests/test_reliability_v7.py tests/test_state_v6.py tests/test_decision_log_v6.py -v
```

- [ ] **Step 5: Run repository secret/path scan**

Search tracked V7 changes for `gsk_`, `BEGIN PRIVATE KEY`, exchange order endpoints, `withdraw`, `transfer`, and any literal secret value. Code identifiers such as `GROQ_API_KEY` are allowed; credential values are not.

- [ ] **Step 6: Verify trial sequence and budgets from artifacts**

Assert no duplicate trial numbers, first trial 858, monotonic order, first-line count <= 24, and total count <= 60.

- [ ] **Step 7: Verify V6 freeze/report are byte-identical to the V6 base**

Compare the V7 branch copies of `artifacts/multi_asset_v6/forward_freeze.json`, `final_candidate.json`, and `final_report.md` against commit `46212f4c9eef07001341a87dffea40cd223cfa84`; there must be no V7 edits to those files.

- [ ] **Step 8: Commit any verification-only documentation update**

If no production fix was needed, commit the verified core status into the V7 report/protocol artifacts when real research data are run; do not fabricate performance in unit tests.

---

## Core Completion Gate

This plan is complete when all core tests pass, the first-line experiment machinery can run from trial 858 with H1/H2/H3 and at most one combination, failure memory is persisted, V6 evidence remains immutable, and a V7 candidate can be frozen and evaluated by A1 without any forward-driven mutation.

If first-line results do not sufficiently improve the dominant `WRONG_SIDE`/economic failure profile, proceed to `docs/superpowers/plans/2026-08-11-v7-research-council-escalation-implementation.md`. If first-line evidence is already strong enough for a V7 freeze, do not execute escalation merely to increase complexity; freeze the simpler candidate and begin untouched A1 evidence collection.