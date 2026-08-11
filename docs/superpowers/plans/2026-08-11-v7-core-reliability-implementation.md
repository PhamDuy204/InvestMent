# V7 Core Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` and implement this plan task-by-task with TDD.

**Goal:** Implement the simple-first V7 core that tests H1 quarter-hour conflict veto, H2 high-dispersion exposure gate, and H3 weak-edge veto; records every inspected performance configuration from trial 858 onward; attributes failed mechanisms; freezes one immutable candidate; and evaluates the strict A1 readiness gate without any live-trading path.

**Architecture:** Reuse the V6 H12 direction, causal universe, replay/account simulation, hysteresis, MARKET execution, 1x exposure, costs, funding, liquidation, PBO/DSR, and stress helpers. Add only focused V7 modules for causal H1/H2 features, fold-fitted H1/H2/H3 gates, bounded trial accounting, failure memory, immutable freeze/readiness, and artifact orchestration. V7 reliability modules may veto or reduce new exposure but may never create an opposite direction to H12.

**Tech stack:** Python 3, pandas, NumPy, existing scikit-learn research dependency, pytest, Ruff, existing V3/V6 portfolio/account code, JSON/JSONL/CSV/GZip artifacts.

## Locked constraints

- Branch: `v7-factor-observatory`; parent V6 head: `46212f4c9eef07001341a87dffea40cd223cfa84`.
- V6 candidate hash remains `be84d12f86df294fc7eaf30affe5cf6d89df99cb1092e7856f2dbfd016b3ec92`; V7 must not modify V6 freeze/candidate/report artifacts.
- Starting research count is 857; first inspected V7 performance configuration is trial 858.
- First-line cap: 24 inspected performance configurations. Total V7 cap including escalation: 60.
- H1/H2/H3 may only veto/reduce new exposure. They may not flip H12 direction, increase leverage, force an opposite position, or replace MARKET/1x.
- H1/H2/H3 thresholds are fitted only on their corresponding inner/training fold and applied unchanged to the evaluation fold.
- 2021–2023 and Aug 1–10, 2026 are locked observed evidence and cannot be used for V7 parameter selection.
- `READY_FOR_PAPER_TRADING` requires both at least 30 untouched calendar days and at least 40 eligible H12 forward observations after V7 freeze, plus all A1 metric gates.
- A1 metrics: net return > 0 at 10 bps; PF > 1.10; Sharpe > 0.50; net return >= 0 at 20 bps; net return >= 0 under +1h delay; zero liquidation; zero exposure violations; zero margin violations; unchanged candidate hash; zero forward-driven retuning.
- No exchange order/cancel/withdraw/transfer/OTP/exchange-leverage-mutation capability may be added.
- `GROQ_API_KEY` is not required by this core plan and no real secret value may appear in code, tests, logs, artifacts, prompts, or diffs.

## Files

Create:
- `src/crypto_research/features_v7.py`
- `src/crypto_research/reliability_v7.py`
- `src/crypto_research/trials_v7.py`
- `src/crypto_research/diagnostics_v7.py`
- `src/crypto_research/forward_v7.py`
- `src/crypto_research/v7_cycle.py`
- `src/crypto_research/run_v7.py`
- `tests/test_features_v7.py`
- `tests/test_reliability_v7.py`
- `tests/test_trials_v7.py`
- `tests/test_diagnostics_v7.py`
- `tests/test_forward_v7.py`
- `tests/test_v7_cycle.py`
- `tests/test_run_v7.py`

Modify only as needed for compatibility:
- `src/crypto_research/decision_diagnostics.py`: add V7 causal/label constants only; preserve V6 behavior.
- `src/crypto_research/run_v6.py`: do not change behavior; reuse public helpers directly. Expose a helper only if an import boundary blocks reuse and cover that exposure with V6 regressions.
- Existing `tests/test_decision_log_v6.py` and `tests/test_state_v6.py` are regression gates and normally remain unchanged.

---

## Task 1 — Trial accounting and artifact contract

**Files:** `trials_v7.py`, `v7_cycle.py`, `test_trials_v7.py`, `test_v7_cycle.py`.

**Interfaces:**

```python
class V7TrialRegistry:
    def __init__(
        self,
        path: str | Path,
        *,
        prior_count: int = 857,
        first_line_cap: int = 24,
        total_cap: int = 60,
    ): ...

    @property
    def total_count(self) -> int: ...

    def record(
        self,
        stage: str,
        hypothesis: str,
        status: str,
        *,
        config: dict[str, object] | None = None,
        metrics: dict[str, object] | None = None,
        phase: str = "first_line",
    ) -> dict[str, object]: ...

    def to_csv(self) -> Path: ...
```

The ellipsis tokens above are Python function bodies in an interface sketch, not implementation placeholders; implementation must contain real bodies.

Also implement:

```python
REQUIRED_V7_ARTIFACTS: set[str]
def ensure_v7_artifact_contract(root: str | Path) -> list[str]: ...
```

### TDD steps

- [ ] Write `test_v7_registry_starts_at_858_and_persists`: first row must be trial 858 and reload must keep total 858.
- [ ] Write `test_v7_first_line_budget_rejects_25th_configuration`: after 24 `phase="first_line"` rows, the next first-line record raises `RuntimeError` containing `first-line`.
- [ ] Write `test_v7_total_budget_rejects_61st_configuration`: after 60 V7 performance rows, any next record raises `RuntimeError` containing `total`.
- [ ] Run `pytest tests/test_trials_v7.py -v` and confirm RED because module is absent.
- [ ] Implement by adapting V6 registry semantics. `trial_id = f"v7-{trial_number:04d}-{config_hash[:10]}"`; keep config hash and metrics JSON deterministic.
- [ ] Define the full required artifact set: `v7_protocol.json`, `literature_registry.json`, `hypothesis_registry.jsonl`, `experiment_registry.csv`, `agent_research_log.jsonl`, `research_blackboard.jsonl`, `factor_observatory.json`, `failure_ledger.csv.gz`, `do_not_repeat.json`, `qh_imbalance_results.json`, `dispersion_results.json`, `weak_edge_results.json`, `combination_results.json`, `error_attribution.json`, `stress_results.json`, `dsr_results.json`, `pbo_results.json`, `final_candidate.json`, `forward_freeze.json`, `forward_observations.csv.gz`, `readiness_gate.json`, `final_report.md`.
- [ ] Core-only runs write explicit `NOT_RUN_CORE_ONLY` states for council artifacts; they are not silently omitted.
- [ ] Run `pytest tests/test_trials_v7.py tests/test_v7_cycle.py -v` and confirm GREEN.
- [ ] Commit: `feat: lock V7 trial budgets and artifact contract`.

---

## Task 2 — Causal H1 quarter-hour imbalance

**Files:** `features_v7.py`, `test_features_v7.py`.

**Interfaces:**

```python
def signed_aggressor_volume(quantity: float, is_buyer_maker: bool) -> float: ...
def previous_completed_quarter_open(decision_timestamp: pd.Timestamp) -> pd.Timestamp: ...
def build_qh_opening_imbalance(
    trades: pd.DataFrame,
    decisions: pd.DataFrame,
    *,
    opening_seconds: int = 10,
) -> pd.DataFrame: ...
```

Output columns: `decision_timestamp`, `symbol`, `qh_window_start`, `qh_window_end`, `qh_order_imbalance`, `qh_abs_order_imbalance`, `qh_trade_count`.

### TDD steps

- [ ] Test aggressor mapping: `isBuyerMaker=True -> negative signed volume`; `False -> positive signed volume`.
- [ ] Test boundary: decision `2026-01-01T04:00:00Z` maps to opening start `03:45:00Z`.
- [ ] Build a fixture with trades at `03:45:00`, `03:45:09`, `04:00:00`, `04:00:09`; a `04:00` decision must consume only the first two.
- [ ] Test window semantics as half-open `[03:45:00, 03:45:10)`, while exposing display `qh_window_end=03:45:09` for one-second data.
- [ ] Mutate all trades at or after decision time by 1000x and assert the pre-decision H1 row is identical.
- [ ] Run `pytest tests/test_features_v7.py -v` and confirm RED.
- [ ] Implement UTC normalization and direct grouped window selection; never use forward `merge_asof`.
- [ ] Compute `OI = signed_sum / absolute_quantity_sum`, or `0.0` when denominator is zero.
- [ ] Re-run test file and confirm GREEN.
- [ ] Commit: `feat: add causal quarter-hour imbalance feature`.

---

## Task 3 — Causal H2 cross-sectional dispersion

**Files:** `features_v7.py`, `test_features_v7.py`.

**Interface:**

```python
def build_cross_sectional_dispersion(
    panel: pd.DataFrame,
    *,
    timestamp_col: str = "decision_timestamp",
    return_col: str = "ret_12",
    eligible_col: str = "in_universe",
) -> pd.DataFrame: ...
```

Output: `decision_timestamp`, `dispersion_iqr`, `eligible_symbol_count`.

### TDD steps

- [ ] Create one decision timestamp with eligible returns `[0.01, 0.02, 0.05]` and an ineligible outlier `0.90`; expected IQR uses only eligible values.
- [ ] Require `eligible_symbol_count == 3`.
- [ ] When fewer than two finite eligible values exist, output `NaN` dispersion; the gate later treats missing state as inactive.
- [ ] Mutate only later-timestamp returns and prove earlier dispersion is unchanged.
- [ ] Run the targeted test and confirm RED.
- [ ] Implement group-by-timestamp IQR with causal universe filter.
- [ ] Run `pytest tests/test_features_v7.py -v` and confirm GREEN.
- [ ] Commit: `feat: add causal cross-sectional dispersion feature`.

---

## Task 4 — Fold-fitted H1/H2/H3 reliability gates

**Files:** `reliability_v7.py`, `test_reliability_v7.py`.

**Interfaces:**

```python
@dataclass(frozen=True)
class ReliabilityGateConfig:
    qh_abs_threshold: float | None
    dispersion_threshold: float | None
    weak_score_threshold: float | None
    weak_score_veto_enabled: bool
    high_dispersion_scale: float = 0.5


def fit_reliability_gates(
    train: pd.DataFrame,
    *,
    score_col: str = "effective_score",
    net_contribution_col: str = "realized_net_contribution",
) -> ReliabilityGateConfig: ...


def apply_reliability_gates(
    row: object,
    previous_weight: float,
    base_target_weight: float,
    config: ReliabilityGateConfig,
    *,
    enable_h1: bool = True,
    enable_h2: bool = True,
    enable_h3: bool = True,
) -> dict[str, object]: ...
```

### TDD steps

- [ ] Fit thresholds on training only: H1 median of `abs(qh_order_imbalance)`; H2 80th percentile `dispersion_iqr`; H3 20th percentile `abs(effective_score)`.
- [ ] H3 is enabled only if training weak-score bucket mean `realized_net_contribution <= 0`.
- [ ] H1 strong conflict on new entry produces target 0 and `h1_veto=True`; H1 may not prevent a requested reduction/exit.
- [ ] H2 must scale only the incremental exposure increase. Example: previous `+0.10`, base `+0.25`, scale `0.5` -> `+0.175`, not `+0.125`.
- [ ] H2 reduction example: previous `+0.25`, base `+0.10` -> unchanged `+0.10`.
- [ ] H3 weak score vetoes only new/increased exposure.
- [ ] For base targets `-0.25` and `+0.25`, every gate output sign is either zero or the base sign.
- [ ] Mutating evaluation features/labels after fitting must not change `ReliabilityGateConfig`.
- [ ] Run `pytest tests/test_reliability_v7.py -v` and confirm RED.
- [ ] Implement H1 strong conflict as sign disagreement plus `abs(qh_order_imbalance) > qh_abs_threshold`; inactive on missing values or zero H12 score.
- [ ] Implement H2 incremental scaling: `new_abs = abs(previous) + 0.5 * max(abs(base)-abs(previous), 0)` when high dispersion and same intended direction/increase.
- [ ] Implement H3 as specified; preserve HOLD/REDUCE/EXIT.
- [ ] Confirm GREEN and commit: `feat: add fold-fitted V7 reliability gates`.

---

## Task 5 — Failure ledger and do-not-repeat fingerprints

**Files:** `diagnostics_v7.py`, `test_diagnostics_v7.py`.

**Interfaces:**

```python
def mechanism_fingerprint(
    target_error: str,
    expected_mechanism: str,
    causal_inputs: list[str],
    action: str,
) -> str: ...


def build_failure_record(
    *,
    trial_number: int,
    hypothesis_id: str,
    target_error: str,
    expected_mechanism: str,
    actual_error_delta: float,
    net_effect_bps: float,
    turnover_effect: float,
    drawdown_effect: float,
    damaged_regime: str,
    helped_regime: str,
    assumption_status: str,
    failure_reason: str,
    do_not_repeat_fingerprint: str,
    next_allowed_question: str,
    timestamp_utc: str,
) -> dict[str, object]: ...


def append_failure_ledger(records: list[dict[str, object]], path: str | Path) -> Path: ...
def load_do_not_repeat(path: str | Path) -> set[str]: ...
def reject_repeated_mechanism(
    fingerprint: str,
    blocked: set[str],
    *,
    materially_new_evidence: bool = False,
) -> None: ...
```

### TDD steps

- [ ] Fingerprint is invariant to whitespace/case in mechanism and ordering of causal inputs.
- [ ] Same blocked fingerprint raises unless `materially_new_evidence=True`.
- [ ] Failure records require all specified fields and reject missing/nonfinite core numeric values.
- [ ] Normalize mechanism text, sort inputs, hash canonical JSON with SHA-256.
- [ ] Append GZip CSV without overwriting earlier rows.
- [ ] `do_not_repeat.json` will later store sorted fingerprints plus human-readable summaries; loader accepts that artifact.
- [ ] Run tests RED -> implement -> GREEN.
- [ ] Commit: `feat: add V7 failure memory and fingerprints`.

---

## Task 6 — V7 causal/label diagnostic schema

**Files:** modify `decision_diagnostics.py`; tests `test_diagnostics_v7.py`; regress `test_decision_log_v6.py`.

### TDD steps

- [ ] Add test asserting `V7_CAUSAL_COLUMNS` and `V7_LABEL_COLUMNS` are disjoint.
- [ ] Causal set includes `qh_order_imbalance`, `qh_abs_order_imbalance`, `dispersion_iqr`, and fold-fitted threshold metadata.
- [ ] Label set includes `realized_return`, `oracle_direction`, `oracle_exit`, and error classes such as `WRONG_SIDE`.
- [ ] Explicitly assert no `holding_return_label`, future PnL, oracle field, or readiness-forward result appears in causal set.
- [ ] Add constants only; do not rewrite V6 constants or enrichment behavior.
- [ ] Run `pytest tests/test_decision_log_v6.py tests/test_diagnostics_v7.py -v` and confirm GREEN.
- [ ] Commit: `feat: define V7 causal diagnostic schema`.

---

## Task 7 — Fixed first-line replay sequence

**Files:** `run_v7.py`, `v7_cycle.py`, `test_run_v7.py`.

**Interfaces:**

```python
def split_selection_evaluation(
    decision_log: pd.DataFrame,
    *,
    selection_fraction: float = 0.70,
) -> tuple[pd.DataFrame, pd.DataFrame]: ...


def run_v7_first_line(
    decision_log: pd.DataFrame,
    qh_features: pd.DataFrame,
    dispersion: pd.DataFrame,
    *,
    artifact_root: str | Path,
    prior_trials: int = 857,
    round_trip_cost_bps: float = 10.0,
    selection_fraction: float = 0.70,
) -> dict[str, object]: ...
```

### TDD fixture

Build `tests/test_run_v7.py::_toy_first_line_inputs()` with 12 UTC timestamps at 12h cadence and two symbols per timestamp. Each decision row contains `decision_timestamp`, `symbol`, `target_weight`, `holding_return_label`, `funding_sum_label`, `effective_score`, and `realized_net_contribution`; QH fixture has one row per decision/symbol; dispersion fixture has one row per timestamp. No test uses hidden forward data.

### TDD steps

- [ ] Run with `decision_log, qh, dispersion = _toy_first_line_inputs()` and `artifact_root=tmp_path`.
- [ ] Registry first row is trial 858 `exact_v6_control`; first four hypotheses are exactly `exact_v6_control`, `H1_qh_conflict_veto`, `H2_high_dispersion_gate`, `H3_weak_edge_veto`.
- [ ] If fewer than two individuals pass, write `combination_results.json` status `NOT_RUN_FEWER_THAN_TWO_PROMOTED` and do not spend a combination performance trial.
- [ ] Exact control is recomputed with `replay_weight_overlay(decision_log, scale_fn=lambda row: 1.0, round_trip_cost_bps=10.0)` after causal feature merges so comparison population is identical.
- [ ] Fit gate config only on selection. H1/H2/H3-alone runs disable the two non-tested gates. Combination reuses already fitted thresholds; it does not refit.
- [ ] Deterministic promotion requires positive 10-bps net improvement versus control, target-error/economic failure improvement, no material Sharpe/DD damage, non-collapse at 20 bps, non-collapse at +1h delay, and benefit across more than one temporal evaluation fold.
- [ ] Write H1/H2/H3/combination JSON artifacts and shared registry.
- [ ] Run `pytest tests/test_run_v7.py tests/test_reliability_v7.py tests/test_trials_v7.py -v` RED -> implement -> GREEN.
- [ ] Commit: `feat: add fixed V7 first-line experiment cycle`.

---

## Task 8 — Economic/error attribution

**Files:** `run_v7.py`, `diagnostics_v7.py`, tests.

**Interface:**

```python
def attribute_candidate_errors(
    base_log: pd.DataFrame,
    candidate_decisions: pd.DataFrame,
    *,
    round_trip_cost_bps: float,
) -> dict[str, object]: ...
```

### TDD steps

- [ ] Per error class report baseline count, candidate count, count delta, avoided-loss bps, lost-correct-trade bps, net bps effect.
- [ ] Reuse existing `classify_error`/oracle semantics; do not define a new post-hoc oracle.
- [ ] Every rejected inspected candidate produces a ledger row with `falsified` or `not_supported`; inner-promoted candidates use `supported_inner_not_forward_confirmed`.
- [ ] Write `error_attribution.json`, `failure_ledger.csv.gz`, `do_not_repeat.json`.
- [ ] Run `pytest tests/test_diagnostics_v7.py tests/test_run_v7.py -v` and confirm GREEN.
- [ ] Commit: `feat: attribute V7 errors and persist failure memory`.

---

## Task 9 — Stress, PBO, and DSR for final contenders

**Files:** `run_v7.py`, `test_run_v7.py`.

**Interface:**

```python
def run_v7_stress_suite(
    periods: pd.DataFrame,
    market: pd.DataFrame,
    *,
    base_round_trip_cost_bps: float = 10.0,
) -> dict[str, object]: ...
```

### TDD steps

- [ ] Require named stress outputs for 10 bps base, 20 bps, +1h delay, funding x3, slippage 5 bps/way, maintenance margin 2%, maintenance margin 5%, and adverse correlation-one shock.
- [ ] Wrap/reuse `run_leverage_v3.run_grid`, `shock_grid`, and existing V6 helpers; do not clone account/liquidation logic.
- [ ] Recommended V7 exposure remains 1x; higher leverage is stress evidence only.
- [ ] Recompute CSCV/PBO on aligned V7 candidate return matrix. Do not call it CPCV.
- [ ] Recompute approximate DSR and retain an explicit incomplete-history status if all historical trial Sharpes remain unavailable.
- [ ] Write `stress_results.json`, `dsr_results.json`, `pbo_results.json`.
- [ ] Test and commit: `feat: add V7 contender stress and multiple-testing reports`.

---

## Task 10 — Immutable V7 freeze and A1 readiness

**Files:** `forward_v7.py`, `test_forward_v7.py`.

**Interfaces:**

```python
def freeze_v7_candidate(
    config: dict[str, object],
    *,
    artifact_root: str | Path,
    timestamp: str,
    total_trial_count: int,
    source_sha: str,
    causal_schema_version: str,
) -> dict[str, object]: ...


def verify_v7_freeze(path: str | Path) -> bool: ...


def evaluate_a1_readiness(
    forward: pd.DataFrame,
    freeze: dict[str, object],
    *,
    candidate_hash: str,
    ret_10bps: float,
    profit_factor: float,
    sharpe: float,
    ret_20bps: float,
    delay_1h_return: float,
    liquidation_count: int,
    exposure_violation_count: int,
    margin_violation_count: int,
    forward_driven_retuning: bool,
) -> dict[str, object]: ...
```

### Exact test fixtures

```python
passing_metrics = {
    "ret_10bps": 0.01,
    "profit_factor": 1.20,
    "sharpe": 0.75,
    "ret_20bps": 0.002,
    "delay_1h_return": 0.001,
    "liquidation_count": 0,
    "exposure_violation_count": 0,
    "margin_violation_count": 0,
    "forward_driven_retuning": False,
}
```

A valid freeze fixture uses candidate `{"name": "V7_TEST", "leverage": 1.0, "execution_mode": "MARKET"}`, source SHA of 40 hex characters, trial count 861, and schema `v7-causal-1`.

### TDD steps

- [ ] Hash canonical object containing candidate config, source SHA, causal schema version, and total trial count. Mutating any one makes verification fail.
- [ ] Build 50 eligible observation timestamps at 12h cadence; this gives more than 40 observations but fewer than 30 calendar days. Even with `passing_metrics`, verdict is `NEEDS_MORE_RESEARCH` and failed gate includes `minimum_calendar_days`.
- [ ] Build 39 eligible observation timestamps at 24h cadence; this spans more than 30 days but has fewer than 40 observations. Verdict stays `NEEDS_MORE_RESEARCH` with `minimum_h12_observations`.
- [ ] Build 61 timestamps at 12h cadence so both evidence-volume gates pass; with all `passing_metrics` and matching hash, verdict is `READY_FOR_PAPER_TRADING`.
- [ ] Negative `ret_20bps` or negative `delay_1h_return` must force `NEEDS_MORE_RESEARCH`.
- [ ] Hash mismatch or `forward_driven_retuning=True` must force `NEEDS_MORE_RESEARCH`.
- [ ] Exact verdict vocabulary is only `NEEDS_MORE_RESEARCH` or `READY_FOR_PAPER_TRADING`.
- [ ] Run `pytest tests/test_forward_v7.py -v` RED -> implement -> GREEN.
- [ ] Commit: `feat: add immutable V7 freeze and A1 readiness gate`.

---

## Task 11 — Assemble core V7 artifacts/report

**Files:** `run_v7.py`, `v7_cycle.py`, `test_v7_cycle.py`, `test_run_v7.py`.

**Interface:**

```python
def run_v7_core_cycle(
    decision_log: pd.DataFrame,
    qh_features: pd.DataFrame,
    dispersion: pd.DataFrame,
    market: pd.DataFrame,
    *,
    artifact_root: str | Path,
    source_sha: str,
) -> dict[str, object]: ...
```

### TDD steps

- [ ] End-to-end toy test runs core cycle into `tmp_path`, freezes returned candidate with `freeze_v7_candidate`, writes a synthetic `forward_observations.csv.gz`, evaluates readiness, and then requires an empty artifact-contract missing list.
- [ ] `v7_protocol.json` records exact H1/H2/H3 formulas, selection split, first-line/total budgets, locked evidence, 10/20 bps assumptions, MARKET/1x inheritance, and A1 thresholds.
- [ ] `final_candidate.json` includes module list, fitted selection thresholds, source SHA, trial count, discovery/evaluation metrics, stress status, and unresolved error buckets.
- [ ] `final_report.md` distinguishes discovery/evaluation from untouched forward evidence and may print `READY_FOR_PAPER_TRADING` only when `readiness_gate.json` has that exact verdict.
- [ ] If first-line evidence does not sufficiently resolve the target economic/error gap, write `escalation_required=true` plus unresolved buckets; otherwise write `false` and do not escalate merely for complexity.
- [ ] Core-only council artifacts carry explicit `NOT_RUN_CORE_ONLY` payloads.
- [ ] Run `pytest tests/test_v7_cycle.py tests/test_run_v7.py tests/test_forward_v7.py -v` and confirm GREEN.
- [ ] Commit: `feat: assemble V7 core research artifacts`.

---

## Task 12 — Full regression, leakage, security, and checkpoint

- [ ] Run targeted V7 core suite:
  `pytest tests/test_features_v7.py tests/test_reliability_v7.py tests/test_trials_v7.py tests/test_diagnostics_v7.py tests/test_forward_v7.py tests/test_v7_cycle.py tests/test_run_v7.py -v`.
- [ ] Run full regression: `pytest -q`.
- [ ] Run `ruff check src tests`.
- [ ] Run `python -m compileall -q src tests`.
- [ ] Run leakage regressions: `pytest tests/test_features_v7.py tests/test_reliability_v7.py tests/test_state_v6.py tests/test_decision_log_v6.py -v`.
- [ ] Secret/path scan tracked V7 changes for `gsk_`, `BEGIN PRIVATE KEY`, bearer/private key values, exchange order endpoints, `withdraw`, `transfer`, OTP data, and exchange secrets. Identifiers such as `GROQ_API_KEY` are allowed; real values are not.
- [ ] Validate registry: first trial 858, monotonic unique trial numbers, first-line count <=24, total V7 count <=60.
- [ ] Compare `artifacts/multi_asset_v6/forward_freeze.json`, `final_candidate.json`, and `final_report.md` byte-for-byte against V6 head `46212f4c9eef07001341a87dffea40cd223cfa84`.
- [ ] If a regression fails, invoke `superpowers:systematic-debugging` before changing production logic.
- [ ] Before claiming completion, invoke `superpowers:verification-before-completion` and rerun the authoritative verification commands.

## Core completion gate

Core implementation is complete only when H1/H2/H3 plus at most one combination can be evaluated from trial 858 under fixed causal rules, all failures are attributed and remembered, V6 evidence remains immutable, V7 can freeze one candidate with a reproducible hash, and A1 can never return READY without both evidence-volume requirements and all hard metric/stress/integrity gates.

If the core cycle reports `escalation_required=true`, proceed to `docs/superpowers/plans/2026-08-11-v7-research-council-escalation-implementation.md`. If a simple candidate is sufficient for freeze, skip escalation and begin untouched A1 collection.