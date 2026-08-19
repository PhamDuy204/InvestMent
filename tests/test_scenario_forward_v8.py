from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from crypto_research.scenario_forward_v8 import (
    append_scenario_evaluation,
    lock_forward_scenario,
)


def _prediction() -> dict[str, object]:
    return {
        "bullish_path_frequency": 0.35,
        "bearish_path_frequency": 0.40,
        "panic_path_frequency": 0.15,
        "squeeze_path_frequency": 0.10,
        "opinion_dispersion": 0.72,
        "dominant_causal_narratives": ["crowded longs plus weak depth"],
        "critical_tipping_variables": ["funding", "depth_20_bid"],
    }


def test_lock_forward_scenario_is_append_only_and_hashes_seed(tmp_path) -> None:
    created = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)
    registry = tmp_path / "scenario_registry.jsonl"

    row = lock_forward_scenario(
        registry,
        scenario_id="scenario-001",
        created_at=created,
        seed_cutoff_time=created - timedelta(seconds=1),
        seed_packet={"news": ["a"], "funding": 0.0001},
        source_hashes=["abc", "def"],
        model="mirofish-oasis",
        mirofish_commit="117ed37758cdc96f73b7d5e0d22713c50439695f",
        personas=["retail momentum trader", "market maker"],
        prediction_horizon_hours=12,
        prediction=_prediction(),
        confidence=0.6,
    )

    assert row["locked"] is True
    assert row["seed_hash"]
    assert row["actual_evaluation_deadline"] == (created + timedelta(hours=12)).isoformat()
    assert len(registry.read_text().splitlines()) == 1

    with pytest.raises(ValueError, match="already exists"):
        lock_forward_scenario(
            registry,
            scenario_id="scenario-001",
            created_at=created,
            seed_cutoff_time=created,
            seed_packet={},
            source_hashes=[],
            model="mirofish-oasis",
            mirofish_commit="same",
            personas=[],
            prediction_horizon_hours=12,
            prediction=_prediction(),
            confidence=0.5,
        )


def test_forward_scenario_rejects_future_seed_and_early_evaluation(tmp_path) -> None:
    created = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)
    registry = tmp_path / "scenario_registry.jsonl"

    with pytest.raises(ValueError, match="seed_cutoff"):
        lock_forward_scenario(
            registry,
            scenario_id="future-seed",
            created_at=created,
            seed_cutoff_time=created + timedelta(seconds=1),
            seed_packet={},
            source_hashes=[],
            model="mirofish-oasis",
            mirofish_commit="x",
            personas=[],
            prediction_horizon_hours=12,
            prediction=_prediction(),
            confidence=0.5,
        )

    lock_forward_scenario(
        registry,
        scenario_id="scenario-002",
        created_at=created,
        seed_cutoff_time=created,
        seed_packet={},
        source_hashes=[],
        model="mirofish-oasis",
        mirofish_commit="x",
        personas=[],
        prediction_horizon_hours=12,
        prediction=_prediction(),
        confidence=0.5,
    )
    with pytest.raises(ValueError, match="deadline"):
        append_scenario_evaluation(
            registry,
            scenario_id="scenario-002",
            evaluated_at=created + timedelta(hours=1),
            actual_outcome={"return": 0.01},
            score={"direction_correct": True},
        )


def test_scenario_evaluation_appends_without_rewriting_prediction(tmp_path) -> None:
    created = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)
    registry = tmp_path / "scenario_registry.jsonl"
    original = lock_forward_scenario(
        registry,
        scenario_id="scenario-003",
        created_at=created,
        seed_cutoff_time=created,
        seed_packet={"state": "known"},
        source_hashes=["a"],
        model="mirofish-oasis",
        mirofish_commit="x",
        personas=["macro fund"],
        prediction_horizon_hours=12,
        prediction=_prediction(),
        confidence=0.7,
    )

    append_scenario_evaluation(
        registry,
        scenario_id="scenario-003",
        evaluated_at=created + timedelta(hours=13),
        actual_outcome={"return": -0.02},
        score={"direction_correct": True},
    )

    rows = [json.loads(line) for line in registry.read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0] == original
    assert rows[1]["record_type"] == "EVALUATION"
    assert rows[1]["scenario_id"] == "scenario-003"
