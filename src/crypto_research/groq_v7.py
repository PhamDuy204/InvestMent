from __future__ import annotations

import json
import re
import time
from dataclasses import asdict
from typing import Any

from crypto_research.hypotheses_v7 import ResearchHypothesis, validate_hypothesis

RESEARCH_TOOL_ALLOWLIST = (
    "search_literature",
    "query_error_ledger",
    "query_factor_observatory",
    "build_experiment_manifest",
    "append_evidence_card",
)

_FACTOR_FAMILIES = (
    "microstructure",
    "derivatives",
    "cross_asset_macro",
    "on_chain",
    "news_event",
    "attention_sentiment",
    "cross_sectional",
    "execution_risk",
    "scenario_swarm",
)

_BLOCKED_CONTEXT_TERMS = (
    "api_key",
    "secret",
    "token",
    "password",
    "authorization",
    "forward",
    "future",
    "oracle",
    "untouched_forward",
)


def sanitize_v7_context(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(term in lowered for term in _BLOCKED_CONTEXT_TERMS):
                continue
            clean[str(key)] = sanitize_v7_context(item)
        return clean
    if isinstance(value, (list, tuple)):
        return [sanitize_v7_context(item) for item in value]
    return value


def list_model_ids(client: Any) -> set[str]:
    response = client.models.list()
    return {str(item.id) for item in response.data if getattr(item, "id", None)}


def _first_available(ids: set[str], preferred: tuple[str, ...], *, contains: str | None = None) -> str | None:
    for model in preferred:
        if model in ids:
            return model
    if contains is not None:
        matches = sorted(model for model in ids if contains.lower() in model.lower())
        if matches:
            return matches[-1]
    return None


def select_v7_role_models(ids: set[str]) -> dict[str, str]:
    if not ids:
        raise ValueError("Groq model list is empty")
    fallback = sorted(ids)[0]
    qwen = _first_available(ids, ("qwen/qwen3.6-27b", "qwen/qwen3-32b"), contains="qwen") or fallback
    auditor = _first_available(ids, ("openai/gpt-oss-120b", "openai/gpt-oss-20b")) or qwen
    judge = _first_available(ids, ("openai/gpt-oss-20b", "openai/gpt-oss-120b")) or auditor
    return {
        "evidence_scout": qwen,
        "error_scientist": qwen,
        "methodology_auditor": auditor,
        "research_judge": judge,
    }


def _hypothesis_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "hypothesis_id": {"type": "string"},
            "target_error": {"type": "string"},
            "observation": {"type": "string"},
            "causal_inputs": {"type": "array", "items": {"type": "string"}},
            "expected_mechanism": {"type": "string"},
            "single_change": {"type": "string"},
            "expected_effect": {"type": "string"},
            "cost_risk": {"type": "string"},
            "invalidation_condition": {"type": "string"},
            "required_test": {"type": "string"},
            "factor_family": {"type": "string", "enum": list(_FACTOR_FAMILIES)},
            "source_ids": {"type": "array", "items": {"type": "string"}},
            "materially_new_evidence": {"type": "boolean"},
        },
        "required": [
            "hypothesis_id",
            "target_error",
            "observation",
            "causal_inputs",
            "expected_mechanism",
            "single_change",
            "expected_effect",
            "cost_risk",
            "invalidation_condition",
            "required_test",
            "factor_family",
            "source_ids",
            "materially_new_evidence",
        ],
        "additionalProperties": False,
    }


def _role_schema(role: str) -> dict[str, Any]:
    evidence_card = {
        "type": "object",
        "properties": {
            "claim": {"type": "string"},
            "source_ids": {"type": "array", "items": {"type": "string"}},
            "support": {"type": "string"},
            "contradictory_evidence": {"type": "string"},
        },
        "required": ["claim", "source_ids", "support", "contradictory_evidence"],
        "additionalProperties": False,
    }
    review = {
        "type": "object",
        "properties": {
            "hypothesis_id": {"type": "string"},
            "decision": {"type": "string", "enum": ["test", "reject"]},
            "reason": {"type": "string"},
        },
        "required": ["hypothesis_id", "decision", "reason"],
        "additionalProperties": False,
    }
    schemas = {
        "evidence_scout": {
            "type": "object",
            "properties": {
                "evidence_cards": {"type": "array", "items": evidence_card},
                "evidence_gaps": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["evidence_cards", "evidence_gaps"],
            "additionalProperties": False,
        },
        "error_scientist": {
            "type": "object",
            "properties": {
                "hypotheses": {"type": "array", "items": _hypothesis_schema()},
                "notes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["hypotheses", "notes"],
            "additionalProperties": False,
        },
        "methodology_auditor": {
            "type": "object",
            "properties": {
                "reviews": {"type": "array", "items": review},
                "dissent": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["reviews", "dissent"],
            "additionalProperties": False,
        },
        "research_judge": {
            "type": "object",
            "properties": {
                "ranked_hypothesis_ids": {"type": "array", "items": {"type": "string"}},
                "reasoning_summary": {"type": "string"},
            },
            "required": ["ranked_hypothesis_ids", "reasoning_summary"],
            "additionalProperties": False,
        },
    }
    return schemas[role]


def _is_strict_model(model: str) -> bool:
    return model in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}


def _is_json_validation_error(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    text = str(exc).lower()
    return bool(status == 400 and ("json" in text or "validate" in text or "invalid_request_error" in text))


def _is_rate_limit_error(exc: Exception) -> bool:
    return getattr(exc, "status_code", None) == 429


def _rate_limit_delay_seconds(exc: Exception) -> float:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) or {}
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw is not None:
        try:
            return max(0.0, min(10.0, float(raw)))
        except (TypeError, ValueError):
            pass
    match = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)s", str(exc), re.IGNORECASE)
    if match:
        return max(0.0, min(10.0, float(match.group(1)) + 0.25))
    return 5.0


def _chat_json_once(client: Any, *, model: str, role: str, context: Any) -> dict[str, Any]:
    response_format: dict[str, Any]
    if _is_strict_model(model):
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": f"v7_{role}",
                "strict": True,
                "schema": _role_schema(role),
            },
        }
    else:
        response_format = {"type": "json_object"}
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "V7 quantitative research/backtest only. Use supplied causal evidence only. "
                    "Do not create executable trading direction, leverage changes, or exchange actions. "
                    "Preserve contradictory evidence. Return one valid JSON object only, without markdown. "
                    "For hypothesis objects, include every required schema field exactly once. "
                    "causal_inputs may contain only information available at the decision timestamp; never put a forward/future/oracle outcome in causal_inputs. "
                    "Outcome labels belong only in required_test or invalidation_condition."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"role": role, "context": context}, sort_keys=True, default=str),
            },
        ],
        response_format=response_format,
    )
    return json.loads(response.choices[0].message.content or "{}")


def _chat_json(
    client: Any,
    *,
    model: str,
    role: str,
    context: Any,
    fallback_model: str | None = None,
) -> dict[str, Any]:
    try:
        return _chat_json_once(client, model=model, role=role, context=context)
    except Exception as exc:
        if _is_rate_limit_error(exc):
            time.sleep(_rate_limit_delay_seconds(exc))
            try:
                return _chat_json_once(client, model=model, role=role, context=context)
            except Exception as retry_exc:
                exc = retry_exc
        if fallback_model is None or fallback_model == model or not _is_json_validation_error(exc):
            raise exc
        result = _chat_json_once(client, model=fallback_model, role=role, context=context)
        result.setdefault("_runtime_fallback", {"from": model, "to": fallback_model, "reason": "json_validation_400"})
        return result


def _hypothesis_from_payload(payload: dict[str, Any]) -> ResearchHypothesis:
    return ResearchHypothesis(
        hypothesis_id=str(payload["hypothesis_id"]),
        target_error=str(payload["target_error"]),
        observation=str(payload["observation"]),
        causal_inputs=tuple(str(item) for item in payload["causal_inputs"]),
        expected_mechanism=str(payload["expected_mechanism"]),
        single_change=str(payload["single_change"]),
        expected_effect=str(payload["expected_effect"]),
        cost_risk=str(payload["cost_risk"]),
        invalidation_condition=str(payload["invalidation_condition"]),
        required_test=str(payload["required_test"]),
        factor_family=str(payload["factor_family"]),
        source_ids=tuple(str(item) for item in payload["source_ids"]),
        materially_new_evidence=bool(payload.get("materially_new_evidence", False)),
    )


def run_v7_research_council(
    context: dict[str, Any],
    *,
    client: Any,
    blocked_fingerprints: set[str],
) -> dict[str, Any]:
    ids = list_model_ids(client)
    models = select_v7_role_models(ids)
    clean = sanitize_v7_context(context)
    json_fallback = _first_available(ids, ("openai/gpt-oss-120b", "openai/gpt-oss-20b")) or models["research_judge"]

    evidence = _chat_json(
        client,
        model=models["evidence_scout"],
        fallback_model=json_fallback,
        role="evidence_scout",
        context=clean,
    )
    scientist = _chat_json(
        client,
        model=models["error_scientist"],
        fallback_model=json_fallback,
        role="error_scientist",
        context={"research_context": clean, "evidence": evidence},
    )

    validated: list[ResearchHypothesis] = []
    rejected: list[dict[str, str]] = []
    for raw in scientist.get("hypotheses", []):
        try:
            hypothesis = _hypothesis_from_payload(dict(raw))
            validated.append(validate_hypothesis(hypothesis, blocked_fingerprints=blocked_fingerprints))
        except (KeyError, TypeError, ValueError) as exc:
            rejected.append(
                {
                    "hypothesis_id": str(raw.get("hypothesis_id", "UNKNOWN")) if isinstance(raw, dict) else "UNKNOWN",
                    "reason": str(exc),
                }
            )

    audit = _chat_json(
        client,
        model=models["methodology_auditor"],
        fallback_model=json_fallback,
        role="methodology_auditor",
        context={
            "research_context": clean,
            "evidence": evidence,
            "validated_hypotheses": [asdict(item) for item in validated],
            "locally_rejected_hypotheses": rejected,
        },
    )
    review_decisions = {
        str(item.get("hypothesis_id")): str(item.get("decision", "reject")).lower()
        for item in audit.get("reviews", [])
        if isinstance(item, dict)
    }
    auditor_approved = [
        hypothesis
        for hypothesis in validated
        if review_decisions.get(hypothesis.hypothesis_id, "reject") == "test"
    ]

    judge = _chat_json(
        client,
        model=models["research_judge"],
        fallback_model=json_fallback,
        role="research_judge",
        context={
            "research_context": clean,
            "approved_hypotheses": [asdict(item) for item in auditor_approved],
            "audit": audit,
        },
    )
    ranked_ids = [str(item) for item in judge.get("ranked_hypothesis_ids", [])]
    rank = {hypothesis_id: index for index, hypothesis_id in enumerate(ranked_ids)}
    approved = [hypothesis for hypothesis in auditor_approved if hypothesis.hypothesis_id in rank]
    approved.sort(key=lambda item: rank[item.hypothesis_id])

    return {
        "status": "COMPLETED",
        "available_models": sorted(ids),
        "role_models": models,
        "research_tool_allowlist": list(RESEARCH_TOOL_ALLOWLIST),
        "sanitized_context": clean,
        "evidence": evidence,
        "scientist": scientist,
        "validated_hypotheses": [asdict(item) for item in validated],
        "locally_rejected_hypotheses": rejected,
        "audit": audit,
        "judge": judge,
        "approved_hypotheses": [asdict(item) for item in approved],
    }
