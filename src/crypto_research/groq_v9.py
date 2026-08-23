"""Qwen-only V9 research council with local JSON validation and no model fallback."""

from __future__ import annotations

import json
from typing import Any

from crypto_research.groq_v7 import sanitize_v7_context

DECISIONS = {"ALLOW_TEST", "REJECT_NO_TEST", "NEED_MORE_EVIDENCE"}
_HYPOTHESIS_REQUIRED = {
    "hypothesis_id",
    "mechanism",
    "target_error",
    "causal_inputs",
    "outcome_only_fields",
    "selection_rule",
    "evaluation_rule",
    "expected_mechanism",
    "exact_single_change",
    "costs",
    "stress_tests",
    "failure_condition",
    "distinct_from_previous",
    "predeclared_timestamp_utc",
    "code_config_hash",
}


class CouncilModelUnavailable(RuntimeError):
    pass


def select_qwen_model(model_ids: set[str]) -> str:
    qwen = sorted(model for model in model_ids if "qwen" in model.lower())
    if not qwen:
        raise CouncilModelUnavailable("COUNCIL_MODEL_UNAVAILABLE: no active Qwen model")
    preferred = "qwen/qwen3.6-27b"
    return preferred if preferred in qwen else qwen[-1]


def _validate_role(role: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("council output must be a JSON object")
    if role == "evidence_scout":
        required = {"new_evidence", "evidence_gaps", "notes"}
        if required.difference(payload) or not all(isinstance(payload[key], list) for key in required):
            raise ValueError("invalid evidence_scout structure")
    elif role == "error_scientist":
        required = {"largest_failure_mode", "hypotheses", "notes"}
        if required.difference(payload) or not isinstance(payload["hypotheses"], list) or not isinstance(payload["notes"], list):
            raise ValueError("invalid error_scientist structure")
        for hypothesis in payload["hypotheses"]:
            if not isinstance(hypothesis, dict) or _HYPOTHESIS_REQUIRED.difference(hypothesis):
                raise ValueError("hypothesis does not satisfy V9 predeclaration contract")
    elif role == "methodology_auditor":
        if {"decision", "reasons"}.difference(payload) or payload["decision"] not in DECISIONS or not isinstance(payload["reasons"], list):
            raise ValueError("invalid methodology_auditor structure")
    elif role == "research_judge":
        if {"decision", "hypothesis_id", "reasoning_summary"}.difference(payload) or payload["decision"] not in DECISIONS:
            raise ValueError("invalid research_judge structure")
    else:
        raise ValueError(f"unsupported council role: {role}")
    return payload


def _role_contract(role: str) -> str:
    contracts = {
        "evidence_scout": '{"new_evidence":[],"evidence_gaps":[],"notes":[]}',
        "error_scientist": (
            '{"largest_failure_mode":"...","hypotheses":[],"notes":[]}. '
            "Any hypothesis object must include exactly the scientific fields described in the system message."
        ),
        "methodology_auditor": '{"decision":"ALLOW_TEST|REJECT_NO_TEST|NEED_MORE_EVIDENCE","reasons":[]}',
        "research_judge": '{"decision":"ALLOW_TEST|REJECT_NO_TEST|NEED_MORE_EVIDENCE","hypothesis_id":null,"reasoning_summary":"..."}',
    }
    return contracts[role]


def _chat_json_qwen(client: Any, *, model: str, role: str, context: Any) -> dict[str, Any]:
    system = (
        "V9 quantitative research, backtest, simulation and paper-trading only. Never issue or recommend an executable "
        "exchange order, cancellation, leverage/margin mutation, transfer, withdrawal, borrow or repay action. Use only "
        "causal evidence available by the declared decision time. Do not use future outcomes as causal inputs. Do not "
        "optimize thresholds after seeing evaluation outcomes. Return one JSON object only. Do not expose hidden reasoning. "
        "For any proposed performance hypothesis include: hypothesis_id, mechanism, target_error, causal_inputs, "
        "outcome_only_fields, selection_rule, evaluation_rule, expected_mechanism, exact_single_change, costs, stress_tests, "
        "failure_condition, distinct_from_previous, predeclared_timestamp_utc, code_config_hash. "
        f"Required role contract: {_role_contract(role)}"
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps({"role": role, "context": context}, sort_keys=True, default=str)},
    ]
    last_error: Exception | None = None
    for attempt in range(2):
        if attempt:
            messages.append({"role": "user", "content": "Repair the previous response. Return only one valid JSON object matching the required role contract."})
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                messages=messages,
                response_format={"type": "json_object"},
                reasoning_format="hidden",
                max_completion_tokens=6144 if role in {"evidence_scout", "error_scientist"} else 4096,
            )
            payload = json.loads(response.choices[0].message.content or "{}")
            return _validate_role(role, payload)
        except Exception as exc:
            api_json_failure = getattr(exc, "status_code", None) == 400 and "json_validate_failed" in str(exc)
            if not api_json_failure and not isinstance(exc, (json.JSONDecodeError, TypeError, ValueError)):
                raise
            last_error = exc
    raise ValueError(f"Qwen council output invalid after one repair: {last_error}")


def run_v9_research_council(
    context: dict[str, Any], *, client: Any, deterministic_allow_test: bool
) -> dict[str, Any]:
    model_ids = {str(item.id) for item in client.models.list().data if getattr(item, "id", None)}
    model = select_qwen_model(model_ids)
    clean = sanitize_v7_context(context)
    evidence = _chat_json_qwen(client, model=model, role="evidence_scout", context=clean)
    scientist = _chat_json_qwen(
        client,
        model=model,
        role="error_scientist",
        context={"research_context": clean, "evidence": evidence},
    )
    audit = _chat_json_qwen(
        client,
        model=model,
        role="methodology_auditor",
        context={"research_context": clean, "evidence": evidence, "scientist": scientist},
    )
    judge = _chat_json_qwen(
        client,
        model=model,
        role="research_judge",
        context={"research_context": clean, "audit": audit, "scientist": scientist},
    )
    authorized = bool(
        deterministic_allow_test
        and audit["decision"] == "ALLOW_TEST"
        and judge["decision"] == "ALLOW_TEST"
        and judge.get("hypothesis_id")
    )
    if authorized:
        effective = "ALLOW_TEST"
    elif "REJECT_NO_TEST" in {audit["decision"], judge["decision"]}:
        effective = "REJECT_NO_TEST"
    else:
        effective = "NEED_MORE_EVIDENCE"
    return {
        "schema_version": "v9-qwen-council-1",
        "status": "COMPLETED",
        "model": model,
        "json_mode": "JSON_OBJECT_LOCAL_VALIDATION",
        "strict_json_schema_assumed": False,
        "reasoning_persisted": False,
        "evidence_scout": evidence,
        "error_scientist": scientist,
        "methodology_auditor": audit,
        "judge": judge,
        "deterministic_allow_test": bool(deterministic_allow_test),
        "effective_decision": effective,
        "performance_trial_authorized": authorized,
    }
