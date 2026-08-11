# V7 Research Council and Escalation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the bounded V7 escalation layer that converts unresolved first-line error buckets into auditable factor hypotheses, uses a structured Groq research council and append-only blackboard, admits factor families one at a time, allows one fixed nonlinear reliability challenger, and integrates MiroFish/OASIS only as an isolated event/scenario evidence sidecar.

**Architecture:** LLM agents are research-governance components, not traders. They communicate with typed evidence/hypothesis records, and deterministic Python validators decide whether a proposal may consume a performance trial. Factor families must prove causal availability and positive evaluation value independently before entering one fixed nonlinear reliability model. MiroFish/OASIS output is treated as event/narrative risk evidence and cannot create direct LONG/SHORT direction.

**Tech Stack:** Python 3, pandas, NumPy, existing scikit-learn dependency, Groq Python client/runtime model discovery, JSON/JSONL/CSV artifacts, standard-library `urllib.request` for an optional local scenario sidecar, pytest, Ruff.

## Global Constraints

- Execute this plan only when V7 core returns `escalation_required=true` and no valid V7 `forward_freeze.json` exists.
- Reuse the same `V7TrialRegistry` from the core plan. No separate ML, factor, or scenario performance registry is allowed.
- Total V7 performance-bearing configurations remain <=60. Since first-line cap is 24, escalation can consume at most 36 additional inspected performance configurations.
- LLM-only research proposals do not consume a performance trial until an approved backtest result is inspected, but every proposal is logged.
- Agent contexts must strip all forward, future, oracle, untouched-forward, secret, token, password, authorization, and API-key material.
- `GROQ_API_KEY` is read only from environment/secret storage. Its value is never printed, persisted, echoed into prompts, or committed.
- Agents may retrieve evidence, propose hypotheses, preserve dissent, audit methods, and construct experiment manifests. They may not generate executable BUY/SELL/LONG/SHORT orders or bypass deterministic promotion code.
- No order/cancel/withdraw/transfer/exchange-leverage tool is implemented or exposed.
- A factor is only observed until it passes the fixed admission rule defined below.
- A failed mechanism fingerprint in `do_not_repeat.json` may re-enter only when `materially_new_evidence=true` and the new evidence IDs differ from the previous record.
- The first nonlinear model is one fixed `HistGradientBoostingClassifier` configuration. No V7 hyperparameter search is allowed.
- MiroFish/OASIS is a scenario/narrative simulator in V7, not a native price or order-book forecasting engine.
- Scenario output can enter a strategy-performance trial only after a causal historical event study has at least 12 distinct events, at least 2 temporal evaluation folds, causal pre-event inputs, and positive incremental after-cost evidence.
- No council, ML, or scenario output can change a valid frozen V7 candidate. Only the core A1 gate can emit `READY_FOR_PAPER_TRADING`.

---

### Task 1: Append-only Research Blackboard and hypothesis governance

**Files:**
- Create: `src/crypto_research/research_blackboard_v7.py`
- Create: `src/crypto_research/hypotheses_v7.py`
- Test: `tests/test_research_blackboard_v7.py`
- Test: `tests/test_hypotheses_v7.py`

**Interfaces:**
- Consumes: `mechanism_fingerprint`, `reject_repeated_mechanism` from core `diagnostics_v7.py`.
- Produces: `EvidenceCard`, `ResearchHypothesis`, `ExperimentManifest`, append/load blackboard, `validate_hypothesis`, `build_experiment_manifest`.

- [ ] **Step 1: Write failing blackboard tests**

```python
# tests/test_research_blackboard_v7.py
import pytest

from crypto_research.research_blackboard_v7 import EvidenceCard, append_evidence_card, load_evidence_cards


def _card(card_id: str, claim: str, contradictory=()):
    return EvidenceCard(
        card_id=card_id,
        author_agent="evidence_scout",
        claim=claim,
        source_ids=("paper-1",),
        timestamp_utc="2026-08-11T04:00:00Z",
        data_cutoff_utc="2026-08-11T03:59:59Z",
        causal=True,
        target_error="WRONG_SIDE",
        expected_mechanism="conditional reliability",
        confidence=0.7,
        supporting_evidence=("support",),
        contradictory_evidence=tuple(contradictory),
        data_required=("causal_feature",),
        recommended_action="test one factor family",
    )


def test_evidence_card_rejects_out_of_range_confidence():
    with pytest.raises(ValueError, match="confidence"):
        EvidenceCard(card_id="x", author_agent="a", claim="c", source_ids=("s",), timestamp_utc="2026-08-11T04:00:00Z", data_cutoff_utc="2026-08-11T03:00:00Z", causal=True, target_error="WRONG_SIDE", expected_mechanism="m", confidence=1.5, supporting_evidence=(), contradictory_evidence=(), data_required=(), recommended_action="test")


def test_blackboard_preserves_support_and_dissent(tmp_path):
    path = tmp_path / "research_blackboard.jsonl"
    append_evidence_card(_card("c1", "factor may help"), path)
    append_evidence_card(_card("c2", "factor may fail", contradictory=("c1",)), path)
    cards = load_evidence_cards(path)
    assert [card.card_id for card in cards] == ["c1", "c2"]
    assert cards[1].contradictory_evidence == ("c1",)
```

- [ ] **Step 2: Run to verify RED**

Run: `pytest tests/test_research_blackboard_v7.py -v`

- [ ] **Step 3: Implement blackboard**

```python
# src/crypto_research/research_blackboard_v7.py
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class EvidenceCard:
    card_id: str
    author_agent: str
    claim: str
    source_ids: tuple[str, ...]
    timestamp_utc: str
    data_cutoff_utc: str
    causal: bool
    target_error: str
    expected_mechanism: str
    confidence: float
    supporting_evidence: tuple[str, ...]
    contradictory_evidence: tuple[str, ...]
    data_required: tuple[str, ...]
    recommended_action: str

    def __post_init__(self):
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        for field_name in ("card_id", "author_agent", "claim", "target_error", "expected_mechanism"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must be non-empty")


def append_evidence_card(card: EvidenceCard, path: str | Path) -> None:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(card), sort_keys=True) + "\n")


def load_evidence_cards(path: str | Path) -> list[EvidenceCard]:
    target = Path(path)
    if not target.exists(): return []
    cards = []
    for line in target.read_text().splitlines():
        if line.strip():
            payload = json.loads(line)
            for key in ("source_ids", "supporting_evidence", "contradictory_evidence", "data_required"):
                payload[key] = tuple(payload[key])
            cards.append(EvidenceCard(**payload))
    return cards
```

- [ ] **Step 4: Write failing hypothesis tests**

```python
# tests/test_hypotheses_v7.py
import pytest

from crypto_research.hypotheses_v7 import ResearchHypothesis, build_experiment_manifest, validate_hypothesis


def _hypothesis(single_change="veto exposure increase when derivatives crowding conflicts with H12"):
    return ResearchHypothesis(
        hypothesis_id="h-derivatives-1", target_error="WRONG_SIDE", observation="wrong-side clusters in crowded states",
        causal_inputs=("funding", "open_interest_change"), expected_mechanism="crowding reduces H12 reliability",
        single_change=single_change, expected_effect="reduce wrong-side loss bps", cost_risk="may skip correct trades",
        invalidation_condition="evaluation net bps <= control or WRONG_SIDE does not improve",
        required_test="walk-forward 10bps, 20bps, plus1h", factor_family="derivatives",
        source_ids=("paper-derivatives-1",), materially_new_evidence=False,
    )


def test_direct_direction_hypothesis_is_rejected():
    bad = _hypothesis("go short BTC when funding is high")
    with pytest.raises(ValueError, match="direct direction"):
        validate_hypothesis(bad, blocked_fingerprints=set())


def test_manifest_has_research_only_actions():
    good = validate_hypothesis(_hypothesis(), blocked_fingerprints=set())
    manifest = build_experiment_manifest(good, train_window=("2024-01-01", "2024-12-31"), evaluation_window=("2025-01-01", "2025-06-30"))
    assert set(manifest.allowed_actions) <= {"veto_entry", "veto_increase", "scale_increase", "reliability_score", "risk_context", "event_risk_context"}
```

- [ ] **Step 5: Implement hypothesis governance**

```python
# src/crypto_research/hypotheses_v7.py
from __future__ import annotations

from dataclasses import dataclass

from crypto_research.diagnostics_v7 import mechanism_fingerprint, reject_repeated_mechanism

_ALLOWED_ACTIONS = ("veto_entry", "veto_increase", "scale_increase", "reliability_score", "risk_context", "event_risk_context")
_BLOCKED_TEXT = ("go long", "go short", "buy btc", "sell btc", "buy eth", "sell eth", "direct directional alpha", "flip h12")


@dataclass(frozen=True)
class ResearchHypothesis:
    hypothesis_id: str; target_error: str; observation: str; causal_inputs: tuple[str, ...]; expected_mechanism: str
    single_change: str; expected_effect: str; cost_risk: str; invalidation_condition: str; required_test: str
    factor_family: str; source_ids: tuple[str, ...]; materially_new_evidence: bool


@dataclass(frozen=True)
class ExperimentManifest:
    hypothesis_id: str; trial_phase: str; causal_inputs: tuple[str, ...]; train_window: tuple[str, str]
    evaluation_window: tuple[str, str]; metrics: tuple[str, ...]; cost_bps: tuple[float, ...]
    delay_minutes: tuple[int, ...]; allowed_actions: tuple[str, ...]


def validate_hypothesis(h: ResearchHypothesis, *, blocked_fingerprints: set[str]):
    text = " ".join((h.observation, h.expected_mechanism, h.single_change, h.expected_effect)).lower()
    if any(token in text for token in _BLOCKED_TEXT): raise ValueError("direct direction proposal is forbidden")
    if not h.invalidation_condition.strip() or not h.causal_inputs or not h.source_ids: raise ValueError("hypothesis lacks causal evidence or invalidation")
    fingerprint = mechanism_fingerprint(h.target_error, h.expected_mechanism, list(h.causal_inputs), h.single_change)
    reject_repeated_mechanism(fingerprint, blocked_fingerprints, materially_new_evidence=h.materially_new_evidence)
    return h


def build_experiment_manifest(h: ResearchHypothesis, *, train_window, evaluation_window):
    return ExperimentManifest(h.hypothesis_id, "escalation", h.causal_inputs, train_window, evaluation_window, ("net_return", "sharpe", "max_drawdown", h.target_error), (10.0, 20.0), (0, 60), _ALLOWED_ACTIONS)
```

- [ ] **Step 6: Run and commit**

Run: `pytest tests/test_research_blackboard_v7.py tests/test_hypotheses_v7.py -v`

Commit:
```bash
git add src/crypto_research/research_blackboard_v7.py src/crypto_research/hypotheses_v7.py tests/test_research_blackboard_v7.py tests/test_hypotheses_v7.py
git commit -m "feat: add V7 research blackboard and hypothesis governance"
```

---

### Task 2: Local V7 research skills

**Files:**
- Create: `skills/v7-research-scientist/SKILL.md`
- Create: `skills/v7-methodology-auditor/SKILL.md`
- Test: `tests/test_hypotheses_v7.py`

**Interfaces:**
- Research Scientist emits only `ResearchHypothesis` fields.
- Methodology Auditor emits `decision`, `risks`, `causal_findings`, `cost_findings`, `duplicate_mechanism`, `required_controls`.

- [ ] **Step 1: Invoke the required skill-authoring workflow**

Read and follow `superpowers:writing-skills` before creating either `SKILL.md`.

- [ ] **Step 2: Add static skill-content tests**

```python
from pathlib import Path


def test_v7_local_skills_encode_research_safety_rules():
    paths = [Path("skills/v7-research-scientist/SKILL.md"), Path("skills/v7-methodology-auditor/SKILL.md")]
    required = ("research/backtest only", "no direct long/short", "future/oracle/forward", "one mechanism", "invalidation", "transaction cost", "do-not-repeat")
    for path in paths:
        text = path.read_text().lower()
        for phrase in required:
            assert phrase in text
```

- [ ] **Step 3: Write the Research Scientist skill**

```markdown
---
name: v7-research-scientist
description: Convert one unresolved V7 error/evidence gap into one falsifiable causal research hypothesis.
---

# V7 Research Scientist

Research/backtest only. No direct LONG/SHORT order generation.
Never consume future/oracle/forward evidence when formulating a V7 hypothesis.
Use one mechanism per hypothesis and include a concrete invalidation condition.
Account for transaction cost and lost-correct-trade risk.
Check do-not-repeat before proposing a mechanism.

Process:
1. Read exactly one unresolved error bucket.
2. Read causal blackboard evidence and contradictory evidence.
3. Read do-not-repeat fingerprints.
4. Prefer no hypothesis over a duplicate or weak mechanism.
5. Emit only the ResearchHypothesis fields defined by V7.
```

- [ ] **Step 4: Write the Methodology Auditor skill**

```markdown
---
name: v7-methodology-auditor
description: Red-team a proposed V7 quantitative research hypothesis before it can consume a performance trial.
---

# V7 Methodology Auditor

Research/backtest only. No direct LONG/SHORT order generation.
Reject future/oracle/forward leakage, duplicate do-not-repeat mechanisms, unbounded parameter search, reverse causality, unrealistic execution, and missing transaction cost.
Require one mechanism and an explicit invalidation condition.
Preserve dissent instead of rewriting it away.

Return fields: decision, risks, causal_findings, cost_findings, duplicate_mechanism, required_controls.
```

- [ ] **Step 5: Run and commit**

Run: `pytest tests/test_hypotheses_v7.py -v`

Commit:
```bash
git add skills/v7-research-scientist/SKILL.md skills/v7-methodology-auditor/SKILL.md tests/test_hypotheses_v7.py
git commit -m "docs: add V7 research scientist and auditor skills"
```

---

### Task 3: Structured Groq research council

**Files:**
- Create: `src/crypto_research/groq_v7.py`
- Test: `tests/test_groq_v7.py`

**Interfaces:**
- Consumes: runtime Groq client; `ResearchHypothesis`; blackboard evidence.
- Produces: `sanitize_v7_context`, `select_v7_role_models`, `run_v7_research_council`.

- [ ] **Step 1: Write failing sanitization/model tests**

```python
# tests/test_groq_v7.py
from crypto_research.groq_v7 import sanitize_v7_context, select_v7_role_models


def test_context_strips_forward_oracle_and_secret_fields():
    clean = sanitize_v7_context({"api_key": "secret", "forward_results": {"net": 9}, "oracle_direction": 1, "future_return": 0.5, "error_ledger": {"WRONG_SIDE": 10}})
    assert clean == {"error_ledger": {"WRONG_SIDE": 10}}


def test_role_model_selection_uses_discovered_fallbacks():
    ids = {"qwen/qwen3.6-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"}
    roles = select_v7_role_models(ids)
    assert roles == {"evidence_scout": "qwen/qwen3.6-27b", "error_scientist": "qwen/qwen3.6-27b", "methodology_auditor": "openai/gpt-oss-120b", "research_judge": "openai/gpt-oss-20b"}
```

- [ ] **Step 2: Run to verify RED**

Run: `pytest tests/test_groq_v7.py -v`

- [ ] **Step 3: Implement sanitization and model selection**

```python
# src/crypto_research/groq_v7.py
from __future__ import annotations

import json
from typing import Any

_BLOCKED_KEYS = ("forward", "future", "oracle", "secret", "token", "password", "authorization", "api_key", "apikey")


def sanitize_v7_context(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_v7_context(item) for key, item in value.items() if not any(blocked in str(key).lower() for blocked in _BLOCKED_KEYS)}
    if isinstance(value, list): return [sanitize_v7_context(item) for item in value]
    if isinstance(value, tuple): return tuple(sanitize_v7_context(item) for item in value)
    return value


def select_v7_role_models(ids: set[str]) -> dict[str, str]:
    if not ids: raise ValueError("Groq model list is empty")
    fallback = sorted(ids)[0]
    qwen = "qwen/qwen3.6-27b" if "qwen/qwen3.6-27b" in ids else next((model for model in sorted(ids) if "qwen" in model.lower()), fallback)
    auditor = "openai/gpt-oss-120b" if "openai/gpt-oss-120b" in ids else ("openai/gpt-oss-20b" if "openai/gpt-oss-20b" in ids else qwen)
    judge = "openai/gpt-oss-20b" if "openai/gpt-oss-20b" in ids else auditor
    return {"evidence_scout": qwen, "error_scientist": qwen, "methodology_auditor": auditor, "research_judge": judge}
```

- [ ] **Step 4: Add fake-client council test**

```python

def test_council_preserves_audit_and_dissent(fake_groq_client):
    result = run_v7_research_council({"error_ledger": {"WRONG_SIDE": 10}, "dissent": ["factor may be reverse-causal"]}, client=fake_groq_client)
    assert "audit" in result
    assert "dissent" in result["sanitized_context"]
    assert result["role_models"]
```

The fake client implements `models.list()` and `chat.completions.create()` with deterministic JSON responses for all four roles. Include one scout proposal that says `go short BTC`; the council must expose it under `locally_rejected` even if a fake auditor marks it acceptable.

- [ ] **Step 5: Implement council orchestration**

```python

def _chat_json(client, *, model: str, role: str, context: dict[str, Any]) -> dict[str, Any]:
    response = client.chat.completions.create(model=model, temperature=0, messages=[{"role": "system", "content": "V7 quantitative research only. Never produce direct LONG/SHORT trades. Return JSON only."}, {"role": "user", "content": json.dumps({"role": role, "context": context}, default=str)}], response_format={"type": "json_object"})
    return json.loads(response.choices[0].message.content or "{}")


def run_v7_research_council(context: dict[str, Any], *, client: Any) -> dict[str, Any]:
    ids = {str(item.id) for item in client.models.list().data if getattr(item, "id", None)}
    roles = select_v7_role_models(ids); clean = sanitize_v7_context(context)
    evidence = _chat_json(client, model=roles["evidence_scout"], role="evidence_scout", context=clean)
    hypotheses = _chat_json(client, model=roles["error_scientist"], role="error_scientist", context={"context": clean, "evidence": evidence})
    locally_rejected = []
    for item in hypotheses.get("hypotheses", []):
        text = json.dumps(item).lower()
        if any(term in text for term in ("go long", "go short", "buy btc", "sell btc", "flip h12")):
            locally_rejected.append({"hypothesis": item, "reason": "direct direction forbidden"})
    audit = _chat_json(client, model=roles["methodology_auditor"], role="methodology_auditor", context={"context": clean, "evidence": evidence, "hypotheses": hypotheses, "locally_rejected": locally_rejected})
    judge = _chat_json(client, model=roles["research_judge"], role="research_judge", context={"context": clean, "audit": audit, "locally_rejected": locally_rejected})
    return {"sanitized_context": clean, "role_models": roles, "evidence": evidence, "hypotheses": hypotheses, "locally_rejected": locally_rejected, "audit": audit, "judge": judge}
```

- [ ] **Step 6: Run and commit**

Run: `pytest tests/test_groq_v7.py -v`

Commit:
```bash
git add src/crypto_research/groq_v7.py tests/test_groq_v7.py
git commit -m "feat: add structured Groq V7 research council"
```

---

### Task 4: Factor Observatory with fixed admission rules

**Files:**
- Create: `src/crypto_research/factor_observatory_v7.py`
- Test: `tests/test_factor_observatory_v7.py`

**Interfaces:**
- Produces: `FactorEvidence`, `factor_admission_reasons`, `admit_factor`, `write_factor_observatory`.

**Fixed admission rule:** factor is admitted only if `causal_available=True`, `coverage_fraction >= 0.80`, `source_quality` is one of `official`, `peer_reviewed`, `preprint_with_method`, `verified_repository`, `evaluation_fold_count >= 2`, `incremental_net_bps > 0`, and for `attention_sentiment`, `reverse_causality_checked=True`.

- [ ] **Step 1: Write failing admission tests**

```python
# tests/test_factor_observatory_v7.py
from crypto_research.factor_observatory_v7 import FactorEvidence, admit_factor, factor_admission_reasons


def _evidence(**changes):
    values = dict(factor_family="derivatives", feature_name="funding_oi_crowding", source_ids=("paper-1",), coverage_fraction=0.95, causal_available=True, source_quality="preprint_with_method", stability_score=0.7, target_error="WRONG_SIDE", association_value=0.1, incremental_net_bps=3.0, incremental_sharpe_delta=0.05, turnover_delta=-0.1, evaluation_fold_count=3, reverse_causality_checked=True, status="EVALUATED")
    values.update(changes); return FactorEvidence(**values)


def test_factor_admission_uses_fixed_rules():
    assert admit_factor(_evidence())
    assert not admit_factor(_evidence(coverage_fraction=0.79))
    assert not admit_factor(_evidence(causal_available=False))
    assert not admit_factor(_evidence(source_quality="unverified_blog_only"))
    assert not admit_factor(_evidence(evaluation_fold_count=1))
    assert not admit_factor(_evidence(incremental_net_bps=0.0))


def test_sentiment_requires_reverse_causality_check():
    item = _evidence(factor_family="attention_sentiment", reverse_causality_checked=False)
    assert not admit_factor(item)
    assert "reverse_causality" in " ".join(factor_admission_reasons(item))
```

- [ ] **Step 2: Run to verify RED**

Run: `pytest tests/test_factor_observatory_v7.py -v`

- [ ] **Step 3: Implement fixed admission**

```python
# src/crypto_research/factor_observatory_v7.py
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

_ALLOWED_SOURCE_QUALITY = {"official", "peer_reviewed", "preprint_with_method", "verified_repository"}


@dataclass(frozen=True)
class FactorEvidence:
    factor_family: str; feature_name: str; source_ids: tuple[str, ...]; coverage_fraction: float
    causal_available: bool; source_quality: str; stability_score: float; target_error: str
    association_value: float; incremental_net_bps: float; incremental_sharpe_delta: float
    turnover_delta: float; evaluation_fold_count: int; reverse_causality_checked: bool; status: str


def factor_admission_reasons(evidence: FactorEvidence) -> list[str]:
    reasons = []
    if not evidence.causal_available: reasons.append("causal_available_false")
    if evidence.coverage_fraction < 0.80: reasons.append("coverage_below_0.80")
    if evidence.source_quality not in _ALLOWED_SOURCE_QUALITY: reasons.append("source_quality_rejected")
    if evidence.evaluation_fold_count < 2: reasons.append("fewer_than_two_evaluation_folds")
    if evidence.incremental_net_bps <= 0.0: reasons.append("incremental_net_bps_nonpositive")
    if evidence.factor_family == "attention_sentiment" and not evidence.reverse_causality_checked: reasons.append("reverse_causality_not_checked")
    return reasons


def admit_factor(evidence: FactorEvidence) -> bool:
    return not factor_admission_reasons(evidence)


def write_factor_observatory(rows: list[FactorEvidence], path: str | Path) -> Path:
    payload = [{**asdict(row), "admitted": admit_factor(row), "rejection_reasons": factor_admission_reasons(row)} for row in rows]
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps({"factors": payload}, indent=2)); return target
```

- [ ] **Step 4: Run and commit**

Run: `pytest tests/test_factor_observatory_v7.py -v`

Commit:
```bash
git add src/crypto_research/factor_observatory_v7.py tests/test_factor_observatory_v7.py
git commit -m "feat: add V7 factor observatory admission gates"
```

---

### Task 5: Bounded research event loop

**Files:**
- Create: `src/crypto_research/run_v7_research.py`
- Test: `tests/test_run_v7_research.py`

**Interfaces:**
- Consumes: core `V7TrialRegistry`, failure memory, Tasks 1–4, callback `backtest_runner(manifest, hypothesis) -> dict`.
- Produces: `run_factor_family_challenge`, `run_research_event_loop`.

- [ ] **Step 1: Write failing trigger/budget tests**

```python
# tests/test_run_v7_research.py
from crypto_research.run_v7_research import run_research_event_loop


def test_empty_trigger_does_not_call_groq(tmp_path, fake_groq_client, failing_backtest_runner):
    result = run_research_event_loop({"unresolved_error_buckets": [], "new_evidence": [], "failed_experiments": []}, client=fake_groq_client, backtest_runner=failing_backtest_runner, artifact_root=tmp_path)
    assert result["status"] == "NO_RESEARCH_TRIGGER"


def test_budget_exhaustion_blocks_backtest(tmp_path, fake_groq_client, failing_backtest_runner):
    registry = V7TrialRegistry(tmp_path / "experiment_registry.csv")
    for index in range(60): registry.record("X", f"x-{index}", "INSPECTED", phase="escalation")
    registry.to_csv()
    result = run_research_event_loop({"unresolved_error_buckets": ["WRONG_SIDE"]}, client=fake_groq_client, backtest_runner=failing_backtest_runner, artifact_root=tmp_path)
    assert result["status"] == "V7_TRIAL_BUDGET_EXHAUSTED"
```

- [ ] **Step 2: Run to verify RED**

Run: `pytest tests/test_run_v7_research.py -v`

- [ ] **Step 3: Implement trigger and budget guards**

```python
# src/crypto_research/run_v7_research.py
from __future__ import annotations

import json
from pathlib import Path

from crypto_research.groq_v7 import run_v7_research_council
from crypto_research.trials_v7 import V7TrialRegistry


def _has_trigger(context):
    return bool(context.get("unresolved_error_buckets") or context.get("new_evidence") or context.get("failed_experiments") or context.get("evidence_gap"))


def run_research_event_loop(context, *, client, backtest_runner, artifact_root):
    root = Path(artifact_root); registry = V7TrialRegistry(root / "experiment_registry.csv")
    if not _has_trigger(context): return {"status": "NO_RESEARCH_TRIGGER"}
    if registry.total_count >= 917: return {"status": "V7_TRIAL_BUDGET_EXHAUSTED"}
    council = run_v7_research_council(context, client=client)
    with (root / "agent_research_log.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(council, default=str, sort_keys=True) + "\n")
    return {"status": "COUNCIL_COMPLETED", "council": council, "trial_count": registry.total_count}
```

- [ ] **Step 4: Add one-family challenge test and implementation**

```python

def run_factor_family_challenge(context, hypothesis, *, registry, backtest_runner, artifact_root):
    manifest = build_experiment_manifest(hypothesis, train_window=context["train_window"], evaluation_window=context["evaluation_window"])
    result = backtest_runner(manifest, hypothesis)
    registry.record("F", hypothesis.hypothesis_id, "INSPECTED", phase="escalation", config={"factor_family": hypothesis.factor_family, "causal_inputs": list(hypothesis.causal_inputs)}, metrics=result)
    registry.to_csv()
    return result
```

Test with a callback counter; one approved `derivatives` hypothesis must invoke the backtest exactly once and append exactly one shared-registry row.

- [ ] **Step 5: Add append-only hypothesis log**

Every raw and locally rejected proposal from the council is appended to `hypothesis_registry.jsonl` before any performance backtest. Include `status` values `PROPOSED`, `REJECTED_LOCAL`, `REJECTED_AUDITOR`, or `APPROVED_FOR_ONE_TRIAL`.

- [ ] **Step 6: Run and commit**

Run: `pytest tests/test_run_v7_research.py tests/test_groq_v7.py tests/test_factor_observatory_v7.py -v`

Commit:
```bash
git add src/crypto_research/run_v7_research.py tests/test_run_v7_research.py
git commit -m "feat: add bounded V7 research event loop"
```

---

### Task 6: One fixed nonlinear reliability challenger

**Files:**
- Create: `src/crypto_research/reliability_ml_v7.py`
- Modify: `src/crypto_research/run_v7_research.py`
- Test: `tests/test_reliability_ml_v7.py`
- Test: `tests/test_run_v7_research.py`

**Interfaces:**
- Produces: `ReliabilityModelConfig`, `fit_reliability_model`, `predict_reliability`, `apply_reliability_probability`, `run_nonlinear_challenger`.

- [ ] **Step 1: Write failing fixed-model tests**

```python
# tests/test_reliability_ml_v7.py
import numpy as np
import pandas as pd

from crypto_research.reliability_ml_v7 import ReliabilityModelConfig, apply_reliability_probability, fit_reliability_model, predict_reliability


def test_probability_can_only_veto_or_keep_h12_target():
    assert apply_reliability_probability(0.40, previous_weight=0.0, base_target_weight=0.25) == 0.0
    assert apply_reliability_probability(0.60, previous_weight=0.0, base_target_weight=0.25) == 0.25
    assert apply_reliability_probability(0.40, previous_weight=0.25, base_target_weight=0.10) == 0.10


def test_fixed_model_is_deterministic():
    frame = pd.DataFrame({"f1": [0, 1, 0, 1, 0, 1], "f2": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "reliable_label": [0, 1, 0, 1, 0, 1]})
    config = ReliabilityModelConfig(feature_names=("f1", "f2"))
    first = predict_reliability(fit_reliability_model(frame, config), frame, config)
    second = predict_reliability(fit_reliability_model(frame, config), frame, config)
    np.testing.assert_allclose(first, second)
```

- [ ] **Step 2: Run to verify RED**

Run: `pytest tests/test_reliability_ml_v7.py -v`

- [ ] **Step 3: Implement fixed model and 0.50 veto rule**

```python
# src/crypto_research/reliability_ml_v7.py
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier


@dataclass(frozen=True)
class ReliabilityModelConfig:
    feature_names: tuple[str, ...]
    max_iter: int = 100
    max_leaf_nodes: int = 15
    learning_rate: float = 0.05
    random_state: int = 42


def fit_reliability_model(train: pd.DataFrame, config: ReliabilityModelConfig):
    model = HistGradientBoostingClassifier(max_iter=config.max_iter, max_leaf_nodes=config.max_leaf_nodes, learning_rate=config.learning_rate, random_state=config.random_state)
    model.fit(train.loc[:, list(config.feature_names)], train["reliable_label"].astype(int))
    return model


def predict_reliability(model, frame: pd.DataFrame, config: ReliabilityModelConfig) -> np.ndarray:
    return model.predict_proba(frame.loc[:, list(config.feature_names)])[:, 1]


def apply_reliability_probability(probability: float, *, previous_weight: float, base_target_weight: float) -> float:
    previous = float(previous_weight); base = float(base_target_weight)
    if float(probability) < 0.50 and abs(base) > abs(previous) + 1e-12:
        return previous if abs(previous) > 1e-12 else 0.0
    return base
```

- [ ] **Step 4: Add admission-only feature test**

`run_nonlinear_challenger` receives an explicit `admitted_features: set[str]` and raises `ValueError` if any `config.feature_names` is absent. It also returns `NOT_RUN_FEWER_THAN_TWO_ADMITTED_FEATURES` when fewer than two features are admitted.

```python

def run_nonlinear_challenger(train, evaluation, *, config, admitted_features, registry, strategy_backtest_runner):
    if len(admitted_features) < 2: return {"status": "NOT_RUN_FEWER_THAN_TWO_ADMITTED_FEATURES"}
    missing = set(config.feature_names).difference(admitted_features)
    if missing: raise ValueError(f"ML features not admitted: {sorted(missing)}")
    model = fit_reliability_model(train, config)
    probabilities = predict_reliability(model, evaluation, config)
    result = strategy_backtest_runner(evaluation, probabilities)
    registry.record("ML", "fixed_hist_gradient_boosting_reliability", "INSPECTED", phase="escalation", config=config.__dict__, metrics=result)
    registry.to_csv(); return {"status": "INSPECTED", "metrics": result}
```

Exactly one fixed ML strategy configuration may be inspected in V7; no hyperparameter loop or threshold sweep is added.

- [ ] **Step 5: Run and commit**

Run: `pytest tests/test_reliability_ml_v7.py tests/test_run_v7_research.py -v`

Commit:
```bash
git add src/crypto_research/reliability_ml_v7.py src/crypto_research/run_v7_research.py tests/test_reliability_ml_v7.py tests/test_run_v7_research.py
git commit -m "feat: add fixed nonlinear V7 reliability challenger"
```

---

### Task 7: Isolated MiroFish/OASIS scenario sidecar and event-study gate

**Files:**
- Create: `src/crypto_research/scenario_v7.py`
- Modify: `src/crypto_research/factor_observatory_v7.py`
- Test: `tests/test_scenario_v7.py`
- Test: `tests/test_factor_observatory_v7.py`

**Interfaces:**
- Produces: `ScenarioRequest`, `ScenarioResult`, `DisabledScenarioSimulator`, `MiroFishSidecarClient`, `build_scenario_event_study`.

- [ ] **Step 1: Write failing scenario schema tests**

```python
# tests/test_scenario_v7.py
from dataclasses import fields
import pytest

from crypto_research.scenario_v7 import ScenarioResult


def test_scenario_result_has_no_direct_trade_field():
    names = {item.name.lower() for item in fields(ScenarioResult)}
    assert not names & {"side", "position", "buy", "sell", "long", "short"}


def test_scenario_result_validates_ranges():
    with pytest.raises(ValueError, match="confidence"):
        ScenarioResult(event_id="e1", consensus_strength=0.5, scenario_disagreement=0.5, tail_risk_bucket="high", liquidity_stress_bucket="high", narrative_polarity=0.0, confidence=1.2)
```

- [ ] **Step 2: Run to verify RED**

Run: `pytest tests/test_scenario_v7.py -v`

- [ ] **Step 3: Implement strict sidecar schema and disabled default**

```python
# src/crypto_research/scenario_v7.py
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
import urllib.request

import pandas as pd

_BUCKETS = {"low", "medium", "high", "extreme"}


@dataclass(frozen=True)
class ScenarioRequest:
    event_id: str; event_timestamp_utc: str; event_text: str; causal_context: dict[str, object]; participant_roles: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioResult:
    event_id: str; consensus_strength: float; scenario_disagreement: float; tail_risk_bucket: str
    liquidity_stress_bucket: str; narrative_polarity: float; confidence: float
    source: str = "MIROFISH_OASIS_SIDECAR"

    def __post_init__(self):
        if not 0 <= self.consensus_strength <= 1 or not 0 <= self.scenario_disagreement <= 1: raise ValueError("scenario probability field out of range")
        if not 0 <= self.confidence <= 1: raise ValueError("confidence out of range")
        if not -1 <= self.narrative_polarity <= 1: raise ValueError("narrative_polarity out of range")
        if self.tail_risk_bucket not in _BUCKETS or self.liquidity_stress_bucket not in _BUCKETS: raise ValueError("invalid risk bucket")


class DisabledScenarioSimulator:
    def run(self, request: ScenarioRequest):
        return {"status": "SCENARIO_SIMULATOR_NOT_CONFIGURED", "event_id": request.event_id}


class MiroFishSidecarClient:
    def __init__(self, endpoint: str, *, timeout_seconds: float = 30.0): self.endpoint = endpoint; self.timeout_seconds = timeout_seconds
    def run(self, request: ScenarioRequest) -> ScenarioResult:
        body = json.dumps(asdict(request), sort_keys=True).encode(); http = urllib.request.Request(self.endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(http, timeout=self.timeout_seconds) as response: payload = json.loads(response.read().decode())
        forbidden = {"side", "position", "buy", "sell", "long", "short"}.intersection(key.lower() for key in payload)
        if forbidden: raise ValueError(f"scenario sidecar returned forbidden direction fields: {sorted(forbidden)}")
        allowed = {item.name for item in fields(ScenarioResult)}
        extra = set(payload).difference(allowed)
        if extra: raise ValueError(f"scenario sidecar returned extra fields: {sorted(extra)}")
        return ScenarioResult(**payload)


def scenario_simulator_from_env():
    endpoint = os.environ.get("V7_SCENARIO_SIDECAR_URL", "").strip()
    return MiroFishSidecarClient(endpoint) if endpoint else DisabledScenarioSimulator()
```

Add `from dataclasses import fields` to the production imports.

- [ ] **Step 4: Write exact event-study minimum-evidence test**

```python

def test_scenario_event_study_requires_12_events_and_two_folds():
    events = pd.DataFrame({"event_id": [f"e{i}" for i in range(11)], "event_timestamp": pd.date_range("2024-01-01", periods=11, freq="30D", tz="UTC"), "fold": [i % 2 for i in range(11)]})
    scenario = pd.DataFrame({"event_id": events["event_id"], "scenario_disagreement": [0.5] * 11, "confidence": [0.7] * 11})
    outcomes = pd.DataFrame({"event_id": events["event_id"], "incremental_net_bps": [1.0] * 11})
    result = build_scenario_event_study(events, scenario, outcomes)
    assert result["status"] == "INSUFFICIENT_EVENT_EVIDENCE"
```

- [ ] **Step 5: Implement causal event-study gate**

```python

def build_scenario_event_study(events: pd.DataFrame, scenario_results: pd.DataFrame, outcomes: pd.DataFrame):
    merged = events.merge(scenario_results, on="event_id", validate="one_to_one").merge(outcomes, on="event_id", validate="one_to_one")
    distinct_events = int(merged["event_id"].nunique()); folds = int(merged["fold"].nunique())
    mean_incremental = float(pd.to_numeric(merged["incremental_net_bps"], errors="coerce").mean())
    enough = distinct_events >= 12 and folds >= 2
    return {"status": "ADMITTED_FOR_FACTOR_REVIEW" if enough and mean_incremental > 0 else ("INSUFFICIENT_EVENT_EVIDENCE" if not enough else "NO_POSITIVE_INCREMENTAL_VALUE"), "distinct_events": distinct_events, "evaluation_fold_count": folds, "incremental_net_bps": mean_incremental}
```

Use only event text/context timestamped at or before `event_timestamp` as sidecar input. Later price/PnL fields exist only in `outcomes` and are never sent to the simulator.

- [ ] **Step 6: Feed scenario evidence through normal Factor Observatory**

Construct `FactorEvidence(factor_family="scenario_swarm", ...)` only when event-study status is `ADMITTED_FOR_FACTOR_REVIEW`; it still must pass the normal 0.80 coverage, two-fold, source-quality, and positive-net rules before entering ML or a separate risk-context performance trial.

- [ ] **Step 7: Run and commit**

Run: `pytest tests/test_scenario_v7.py tests/test_factor_observatory_v7.py -v`

Commit:
```bash
git add src/crypto_research/scenario_v7.py src/crypto_research/factor_observatory_v7.py tests/test_scenario_v7.py tests/test_factor_observatory_v7.py
git commit -m "feat: add evidence-gated V7 scenario swarm sidecar"
```

---

### Task 8: Pre-freeze integration and full verification

**Files:**
- Modify: `src/crypto_research/run_v7.py`
- Modify: `src/crypto_research/v7_cycle.py`
- Modify: `src/crypto_research/run_v7_research.py`
- Test: `tests/test_run_v7_research.py`
- Test: `tests/test_forward_v7.py`

**Interfaces:**
- Produces: `maybe_run_v7_escalation(core_result, *, artifact_root, client, backtest_runner)`.

- [ ] **Step 1: Write freeze-block and simple-first skip tests**

```python

def test_valid_freeze_blocks_escalation(tmp_path, fake_groq_client, failing_backtest_runner):
    freeze_v7_candidate({"name": "frozen"}, artifact_root=tmp_path, timestamp="2026-08-11T04:00:00Z", total_trial_count=861, source_sha="c" * 40, causal_schema_version="v7-causal-1")
    result = maybe_run_v7_escalation({"escalation_required": True}, artifact_root=tmp_path, client=fake_groq_client, backtest_runner=failing_backtest_runner)
    assert result["status"] == "V7_FROZEN_NO_RETUNING"


def test_simple_candidate_skips_escalation(tmp_path, fake_groq_client, failing_backtest_runner):
    result = maybe_run_v7_escalation({"escalation_required": False}, artifact_root=tmp_path, client=fake_groq_client, backtest_runner=failing_backtest_runner)
    assert result["status"] == "SIMPLE_FIRST_NO_ESCALATION"
```

- [ ] **Step 2: Implement pre-freeze guard**

```python
# add to src/crypto_research/run_v7_research.py
from crypto_research.forward_v7 import verify_v7_freeze


def maybe_run_v7_escalation(core_result, *, artifact_root, client, backtest_runner):
    root = Path(artifact_root); freeze_path = root / "forward_freeze.json"
    if freeze_path.exists() and verify_v7_freeze(freeze_path): return {"status": "V7_FROZEN_NO_RETUNING"}
    if not core_result.get("escalation_required", False): return {"status": "SIMPLE_FIRST_NO_ESCALATION"}
    context = {"unresolved_error_buckets": core_result.get("unresolved_error_buckets", []), "evidence_gap": "directional reliability"}
    return run_research_event_loop(context, client=client, backtest_runner=backtest_runner, artifact_root=root)
```

- [ ] **Step 3: Run targeted council/escalation suite**

```bash
pytest tests/test_research_blackboard_v7.py tests/test_hypotheses_v7.py tests/test_groq_v7.py tests/test_factor_observatory_v7.py tests/test_reliability_ml_v7.py tests/test_scenario_v7.py tests/test_run_v7_research.py tests/test_forward_v7.py -v
```

Expected: PASS.

- [ ] **Step 4: Run full project regression/lint/compile**

```bash
pytest -q
ruff check src tests
python -m compileall -q src tests
```

Expected: all succeed.

- [ ] **Step 5: Verify safety invariants with tests and diff scan**

```bash
git diff 46212f4c9eef07001341a87dffea40cd223cfa84...HEAD | grep -E 'gsk_|BEGIN PRIVATE KEY|place_order|create_order|cancel_order|withdraw|transfer|otp|oneTimePassword' && exit 1 || true
```

Additionally assert in tests that sanitized Groq context excludes forward/future/oracle/secret fields, direct-direction hypotheses are locally rejected, dissent cards survive, repeated mechanisms are blocked, valid freeze blocks all new trials, and scenario result schema has no direction fields.

- [ ] **Step 6: Verify one shared trial registry**

```python
registry = pd.read_csv("artifacts/multi_asset_v7/experiment_registry.csv")
assert registry["trial_number"].is_unique
assert registry["trial_number"].is_monotonic_increasing
assert int(registry.iloc[0]["trial_number"]) == 858
assert len(registry) <= 60
assert not Path("artifacts/multi_asset_v7/ml_trial_registry.csv").exists()
assert not Path("artifacts/multi_asset_v7/scenario_trial_registry.csv").exists()
```

- [ ] **Step 7: If any failure appears, use systematic debugging**

Invoke `superpowers:systematic-debugging`, reproduce the narrow failure, fix root cause, and rerun Steps 3–6.

- [ ] **Step 8: Before declaring escalation complete, use verification-before-completion**

Invoke `superpowers:verification-before-completion` and rerun Steps 3–6 on the final head.

## Escalation Completion Gate

Escalation is complete when agent communication is typed and append-only, factor families are admitted under fixed rules one at a time, the shared <=60 trial budget is enforced, at most one fixed nonlinear reliability challenger can run after factor admission, MiroFish/OASIS is isolated behind an event-study evidence gate, no agent can create direct trade direction or mutate a freeze, and any selected escalation candidate flows back through the core `freeze_v7_candidate` and A1 readiness path rather than directly producing READY.