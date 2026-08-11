from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

ENV_NAME = "GROQ" + "_API_KEY"
MODEL = "openai/gpt-oss-20b"
SECRET_KEYS = ("api_key", "authorization", "secret", "token", "password")


def sanitize_context(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_context(item) for key, item in value.items() if not any(secret in str(key).lower() for secret in SECRET_KEYS)}
    if isinstance(value, (list, tuple)):
        return [sanitize_context(item) for item in value]
    return value


def _object(required, properties):
    return {"type": "object", "additionalProperties": False, "required": required, "properties": properties}


ROLE_SPECS = {
    "failure_diagnostician": _object(
        ["failure_modes", "evidence", "likely_mechanisms", "tests_to_disprove"],
        {name: {"type": "array", "items": {"type": "string"}} for name in ["failure_modes", "evidence", "likely_mechanisms", "tests_to_disprove"]},
    ),
    "literature_code_scout": _object(
        ["hypotheses"],
        {"hypotheses": {"type": "array", "items": _object(
            ["problem", "method", "paper", "existing_code", "minimum_implementation", "expected_effect", "failure_condition"],
            {name: {"type": "string"} for name in ["problem", "method", "paper", "existing_code", "minimum_implementation", "expected_effect", "failure_condition"]},
        )}},
    ),
    "methodology_auditor": _object(
        ["findings"],
        {"findings": {"type": "array", "items": _object(
            ["hypothesis", "risks", "decision", "required_controls"],
            {"hypothesis": {"type": "string"}, "risks": {"type": "array", "items": {"type": "string"}}, "decision": {"type": "string", "enum": ["reject", "revise", "test"]}, "required_controls": {"type": "array", "items": {"type": "string"}}},
        )}},
    ),
    "research_synthesizer": _object(
        ["ranked_experiments"],
        {"ranked_experiments": {"type": "array", "items": _object(
            ["name", "priority", "rationale", "data_required", "expected_metric_effect", "falsification"],
            {"name": {"type": "string"}, "priority": {"type": "integer", "minimum": 1}, "rationale": {"type": "string"}, "data_required": {"type": "string"}, "expected_metric_effect": {"type": "string"}, "falsification": {"type": "string"}},
        )}},
    ),
}


def validate_role_output(role: str, payload: dict[str, Any]) -> dict[str, Any]:
    if role not in ROLE_SPECS:
        raise ValueError(f"unknown role: {role}")
    schema = ROLE_SPECS[role]
    missing = [field for field in schema["required"] if field not in payload]
    if missing:
        raise ValueError(f"missing role output fields: {missing}")
    if set(payload) != set(schema["properties"]):
        raise ValueError("unexpected role output fields")
    return payload


def _cache_key(role: str, context: Any) -> str:
    text = json.dumps({"role": role, "model": MODEL, "context": sanitize_context(context)}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def call_structured_role(role: str, context: Any, *, client=None, cache_dir: str | Path = "artifacts/multi_asset_v3/groq_cache") -> dict[str, Any]:
    if role not in ROLE_SPECS:
        raise ValueError(f"unknown role: {role}")
    if client is None:
        if not os.environ.get(ENV_NAME):
            raise RuntimeError("Groq environment key is not available")
        raise RuntimeError("Groq client transport must be injected")
    clean = sanitize_context(context)
    cache = Path(cache_dir)
    cached = cache / f"{role}-{_cache_key(role, clean)}.json"
    if cached.exists():
        return validate_role_output(role, json.loads(cached.read_text()))
    parsed = validate_role_output(role, client(role, ROLE_SPECS[role], clean))
    cache.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(parsed, indent=2, sort_keys=True))
    return parsed


def run_research_agents(context: dict[str, Any], *, client=None, artifact_root: str | Path = "artifacts/multi_asset_v3") -> dict[str, Any]:
    root = Path(artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    if client is None and not os.environ.get(ENV_NAME):
        result = {"status": "BLOCKED_MISSING_ENVIRONMENT_KEY", "model": MODEL, "historical_news_backtest": "HISTORICAL_GROQ_NEWS_BACKTEST_NOT_AVAILABLE"}
        (root / "groq_research_log.json").write_text(json.dumps(result, indent=2))
        (root / "groq_hypotheses.json").write_text(json.dumps({"status": result["status"], "hypotheses": []}, indent=2))
        return result
    clean = sanitize_context(context)
    cache_dir = root / "groq_cache"
    diagnosis = call_structured_role("failure_diagnostician", clean, client=client, cache_dir=cache_dir)
    scout = call_structured_role("literature_code_scout", {"diagnosis": diagnosis, "research_context": clean}, client=client, cache_dir=cache_dir)
    audit = call_structured_role("methodology_auditor", {"diagnosis": diagnosis, "hypotheses": scout["hypotheses"], "research_context": clean}, client=client, cache_dir=cache_dir)
    synthesis = call_structured_role("research_synthesizer", {"diagnosis": diagnosis, "hypotheses": scout["hypotheses"], "audit": audit, "research_context": clean}, client=client, cache_dir=cache_dir)
    result = {"status": "COMPLETED", "model": MODEL, "diagnosis": diagnosis, "scout": scout, "audit": audit, "synthesis": synthesis, "historical_news_backtest": "HISTORICAL_GROQ_NEWS_BACKTEST_NOT_AVAILABLE"}
    (root / "groq_research_log.json").write_text(json.dumps(result, indent=2, sort_keys=True))
    (root / "groq_hypotheses.json").write_text(json.dumps({"status": "COMPLETED", "hypotheses": scout["hypotheses"], "ranked_experiments": synthesis["ranked_experiments"]}, indent=2, sort_keys=True))
    return result
