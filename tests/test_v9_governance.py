from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from crypto_research.governance_v9 import (
    build_candidate_freeze_payload,
    build_paper_readiness,
    validate_trial_continuity,
    verify_candidate_freeze,
)


def _registry(path: Path, trials: list[int]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["trial_number", "hypothesis", "status"])
        writer.writeheader()
        for trial in trials:
            writer.writerow({"trial_number": trial, "hypothesis": f"H{trial}", "status": "REJECTED"})


def test_v9_trial_continuity_accepts_869_and_requires_870_next(tmp_path) -> None:
    path = tmp_path / "registry.csv"
    _registry(path, [868, 869])

    result = validate_trial_continuity(path, expected_max=869, next_trial=870)

    assert result["max_trial"] == 869
    assert result["next_trial"] == 870
    assert result["next_trial_already_present"] is False


@pytest.mark.parametrize("trials", ([868, 869, 869], [868, 870]))
def test_v9_trial_continuity_rejects_duplicate_or_skipped_trial(tmp_path, trials) -> None:
    path = tmp_path / "registry.csv"
    _registry(path, list(trials))

    with pytest.raises(ValueError):
        validate_trial_continuity(path, expected_max=869, next_trial=870)


def test_candidate_freeze_hash_detects_mutation(tmp_path) -> None:
    payload = build_candidate_freeze_payload(
        candidate_id="candidate-v1",
        code_sha="abc123",
        config={"feature": "x", "threshold": 0.5},
        performance_trial_ids=[870],
        frozen_at_utc="2026-08-20T11:00:00Z",
        source_artifact_hashes={"registry": "deadbeef"},
    )
    path = tmp_path / "candidate_freeze.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert verify_candidate_freeze(path)

    payload["config"]["threshold"] = 0.6
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert not verify_candidate_freeze(path)


def test_paper_readiness_is_categorical_and_fails_without_science_or_freeze() -> None:
    readiness = build_paper_readiness(
        source_of_truth=True,
        causality=True,
        science=False,
        execution=True,
        operational=True,
        safety=True,
        freeze=False,
        blockers=["no_admitted_candidate"],
    )

    assert readiness["readiness"] == "V9_NOT_READY_FOR_PAPER"
    assert readiness["A1"] == "NOT_STARTED"
    assert readiness["paper_validated"] is False
    assert readiness["live_authorization"] == "LIVE_NOT_AUTHORIZED"
    assert readiness["blockers"] == ["no_admitted_candidate"]
