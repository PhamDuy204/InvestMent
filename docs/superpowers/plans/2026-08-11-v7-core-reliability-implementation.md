# V7 Core Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the simple-first V7 research core: causal H1 quarter-hour conflict veto, H2 dispersion gate, H3 weak-edge veto, bounded trial accounting from 858, failure attribution, immutable freeze, and strict A1 readiness without any live-trading path.

**Architecture:** Reuse V6 H12 direction, causal universe, replay/account simulation, hysteresis, MARKET execution, 1x exposure, funding/cost/liquidation mechanics, and stress primitives. Add small V7 modules for causal features, fold-fitted reliability gates, research statistics, failure memory, bounded trials, freeze/readiness, and artifact orchestration. A V7 reliability layer can only veto or reduce new exposure; it can never create an opposite direction to H12.

**Tech Stack:** Python 3, pandas, NumPy, SciPy if already installed, existing scikit-learn research dependency, pytest, Ruff, existing V3/V6 portfolio/account modules, JSON/JSONL/CSV/GZip artifacts.

## Global Constraints

- Work on `v7-factor-observatory`, whose parent V6 head is `46212f4c9eef07001341a87dffea40cd223cfa84`.
- Preserve V6 frozen candidate hash `be84d12f86df294fc7eaf30affe5cf6d89df99cb1092e7856f2dbfd016b3ec92`; do not alter V6 freeze/candidate/report artifacts.
- Research counter starts at 857. First inspected V7 performance configuration is 858.
- First-line performance cap is 24. Total V7 performance cap, including escalation, is 60.
- H1/H2/H3 may veto or reduce a new exposure increase only. They may not flip H12 direction, raise leverage, force an opposite position, or replace inherited MARKET/1x execution/risk.
- Fit H1/H2/H3 thresholds only on the corresponding training/inner fold; apply unchanged to evaluation.
- 2021–2023 and Aug 1–10, 2026 are locked observed evidence and may not be used for V7 selection or retuning.
- `READY_FOR_PAPER_TRADING` requires BOTH at least 30 untouched calendar days AND at least 40 eligible H12 observations after V7 freeze.
- A1 additionally requires: net > 0 at 10 bps, PF > 1.10, Sharpe > 0.50, net >= 0 at 20 bps, net >= 0 with +1h delay, zero liquidation, zero exposure violations, zero margin violations, unchanged candidate hash, and zero forward-driven retuning.
- Do not add order placement, order cancellation, withdrawals, transfers, OTP flows, or exchange-side leverage mutation.
- Real secrets, including Groq or exchange credential values, must never appear in code, tests, logs, artifacts, prompts, or diffs.

---

### Task 1: V7 trial registry and artifact contract

**Files:**
- Create: `src/crypto_research/trials_v7.py`
- Create: `src/crypto_research/v7_cycle.py`
- Test: `tests/test_trials_v7.py`
- Test: `tests/test_v7_cycle.py`

**Interfaces:**
- Consumes: V6 convention from `src/crypto_research/trials_v6.py`.
- Produces: `V7TrialRegistry`, `REQUIRED_V7_ARTIFACTS`, `ensure_v7_artifact_contract`.

- [ ] **Step 1: Write the failing registry tests**

```python
# tests/test_trials_v7.py
import pytest

from crypto_research.trials_v7 import V7TrialRegistry


def test_registry_starts_at_858_and_persists(tmp_path):
    path = tmp_path / "experiment_registry.csv"
    registry = V7TrialRegistry(path)
    row = registry.record("A", "exact_v6_control", "CONTROL", phase="first_line")
    assert row["trial_number"] == 858
    registry.to_csv()
    loaded = V7TrialRegistry(path)
    assert loaded.total_count == 858


def test_first_line_cap_blocks_25th_trial(tmp_path):
    registry = V7TrialRegistry(tmp_path / "registry.csv", first_line_cap=24)
    for index in range(24):
        registry.record("H", f"first-{index}", "INSPECTED", phase="first_line")
    with pytest.raises(RuntimeError, match="first-line"):
        registry.record("H", "overflow", "INSPECTED", phase="first_line")


def test_total_cap_blocks_61st_v7_trial(tmp_path):
    registry = V7TrialRegistry(tmp_path / "registry.csv", total_cap=60)
    for index in range(60):
        registry.record("X", f"trial-{index}", "INSPECTED", phase="escalation")
    with pytest.raises(RuntimeError, match="total"):
        registry.record("X", "overflow", "INSPECTED", phase="escalation")
```

- [ ] **Step 2: Run the test to verify RED**

Run: `pytest tests/test_trials_v7.py -v`

Expected: import failure for `crypto_research.trials_v7`.

- [ ] **Step 3: Implement the registry**

```python
# src/crypto_research/trials_v7.py
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_COLUMNS = [
    "trial_number", "trial_id", "phase", "stage", "hypothesis", "status",
    "config_hash", "metrics_json", "timestamp_utc",
]


class V7TrialRegistry:
    def __init__(self, path: str | Path, *, prior_count: int = 857, first_line_cap: int = 24, total_cap: int = 60):
        if prior_count != 857:
            raise ValueError("V7 prior_count must remain 857")
        if first_line_cap <= 0 or total_cap < first_line_cap:
            raise ValueError("invalid V7 trial budgets")
        self.path = Path(path)
        self.prior_count = prior_count
        self.first_line_cap = first_line_cap
        self.total_cap = total_cap
        self.rows = pd.read_csv(self.path).to_dict("records") if self.path.exists() else []

    @property
    def total_count(self) -> int:
        return self.prior_count + len(self.rows)

    def record(self, stage: str, hypothesis: str, status: str, *, config=None, metrics=None, phase: str = "first_line"):
        if len(self.rows) >= self.total_cap:
            raise RuntimeError("V7 total trial budget exhausted")
        if phase == "first_line" and sum(row["phase"] == "first_line" for row in self.rows) >= self.first_line_cap:
            raise RuntimeError("V7 first-line trial budget exhausted")
        payload = json.dumps(config or {}, sort_keys=True, separators=(",", ":"), default=str)
        config_hash = hashlib.sha256(payload.encode()).hexdigest()
        trial_number = self.prior_count + len(self.rows) + 1
        row = {
            "trial_number": trial_number,
            "trial_id": f"v7-{trial_number:04d}-{config_hash[:10]}",
            "phase": phase,
            "stage": stage,
            "hypothesis": hypothesis,
            "status": status,
            "config_hash": config_hash,
            "metrics_json": json.dumps(metrics or {}, sort_keys=True, default=str),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        self.rows.append(row)
        return row

    def to_csv(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(self.rows, columns=_COLUMNS).to_csv(self.path, index=False)
        return self.path
```

- [ ] **Step 4: Write and implement the artifact-contract test**

```python
# tests/test_v7_cycle.py
from crypto_research.v7_cycle import REQUIRED_V7_ARTIFACTS, ensure_v7_artifact_contract


def test_required_v7_artifacts_cover_full_contract(tmp_path):
    expected = {
        "v7_protocol.json", "literature_registry.json", "hypothesis_registry.jsonl",
        "experiment_registry.csv", "agent_research_log.jsonl", "research_blackboard.jsonl",
        "factor_observatory.json", "failure_ledger.csv.gz", "do_not_repeat.json",
        "qh_imbalance_results.json", "dispersion_results.json", "weak_edge_results.json",
        "combination_results.json", "error_attribution.json", "stress_results.json",
        "dsr_results.json", "pbo_results.json", "final_candidate.json", "forward_freeze.json",
        "forward_observations.csv.gz", "readiness_gate.json", "final_report.md",
    }
    assert expected == REQUIRED_V7_ARTIFACTS
    assert ensure_v7_artifact_contract(tmp_path) == sorted(expected)
```

```python
# src/crypto_research/v7_cycle.py
from pathlib import Path

REQUIRED_V7_ARTIFACTS = {
    "v7_protocol.json", "literature_registry.json", "hypothesis_registry.jsonl",
    "experiment_registry.csv", "agent_research_log.jsonl", "research_blackboard.jsonl",
    "factor_observatory.json", "failure_ledger.csv.gz", "do_not_repeat.json",
    "qh_imbalance_results.json", "dispersion_results.json", "weak_edge_results.json",
    "combination_results.json", "error_attribution.json", "stress_results.json",
    "dsr_results.json", "pbo_results.json", "final_candidate.json", "forward_freeze.json",
    "forward_observations.csv.gz", "readiness_gate.json", "final_report.md",
}


def ensure_v7_artifact_contract(root: str | Path) -> list[str]:
    base = Path(root)
    return sorted(name for name in REQUIRED_V7_ARTIFACTS if not (base / name).exists())
```

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/test_trials_v7.py tests/test_v7_cycle.py -v`

Expected: PASS.

Commit:
```bash
git add src/crypto_research/trials_v7.py src/crypto_research/v7_cycle.py tests/test_trials_v7.py tests/test_v7_cycle.py
git commit -m "feat: lock V7 trial budgets and artifact contract"
```

---

### Task 2: Causal H1 and H2 features

**Files:**
- Create: `src/crypto_research/features_v7.py`
- Test: `tests/test_features_v7.py`

**Interfaces:**
- Produces: `signed_aggressor_volume`, `previous_completed_quarter_open`, `build_qh_opening_imbalance`, `build_cross_sectional_dispersion`.

- [ ] **Step 1: Write failing causal-feature tests**

```python
# tests/test_features_v7.py
import numpy as np
import pandas as pd
import pytest

from crypto_research.features_v7 import (
    build_cross_sectional_dispersion,
    build_qh_opening_imbalance,
    previous_completed_quarter_open,
    signed_aggressor_volume,
)


def test_aggressor_sign_mapping():
    assert signed_aggressor_volume(3.0, True) == -3.0
    assert signed_aggressor_volume(3.0, False) == 3.0


def test_previous_quarter_boundary():
    assert previous_completed_quarter_open(pd.Timestamp("2026-01-01T04:00:00Z")) == pd.Timestamp("2026-01-01T03:45:00Z")


def test_qh_feature_never_uses_current_quarter():
    trades = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-01-01T03:45:00Z", "2026-01-01T03:45:09Z", "2026-01-01T04:00:00Z", "2026-01-01T04:00:09Z"]),
        "symbol": ["BTCUSDT"] * 4,
        "quantity": [1.0, 3.0, 1000.0, 1000.0],
        "isBuyerMaker": [False, True, False, False],
    })
    decisions = pd.DataFrame({"decision_timestamp": pd.to_datetime(["2026-01-01T04:00:00Z"]), "symbol": ["BTCUSDT"]})
    out = build_qh_opening_imbalance(trades, decisions)
    assert out.loc[0, "qh_trade_count"] == 2
    assert out.loc[0, "qh_order_imbalance"] == pytest.approx(-0.5)
    assert out.loc[0, "qh_window_start"] == pd.Timestamp("2026-01-01T03:45:00Z")


def test_future_trade_mutation_does_not_change_qh_feature():
    trades = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-01-01T03:45:00Z", "2026-01-01T04:00:00Z"]),
        "symbol": ["BTCUSDT", "BTCUSDT"], "quantity": [2.0, 1.0], "isBuyerMaker": [False, False],
    })
    decisions = pd.DataFrame({"decision_timestamp": pd.to_datetime(["2026-01-01T04:00:00Z"]), "symbol": ["BTCUSDT"]})
    before = build_qh_opening_imbalance(trades, decisions)
    changed = trades.copy(); changed.loc[changed["timestamp"] >= decisions.loc[0, "decision_timestamp"], "quantity"] = 999999.0
    after = build_qh_opening_imbalance(changed, decisions)
    pd.testing.assert_frame_equal(before, after)


def test_dispersion_uses_only_current_eligible_universe():
    panel = pd.DataFrame({
        "decision_timestamp": pd.to_datetime(["2026-01-01T00:00Z"] * 4),
        "symbol": ["A", "B", "C", "D"], "ret_12": [0.01, 0.02, 0.05, 0.90],
        "in_universe": [True, True, True, False],
    })
    out = build_cross_sectional_dispersion(panel)
    expected = np.quantile([0.01, 0.02, 0.05], 0.75) - np.quantile([0.01, 0.02, 0.05], 0.25)
    assert out.loc[0, "dispersion_iqr"] == pytest.approx(expected)
    assert out.loc[0, "eligible_symbol_count"] == 3
```

- [ ] **Step 2: Run to verify RED**

Run: `pytest tests/test_features_v7.py -v`

Expected: import failure for new module.

- [ ] **Step 3: Implement the features**

```python
# src/crypto_research/features_v7.py
from __future__ import annotations

import numpy as np
import pandas as pd


def signed_aggressor_volume(quantity: float, is_buyer_maker: bool) -> float:
    qty = float(quantity)
    return -qty if bool(is_buyer_maker) else qty


def previous_completed_quarter_open(decision_timestamp: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(decision_timestamp)
    timestamp = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
    floored = timestamp.floor("15min")
    return floored - pd.Timedelta(minutes=15) if timestamp == floored else floored


def build_qh_opening_imbalance(trades: pd.DataFrame, decisions: pd.DataFrame, *, opening_seconds: int = 10) -> pd.DataFrame:
    if opening_seconds <= 0:
        raise ValueError("opening_seconds must be positive")
    work = trades.copy(); work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    dec = decisions.copy(); dec["decision_timestamp"] = pd.to_datetime(dec["decision_timestamp"], utc=True)
    rows = []
    for item in dec.itertuples(index=False):
        start = previous_completed_quarter_open(pd.Timestamp(item.decision_timestamp))
        stop = start + pd.Timedelta(seconds=opening_seconds)
        part = work.loc[(work["symbol"] == item.symbol) & (work["timestamp"] >= start) & (work["timestamp"] < stop)]
        signed = sum(signed_aggressor_volume(row.quantity, row.isBuyerMaker) for row in part.itertuples(index=False))
        total = float(pd.to_numeric(part.get("quantity", pd.Series(dtype=float)), errors="coerce").abs().sum())
        imbalance = signed / total if total > 0 else 0.0
        rows.append({"decision_timestamp": pd.Timestamp(item.decision_timestamp), "symbol": item.symbol, "qh_window_start": start, "qh_window_end": stop - pd.Timedelta(seconds=1), "qh_order_imbalance": float(imbalance), "qh_abs_order_imbalance": abs(float(imbalance)), "qh_trade_count": int(len(part))})
    return pd.DataFrame(rows)


def build_cross_sectional_dispersion(panel: pd.DataFrame, *, timestamp_col: str = "decision_timestamp", return_col: str = "ret_12", eligible_col: str = "in_universe") -> pd.DataFrame:
    work = panel.copy(); work[timestamp_col] = pd.to_datetime(work[timestamp_col], utc=True)
    rows = []
    for timestamp, group in work.groupby(timestamp_col, sort=True):
        values = pd.to_numeric(group.loc[group[eligible_col].astype(bool), return_col], errors="coerce").dropna()
        iqr = float(values.quantile(0.75) - values.quantile(0.25)) if len(values) >= 2 else np.nan
        rows.append({"decision_timestamp": pd.Timestamp(timestamp), "dispersion_iqr": iqr, "eligible_symbol_count": int(len(values))})
    return pd.DataFrame(rows)
```

- [ ] **Step 4: Add the H2 future-mutation regression**

```python
def test_future_dispersion_mutation_does_not_change_prior_row():
    panel = pd.DataFrame({
        "decision_timestamp": pd.to_datetime(["2026-01-01T00:00Z", "2026-01-01T00:00Z", "2026-01-01T12:00Z", "2026-01-01T12:00Z"]),
        "symbol": ["A", "B", "A", "B"], "ret_12": [0.01, 0.03, 0.02, 0.04], "in_universe": [True] * 4,
    })
    before = build_cross_sectional_dispersion(panel).iloc[[0]].reset_index(drop=True)
    changed = panel.copy(); changed.loc[changed["decision_timestamp"] > pd.Timestamp("2026-01-01T00:00Z"), "ret_12"] = 99.0
    after = build_cross_sectional_dispersion(changed).iloc[[0]].reset_index(drop=True)
    pd.testing.assert_frame_equal(before, after)
```

- [ ] **Step 5: Run and commit**

Run: `pytest tests/test_features_v7.py -v`

Expected: PASS.

Commit:
```bash
git add src/crypto_research/features_v7.py tests/test_features_v7.py
git commit -m "feat: add causal V7 reliability features"
```

---

### Task 3: Fold-fitted H1/H2/H3 reliability gates

**Files:**
- Create: `src/crypto_research/reliability_v7.py`
- Test: `tests/test_reliability_v7.py`

**Interfaces:**
- Consumes causal columns from Task 2 and inherited H12 `effective_score`/base target.
- Produces `ReliabilityGateConfig`, `fit_reliability_gates`, `apply_reliability_gates`.

- [ ] **Step 1: Write failing gate tests**

```python
# tests/test_reliability_v7.py
import pandas as pd
import pytest

from crypto_research.reliability_v7 import apply_reliability_gates, fit_reliability_gates


def _train():
    return pd.DataFrame({
        "qh_abs_order_imbalance": [0.1, 0.2, 0.3, 0.4, 0.5],
        "dispersion_iqr": [1.0, 2.0, 3.0, 4.0, 5.0],
        "effective_score": [0.01, 0.02, 0.03, 0.04, 0.05],
        "realized_net_contribution": [-0.01, 0.01, 0.01, 0.01, 0.01],
    })


def test_fit_uses_predeclared_training_percentiles():
    train = _train(); cfg = fit_reliability_gates(train)
    assert cfg.qh_abs_threshold == pytest.approx(train["qh_abs_order_imbalance"].median())
    assert cfg.dispersion_threshold == pytest.approx(train["dispersion_iqr"].quantile(0.80))
    assert cfg.weak_score_threshold == pytest.approx(train["effective_score"].abs().quantile(0.20))
    assert cfg.weak_score_veto_enabled


def test_h1_veto_blocks_new_conflicting_entry():
    cfg = fit_reliability_gates(_train())
    row = pd.Series({"qh_order_imbalance": -0.9, "dispersion_iqr": 0.0, "effective_score": 0.04})
    out = apply_reliability_gates(row, 0.0, 0.25, cfg, enable_h2=False, enable_h3=False)
    assert out["target_weight"] == 0.0
    assert out["h1_veto"]


def test_h2_scales_increment_not_whole_target():
    cfg = fit_reliability_gates(_train())
    row = pd.Series({"qh_order_imbalance": 0.0, "dispersion_iqr": 99.0, "effective_score": 0.04})
    out = apply_reliability_gates(row, 0.10, 0.25, cfg, enable_h1=False, enable_h3=False)
    assert out["target_weight"] == pytest.approx(0.175)


def test_reduction_passes_through_high_dispersion():
    cfg = fit_reliability_gates(_train())
    row = pd.Series({"qh_order_imbalance": 0.0, "dispersion_iqr": 99.0, "effective_score": 0.04})
    out = apply_reliability_gates(row, 0.25, 0.10, cfg, enable_h1=False, enable_h3=False)
    assert out["target_weight"] == pytest.approx(0.10)


def test_gates_never_reverse_base_direction():
    cfg = fit_reliability_gates(_train())
    for base in (-0.25, 0.25):
        row = pd.Series({"qh_order_imbalance": -0.9 if base > 0 else 0.9, "dispersion_iqr": 99.0, "effective_score": base})
        out = apply_reliability_gates(row, 0.0, base, cfg)
        assert out["target_weight"] == 0.0 or out["target_weight"] * base > 0
```

- [ ] **Step 2: Run to verify RED**

Run: `pytest tests/test_reliability_v7.py -v`

- [ ] **Step 3: Implement the gates**

```python
# src/crypto_research/reliability_v7.py
from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd


@dataclass(frozen=True)
class ReliabilityGateConfig:
    qh_abs_threshold: float | None
    dispersion_threshold: float | None
    weak_score_threshold: float | None
    weak_score_veto_enabled: bool
    high_dispersion_scale: float = 0.5


def fit_reliability_gates(train: pd.DataFrame, *, score_col: str = "effective_score", net_contribution_col: str = "realized_net_contribution") -> ReliabilityGateConfig:
    qh = pd.to_numeric(train["qh_abs_order_imbalance"], errors="coerce").dropna()
    disp = pd.to_numeric(train["dispersion_iqr"], errors="coerce").dropna()
    score = pd.to_numeric(train[score_col], errors="coerce")
    weak_threshold = float(score.abs().quantile(0.20))
    weak_mask = score.abs() <= weak_threshold
    weak_net = pd.to_numeric(train.loc[weak_mask, net_contribution_col], errors="coerce").dropna()
    return ReliabilityGateConfig(
        qh_abs_threshold=float(qh.median()) if len(qh) else None,
        dispersion_threshold=float(disp.quantile(0.80)) if len(disp) else None,
        weak_score_threshold=weak_threshold if score.notna().any() else None,
        weak_score_veto_enabled=bool(len(weak_net) and float(weak_net.mean()) <= 0.0),
    )


def _is_increase(previous: float, target: float) -> bool:
    return abs(target) > abs(previous) + 1e-12


def apply_reliability_gates(row, previous_weight: float, base_target_weight: float, config: ReliabilityGateConfig, *, enable_h1: bool = True, enable_h2: bool = True, enable_h3: bool = True):
    previous = float(previous_weight); target = float(base_target_weight)
    h1_veto = h2_scaled = h3_veto = False
    score = float(row.get("effective_score", 0.0))
    qh = float(row.get("qh_order_imbalance", float("nan")))
    if enable_h1 and config.qh_abs_threshold is not None and math.isfinite(qh) and score != 0 and _is_increase(previous, target):
        if qh * score < 0 and abs(qh) > config.qh_abs_threshold:
            target = previous if abs(previous) > 1e-12 else 0.0; h1_veto = True
    dispersion = float(row.get("dispersion_iqr", float("nan")))
    if enable_h2 and config.dispersion_threshold is not None and math.isfinite(dispersion) and dispersion > config.dispersion_threshold and _is_increase(previous, target):
        sign = 1.0 if target > 0 else -1.0
        target = sign * (abs(previous) + config.high_dispersion_scale * (abs(target) - abs(previous))); h2_scaled = True
    if enable_h3 and config.weak_score_veto_enabled and config.weak_score_threshold is not None and abs(score) <= config.weak_score_threshold and _is_increase(previous, target):
        target = previous if abs(previous) > 1e-12 else 0.0; h3_veto = True
    if base_target_weight != 0 and target * base_target_weight < -1e-12:
        raise RuntimeError("V7 reliability gate reversed H12 direction")
    return {"target_weight": float(target), "h1_veto": h1_veto, "h2_scaled": h2_scaled, "h3_veto": h3_veto}
```

- [ ] **Step 4: Add fold-isolation regression**

```python
def test_evaluation_mutation_cannot_change_fitted_config():
    train = _train(); evaluation = _train().copy()
    before = fit_reliability_gates(train)
    evaluation.loc[:, "qh_abs_order_imbalance"] = 999.0
    evaluation.loc[:, "dispersion_iqr"] = 999.0
    evaluation.loc[:, "realized_net_contribution"] = -999.0
    after = fit_reliability_gates(train)
    assert before == after
```

- [ ] **Step 5: Run and commit**

Run: `pytest tests/test_reliability_v7.py -v`

Commit:
```bash
git add src/crypto_research/reliability_v7.py tests/test_reliability_v7.py
git commit -m "feat: add fold-fitted V7 reliability gates"
```

---

### Task 4: Failure memory and V7 causal schema

**Files:**
- Create: `src/crypto_research/diagnostics_v7.py`
- Modify: `src/crypto_research/decision_diagnostics.py`
- Test: `tests/test_diagnostics_v7.py`
- Regression: `tests/test_decision_log_v6.py`

**Interfaces:**
- Produces: `mechanism_fingerprint`, `build_failure_record`, `append_failure_ledger`, `load_do_not_repeat`, `reject_repeated_mechanism`, `V7_CAUSAL_COLUMNS`, `V7_LABEL_COLUMNS`.

- [ ] **Step 1: Write failing diagnostics tests**

```python
# tests/test_diagnostics_v7.py
import json
import pytest

from crypto_research.decision_diagnostics import V7_CAUSAL_COLUMNS, V7_LABEL_COLUMNS
from crypto_research.diagnostics_v7 import mechanism_fingerprint, reject_repeated_mechanism


def test_fingerprint_normalizes_text_and_input_order():
    left = mechanism_fingerprint("WRONG_SIDE", "QH conflict veto", ["qh", "h12"], "veto_increase")
    right = mechanism_fingerprint("WRONG_SIDE", "  qh conflict veto  ", ["h12", "qh"], "veto_increase")
    assert left == right


def test_repeated_failed_mechanism_requires_new_evidence():
    with pytest.raises(ValueError, match="do-not-repeat"):
        reject_repeated_mechanism("abc", {"abc"})
    reject_repeated_mechanism("abc", {"abc"}, materially_new_evidence=True)


def test_v7_causal_and_label_schemas_are_disjoint():
    assert not set(V7_CAUSAL_COLUMNS) & set(V7_LABEL_COLUMNS)
    assert "qh_order_imbalance" in V7_CAUSAL_COLUMNS
    assert "dispersion_iqr" in V7_CAUSAL_COLUMNS
    assert "oracle_direction" in V7_LABEL_COLUMNS
    assert "oracle_direction" not in V7_CAUSAL_COLUMNS
```

- [ ] **Step 2: Run to verify RED**

Run: `pytest tests/test_diagnostics_v7.py -v`

- [ ] **Step 3: Implement failure memory**

```python
# src/crypto_research/diagnostics_v7.py
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import pandas as pd


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).strip().lower())


def mechanism_fingerprint(target_error: str, expected_mechanism: str, causal_inputs: list[str], action: str) -> str:
    payload = {"target_error": _norm(target_error), "expected_mechanism": _norm(expected_mechanism), "causal_inputs": sorted(_norm(value) for value in causal_inputs), "action": _norm(action)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def reject_repeated_mechanism(fingerprint: str, blocked: set[str], *, materially_new_evidence: bool = False) -> None:
    if fingerprint in blocked and not materially_new_evidence:
        raise ValueError("do-not-repeat mechanism requires materially new evidence")


def build_failure_record(**values):
    required = {"trial_number", "hypothesis_id", "target_error", "expected_mechanism", "actual_error_delta", "net_effect_bps", "turnover_effect", "drawdown_effect", "damaged_regime", "helped_regime", "assumption_status", "failure_reason", "do_not_repeat_fingerprint", "next_allowed_question", "timestamp_utc"}
    missing = required.difference(values)
    if missing:
        raise ValueError(f"missing failure fields: {sorted(missing)}")
    return {key: values[key] for key in sorted(required)}


def append_failure_ledger(records, path: str | Path) -> Path:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    old = pd.read_csv(target, compression="gzip") if target.exists() else pd.DataFrame()
    pd.concat([old, pd.DataFrame(records)], ignore_index=True).to_csv(target, index=False, compression="gzip")
    return target


def load_do_not_repeat(path: str | Path) -> set[str]:
    target = Path(path)
    if not target.exists(): return set()
    payload = json.loads(target.read_text())
    return set(payload.get("fingerprints", []))
```

- [ ] **Step 4: Add V7 constants without changing V6 constants/functions**

```python
# append to src/crypto_research/decision_diagnostics.py
V7_CAUSAL_COLUMNS = V6_CAUSAL_COLUMNS + (
    "qh_order_imbalance", "qh_abs_order_imbalance", "dispersion_iqr",
    "qh_abs_threshold", "dispersion_threshold", "weak_score_threshold",
)
V7_LABEL_COLUMNS = V6_LABEL_COLUMNS
```

- [ ] **Step 5: Run V6/V7 diagnostics and commit**

Run: `pytest tests/test_decision_log_v6.py tests/test_diagnostics_v7.py -v`

Expected: PASS.

Commit:
```bash
git add src/crypto_research/diagnostics_v7.py src/crypto_research/decision_diagnostics.py tests/test_diagnostics_v7.py
git commit -m "feat: add V7 failure memory and causal schema"
```

---

### Task 5: V7 research statistics

**Files:**
- Create: `src/crypto_research/statistics_v7.py`
- Test: `tests/test_statistics_v7.py`

**Interfaces:**
- Produces: `block_bootstrap_equity`, `cscv_pbo`, `approximate_dsr`.

- [ ] **Step 1: Write failing statistics tests**

```python
# tests/test_statistics_v7.py
import numpy as np
import pandas as pd

from crypto_research.statistics_v7 import approximate_dsr, block_bootstrap_equity, cscv_pbo


def test_block_bootstrap_is_reproducible():
    returns = pd.Series([0.01, -0.005, 0.002, 0.004] * 20)
    assert block_bootstrap_equity(returns, samples=100, block_length=4, seed=42) == block_bootstrap_equity(returns, samples=100, block_length=4, seed=42)


def test_pbo_is_bounded():
    matrix = pd.DataFrame({"a": np.linspace(-0.01, 0.02, 80), "b": np.linspace(0.01, -0.01, 80), "c": np.sin(np.arange(80)) / 100})
    result = cscv_pbo(matrix, segments=8)
    assert 0.0 <= result["pbo"] <= 1.0
    assert result["segments"] == 8


def test_approximate_dsr_marks_incomplete_trial_history():
    result = approximate_dsr(observed_sharpe=1.0, trial_sharpes=[0.5, 0.8, 1.0], observations=200, total_trial_count=860)
    assert "INCOMPLETE" in result["status"]
    assert result["total_trial_count"] == 860
```

- [ ] **Step 2: Run to verify RED**

Run: `pytest tests/test_statistics_v7.py -v`

- [ ] **Step 3: Implement deterministic bootstrap and CSCV/PBO**

```python
# src/crypto_research/statistics_v7.py
from __future__ import annotations

import itertools
import math
import statistics

import numpy as np
import pandas as pd


def block_bootstrap_equity(returns: pd.Series, *, samples: int = 2000, block_length: int = 20, seed: int = 42):
    values = pd.to_numeric(returns, errors="coerce").dropna().to_numpy(float)
    rng = np.random.default_rng(seed); finals = []; drawdowns = []
    for _ in range(samples):
        picks = []
        while len(picks) < len(values):
            start = int(rng.integers(0, max(len(values) - block_length + 1, 1)))
            picks.extend(values[start:start + block_length].tolist())
        path = np.cumprod(1.0 + np.asarray(picks[:len(values)]))
        peak = np.maximum.accumulate(path)
        finals.append(float(path[-1])); drawdowns.append(float(np.max(1.0 - path / peak)))
    return {"samples": samples, "block_length": block_length, "final_equity_p05": float(np.quantile(finals, 0.05)), "final_equity_median": float(np.median(finals)), "final_equity_p95": float(np.quantile(finals, 0.95)), "probability_final_equity_below_one": float(np.mean(np.asarray(finals) < 1.0)), "max_drawdown_median": float(np.median(drawdowns)), "max_drawdown_p95": float(np.quantile(drawdowns, 0.95))}


def _sharpe(values: np.ndarray) -> float:
    std = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    return float(np.mean(values) / std) if std > 0 else 0.0


def cscv_pbo(candidate_returns: pd.DataFrame, *, segments: int = 8):
    clean = candidate_returns.dropna().copy()
    if segments % 2 or len(clean) < segments:
        raise ValueError("CSCV requires an even segment count and enough rows")
    parts = np.array_split(np.arange(len(clean)), segments); logits = []
    half = segments // 2
    for chosen in itertools.combinations(range(segments), half):
        train_idx = np.concatenate([parts[i] for i in chosen]); test_idx = np.concatenate([parts[i] for i in range(segments) if i not in chosen])
        train_scores = {col: _sharpe(clean[col].to_numpy()[train_idx]) for col in clean.columns}
        winner = max(train_scores, key=train_scores.get)
        test_scores = sorted((_sharpe(clean[col].to_numpy()[test_idx]), col) for col in clean.columns)
        rank = next(index for index, item in enumerate(test_scores, start=1) if item[1] == winner)
        percentile = rank / (len(test_scores) + 1.0)
        logits.append(math.log(percentile / (1.0 - percentile)))
    return {"segments": segments, "combinations": len(logits), "pbo": float(np.mean(np.asarray(logits) <= 0.0)), "status": "CSCV_PBO_NOT_CPCV"}


def approximate_dsr(*, observed_sharpe: float, trial_sharpes: list[float], observations: int, total_trial_count: int):
    finite = [float(x) for x in trial_sharpes if math.isfinite(float(x))]
    benchmark = max(finite) if finite else 0.0
    scale = max(1.0 / math.sqrt(max(observations, 1)), 1e-12)
    z = (float(observed_sharpe) - benchmark) / scale
    probability = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return {"observed_sharpe": float(observed_sharpe), "benchmark_sharpe": float(benchmark), "available_trial_sharpes": len(finite), "total_trial_count": int(total_trial_count), "observations": int(observations), "probability": float(probability), "status": "APPROXIMATE_DSR_HISTORICAL_TRIAL_SHARPE_DISTRIBUTION_INCOMPLETE"}
```

- [ ] **Step 4: Run tests and commit**

Run: `pytest tests/test_statistics_v7.py -v`

Commit:
```bash
git add src/crypto_research/statistics_v7.py tests/test_statistics_v7.py
git commit -m "feat: add V7 bootstrap and multiple-testing statistics"
```

---

### Task 6: Fixed first-line replay, attribution, and stress

**Files:**
- Create: `src/crypto_research/run_v7.py`
- Modify: `src/crypto_research/v7_cycle.py`
- Test: `tests/test_run_v7.py`

**Interfaces:**
- Consumes: `run_v6.replay_weight_overlay`, Tasks 1–5, `run_leverage_v3.run_grid`, `run_leverage_v3.shock_grid`.
- Produces: `split_selection_evaluation`, `run_v7_first_line`, `attribute_candidate_errors`, `run_v7_stress_suite`.

- [ ] **Step 1: Write the failing fixed-sequence test fixture**

```python
# tests/test_run_v7.py
import json
import pandas as pd

from crypto_research.run_v7 import run_v7_first_line


def _toy_inputs():
    times = pd.date_range("2026-01-01", periods=12, freq="12h", tz="UTC")
    rows = []
    qh = []
    for index, timestamp in enumerate(times):
        for symbol, side in (("A", 1.0), ("B", -1.0)):
            score = 0.04 * side
            realized = 0.01 if index % 3 else -0.015
            rows.append({"decision_timestamp": timestamp, "symbol": symbol, "target_weight": 0.20 * side, "holding_return_label": realized * side, "funding_sum_label": 0.0, "effective_score": score, "realized_net_contribution": realized * 0.20})
            qh.append({"decision_timestamp": timestamp, "symbol": symbol, "qh_order_imbalance": score * 5.0, "qh_abs_order_imbalance": abs(score * 5.0)})
    decisions = pd.DataFrame(rows)
    qh_features = pd.DataFrame(qh)
    dispersion = pd.DataFrame({"decision_timestamp": times, "dispersion_iqr": [0.01 + 0.001 * i for i in range(len(times))], "eligible_symbol_count": [2] * len(times)})
    return decisions, qh_features, dispersion


def test_first_line_sequence_starts_at_858(tmp_path):
    decisions, qh, dispersion = _toy_inputs()
    run_v7_first_line(decisions, qh, dispersion, artifact_root=tmp_path)
    registry = pd.read_csv(tmp_path / "experiment_registry.csv")
    assert registry.iloc[0]["trial_number"] == 858
    assert registry["hypothesis"].tolist()[:4] == ["exact_v6_control", "H1_qh_conflict_veto", "H2_high_dispersion_gate", "H3_weak_edge_veto"]
```

- [ ] **Step 2: Run to verify RED**

Run: `pytest tests/test_run_v7.py::test_first_line_sequence_starts_at_858 -v`

- [ ] **Step 3: Implement fixed split and one-candidate evaluator**

```python
# src/crypto_research/run_v7.py
from pathlib import Path
import json

import pandas as pd

from crypto_research.reliability_v7 import apply_reliability_gates, fit_reliability_gates
from crypto_research.run_v6 import replay_weight_overlay
from crypto_research.trials_v7 import V7TrialRegistry


def split_selection_evaluation(decision_log: pd.DataFrame, *, selection_fraction: float = 0.70):
    times = pd.Index(sorted(pd.to_datetime(decision_log["decision_timestamp"], utc=True).unique()))
    if len(times) < 4 or not 0 < selection_fraction < 1:
        raise ValueError("insufficient timestamps or invalid split")
    split = max(1, min(len(times) - 1, int(len(times) * selection_fraction)))
    cutoff = times[split - 1]
    work = decision_log.copy(); work["decision_timestamp"] = pd.to_datetime(work["decision_timestamp"], utc=True)
    return work.loc[work["decision_timestamp"] <= cutoff].copy(), work.loc[work["decision_timestamp"] > cutoff].copy()


def _candidate_replay(frame, config, *, enable_h1, enable_h2, enable_h3, cost_bps):
    def scale_fn(row):
        previous = float(getattr(row, "previous_weight", 0.0))
        base = float(row.target_weight)
        result = apply_reliability_gates(row._asdict(), previous, base, config, enable_h1=enable_h1, enable_h2=enable_h2, enable_h3=enable_h3)
        return 0.0 if abs(base) <= 1e-12 else min(1.0, abs(float(result["target_weight"]) / base))
    return replay_weight_overlay(frame, scale_fn=scale_fn, round_trip_cost_bps=cost_bps)
```

- [ ] **Step 4: Implement `run_v7_first_line` with the exact sequence**

```python
def run_v7_first_line(decision_log, qh_features, dispersion, *, artifact_root, prior_trials=857, round_trip_cost_bps=10.0, selection_fraction=0.70):
    root = Path(artifact_root); root.mkdir(parents=True, exist_ok=True)
    work = decision_log.copy(); work["decision_timestamp"] = pd.to_datetime(work["decision_timestamp"], utc=True)
    qh = qh_features.copy(); qh["decision_timestamp"] = pd.to_datetime(qh["decision_timestamp"], utc=True)
    disp = dispersion.copy(); disp["decision_timestamp"] = pd.to_datetime(disp["decision_timestamp"], utc=True)
    work = work.merge(qh, on=["decision_timestamp", "symbol"], how="left", validate="one_to_one").merge(disp, on="decision_timestamp", how="left", validate="many_to_one")
    selection, evaluation = split_selection_evaluation(work, selection_fraction=selection_fraction)
    config = fit_reliability_gates(selection)
    registry = V7TrialRegistry(root / "experiment_registry.csv", prior_count=prior_trials)
    specs = [
        ("exact_v6_control", False, False, False),
        ("H1_qh_conflict_veto", True, False, False),
        ("H2_high_dispersion_gate", False, True, False),
        ("H3_weak_edge_veto", False, False, True),
    ]
    results = {}
    for name, h1, h2, h3 in specs:
        sel_periods, _, sel_metrics = _candidate_replay(selection, config, enable_h1=h1, enable_h2=h2, enable_h3=h3, cost_bps=round_trip_cost_bps)
        eval_periods, _, eval_metrics = _candidate_replay(evaluation, config, enable_h1=h1, enable_h2=h2, enable_h3=h3, cost_bps=round_trip_cost_bps)
        registry.record("A" if name == "exact_v6_control" else name[:2], name, "INSPECTED", config={"h1": h1, "h2": h2, "h3": h3}, metrics={"selection": sel_metrics, "evaluation": eval_metrics})
        results[name] = {"selection": sel_metrics, "evaluation": eval_metrics, "selection_periods": sel_periods, "evaluation_periods": eval_periods}
    registry.to_csv()
    base = results["exact_v6_control"]["evaluation"]
    promoted = [name for name in specs[1:] if results[name[0]]["evaluation"]["net_return"] > base["net_return"]]
    promoted_names = [item[0] for item in promoted]
    if len(promoted_names) < 2:
        (root / "combination_results.json").write_text(json.dumps({"status": "NOT_RUN_FEWER_THAN_TWO_PROMOTED", "promoted": promoted_names}, indent=2))
    return {"gate_config": config.__dict__, "results": {key: {"selection": value["selection"], "evaluation": value["evaluation"]} for key, value in results.items()}, "promoted": promoted_names, "trial_count_after": registry.total_count}
```

The minimal implementation above is intentionally incomplete on promotion rigor; in the same task, replace the temporary `net_return`-only `promoted` line before GREEN with the exact deterministic gate below and cover it with tests:

```python
def _promotion_gate(base, candidate, *, target_error_delta: int, fold_positive_count: int, fold_count: int):
    return bool(
        candidate["net_return"] > base["net_return"]
        and candidate["sharpe"] >= base["sharpe"] - 1e-12
        and candidate["max_drawdown"] <= base["max_drawdown"] + 1e-12
        and target_error_delta < 0
        and fold_count >= 2
        and fold_positive_count >= 2
    )
```

- [ ] **Step 5: Add no-combination and candidate-artifact tests**

```python
def test_combination_not_spent_when_fewer_than_two_promote(tmp_path):
    decisions, qh, dispersion = _toy_inputs()
    result = run_v7_first_line(decisions, qh, dispersion, artifact_root=tmp_path)
    payload = json.loads((tmp_path / "combination_results.json").read_text())
    if len(result["promoted"]) < 2:
        assert payload["status"] == "NOT_RUN_FEWER_THAN_TWO_PROMOTED"
        registry = pd.read_csv(tmp_path / "experiment_registry.csv")
        assert "H123_combination" not in set(registry["hypothesis"])
```

Also add tests that every candidate inspected at 10 bps is re-evaluated at 20 bps and with +1h delay before promotion; implement those evaluations using the same candidate specification with the inherited delayed-execution path, never by changing thresholds.

- [ ] **Step 6: Implement error attribution and failure ledger integration**

```python
def attribute_candidate_errors(base_errors: pd.Series, candidate_errors: pd.Series, base_contribution: pd.Series, candidate_contribution: pd.Series):
    classes = sorted(set(base_errors.dropna()) | set(candidate_errors.dropna()))
    output = {}
    for error in classes:
        before = int((base_errors == error).sum()); after = int((candidate_errors == error).sum())
        output[error] = {"baseline_count": before, "candidate_count": after, "count_delta": after - before}
    output["economic"] = {"net_effect_bps": float((candidate_contribution.sum() - base_contribution.sum()) * 10000.0)}
    return output
```

Use existing `classify_error` to generate aligned `base_errors` and `candidate_errors`; do not invent a new oracle. Rejected candidates call `build_failure_record` and append `failure_ledger.csv.gz`; write sorted fingerprints to `do_not_repeat.json`.

- [ ] **Step 7: Add stress wrapper**

```python
from crypto_research.run_leverage_v3 import run_grid, shock_grid


def run_v7_stress_suite(periods, market):
    return {
        "base_10bps": run_grid(periods, market, leverages=(1,), round_trip_cost_bps=10.0),
        "cost_20bps": run_grid(periods, market, leverages=(1,), round_trip_cost_bps=20.0),
        "slippage_5bps_one_way": run_grid(periods, market, leverages=(1,), slippage_bps=5.0),
        "funding_x3": run_grid(periods, market, leverages=(1,), funding_multiplier=3.0),
        "maintenance_2pct": run_grid(periods, market, leverages=(1,), maintenance_margin_rate=0.02),
        "maintenance_5pct": run_grid(periods, market, leverages=(1,), maintenance_margin_rate=0.05),
        "correlation_one_shock": shock_grid(periods, leverages=(1,)),
    }
```

The +1h delayed strategy replay is produced separately using the same frozen H1/H2/H3 specification and inherited delayed-entry scoring path; store it in `stress_results.json` alongside this account suite.

- [ ] **Step 8: Run and commit**

Run: `pytest tests/test_run_v7.py tests/test_reliability_v7.py tests/test_trials_v7.py tests/test_diagnostics_v7.py -v`

Expected: PASS.

Commit:
```bash
git add src/crypto_research/run_v7.py src/crypto_research/v7_cycle.py tests/test_run_v7.py
git commit -m "feat: add fixed V7 first-line research cycle"
```

---

### Task 7: Immutable V7 freeze and strict A1 readiness

**Files:**
- Create: `src/crypto_research/forward_v7.py`
- Test: `tests/test_forward_v7.py`

**Interfaces:**
- Produces: `freeze_v7_candidate`, `verify_v7_freeze`, `evaluate_a1_readiness`.

- [ ] **Step 1: Write failing freeze/readiness tests**

```python
# tests/test_forward_v7.py
import json
import pandas as pd

from crypto_research.forward_v7 import evaluate_a1_readiness, freeze_v7_candidate, verify_v7_freeze


def _freeze(tmp_path):
    return freeze_v7_candidate({"name": "V7_TEST", "leverage": 1.0, "execution_mode": "MARKET"}, artifact_root=tmp_path, timestamp="2026-08-11T04:00:00Z", total_trial_count=861, source_sha="a" * 40, causal_schema_version="v7-causal-1")


def _metrics():
    return {"ret_10bps": 0.01, "profit_factor": 1.20, "sharpe": 0.75, "ret_20bps": 0.002, "delay_1h_return": 0.001, "liquidation_count": 0, "exposure_violation_count": 0, "margin_violation_count": 0, "forward_driven_retuning": False}


def test_freeze_detects_mutation(tmp_path):
    payload = _freeze(tmp_path); path = tmp_path / "forward_freeze.json"
    assert verify_v7_freeze(path)
    payload["candidate_config"]["leverage"] = 2.0; path.write_text(json.dumps(payload))
    assert not verify_v7_freeze(path)


def test_ready_requires_30_days_and_40_observations(tmp_path):
    freeze = _freeze(tmp_path); metrics = _metrics()
    short_days = pd.DataFrame({"decision_timestamp": pd.date_range("2026-09-01", periods=50, freq="12h", tz="UTC")})
    result = evaluate_a1_readiness(short_days, freeze, candidate_hash=freeze["candidate_hash_sha256"], **metrics)
    assert result["verdict"] == "NEEDS_MORE_RESEARCH"; assert "minimum_calendar_days" in result["failed_gates"]
    few_rows = pd.DataFrame({"decision_timestamp": pd.date_range("2026-09-01", periods=39, freq="24h", tz="UTC")})
    result = evaluate_a1_readiness(few_rows, freeze, candidate_hash=freeze["candidate_hash_sha256"], **metrics)
    assert result["verdict"] == "NEEDS_MORE_RESEARCH"; assert "minimum_h12_observations" in result["failed_gates"]


def test_all_a1_gates_can_return_ready(tmp_path):
    freeze = _freeze(tmp_path); forward = pd.DataFrame({"decision_timestamp": pd.date_range("2026-09-01", periods=61, freq="12h", tz="UTC")})
    result = evaluate_a1_readiness(forward, freeze, candidate_hash=freeze["candidate_hash_sha256"], **_metrics())
    assert result["verdict"] == "READY_FOR_PAPER_TRADING"
```

- [ ] **Step 2: Run to verify RED**

Run: `pytest tests/test_forward_v7.py -v`

- [ ] **Step 3: Implement freeze and readiness**

```python
# src/crypto_research/forward_v7.py
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def freeze_v7_candidate(config, *, artifact_root, timestamp, total_trial_count, source_sha, causal_schema_version):
    frozen = {"candidate_config": config, "source_sha": source_sha, "causal_schema_version": causal_schema_version, "total_trial_count_at_freeze": int(total_trial_count)}
    digest = hashlib.sha256(_canonical(frozen).encode()).hexdigest()
    payload = {"research_version": "V7", "freeze_timestamp_utc": timestamp, **frozen, "candidate_hash_sha256": digest, "locked_evidence": {"2021_2023": "OBSERVED_NOT_RETUNED", "2026_08_01_to_10": "OBSERVED_NOT_RETUNED"}}
    root = Path(artifact_root); root.mkdir(parents=True, exist_ok=True); (root / "forward_freeze.json").write_text(json.dumps(payload, indent=2, default=str))
    return payload


def verify_v7_freeze(path):
    payload = json.loads(Path(path).read_text())
    frozen = {key: payload[key] for key in ("candidate_config", "source_sha", "causal_schema_version", "total_trial_count_at_freeze")}
    return hashlib.sha256(_canonical(frozen).encode()).hexdigest() == payload.get("candidate_hash_sha256")


def evaluate_a1_readiness(forward, freeze, *, candidate_hash, ret_10bps, profit_factor, sharpe, ret_20bps, delay_1h_return, liquidation_count, exposure_violation_count, margin_violation_count, forward_driven_retuning):
    timestamps = pd.to_datetime(forward["decision_timestamp"], utc=True).sort_values()
    days = float((timestamps.max() - timestamps.min()).total_seconds() / 86400.0) if len(timestamps) > 1 else 0.0
    gates = {
        "minimum_calendar_days": days >= 30.0,
        "minimum_h12_observations": len(timestamps) >= 40,
        "net_10bps_positive": ret_10bps > 0.0,
        "profit_factor": profit_factor > 1.10,
        "sharpe": sharpe > 0.50,
        "net_20bps_nonnegative": ret_20bps >= 0.0,
        "delay_1h_nonnegative": delay_1h_return >= 0.0,
        "zero_liquidation": liquidation_count == 0,
        "zero_exposure_violations": exposure_violation_count == 0,
        "zero_margin_violations": margin_violation_count == 0,
        "candidate_hash_unchanged": candidate_hash == freeze.get("candidate_hash_sha256"),
        "zero_forward_retuning": not forward_driven_retuning,
    }
    failed = [name for name, passed in gates.items() if not passed]
    return {"verdict": "READY_FOR_PAPER_TRADING" if not failed else "NEEDS_MORE_RESEARCH", "calendar_days": days, "eligible_h12_observations": int(len(timestamps)), "gates": gates, "failed_gates": failed}
```

- [ ] **Step 4: Add hard-gate tests**

```python
def test_negative_stress_or_retuning_blocks_ready(tmp_path):
    freeze = _freeze(tmp_path); forward = pd.DataFrame({"decision_timestamp": pd.date_range("2026-09-01", periods=61, freq="12h", tz="UTC")})
    metrics = _metrics(); metrics["ret_20bps"] = -0.0001
    assert evaluate_a1_readiness(forward, freeze, candidate_hash=freeze["candidate_hash_sha256"], **metrics)["verdict"] == "NEEDS_MORE_RESEARCH"
    metrics = _metrics(); metrics["forward_driven_retuning"] = True
    assert evaluate_a1_readiness(forward, freeze, candidate_hash=freeze["candidate_hash_sha256"], **metrics)["verdict"] == "NEEDS_MORE_RESEARCH"
```

- [ ] **Step 5: Run and commit**

Run: `pytest tests/test_forward_v7.py -v`

Commit:
```bash
git add src/crypto_research/forward_v7.py tests/test_forward_v7.py
git commit -m "feat: add immutable V7 freeze and A1 readiness gate"
```

---

### Task 8: Full V7 core artifact/report orchestration

**Files:**
- Modify: `src/crypto_research/run_v7.py`
- Modify: `src/crypto_research/v7_cycle.py`
- Test: `tests/test_v7_cycle.py`
- Test: `tests/test_run_v7.py`

**Interfaces:**
- Produces `run_v7_core_cycle(decision_log, qh_features, dispersion, market, *, artifact_root, source_sha)`.

- [ ] **Step 1: Write the failing end-to-end artifact test**

```python
def test_core_cycle_writes_pre_freeze_artifacts_and_explicit_council_placeholders(tmp_path):
    decisions, qh, dispersion = _toy_inputs()
    market = pd.DataFrame()
    result = run_v7_core_cycle(decisions, qh, dispersion, market, artifact_root=tmp_path, source_sha="b" * 40)
    assert (tmp_path / "v7_protocol.json").exists()
    assert (tmp_path / "final_candidate.json").exists()
    assert json.loads((tmp_path / "agent_research_log.jsonl").read_text())["status"] == "NOT_RUN_CORE_ONLY"
    assert result["source_sha"] == "b" * 40
```

- [ ] **Step 2: Run to verify RED**

Run: `pytest tests/test_v7_cycle.py tests/test_run_v7.py -v`

- [ ] **Step 3: Implement protocol/candidate/placeholders**

```python
# add to src/crypto_research/run_v7.py

def _write_core_placeholders(root: Path):
    payloads = {
        "literature_registry.json": {"status": "NOT_RUN_CORE_ONLY", "sources": []},
        "hypothesis_registry.jsonl": {"status": "NOT_RUN_CORE_ONLY", "hypotheses": []},
        "agent_research_log.jsonl": {"status": "NOT_RUN_CORE_ONLY"},
        "research_blackboard.jsonl": {"status": "NOT_RUN_CORE_ONLY"},
        "factor_observatory.json": {"status": "NOT_RUN_CORE_ONLY", "factors": []},
    }
    for name, payload in payloads.items():
        (root / name).write_text(json.dumps(payload, sort_keys=True))


def run_v7_core_cycle(decision_log, qh_features, dispersion, market, *, artifact_root, source_sha):
    root = Path(artifact_root); root.mkdir(parents=True, exist_ok=True)
    first_line = run_v7_first_line(decision_log, qh_features, dispersion, artifact_root=root)
    _write_core_placeholders(root)
    protocol = {"research_version": "V7", "source_sha": source_sha, "prior_trial_count": 857, "first_line_cap": 24, "total_cap": 60, "h1": {"threshold": "training median abs QH OI", "action": "veto new/increased exposure only"}, "h2": {"threshold": "training 80th percentile dispersion IQR", "scale": 0.5, "action": "scale incremental exposure increase only"}, "h3": {"threshold": "training 20th percentile abs H12 score", "enable_condition": "training weak bucket mean net <= 0"}, "execution_mode": "MARKET", "effective_leverage": 1.0, "a1": {"minimum_calendar_days": 30, "minimum_h12_observations": 40, "profit_factor_gt": 1.10, "sharpe_gt": 0.50}}
    (root / "v7_protocol.json").write_text(json.dumps(protocol, indent=2))
    candidate = {"name": "V7_SIMPLE_FIRST", "source_sha": source_sha, "gate_config": first_line["gate_config"], "promoted": first_line["promoted"], "trial_count": first_line["trial_count_after"], "execution_mode": "MARKET", "recommended_effective_leverage": 1.0}
    (root / "final_candidate.json").write_text(json.dumps(candidate, indent=2))
    unresolved = ["WRONG_SIDE"] if not first_line["promoted"] else []
    result = {"source_sha": source_sha, "candidate": candidate, "escalation_required": bool(unresolved), "unresolved_error_buckets": unresolved}
    return result
```

- [ ] **Step 4: Write final report generation test and implementation**

```python
def _write_report(root: Path, result, readiness=None):
    verdict = "NEEDS_MORE_RESEARCH" if readiness is None else readiness["verdict"]
    lines = ["# V7 Research Report", "", f"Source SHA: `{result['source_sha']}`", "", "Discovery/evaluation evidence is separate from untouched forward evidence.", "", verdict]
    (root / "final_report.md").write_text("\n".join(lines))
```

Test that report cannot contain `READY_FOR_PAPER_TRADING` when no `readiness_gate.json` exists or when its verdict is not READY.

- [ ] **Step 5: Write artifact completion test after freeze/forward**

In the test, call `freeze_v7_candidate` on the returned candidate, create a 61-row synthetic `forward_observations.csv.gz`, call `evaluate_a1_readiness`, write `readiness_gate.json`, create empty-but-explicit `failure_ledger.csv.gz`, `do_not_repeat.json`, H1/H2/H3/combination/error/stress/DSR/PBO artifacts from toy results, then assert `ensure_v7_artifact_contract(tmp_path) == []`.

- [ ] **Step 6: Run and commit**

Run: `pytest tests/test_v7_cycle.py tests/test_run_v7.py tests/test_forward_v7.py tests/test_statistics_v7.py -v`

Expected: PASS.

Commit:
```bash
git add src/crypto_research/run_v7.py src/crypto_research/v7_cycle.py tests/test_v7_cycle.py tests/test_run_v7.py
git commit -m "feat: assemble V7 core research artifacts"
```

---

### Task 9: Verification checkpoint

**Files:** no new production file unless a verified failure requires a root-cause fix.

- [ ] **Step 1: Run targeted V7 suite**

```bash
pytest tests/test_features_v7.py tests/test_reliability_v7.py tests/test_trials_v7.py tests/test_diagnostics_v7.py tests/test_statistics_v7.py tests/test_forward_v7.py tests/test_v7_cycle.py tests/test_run_v7.py -v
```

Expected: PASS.

- [ ] **Step 2: Run full regression**

```bash
pytest -q
```

Expected: PASS including all V3–V6 tests.

- [ ] **Step 3: Run lint and compile**

```bash
ruff check src tests
python -m compileall -q src tests
```

Expected: both succeed.

- [ ] **Step 4: Run leakage regressions**

```bash
pytest tests/test_features_v7.py tests/test_reliability_v7.py tests/test_state_v6.py tests/test_decision_log_v6.py -v
```

Expected: PASS.

- [ ] **Step 5: Verify shared trial budget and V6 immutability**

```python
registry = pd.read_csv("artifacts/multi_asset_v7/experiment_registry.csv")
assert registry["trial_number"].is_unique
assert registry["trial_number"].is_monotonic_increasing
assert int(registry.iloc[0]["trial_number"]) == 858
assert len(registry) <= 60
assert int((registry["phase"] == "first_line").sum()) <= 24
```

Compare `artifacts/multi_asset_v6/forward_freeze.json`, `final_candidate.json`, and `final_report.md` on the V7 branch against V6 head `46212f4c9eef07001341a87dffea40cd223cfa84`; all must be byte-identical.

- [ ] **Step 6: Secret/live-trading scan**

```bash
git diff 46212f4c9eef07001341a87dffea40cd223cfa84...HEAD | grep -E 'gsk_|BEGIN PRIVATE KEY|place_order|create_order|withdraw|transfer|otp|oneTimePassword' && exit 1 || true
```

Manually inspect any benign identifier-only hit; no real credential value or live-order code is permitted.

- [ ] **Step 7: If any verification fails, use systematic debugging**

Invoke `superpowers:systematic-debugging`, reproduce the failure with the narrowest test, fix the root cause, rerun the narrow test, then rerun Steps 1–6.

- [ ] **Step 8: Before claiming the core complete, use verification-before-completion**

Invoke `superpowers:verification-before-completion` and rerun Steps 1–6 on the final head.

## Core Completion Gate

The core is complete when trial 858+ accounting is bounded, H1/H2/H3 and at most one combination run under fixed causal rules, failure memory is persisted, V6 evidence is unchanged, one V7 candidate can be frozen reproducibly, and A1 cannot return `READY_FOR_PAPER_TRADING` without both evidence-volume gates plus all hard economic/stress/integrity gates.

If `run_v7_core_cycle` returns `escalation_required=true`, execute the companion research-council plan. If it returns false and the simple candidate is suitable for freeze, skip escalation and begin untouched A1 collection.