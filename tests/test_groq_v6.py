from types import SimpleNamespace

import pytest

from crypto_research.groq_v6 import (
    list_model_ids,
    sanitize_v6_context,
    select_role_models,
    validate_hypothesis,
)


class _Models:
    def list(self):
        return SimpleNamespace(data=[SimpleNamespace(id="qwen/qwen3.6-27b"), SimpleNamespace(id="openai/gpt-oss-20b")])


class _Client:
    models = _Models()


def test_models_are_discovered_at_runtime_with_fallbacks():
    ids = list_model_ids(_Client())
    assert ids == {"qwen/qwen3.6-27b", "openai/gpt-oss-20b"}
    selected = select_role_models(ids)
    assert selected["hypothesis_scout"] == "qwen/qwen3.6-27b"
    assert selected["synthesizer"] == "openai/gpt-oss-20b"
    assert selected["methodology_auditor"] == "openai/gpt-oss-20b"


def test_context_removes_secret_and_forward_outcomes():
    clean = sanitize_v6_context({"api_key": "secret", "metrics": {"sharpe": 1.0}, "forward_results": {"net": 1}})
    assert "api_key" not in clean
    assert "forward_results" not in clean
    assert clean["metrics"]["sharpe"] == 1.0


def test_hypothesis_rejects_direct_burst_direction_rule():
    with pytest.raises(ValueError, match="direction"):
        validate_hypothesis(
            {
                "hypothesis": "Go SHORT when burst probability is high",
                "stage": "C",
                "causal_inputs": ["burst_probability"],
                "expected_mechanism": "direction alpha",
                "experiment": "short on high burst",
                "complexity_cost": "low",
                "invalidation_condition": "PF <= 1",
            }
        )


def test_runtime_ensemble_calls_discovered_role_models_and_validates_scout():
    import json
    from types import SimpleNamespace

    from crypto_research.groq_v6 import run_v6_research_ensemble

    hypothesis = {
        "hypothesis": "Reduce H12 risk when high volatility coincides with burst state",
        "stage": "C",
        "causal_inputs": ["burst_probability", "vol_state"],
        "expected_mechanism": "reduce adverse hold risk without changing direction",
        "experiment": "scale existing H12 target only",
        "complexity_cost": "one state interaction",
        "invalidation_condition": "no after-cost Sharpe or drawdown improvement",
    }

    class Models:
        def list(self):
            return SimpleNamespace(data=[
                SimpleNamespace(id="qwen/qwen3.6-27b"),
                SimpleNamespace(id="openai/gpt-oss-120b"),
                SimpleNamespace(id="openai/gpt-oss-20b"),
            ])

    class Completions:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs["model"])
            model = kwargs["model"]
            if model.startswith("qwen/"):
                payload = {"hypotheses": [hypothesis]}
            elif model.endswith("120b"):
                payload = {"findings": [{"hypothesis": hypothesis["hypothesis"], "decision": "test", "reason": "causal state-only use"}]}
            else:
                payload = {"accepted_hypotheses": [hypothesis["hypothesis"]], "notes": ["count and backtest locally"]}
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])

    completions = Completions()
    client = SimpleNamespace(models=Models(), chat=SimpleNamespace(completions=completions))
    result = run_v6_research_ensemble({"metrics": {"sharpe": 1.0}, "forward_results": {"net": 9}}, client=client)
    assert result["status"] == "COMPLETED"
    assert completions.calls == ["qwen/qwen3.6-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    assert "forward_results" not in result["sanitized_context"]
    assert len(result["validated_hypotheses"]) == 1
