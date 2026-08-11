from __future__ import annotations

import json
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
    qwen = _first_available(ids, ("qwen/qwen3.6-27b",), contains="qwen") or fallback
    auditor = _first_available(ids, ("openai/gpt-oss-120b", "openai/gpt-oss-20b")) or qwen
    judge = _first_available(ids, ("openai/gpt-oss-20b", "openai/gpt-oss-120b")) or auditor
    return {
        "evidence_scout": qwen,
        "error_scientist": qwen,
        "methodology_auditor": auditor,
        "research_judge": judge,
    }


def _chat_json(client: Any, *, model: str, role: str, context: Any) -> dict[str, Any]:
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "V7 quantitative research/backtest only. Use supplied causal evidence only. "
                    "Do not create executable trading direction, leverage changes, or exchange actions. "
                    "Preserve contradictory evidence. Return JSON only."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"role": role, "context": context}, sort_keys=True, default=str),
            },
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content or "{}")


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

    evidence = _chat_json(
        client,
        model=models["evidence_scout"],
        role="evidence_scout",
        context=clean,
    )
    scientist = _chat_json(
        client,
        model=models["error_scientist"],
        role="error_scientist",
        context={"research_context": clean, "evidence": evidence},
    )

    validated: list[ResearchHypothesis] = []
    rejected: list[dict[str, str]] = []
    for raw in scientist.get("hypotheses", []):
        try:
            hypothesis = _hypothesis_from_payload(dict(raw))
            validated.append(
                validate_hypothesis(
                    hypothesis,
                    blocked_fingerprints=blocked_fingerprints,
                )
            )
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
    approved = [
        hypothesis
        for hypothesis in validated
        if review_decisions.get(hypothesis.hypothesis_id, "reject") == "test"
    ]

    judge = _chat_json(
        client,
        model=models["research_judge"],
        role="research_judge",
        context={
            "research_context": clean,
            "approved_hypotheses": [asdict(item) for item in approved],
            "audit": audit,
        },
    )
    ranked_ids = [str(item) for item in judge.get("ranked_hypothesis_ids", [])]
    rank = {hypothesis_id: index for index, hypothesis_id in enumerate(ranked_ids)}
    approved.sort(key=lambda item: rank.get(item.hypothesis_id, len(rank)))

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
