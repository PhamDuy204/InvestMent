import json
from types import SimpleNamespace

from crypto_research.groq_v7 import (
    RESEARCH_TOOL_ALLOWLIST,
    run_v7_research_council,
    sanitize_v7_context,
    select_v7_role_models,
)


def test_v7_context_strips_forward_oracle_and_secret_fields_recursively():
    clean = sanitize_v7_context(
        {
            "api_key": "secret-value",
            "forward_results": {"net": 9},
            "nested": {
                "oracle_direction": 1,
                "future_return": 0.5,
                "authorization": "Bearer x",
                "error_ledger": {"WRONG_SIDE": 10},
            },
            "safe": [
                {"password": "x", "factor": "funding"},
                {"token_count": 3, "association": 0.1},
            ],
        }
    )
    assert "api_key" not in clean
    assert "forward_results" not in clean
    assert "oracle_direction" not in clean["nested"]
    assert "future_return" not in clean["nested"]
    assert "authorization" not in clean["nested"]
    assert clean["nested"]["error_ledger"]["WRONG_SIDE"] == 10
    assert clean["safe"][0] == {"factor": "funding"}
    assert clean["safe"][1] == {"association": 0.1}


def test_runtime_role_model_selection_uses_preferred_models_with_fallbacks():
    ids = {
        "qwen/qwen3.6-27b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "other/model",
    }
    selected = select_v7_role_models(ids)
    assert selected == {
        "evidence_scout": "qwen/qwen3.6-27b",
        "error_scientist": "qwen/qwen3.6-27b",
        "methodology_auditor": "openai/gpt-oss-120b",
        "research_judge": "openai/gpt-oss-20b",
    }
    fallback = select_v7_role_models({"only/model"})
    assert set(fallback.values()) == {"only/model"}


def test_research_tool_allowlist_has_no_exchange_actions():
    blocked = ("order", "cancel", "withdraw", "transfer", "leverage", "buy", "sell")
    assert RESEARCH_TOOL_ALLOWLIST
    for tool in RESEARCH_TOOL_ALLOWLIST:
        lowered = tool.lower()
        assert not any(word in lowered for word in blocked)


class _Models:
    def list(self):
        return SimpleNamespace(
            data=[
                SimpleNamespace(id="qwen/qwen3.6-27b"),
                SimpleNamespace(id="openai/gpt-oss-120b"),
                SimpleNamespace(id="openai/gpt-oss-20b"),
            ]
        )


class _Completions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        role = json.loads(kwargs["messages"][-1]["content"])["role"]
        if role == "evidence_scout":
            payload = {
                "evidence_cards": [
                    {
                        "claim": "funding crowding may condition H12 reliability",
                        "source_ids": ["paper-1"],
                        "contradictory_evidence": ["paper-2"],
                    }
                ]
            }
        elif role == "error_scientist":
            base = {
                "target_error": "WRONG_SIDE",
                "observation": "wrong-side losses cluster in crowded derivatives states",
                "causal_inputs": ["funding", "open_interest_change"],
                "expected_mechanism": "derivatives crowding reduces H12 reliability",
                "expected_effect": "reduce wrong-side loss bps",
                "cost_risk": "may skip correct trades",
                "invalidation_condition": "evaluation net bps <= control",
                "required_test": "walk-forward 10bps 20bps plus1h",
                "factor_family": "derivatives",
                "source_ids": ["paper-1"],
                "materially_new_evidence": False,
            }
            payload = {
                "hypotheses": [
                    {**base, "hypothesis_id": "good", "single_change": "veto exposure increase under derivatives crowding"},
                    {**base, "hypothesis_id": "bad", "single_change": "go short BTC when funding is high"},
                ]
            }
        elif role == "methodology_auditor":
            payload = {
                "reviews": [
                    {"hypothesis_id": "good", "decision": "test", "risks": []},
                    {"hypothesis_id": "bad", "decision": "test", "risks": []},
                ],
                "dissent": ["paper-2 finds weak transferability"],
            }
        else:
            payload = {"ranked_hypothesis_ids": ["bad", "good"], "notes": ["rank only approved research"]}
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
        )


def test_local_validator_overrides_llm_and_preserves_dissent():
    completions = _Completions()
    client = SimpleNamespace(models=_Models(), chat=SimpleNamespace(completions=completions))
    result = run_v7_research_council(
        {
            "error_ledger": {"WRONG_SIDE": 50},
            "forward_results": {"net": 100},
            "api_key": "must-not-leak",
        },
        client=client,
        blocked_fingerprints=set(),
    )
    assert result["status"] == "COMPLETED"
    assert [item["hypothesis_id"] for item in result["approved_hypotheses"]] == ["good"]
    assert [item["hypothesis_id"] for item in result["locally_rejected_hypotheses"]] == ["bad"]
    assert "direct direction" in result["locally_rejected_hypotheses"][0]["reason"]
    assert result["audit"]["dissent"] == ["paper-2 finds weak transferability"]
    assert "forward_results" not in result["sanitized_context"]
    assert "api_key" not in result["sanitized_context"]
    called_models = [call["model"] for call in completions.calls]
    assert called_models == [
        "qwen/qwen3.6-27b",
        "qwen/qwen3.6-27b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
    ]
