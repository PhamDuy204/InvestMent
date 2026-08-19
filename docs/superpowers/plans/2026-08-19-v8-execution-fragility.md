# V8 Execution Fragility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evaluate one predeclared execution-fragility factor as trial 869 and start a public-data-only forward order-book shadow recorder without introducing any live-trading path.

**Architecture:** Add a small V8 execution-risk module that builds the causal lagged-impact feature, constructs outcome-only delay-damage labels, fits fold-local baseline/augmented OLS models, and maps only the factor-attributable predicted damage into a no-boost exposure-increase scale. Reuse V7 replay, trial registry, diagnostics, delay labels, lag-RV panel, and promotion/stress accounting. Add a separate ccxt-based snapshot recorder for forward L2 evidence; it has no strategy or order methods.

**Tech Stack:** Python 3.11+/3.14-compatible stdlib, numpy, pandas, existing ccxt, pytest, Ruff. No new dependency.

**Spec:** `docs/superpowers/specs/2026-08-19-v8-execution-fragility-design.md`

## Global Constraints

- Research/backtest/simulation only; no live trading actions or trading credentials.
- Preserve H12 direction, MARKET baseline, and 1x maximum effective exposure.
- Trial history is append-only; H8 economic inspection is trial 869 exactly.
- 70/30 chronological split is inside each outer fold; every learned value is fit only on that fold selection.
- No threshold grid, transform grid, or nearby rescue after observing H8.
- Public historical `bookDepth` is not labelled exact executable L2.

---

### Task 1: Execution-fragility feature and damage-label primitives

**Files:**
- Create: `src/crypto_research/execution_v8.py`
- Test: `tests/test_execution_v8.py`

**Interfaces:**
- Produces: `lagged_impact_feature(frame: pd.DataFrame) -> pd.Series`
- Produces: `build_delay_damage_labels(immediate: pd.DataFrame, delayed: pd.DataFrame) -> pd.DataFrame`
- Produces: `fit_delay_damage_models(selection: pd.DataFrame) -> DelayDamageFit`
- Produces: `apply_execution_fragility_scale(frame: pd.DataFrame, fit: DelayDamageFit) -> pd.DataFrame`

- [ ] Write failing tests proving the feature uses only lagged return/quote volume, delay labels use future columns only as labels, scale never flips sign or increases absolute exposure, and reductions/unwinds are unchanged.
- [ ] Run `pytest tests/test_execution_v8.py -q` and verify RED from missing V8 functions.
- [ ] Implement the minimum numpy/pandas code to pass.
- [ ] Run targeted tests and Ruff on the new module/test.

### Task 2: Build the V8 factor panel from existing artifacts

**Files:**
- Create: `scripts/build_v8_execution_panel.py`
- Test: extend `tests/test_execution_v8.py`
- Output: `artifacts/multi_asset_v8/execution_factor_panel.csv.gz`
- Output: `artifacts/multi_asset_v8/execution_factor_panel_integrity.json`

**Interfaces:**
- Consumes V4 decision log, V7 delay labels, V7 hourly factor panel, and V7 basis panel lag-RV columns.
- Produces one row per `(decision_timestamp, symbol)` with causal features plus explicitly named outcome-only labels.

- [ ] Add a failing integrity test for one-to-one row identity, coverage >=0.70, causal cutoff <= decision timestamp, and no future/oracle column in `candidate_feature_columns`.
- [ ] Implement the panel builder by reusing existing artifacts; do not redownload raw data.
- [ ] Build panel and save integrity report before any H8 economic evaluation.

### Task 3: Trial 869 H8 runner

**Files:**
- Create: `scripts/run_v8_h8_execution_fragility.py`
- Test: `tests/test_h8_execution_fragility.py`
- Output: `artifacts/multi_asset_v8/h8_execution_fragility_results.json`
- Append: V8 experiment/failure/hypothesis/research logs while preserving V7 history.

**Interfaces:**
- Reuses `replay_v7_reliability`, `split_selection_evaluation`, `wrong_side_damage`, `stateful_summary`, and `V7TrialRegistry`-compatible append-only accounting.

- [ ] Write failing tests that H8 refuses to run unless inherited last trial is 868, refuses rerun if result exists, fits separately per fold, does not use outcome-only columns as features, and applies scale only to exposure increases.
- [ ] Run tests to confirm RED for missing runner/helper behavior.
- [ ] Implement minimal runner with exact predeclared models/mapping.
- [ ] Run targeted tests/compile.
- [ ] Confirm registry tail is 868 and H8 output absent.
- [ ] Execute H8 once. This consumes trial 869 whether it passes or fails.
- [ ] Persist fold metrics, forecast-admission evidence, selection/evaluation/stress metrics, exposure stats, wrong-side count/damage, and failure fingerprint.
- [ ] If H8 fails, append do-not-repeat memory and do not grid nearby variants.

### Task 4: Public L2 shadow recorder

**Files:**
- Create: `src/crypto_research/l2_shadow_v8.py`
- Create: `scripts/run_v8_l2_shadow.py`
- Test: `tests/test_l2_shadow_v8.py`

**Interfaces:**
- `snapshot_from_order_book(symbol: str, book: dict, captured_at: datetime) -> dict`
- `record_public_depth(symbols: list[str], output_dir: Path, *, limit: int = 20, iterations: int | None = None, interval_seconds: float = 5.0) -> None`

- [ ] Write RED tests using static public-order-book-shaped dictionaries; assert spread/depth calculations and absence of credential/order methods.
- [ ] Implement recorder using installed `ccxt.binanceusdm()` with no keys.
- [ ] Smoke run a finite iteration count and save a lightweight integrity summary.
- [ ] Do not use recorder data to retune H8 after trial 869.

### Task 5: Verification and GitHub V8 sync

**Files:**
- Create/update lightweight V8 report artifacts only; do not stage raw market-data caches.

- [ ] Run full `pytest`, `ruff check src tests scripts`, and `python -m compileall -q src tests scripts` using the project venv.
- [ ] Scan candidate feature lists for future/oracle leakage.
- [ ] Scan source for live-order/cancel/withdraw/transfer/leverage mutation paths and credential values.
- [ ] Verify V7 artifacts unchanged and V8 trial sequence has no duplicates.
- [ ] Sync V8 source/tests/lightweight artifacts to GitHub branch `v8-execution-liquidity-shadow` without modifying/merging V7 PR #4.
- [ ] Open/update a V8 PR against `v7-factor-observatory`, obtain green CI, and report the scientific verdict without claiming readiness unless freeze/A1 gates actually mature.
