from pathlib import Path

import pytest

from crypto_research.diagnostics_v7 import mechanism_fingerprint
from crypto_research.hypotheses_v7 import (
    ResearchHypothesis,
    build_experiment_manifest,
    validate_hypothesis,
)


def _hypothesis(*, single_change: str = "veto exposure increase when derivatives crowding conflicts with H12", materially_new_evidence: bool = False):
    return ResearchHypothesis(
        hypothesis_id="h-derivatives-1",
        target_error="WRONG_SIDE",
        observation="wrong-side clusters in crowded derivatives states",
        causal_inputs=("funding", "open_interest_change"),
        expected_mechanism="derivatives crowding reduces H12 reliability",
        single_change=single_change,
        expected_effect="reduce wrong-side loss bps",
        cost_risk="may skip correct trades",
        invalidation_condition="evaluation net bps <= control or WRONG_SIDE does not improve",
        required_test="walk-forward 10bps 20bps plus1h",
        factor_family="derivatives",
        source_ids=("paper-derivatives-1",),
        materially_new_evidence=materially_new_evidence,
    )


def test_direct_direction_hypothesis_is_rejected():
    bad = _hypothesis(single_change="go short BTC when funding is high")
    with pytest.raises(ValueError, match="direct direction"):
        validate_hypothesis(bad, blocked_fingerprints=set())


def test_duplicate_failed_mechanism_is_blocked_without_material_new_evidence():
    hypothesis = _hypothesis()
    fingerprint = mechanism_fingerprint(
        hypothesis.target_error,
        hypothesis.expected_mechanism,
        list(hypothesis.causal_inputs),
        hypothesis.single_change,
    )
    with pytest.raises(ValueError, match="do-not-repeat"):
        validate_hypothesis(hypothesis, blocked_fingerprints={fingerprint})
    validate_hypothesis(
        _hypothesis(materially_new_evidence=True),
        blocked_fingerprints={fingerprint},
    )


def test_manifest_contains_only_research_actions():
    good = validate_hypothesis(_hypothesis(), blocked_fingerprints=set())
    manifest = build_experiment_manifest(
        good,
        train_window=("2024-01-01", "2024-12-31"),
        evaluation_window=("2025-01-01", "2025-06-30"),
    )
    assert set(manifest.allowed_actions) <= {
        "veto_entry",
        "veto_increase",
        "scale_increase",
        "reliability_score",
        "risk_context",
        "event_risk_context",
    }
    assert manifest.cost_bps == (10.0, 20.0)
    assert manifest.delay_minutes == (0, 60)


def test_v7_local_skills_encode_required_research_rules():
    paths = [
        Path("skills/v7-research-scientist/SKILL.md"),
        Path("skills/v7-methodology-auditor/SKILL.md"),
    ]
    required = (
        "research/backtest only",
        "no direct long/short",
        "future/oracle/forward",
        "one mechanism",
        "invalidation",
        "transaction cost",
        "do-not-repeat",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        for phrase in required:
            assert phrase in text
