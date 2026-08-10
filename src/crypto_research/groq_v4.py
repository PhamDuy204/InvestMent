from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

MODEL_ROUTES = {
    "hypothesis_scout": ("qwen/qwen3.6-27b", "openai/gpt-oss-120b"),
    "methodology_auditor": ("openai/gpt-oss-120b", "qwen/qwen3.6-27b"),
    "research_synthesizer": ("openai/gpt-oss-20b", "openai/gpt-oss-120b"),
}

_HYPOTHESIS_FIELDS = (
    "name",
    "experiment_family",
    "mechanism",
    "minimum_change",
    "expected_effect",
    "falsification",
    "action_scope",
)

_HYPOTHESIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": list(_HYPOTHESIS_FIELDS),
    "properties": {
        "name": {"type": "string"},
        "experiment_family": {"type": "string"},
        "mechanism": {"type": "string"},
        "minimum_change": {"type": "string"},
        "expected_effect": {"type": "string"},
        "falsification": {"type": "string"},
        "action_scope": {"type": "string", "enum": ["research_only"]},
    },
}

ROLE_SCHEMAS = {
    "hypothesis_scout": {
        "type": "object",
        "additionalProperties": False,
        "required": ["hypotheses"],
        "properties": {
            "hypotheses": {
                "type": "array",
                "items": _HYPOTHESIS_SCHEMA,
                "maxItems": 8,
            }
        },
    },
    "methodology_auditor": {
        "type": "object",
        "additionalProperties": False,
        "required": ["accepted", "rejected"],
        "properties": {
            "accepted": {"type": "array", "items": _HYPOTHESIS_SCHEMA},
            "rejected": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "reason"],
                    "properties": {
                        "name": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                },
            },
        },
    },
    "research_synthesizer": {
        "type": "object",
        "additionalProperties": False,
        "required": ["ranked_hypotheses"],
        "properties": {
            "ranked_hypotheses": {
                "type": "array",
                "items": _HYPOTHESIS_SCHEMA,
                "maxItems": 5,
            }
        },
    },
}

_BLOCKED_KEY_PARTS = ("api_key", "authorization", "password", "secret", "token")
_BLOCKED_LABEL_KEYS = {"oos_label", "test_label", "target_label"}


def _blocked_key(key: object) -> bool:
    lowered = str(key).lower()
    return (
        any(part in lowered for part in _BLOCKED_KEY_PARTS)
        or lowered in _BLOCKED_LABEL_KEYS
        or lowered.startswith("future_")
    )


def sanitize_research_context(value: Any) -> Any:
    """Remove secrets and future/OOS labels before an LLM sees research context."""
    if isinstance(value, Mapping):
        return {
            key: sanitize_research_context(item)
            for key, item in value.items()
            if not _blocked_key(key)
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_research_context(item) for item in value]
    return value


def resolve_available_routes(
    client: Any,
    routes: Mapping[str, tuple[str, ...]] = MODEL_ROUTES,
) -> dict[str, tuple[str, ...]]:
    """Keep configured models that the authenticated Groq project can actually access."""
    available = {item.id for item in client.models.list().data}
    resolved = {role: tuple(model for model in models if model in available) for role, models in routes.items()}
    missing = [role for role, models in resolved.items() if not models]
    if missing:
        raise RuntimeError(f"no available Groq model for roles: {missing}")
    return resolved


def validate_hypothesis(payload: Mapping[str, Any]) -> dict[str, str]:
    missing = [field for field in _HYPOTHESIS_FIELDS if field not in payload]
    if missing:
        raise ValueError(f"missing hypothesis fields: {missing}")
    if set(payload) != set(_HYPOTHESIS_FIELDS):
        raise ValueError("unexpected hypothesis fields")
    if payload["action_scope"] != "research_only":
        raise ValueError("V4 hypotheses must be research-only")
    result = {field: str(payload[field]).strip() for field in _HYPOTHESIS_FIELDS}
    if any(not result[field] for field in _HYPOTHESIS_FIELDS):
        raise ValueError("hypothesis fields must be non-empty")
    return result


def build_chat_request(*, role: str, model: str, context: Mapping[str, Any]) -> dict[str, Any]:
    if role not in ROLE_SCHEMAS:
        raise ValueError(f"unknown V4 role: {role}")
    if not (model.startswith("qwen/") or model.startswith("openai/gpt-oss-")):
        raise ValueError(f"unsupported V4 Groq model: {model}")

    clean = sanitize_research_context(context)
    request: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a quantitative research agent. Propose research-only experiments. "
                    "Never place orders, never request credentials, never use future/OOS labels, "
                    "and prefer the smallest falsifiable change. Return JSON only."
                ),
            },
            {"role": "user", "content": json.dumps(clean, sort_keys=True, default=str)},
        ],
    }

    if model.startswith("qwen/"):
        request.update(
            response_format={"type": "json_object"},
            reasoning_effort="default",
            temperature=0.6,
        )
    else:
        request.update(
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": role,
                    "strict": True,
                    "schema": ROLE_SCHEMAS[role],
                },
            },
            reasoning_effort="high" if role == "methodology_auditor" else "medium",
            temperature=0.0,
        )
    return request
