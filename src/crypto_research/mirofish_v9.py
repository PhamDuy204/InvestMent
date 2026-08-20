"""Validation for optional V9 MiroFish scenario/stress registry rows."""

from __future__ import annotations

from typing import Any

_RUN_CLASSES = {"RESEARCH_ONLY", "PREDECLARED_STRESS", "FORWARD_LOCKED"}
_REQUIRED = {
    "run_id", "timestamp_utc", "mirofish_git_sha", "chosen_llm_model", "random_seed",
    "simulation_rounds", "source_documents", "scenario_as_of", "requirement_hash",
    "candidate_hash", "output_artifact_hashes", "status", "run_class", "may_affect", "alpha_role",
}


def validate_scenario_record(row: dict[str, Any]) -> dict[str, Any]:
    missing = _REQUIRED.difference(row)
    if missing:
        raise ValueError(f"missing MiroFish registry fields: {sorted(missing)}")
    if row["run_class"] not in _RUN_CLASSES:
        raise ValueError("invalid MiroFish run_class")
    if bool(row["alpha_role"]):
        raise ValueError("MiroFish alpha role is prohibited")
    if int(row["simulation_rounds"]) <= 0:
        raise ValueError("simulation_rounds must be positive")
    if not isinstance(row["source_documents"], list) or not isinstance(row["output_artifact_hashes"], list):
        raise ValueError("source_documents and output_artifact_hashes must be lists")
    may_affect = row["may_affect"]
    if not isinstance(may_affect, dict):
        raise ValueError("may_affect must be an object")
    required_effects = {"hypothesis_generation", "risk_veto", "paper_sizing", "performance_admission"}
    if required_effects.difference(may_affect):
        raise ValueError("may_affect fields are incomplete")
    if may_affect["performance_admission"] != "VETO_ONLY":
        raise ValueError("MiroFish performance_admission must be VETO_ONLY")
    return row
