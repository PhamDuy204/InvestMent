from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_research.forward_v7 import freeze_v7_candidate
from crypto_research.hypotheses_v7 import ResearchHypothesis
from crypto_research.run_v7_research import (
    maybe_run_v7_escalation,
    run_factor_family_challenge,
    run_nonlinear_challenger,
    run_research_event_loop,
    run_scenario_challenge,
)
from crypto_research.trials_v7 import V7TrialRegistry


def _hypothesis():
    return ResearchHypothesis(
        hypothesis_id="h-derivatives-1",
        target_error="WRONG_SIDE",
        observation="wrong-side losses cluster in crowded derivatives states",
        causal_inputs=("funding", "open_interest_change"),
        expected_mechanism="derivatives crowding reduces H12 reliability",
        single_change="veto exposure increase under derivatives crowding",
        expected_effect="reduce wrong-side loss bps",
        cost_risk="may skip correct trades",
        invalidation_condition="evaluation net bps <= control",
        required_test="walk-forward 10bps 20bps plus1h",
        factor_family="derivatives",
        source_ids=("paper-1",),
        materially_new_evidence=False,
    )


def _factor_backtest(*, context, hypothesis):
    assert hypothesis.hypothesis_id == "h-derivatives-1"
    assert context["research_triggers"] == ["WRONG_SIDE"]
    return {
        "config": {"feature": "funding_crowding", "action": "veto_increase"},
        "metrics": {"net_return": 0.02, "sharpe": 0.9},
        "factor_evidence": {
            "factor_family": "derivatives",
            "feature_name": "funding_crowding",
            "source_ids": ["paper-1", "official-api"],
            "coverage_fraction": 0.90,
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
        },
    }


def test_no_trigger_does_not_call_council_or_backtest(tmp_path):
    def bomb(*args, **kwargs):
        raise AssertionError("must not be called")

    result = run_research_event_loop(
        {"research_triggers": []},
        client=object(),
        backtest_runner=bomb,
        artifact_root=tmp_path,
        council_runner=bomb,
    )
    assert result["status"] == "NO_RESEARCH_TRIGGER"
    assert not (tmp_path / "experiment_registry.csv").exists()


def test_budget_exhausted_before_council_or_backtest(tmp_path):
    registry = V7TrialRegistry(tmp_path / "experiment_registry.csv")
    for index in range(60):
        registry.record("X", f"trial-{index}", "INSPECTED", phase="escalation")
    registry.to_csv()

    def bomb(*args, **kwargs):
        raise AssertionError("must not be called after budget exhaustion")

    result = run_research_event_loop(
        {"research_triggers": ["WRONG_SIDE"]},
        client=object(),
        backtest_runner=bomb,
        artifact_root=tmp_path,
        council_runner=bomb,
    )
    assert result["status"] == "V7_TRIAL_BUDGET_EXHAUSTED"


def test_one_approved_factor_consumes_exactly_one_shared_trial(tmp_path):
    def council(context, *, client, blocked_fingerprints):
        del client, blocked_fingerprints
        assert context["research_triggers"] == ["WRONG_SIDE"]
        return {
            "status": "COMPLETED",
            "approved_hypotheses": [
                {
                    **_hypothesis().__dict__,
                    "causal_inputs": list(_hypothesis().causal_inputs),
                    "source_ids": list(_hypothesis().source_ids),
                }
            ],
            "validated_hypotheses": [],
            "locally_rejected_hypotheses": [],
            "evidence": {"evidence_cards": []},
            "audit": {"dissent": ["independent caution"]},
        }

    result = run_research_event_loop(
        {"research_triggers": ["WRONG_SIDE"]},
        client=object(),
        backtest_runner=_factor_backtest,
        artifact_root=tmp_path,
        council_runner=council,
    )
    registry = pd.read_csv(tmp_path / "experiment_registry.csv")
    assert result["status"] == "COMPLETED"
    assert registry["trial_number"].tolist() == [858]
    assert registry.loc[0, "phase"] == "escalation"
    assert result["factor_results"][0]["status"] == "ADMITTED"
    assert (tmp_path / "factor_observatory.json").exists()
    assert (tmp_path / "agent_research_log.jsonl").exists()
    assert (tmp_path / "hypothesis_registry.jsonl").exists()


def test_factor_challenge_registers_rejected_factor_as_one_trial(tmp_path):
    registry = V7TrialRegistry(tmp_path / "experiment_registry.csv")

    def rejected_runner(*, context, hypothesis):
        payload = _factor_backtest(context=context, hypothesis=hypothesis)
        payload["factor_evidence"]["incremental_net_bps"] = -1.0
        return payload

    result = run_factor_family_challenge(
        {"research_triggers": ["WRONG_SIDE"]},
        _hypothesis(),
        registry=registry,
        backtest_runner=rejected_runner,
        artifact_root=tmp_path,
    )
    registry.to_csv()
    assert result["status"] == "REJECTED"
    assert registry.total_count == 858


def test_valid_freeze_blocks_all_escalation(tmp_path):
    freeze_v7_candidate(
        {"direction": "H12", "execution": "MARKET", "leverage": 1.0},
        artifact_root=tmp_path,
        timestamp="2026-08-11T00:00:00Z",
        total_trial_count=858,
        source_sha="abc",
        causal_schema_version="v7-causal-1",
    )

    def bomb(*args, **kwargs):
        raise AssertionError("frozen V7 must not call research")

    result = maybe_run_v7_escalation(
        {"escalation_required": True},
        artifact_root=tmp_path,
        context={"research_triggers": ["WRONG_SIDE"]},
        client=object(),
        backtest_runner=bomb,
        council_runner=bomb,
    )
    assert result["status"] == "V7_FROZEN_NO_RETUNING"


def test_simple_first_candidate_skips_escalation(tmp_path):
    def bomb(*args, **kwargs):
        raise AssertionError("simple candidate should skip escalation")

    result = maybe_run_v7_escalation(
        {"escalation_required": False},
        artifact_root=tmp_path,
        context={"research_triggers": ["WRONG_SIDE"]},
        client=object(),
        backtest_runner=bomb,
        council_runner=bomb,
    )
    assert result["status"] == "SIMPLE_FIRST_NO_ESCALATION"


def _ml_train():
    index = np.arange(80)
    return pd.DataFrame(
        {
            "funding_crowding": np.sin(index / 5.0),
            "dispersion_iqr": 0.02 + 0.01 * np.cos(index / 7.0),
            "realized_net_contribution": np.where(index % 3 == 0, -0.002, 0.003),
        }
    )


def test_nonlinear_challenger_requires_two_admitted_features_and_uses_one_trial(tmp_path):
    registry = V7TrialRegistry(tmp_path / "experiment_registry.csv")
    ineligible = run_nonlinear_challenger(
        _ml_train(),
        _ml_train().iloc[:20].copy(),
        admitted_features={"funding_crowding"},
        registry=registry,
        strategy_backtest_runner=lambda **kwargs: {"metrics": {}},
    )
    assert ineligible["status"] == "ML_NOT_ELIGIBLE"
    assert registry.total_count == 857

    calls = []

    def runner(*, probabilities, config, evaluation):
        calls.append((probabilities.copy(), config, len(evaluation)))
        return {"metrics": {"net_return": 0.01, "sharpe": 0.7}, "status": "INSPECTED"}

    eligible = run_nonlinear_challenger(
        _ml_train(),
        _ml_train().iloc[:20].copy(),
        admitted_features={"funding_crowding", "dispersion_iqr"},
        registry=registry,
        strategy_backtest_runner=runner,
    )
    assert eligible["status"] == "INSPECTED"
    assert len(calls) == 1
    assert registry.total_count == 858


def test_scenario_challenge_only_spends_trial_after_event_study_admission(tmp_path):
    registry = V7TrialRegistry(tmp_path / "experiment_registry.csv")
    calls = []

    def runner(*, event_study):
        calls.append(event_study)
        return {"metrics": {"net_return": 0.01}, "status": "INSPECTED"}

    blocked = run_scenario_challenge(
        {"status": "INSUFFICIENT_EVENT_EVIDENCE"},
        registry=registry,
        backtest_runner=runner,
    )
    assert blocked["status"] == "SCENARIO_NOT_ELIGIBLE"
    assert registry.total_count == 857
    admitted = run_scenario_challenge(
        {"status": "ADMITTED_FOR_CHALLENGE", "incremental_net_bps": 1.0},
        registry=registry,
        backtest_runner=runner,
    )
    assert admitted["status"] == "INSPECTED"
    assert len(calls) == 1
    assert registry.total_count == 858
