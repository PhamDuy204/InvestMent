import json
from types import SimpleNamespace

from crypto_research.groq_v7 import run_v7_research_council


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
    def create(self, **kwargs):
        role = json.loads(kwargs["messages"][-1]["content"])["role"]
        if role == "evidence_scout":
            payload = {"evidence_cards": [], "evidence_gaps": []}
        elif role == "error_scientist":
            payload = {
                "hypotheses": [
                    {
                        "hypothesis_id": "candidate",
                        "target_error": "WRONG_SIDE",
                        "observation": "causal observation",
                        "causal_inputs": ["lagged_feature"],
                        "expected_mechanism": "new reliability mechanism",
                        "single_change": "veto exposure increase when reliability is poor",
                        "expected_effect": "reduce wrong-side damage",
                        "cost_risk": "may skip correct trades",
                        "invalidation_condition": "evaluation net does not improve",
                        "required_test": "fold-local held-out evaluation",
                        "factor_family": "microstructure",
                        "source_ids": ["source-1"],
                        "materially_new_evidence": True,
                    }
                ],
                "notes": [],
            }
        elif role == "methodology_auditor":
            payload = {
                "reviews": [
                    {"hypothesis_id": "candidate", "decision": "test", "reason": "auditor accepts"}
                ],
                "dissent": [],
            }
        else:
            payload = {
                "ranked_hypothesis_ids": [],
                "reasoning_summary": "NO_TEST: evidence is not specific enough",
            }
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
        )


def test_research_judge_empty_ranking_vetoes_auditor_approved_hypothesis() -> None:
    client = SimpleNamespace(models=_Models(), chat=SimpleNamespace(completions=_Completions()))

    result = run_v7_research_council({}, client=client, blocked_fingerprints=set())

    assert result["approved_hypotheses"] == []
