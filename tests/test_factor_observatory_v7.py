import json

from crypto_research.factor_observatory_v7 import (
    FACTOR_FAMILIES,
    FactorEvidence,
    admit_factor,
    factor_rejection_reasons,
    write_factor_observatory,
)


def _evidence(**overrides):
    values = {
        "factor_family": "derivatives",
        "feature_name": "funding_crowding",
        "source_ids": ("paper-1", "official-api"),
        "coverage_fraction": 0.95,
        "causal_available": True,
        "source_quality": "peer_reviewed",
        "stability_score": 0.70,
        "target_error": "WRONG_SIDE",
        "association_value": 0.20,
        "incremental_net_bps": 3.0,
        "incremental_sharpe_delta": 0.10,
        "turnover_delta": -0.02,
        "evaluation_fold_count": 3,
        "reverse_causality_checked": True,
        "status": "OBSERVED",
    }
    values.update(overrides)
    return FactorEvidence(**values)


def test_factor_family_set_is_fixed():
    assert FACTOR_FAMILIES == {
        "microstructure",
        "derivatives",
        "cross_asset_macro",
        "on_chain",
        "news_event",
        "attention_sentiment",
        "cross_sectional",
        "execution_risk",
        "scenario_swarm",
    }


def test_good_factor_passes_fixed_admission_rule():
    evidence = _evidence()
    assert factor_rejection_reasons(evidence) == []
    assert admit_factor(evidence) is True


def test_admission_rejects_each_required_failure_mode():
    cases = [
        (_evidence(causal_available=False), "not_causally_available"),
        (_evidence(coverage_fraction=0.69), "coverage_below_0_70"),
        (_evidence(source_quality="unverified_blog_only"), "source_quality_not_primary_official_or_peer_reviewed"),
        (_evidence(stability_score=0.49), "stability_below_0_50"),
        (_evidence(evaluation_fold_count=1), "fewer_than_two_evaluation_folds"),
        (_evidence(incremental_net_bps=0.0), "nonpositive_incremental_net_bps"),
        (_evidence(incremental_sharpe_delta=-0.01), "negative_incremental_sharpe_delta"),
    ]
    for evidence, expected in cases:
        reasons = factor_rejection_reasons(evidence)
        assert expected in reasons
        assert admit_factor(evidence) is False


def test_attention_sentiment_requires_reverse_causality_check():
    evidence = _evidence(
        factor_family="attention_sentiment",
        feature_name="search_attention",
        reverse_causality_checked=False,
    )
    assert factor_rejection_reasons(evidence) == ["reverse_causality_not_checked"]
    assert admit_factor(evidence) is False


def test_observatory_serializes_admitted_and_rejected_rows_with_reasons(tmp_path):
    rows = [_evidence(), _evidence(feature_name="bad", coverage_fraction=0.2)]
    path = write_factor_observatory(rows, tmp_path / "factor_observatory.json")
    payload = json.loads(path.read_text())
    assert payload["status"] == "EVALUATED"
    assert len(payload["factors"]) == 2
    assert payload["factors"][0]["admitted"] is True
    assert payload["factors"][0]["rejection_reasons"] == []
    assert payload["factors"][1]["admitted"] is False
    assert payload["factors"][1]["rejection_reasons"] == ["coverage_below_0_70"]
