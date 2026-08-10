from types import SimpleNamespace

import pytest

from crypto_research.groq_v4 import (
    MODEL_ROUTES,
    build_chat_request,
    resolve_available_routes,
    sanitize_research_context,
    validate_hypothesis,
)


def test_model_routes_use_qwen_for_scout_and_gpt_oss_for_audit():
    assert MODEL_ROUTES["hypothesis_scout"][0] == "qwen/qwen3.6-27b"
    assert MODEL_ROUTES["methodology_auditor"][0] == "openai/gpt-oss-120b"
    assert MODEL_ROUTES["research_synthesizer"][0] == "openai/gpt-oss-20b"


def test_qwen_request_uses_json_object_mode():
    request = build_chat_request(
        role="hypothesis_scout",
        model="qwen/qwen3.6-27b",
        context={"failure_codes": ["COST_SENSITIVE"]},
    )
    assert request["response_format"] == {"type": "json_object"}
    assert request["reasoning_effort"] == "default"


def test_gpt_oss_request_uses_strict_json_schema():
    request = build_chat_request(
        role="methodology_auditor",
        model="openai/gpt-oss-120b",
        context={"hypotheses": []},
    )
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["strict"] is True
    assert request["reasoning_effort"] == "high"


def test_runtime_model_check_filters_unavailable_routes():
    client = SimpleNamespace(
        models=SimpleNamespace(
            list=lambda: SimpleNamespace(
                data=[
                    SimpleNamespace(id="qwen/qwen3.6-27b"),
                    SimpleNamespace(id="openai/gpt-oss-20b"),
                ]
            )
        )
    )
    routes = resolve_available_routes(client)
    assert routes["hypothesis_scout"] == ("qwen/qwen3.6-27b",)
    assert routes["methodology_auditor"] == ("qwen/qwen3.6-27b",)
    assert routes["research_synthesizer"] == ("openai/gpt-oss-20b",)


def test_context_sanitizer_removes_secrets_and_oos_labels():
    clean = sanitize_research_context(
        {
            "api_key": "secret",
            "GROQ_API_KEY": "secret2",
            "future_return_12": [1, 2],
            "oos_label": [0, 1],
            "failure_codes": ["DELAY_SENSITIVE"],
        }
    )
    assert "api_key" not in clean
    assert "GROQ_API_KEY" not in clean
    assert "future_return_12" not in clean
    assert "oos_label" not in clean
    assert clean["failure_codes"] == ["DELAY_SENSITIVE"]


def test_hypothesis_validator_rejects_live_execution():
    with pytest.raises(ValueError, match="research-only"):
        validate_hypothesis(
            {
                "name": "bad",
                "experiment_family": "execution",
                "mechanism": "place orders directly",
                "minimum_change": "call exchange order endpoint",
                "expected_effect": "higher pnl",
                "falsification": "none",
                "action_scope": "live_trade",
            }
        )


def test_hypothesis_validator_accepts_research_only_candidate():
    hypothesis = validate_hypothesis(
        {
            "name": "turnover hysteresis",
            "experiment_family": "turnover_control",
            "mechanism": "avoid small target changes",
            "minimum_change": "add a no-trade band to target transitions",
            "expected_effect": "lower turnover without using confirmation labels",
            "falsification": "reject if frozen validation net return or delay stress worsens",
            "action_scope": "research_only",
        }
    )
    assert hypothesis["experiment_family"] == "turnover_control"
