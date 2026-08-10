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
        if set(payload) != {"accepted", "rejected"}:
            raise ValueError("invalid methodology_auditor payload")
        accepted = [validate_hypothesis(item) for item in payload["accepted"]]
        rejected = []
        for item in payload["rejected"]:
            if set(item) != {"name", "reason"}:
                raise ValueError("invalid rejected-hypothesis payload")
            rejected.append({"name": str(item["name"]), "reason": str(item["reason"])})
        return {"accepted": accepted, "rejected": rejected}

    if role == "research_synthesizer":
        if set(payload) != {"ranked_hypotheses"}:
            raise ValueError("invalid research_synthesizer payload")
        return {
            "ranked_hypotheses": [
                validate_hypothesis(item) for item in payload["ranked_hypotheses"]
            ]
        }

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
    audit, audit_model = _call_role(client, "methodology_auditor", audit_context, routes)

    proposed_names = {item["name"] for item in proposed}
    if any(item["name"] not in proposed_names for item in audit["accepted"]):
        raise ValueError("auditor introduced a hypothesis that the scout did not propose")

    synthesis_context = {
        "research_context": clean,
        "accepted_hypotheses": audit["accepted"],
    }
    synthesis, synthesis_model = _call_role(client, "research_synthesizer", synthesis_context, routes)
    accepted_names = {row["name"] for row in audit["accepted"]}
    if any(item["name"] not in accepted_names for item in synthesis["ranked_hypotheses"]):
        raise ValueError("synthesizer introduced a hypothesis not accepted by the auditor")

    registry = _trial_registry(proposed, audit["accepted"], audit["rejected"])
    log = {
        "status": "COMPLETED",
        "models": {
            "hypothesis_scout": scout_model,
            "methodology_auditor": audit_model,
            "research_synthesizer": synthesis_model,
        },
        "failure_codes": clean.get("failure_codes", []),
        "proposed_hypotheses": proposed,
        "audited_hypotheses": audit,
        "ranked_hypotheses": synthesis["ranked_hypotheses"],
    }
    (root / "v4_trial_registry.json").write_text(json.dumps(registry, indent=2, sort_keys=True))
    (root / "v4_research_log.json").write_text(json.dumps(log, indent=2, sort_keys=True))
    return log
