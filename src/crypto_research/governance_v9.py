"""Minimal V9 provenance, freeze, and categorical readiness guards."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def validate_trial_continuity(
    registry_path: str | Path, *, expected_max: int = 869, next_trial: int = 870
) -> dict[str, Any]:
    with Path(registry_path).open(newline="", encoding="utf-8") as handle:
        trials = [int(row["trial_number"]) for row in csv.DictReader(handle) if row.get("trial_number")]
    if not trials:
        raise ValueError("trial registry is empty")
    if len(trials) != len(set(trials)):
        raise ValueError("trial registry contains duplicate trial numbers")
    maximum = max(trials)
    if maximum != expected_max:
        raise ValueError(f"expected max trial {expected_max}, found {maximum}")
    if next_trial != expected_max + 1:
        raise ValueError("next trial must be exactly max trial + 1")
    if next_trial in trials:
        raise ValueError(f"trial {next_trial} already exists")
    return {
        "max_trial": maximum,
        "next_trial": next_trial,
        "next_trial_already_present": False,
        "registry_rows": len(trials),
    }


def _freeze_state(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "candidate_hash"}


def build_candidate_freeze_payload(
    *,
    candidate_id: str,
    code_sha: str,
    config: dict[str, Any],
    performance_trial_ids: list[int],
    frozen_at_utc: str,
    source_artifact_hashes: dict[str, str],
) -> dict[str, Any]:
    if not candidate_id or not code_sha or not performance_trial_ids:
        raise ValueError("candidate_id, code_sha, and performance_trial_ids are required")
    payload: dict[str, Any] = {
        "schema_version": "v9-candidate-freeze-1",
        "candidate_id": candidate_id,
        "code_sha": code_sha,
        "config": config,
        "performance_trial_ids": [int(item) for item in performance_trial_ids],
        "frozen_at_utc": frozen_at_utc,
        "source_artifact_hashes": source_artifact_hashes,
    }
    payload["candidate_hash"] = hashlib.sha256(_canonical(payload).encode()).hexdigest()
    return payload


def verify_candidate_freeze(path: str | Path) -> bool:
    target = Path(path)
    if not target.exists():
        return False
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        expected = str(payload["candidate_hash"])
        actual = hashlib.sha256(_canonical(_freeze_state(payload)).encode()).hexdigest()
        return bool(expected) and expected == actual
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


def build_paper_readiness(
    *,
    source_of_truth: bool,
    causality: bool,
    science: bool,
    execution: bool,
    operational: bool,
    safety: bool,
    freeze: bool,
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    categories = {
        "SOURCE_OF_TRUTH": bool(source_of_truth),
        "CAUSALITY": bool(causality),
        "SCIENCE": bool(science),
        "EXECUTION": bool(execution),
        "OPERATIONAL": bool(operational),
        "SAFETY": bool(safety),
        "FREEZE": bool(freeze),
    }
    ready = all(categories.values())
    return {
        "schema_version": "v9-paper-readiness-1",
        "categories": categories,
        "readiness": "READY_TO_START_PAPER" if ready else "V9_NOT_READY_FOR_PAPER",
        "A1": "START_ELIGIBLE" if ready else "NOT_STARTED",
        "paper_validated": False,
        "live_authorization": "LIVE_NOT_AUTHORIZED",
        "blockers": list(blockers or []),
    }
