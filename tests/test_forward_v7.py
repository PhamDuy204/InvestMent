import json

import pandas as pd

from crypto_research.forward_v7 import (
    evaluate_a1_readiness,
    freeze_v7_candidate,
    verify_v7_freeze,
)


def _freeze(tmp_path):
    return freeze_v7_candidate(
        {"direction": "H12", "execution": "MARKET", "leverage": 1.0},
        artifact_root=tmp_path,
        timestamp="2026-08-11T00:00:00Z",
        total_trial_count=861,
        source_sha="abc123",
        causal_schema_version="v7-causal-1",
    )


def _forward(start: str, periods: int, freq: str = "12h") -> pd.DataFrame:
    timestamps = pd.date_range(start, periods=periods, freq=freq, tz="UTC")
    return pd.DataFrame({"decision_timestamp": timestamps, "eligible_h12": [True] * len(timestamps)})


def _evaluate(forward, freeze, **overrides):
    values = {
        "candidate_hash": freeze["candidate_hash_sha256"],
        "ret_10bps": 0.05,
        "profit_factor": 1.20,
        "sharpe": 0.80,
        "ret_20bps": 0.01,
        "delay_1h_return": 0.01,
        "liquidation_count": 0,
        "exposure_violation_count": 0,
        "margin_violation_count": 0,
        "forward_driven_retuning": False,
    }
    values.update(overrides)
    return evaluate_a1_readiness(forward, freeze, **values)


def test_freeze_hash_detects_config_source_schema_or_trial_mutation(tmp_path):
    freeze = _freeze(tmp_path)
    path = tmp_path / "forward_freeze.json"
    assert verify_v7_freeze(path)
    for field, mutate in (
        ("candidate_config", lambda value: {**value, "leverage": 2.0}),
        ("source_sha", lambda value: value + "x"),
        ("causal_schema_version", lambda value: value + "x"),
        ("total_trial_count_at_freeze", lambda value: value + 1),
    ):
        payload = json.loads(path.read_text())
        payload[field] = mutate(payload[field])
        path.write_text(json.dumps(payload))
        assert not verify_v7_freeze(path)
        path.write_text(json.dumps(freeze))


def test_a1_requires_30_untouched_calendar_days(tmp_path):
    freeze = _freeze(tmp_path)
    forward = _forward("2026-08-12", 58, "12h")
    result = _evaluate(forward, freeze)
    assert result["calendar_days"] == 29
    assert result["verdict"] == "NEEDS_MORE_RESEARCH"
    assert "minimum_calendar_days" in result["failed_gates"]


def test_a1_requires_40_eligible_h12_observations(tmp_path):
    freeze = _freeze(tmp_path)
    forward = _forward("2026-08-12", 39, "24h")
    result = _evaluate(forward, freeze)
    assert result["eligible_h12_observations"] == 39
    assert result["calendar_days"] >= 30
    assert result["verdict"] == "NEEDS_MORE_RESEARCH"
    assert "minimum_h12_observations" in result["failed_gates"]


def test_a1_rejects_negative_20bps_or_delay_return(tmp_path):
    freeze = _freeze(tmp_path)
    forward = _forward("2026-08-12", 60, "12h")
    cost = _evaluate(forward, freeze, ret_20bps=-0.001)
    delay = _evaluate(forward, freeze, delay_1h_return=-0.001)
    assert "nonnegative_20bps" in cost["failed_gates"]
    assert "nonnegative_delay_1h" in delay["failed_gates"]
    assert cost["verdict"] == delay["verdict"] == "NEEDS_MORE_RESEARCH"


def test_a1_rejects_hash_mismatch_or_forward_retuning(tmp_path):
    freeze = _freeze(tmp_path)
    forward = _forward("2026-08-12", 60, "12h")
    mismatch = _evaluate(forward, freeze, candidate_hash="wrong")
    retuned = _evaluate(forward, freeze, forward_driven_retuning=True)
    assert "candidate_hash_unchanged" in mismatch["failed_gates"]
    assert "zero_forward_driven_retuning" in retuned["failed_gates"]


def test_a1_ready_only_when_every_gate_passes(tmp_path):
    freeze = _freeze(tmp_path)
    forward = _forward("2026-08-12", 60, "12h")
    result = _evaluate(forward, freeze)
    assert result["failed_gates"] == []
    assert result["verdict"] == "READY_FOR_PAPER_TRADING"
