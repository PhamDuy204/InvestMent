from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from crypto_research.groq_v4 import (
    MODEL_ROUTES,
    build_chat_request,
    resolve_available_routes,
    sanitize_research_context,
    validate_hypothesis,
)


def _response_json(response: Any) -> dict[str, Any]:
    content = response.choices[0].message.content
    payload = json.loads(content or "{}")
    if not isinstance(payload, dict):
        raise ValueError("Groq role response must be a JSON object")
    return payload


def _validate_role_payload(role: str, payload: dict[str, Any]) -> dict[str, Any]:
    if role == "hypothesis_scout":
        if set(payload) != {"hypotheses"} or not isinstance(payload["hypotheses"], list):
            raise ValueError("invalid hypothesis_scout payload")
        return {"hypotheses": [validate_hypothesis(item) for item in payload["hypotheses"]]}

    if role == "methodology_auditor":
        if set(payload) != {"decisions"} or not isinstance(payload["decisions"], list):
            raise ValueError("invalid methodology_auditor payload")
        decisions = []
        for item in payload["decisions"]:
            if set(item) != {"name", "decision", "reason"}:
                raise ValueError("invalid methodology decision payload")
            decision = str(item["decision"]).strip()
            if decision not in {"accept", "reject"}:
                raise ValueError("methodology decision must be accept or reject")
            decisions.append(
                {
                    "name": str(item["name"]).strip(),
                    "decision": decision,
                    "reason": str(item["reason"]).strip(),
                }
            )
        return {"decisions": decisions}

    if role == "research_synthesizer":
        if set(payload) != {"ranked_names"} or not isinstance(payload["ranked_names"], list):
            raise ValueError("invalid research_synthesizer payload")
        return {"ranked_names": [str(name).strip() for name in payload["ranked_names"]]}

    raise ValueError(f"unknown V4 role: {role}")


def _call_role(
    client: Any,
    role: str,
    context: dict[str, Any],
    routes: dict[str, tuple[str, ...]],
) -> tuple[dict[str, Any], str]:
    errors = []
    for model in routes[role]:
        try:
            response = client.chat.completions.create(
                **build_chat_request(role=role, model=model, context=context)
            )
            return _validate_role_payload(role, _response_json(response)), model
        except Exception as exc:  # fallback is deliberately model-agnostic
            errors.append(f"{model}: {type(exc).__name__}: {exc}")
    raise RuntimeError(f"all Groq models failed for {role}: {' | '.join(errors)}")


def _dedupe_hypotheses(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    result = []
    for row in rows:
        key = tuple(row[field] for field in sorted(row))
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def _trial_registry(
    proposed: list[dict[str, str]],
    accepted: list[dict[str, str]],
    rejected: list[dict[str, str]],
) -> dict[str, Any]:
    accepted_names = {item["name"] for item in accepted}
    rejected_by_name = {item["name"]: item["reason"] for item in rejected}
    rows = []
    for trial_id, hypothesis in enumerate(proposed, start=1):
        name = hypothesis["name"]
        if name in accepted_names:
            status = "PROPOSED_AND_ACCEPTED"
            reason = None
        else:
            status = "PROPOSED_AND_REJECTED"
            reason = rejected_by_name.get(name, "not accepted by methodology auditor")
        rows.append(
            {
                "trial_id": trial_id,
                "source": "GROQ_V4_ENSEMBLE",
                "name": name,
                "experiment_family": hypothesis["experiment_family"],
                "status": status,
                "rejection_reason": reason,
            }
        )
    return {"llm_hypothesis_trials": len(rows), "rows": rows}


def _apply_audit(
    proposed: list[dict[str, str]],
    decisions: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    by_name = {item["name"]: item for item in proposed}
    seen = set()
    accepted = []
    rejected = []
    for item in decisions:
        name = item["name"]
        if name not in by_name:
            raise ValueError("auditor introduced a hypothesis that the scout did not propose")
        if name in seen:
            raise ValueError("auditor returned duplicate decisions")
        seen.add(name)
        if item["decision"] == "accept":
            accepted.append(by_name[name])
        else:
            rejected.append({"name": name, "reason": item["reason"]})
    for name in by_name.keys() - seen:
        rejected.append({"name": name, "reason": "auditor omitted a decision"})
    return accepted, rejected


def run_v4_research(
    client: Any,
    context: dict[str, Any],
    *,
    artifact_dir: str | Path,
    model_routes: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, Any]:
    """Run research-only Groq roles and persist a multiple-testing registry."""
    root = Path(artifact_dir)
    root.mkdir(parents=True, exist_ok=True)
    clean = sanitize_research_context(context)
    routes = model_routes
    if routes is None:
        routes = resolve_available_routes(client) if hasattr(client, "models") else dict(MODEL_ROUTES)

    scout, scout_model = _call_role(client, "hypothesis_scout", clean, routes)
    proposed = _dedupe_hypotheses(scout["hypotheses"])

    audit_context = {"research_context": clean, "hypotheses": proposed}
    audit_raw, audit_model = _call_role(client, "methodology_auditor", audit_context, routes)
    accepted, rejected = _apply_audit(proposed, audit_raw["decisions"])

    synthesis_context = {
        "research_context": clean,
        "accepted_hypotheses": accepted,
    }
    synthesis, synthesis_model = _call_role(client, "research_synthesizer", synthesis_context, routes)
    accepted_by_name = {row["name"]: row for row in accepted}
    ranked_names = synthesis["ranked_names"]
    if len(ranked_names) != len(set(ranked_names)):
        raise ValueError("synthesizer returned duplicate hypothesis names")
    if any(name not in accepted_by_name for name in ranked_names):
        raise ValueError("synthesizer introduced a hypothesis not accepted by the auditor")
    ranked_hypotheses = [accepted_by_name[name] for name in ranked_names]

    registry = _trial_registry(proposed, accepted, rejected)
    log = {
        "status": "COMPLETED",
        "models": {
            "hypothesis_scout": scout_model,
            "methodology_auditor": audit_model,
            "research_synthesizer": synthesis_model,
        },
        "failure_codes": clean.get("failure_codes", []),
        "proposed_hypotheses": proposed,
        "audited_hypotheses": {"accepted": accepted, "rejected": rejected},
        "ranked_hypotheses": ranked_hypotheses,
    }
    (root / "v4_trial_registry.json").write_text(json.dumps(registry, indent=2, sort_keys=True))
    (root / "v4_research_log.json").write_text(json.dumps(log, indent=2, sort_keys=True))
    return log
