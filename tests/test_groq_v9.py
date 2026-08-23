from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from crypto_research.groq_v9 import (
    CouncilModelUnavailable,
    _chat_json_qwen,
    run_v9_research_council,
    select_qwen_model,
)


def test_v9_selects_preferred_active_qwen_and_never_non_qwen() -> None:
    assert select_qwen_model({"openai/gpt-oss-20b", "qwen/qwen3.6-27b"}) == "qwen/qwen3.6-27b"
    assert select_qwen_model({"qwen/other"}) == "qwen/other"
    with pytest.raises(CouncilModelUnavailable):
        select_qwen_model({"openai/gpt-oss-20b"})


class _RepairCompletions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = "not json" if len(self.calls) == 1 else json.dumps({"decision": "NEED_MORE_EVIDENCE", "reasons": ["gap"]})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_v9_qwen_json_gets_one_same_model_repair_and_hides_reasoning() -> None:
    completions = _RepairCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    result = _chat_json_qwen(
        client,
        model="qwen/qwen3.6-27b",
        role="methodology_auditor",
        context={},
    )

    assert result["decision"] == "NEED_MORE_EVIDENCE"
    assert len(completions.calls) == 2
    assert {call["model"] for call in completions.calls} == {"qwen/qwen3.6-27b"}
    assert all(call["reasoning_format"] == "hidden" for call in completions.calls)
    assert all(call["response_format"] == {"type": "json_object"} for call in completions.calls)
    assert all(call["max_completion_tokens"] == 4096 for call in completions.calls)


class _Models:
    def list(self):
        return SimpleNamespace(data=[SimpleNamespace(id="qwen/qwen3.6-27b"), SimpleNamespace(id="openai/gpt-oss-20b")])


class _CouncilCompletions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        role = json.loads(kwargs["messages"][-1]["content"])["role"]
        if role == "evidence_scout":
            payload = {"new_evidence": [], "evidence_gaps": ["no mature prospective outcomes"], "notes": []}
        elif role == "error_scientist":
            payload = {"largest_failure_mode": "no admitted factor", "hypotheses": [], "notes": ["do not spend a trial"]}
        elif role == "methodology_auditor":
            payload = {"decision": "NEED_MORE_EVIDENCE", "reasons": ["prospective evidence immature"]}
        else:
            payload = {"decision": "ALLOW_TEST", "hypothesis_id": None, "reasoning_summary": "methodology must still gate"}
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])


def test_v9_council_uses_qwen_for_all_roles_and_deterministic_gate_vetoes_test() -> None:
    completions = _CouncilCompletions()
    client = SimpleNamespace(models=_Models(), chat=SimpleNamespace(completions=completions))

    result = run_v9_research_council(
        {"prospective_data_integrity": {"mature_outcomes": 0}},
        client=client,
        deterministic_allow_test=False,
    )

    assert result["model"] == "qwen/qwen3.6-27b"
    assert [call["model"] for call in completions.calls] == ["qwen/qwen3.6-27b"] * 4
    assert result["judge"]["decision"] == "ALLOW_TEST"
    assert result["effective_decision"] == "NEED_MORE_EVIDENCE"
    assert result["performance_trial_authorized"] is False

class _ApiJsonFailOnceCompletions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            error = RuntimeError("json_validate_failed")
            error.status_code = 400
            raise error
        payload = {"new_evidence": [], "evidence_gaps": ["retry recovered"], "notes": []}
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])


def test_v9_qwen_retries_one_api_side_json_validation_failure_same_model() -> None:
    completions = _ApiJsonFailOnceCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    result = _chat_json_qwen(
        client,
        model="qwen/qwen3.6-27b",
        role="evidence_scout",
        context={},
    )

    assert result["evidence_gaps"] == ["retry recovered"]
    assert len(completions.calls) == 2
    assert {call["model"] for call in completions.calls} == {"qwen/qwen3.6-27b"}
    assert all(call["max_completion_tokens"] == 6144 for call in completions.calls)
