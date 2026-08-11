from __future__ import annotations

from typing import Any

from crypto_research.groq_research_v3 import sanitize_context

_REQUIRED_HYPOTHESIS_FIELDS = {
    "hypothesis",
    "stage",
    "causal_inputs",
    "expected_mechanism",
    "experiment",
    "complexity_cost",
    "invalidation_condition",
}


def list_model_ids(client: Any) -> set[str]:
    response = client.models.list()
    return {str(item.id) for item in response.data if getattr(item, "id", None)}


def _first_matching(ids: set[str], preferred: tuple[str, ...], contains: str | None = None) -> str | None:
    for model in preferred:
        if model in ids:
            return model
    if contains is not None:
        matches = sorted(model for model in ids if contains.lower() in model.lower())
        if matches:
            return matches[-1]
    return None


def select_role_models(ids: set[str]) -> dict[str, str]:
    if not ids:
        raise ValueError("Groq model list is empty")
    fallback = sorted(ids)[0]
    scout = _first_matching(ids, ("qwen/qwen3.6-27b",), contains="qwen") or fallback
    auditor = _first_matching(ids, ("openai/gpt-oss-120b", "openai/gpt-oss-20b")) or scout
    synthesizer = _first_matching(ids, ("openai/gpt-oss-20b", "openai/gpt-oss-120b")) or auditor
    return {
        "hypothesis_scout": scout,
        "methodology_auditor": auditor,
        "synthesizer": synthesizer,
    }


def sanitize_v6_context(value: Any) -> Any:
    clean = sanitize_context(value)
    if isinstance(clean, dict):
        return {
            key: sanitize_v6_context(item)
            for key, item in clean.items()
            if not any(blocked in str(key).lower() for blocked in ("forward", "future", "oracle"))
        }
    if isinstance(clean, list):
        return [sanitize_v6_context(item) for item in clean]
    return clean


def validate_hypothesis(payload: dict[str, Any]) -> dict[str, Any]:
    if set(payload) != _REQUIRED_HYPOTHESIS_FIELDS:
        missing = sorted(_REQUIRED_HYPOTHESIS_FIELDS.difference(payload))
        extra = sorted(set(payload).difference(_REQUIRED_HYPOTHESIS_FIELDS))
        raise ValueError(f"invalid hypothesis schema missing={missing} extra={extra}")
    if str(payload["stage"]) not in {"B", "C", "D", "E", "F", "G"}:
        raise ValueError("hypothesis stage must be one of B-G")
    if not isinstance(payload["causal_inputs"], list) or not all(isinstance(item, str) for item in payload["causal_inputs"]):
        raise ValueError("causal_inputs must be a string list")
    text = " ".join(
        str(payload[key]).lower()
        for key in ("hypothesis", "expected_mechanism", "experiment")
    )
    if str(payload["stage"]) in {"C", "D"} and any(
        phrase in text
        for phrase in ("go short", "go long", "short on", "long on", "direction alpha", "direct directional")
    ):
        raise ValueError("burst/flow state cannot directly create direction alpha")
    return payload


def _chat_json(client: Any, *, model: str, role: str, context: Any) -> dict[str, Any]:
    import json

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "Quantitative research only. Never place live or paper orders. "
                    "Use only supplied causal evidence. Burst and taker-flow may change risk, horizon, "
                    "hold/exit, or execution, but may not directly create LONG/SHORT direction. Return JSON only."
                ),
            },
            {"role": "user", "content": json.dumps({"role": role, "context": context}, default=str)},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content or "{}")


def run_v6_research_ensemble(context: dict[str, Any], *, client: Any) -> dict[str, Any]:
    ids = list_model_ids(client)
    models = select_role_models(ids)
    clean = sanitize_v6_context(context)
    scout = _chat_json(client, model=models["hypothesis_scout"], role="hypothesis_scout", context=clean)
    raw_hypotheses = scout.get("hypotheses", []) if isinstance(scout, dict) else []
    validated: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for payload in raw_hypotheses:
        try:
            validated.append(validate_hypothesis(dict(payload)))
        except (TypeError, ValueError) as exc:
            rejected.append({"payload": payload, "reason": str(exc)})

    audit = _chat_json(
        client,
        model=models["methodology_auditor"],
        role="methodology_auditor",
        context={"research_context": clean, "validated_hypotheses": validated, "locally_rejected": rejected},
    )
    synthesis = _chat_json(
        client,
        model=models["synthesizer"],
        role="research_synthesizer",
        context={"research_context": clean, "validated_hypotheses": validated, "audit": audit},
    )
    return {
        "status": "COMPLETED",
        "available_models": sorted(ids),
        "role_models": models,
        "sanitized_context": clean,
        "scout": scout,
        "validated_hypotheses": validated,
        "rejected_hypotheses": rejected,
        "audit": audit,
        "synthesis": synthesis,
    }
