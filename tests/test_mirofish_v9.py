from __future__ import annotations

import pytest

from crypto_research.mirofish_v9 import validate_scenario_record


def _row() -> dict:
    return {
        "run_id": "mf-1",
        "timestamp_utc": "2026-08-20T11:00:00Z",
        "mirofish_git_sha": "117ed37758cdc96f73b7d5e0d22713c50439695f",
        "chosen_llm_model": "qwen/qwen3.6-27b",
        "random_seed": 42,
        "simulation_rounds": 10,
        "source_documents": [{"name": "event.json", "sha256": "abc", "published_at": "2026-08-20T10:00:00Z", "first_seen_at": "2026-08-20T10:01:00Z"}],
        "scenario_as_of": "2026-08-20T10:01:00Z",
        "requirement_hash": "req",
        "candidate_hash": None,
        "output_artifact_hashes": ["out"],
        "status": "COMPLETED",
        "run_class": "PREDECLARED_STRESS",
        "may_affect": {
            "hypothesis_generation": True,
            "risk_veto": True,
            "paper_sizing": False,
            "performance_admission": "VETO_ONLY",
        },
        "alpha_role": False,
    }


def test_mirofish_registry_accepts_scenario_stress_but_never_alpha() -> None:
    assert validate_scenario_record(_row())["run_class"] == "PREDECLARED_STRESS"
    bad = _row()
    bad["alpha_role"] = True
    with pytest.raises(ValueError, match="alpha"):
        validate_scenario_record(bad)


def test_mirofish_registry_rejects_performance_rescue() -> None:
    bad = _row()
    bad["may_affect"]["performance_admission"] = "CAN_PROMOTE"
    with pytest.raises(ValueError, match="VETO_ONLY"):
        validate_scenario_record(bad)
