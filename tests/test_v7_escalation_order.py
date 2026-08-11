from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_research.hypotheses_v7 import ResearchHypothesis
from crypto_research.run_v7_research import maybe_run_v7_escalation


def _hypothesis_dict():
    hypothesis = ResearchHypothesis(
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
    payload = hypothesis.__dict__.copy()
    payload["causal_inputs"] = list(hypothesis.causal_inputs)
    payload["source_ids"] = list(hypothesis.source_ids)
    return payload


def _council(context, *, client, blocked_fingerprints):
    del client, blocked_fingerprints
    assert context["research_triggers"] == ["WRONG_SIDE"]
    return {
        "status": "COMPLETED",
        "approved_hypotheses": [_hypothesis_dict()],
        "locally_rejected_hypotheses": [],
        "audit": {"dissent": []},
    }


def _factor_runner(order):
    def runner(*, context, hypothesis):
        del context, hypothesis
        order.append("factor")
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

    return runner


def _ml_frame():
    index = np.arange(80)
    return pd.DataFrame(
        {
            "dispersion_iqr": 0.02 + 0.01 * np.cos(index / 7.0),
            "funding_crowding": np.sin(index / 5.0),
            "realized_net_contribution": np.where(index % 3 == 0, -0.002, 0.003),
        }
    )


def test_escalation_order_is_factor_then_optional_ml_then_optional_scenario(tmp_path):
    order = []

    def ml_runner(*, probabilities, config, evaluation):
        del probabilities, config, evaluation
        order.append("ml")
        return {"status": "INSPECTED", "metrics": {"net_return": 0.01}}

    def scenario_runner(*, event_study):
        assert event_study["status"] == "ADMITTED_FOR_CHALLENGE"
        order.append("scenario")
        return {"status": "INSPECTED", "metrics": {"net_return": 0.005}}

    result = maybe_run_v7_escalation(
        {"escalation_required": True},
        artifact_root=tmp_path,
        context={
            "research_triggers": ["WRONG_SIDE"],
            "unresolved_after_factor": True,
            "unresolved_after_ml": True,
        },
        client=object(),
        backtest_runner=_factor_runner(order),
        council_runner=_council,
        ml_train=_ml_frame(),
        ml_evaluation=_ml_frame().iloc[:20].copy(),
        admitted_features={"dispersion_iqr", "funding_crowding"},
        ml_backtest_runner=ml_runner,
        scenario_event_study={"status": "ADMITTED_FOR_CHALLENGE", "incremental_net_bps": 1.0},
        scenario_backtest_runner=scenario_runner,
    )
    assert order == ["factor", "ml", "scenario"]
    assert result["status"] == "COMPLETED"
    assert result["ml_result"]["status"] == "INSPECTED"
    assert result["scenario_result"]["status"] == "INSPECTED"
    registry = pd.read_csv(tmp_path / "experiment_registry.csv")
    assert registry["trial_number"].tolist() == [858, 859, 860]
    assert registry["stage"].tolist() == ["FACTOR", "ML", "SCENARIO"]


def test_later_tiers_do_not_run_without_explicit_unresolved_flags(tmp_path):
    order = []

    def bomb(*args, **kwargs):
        raise AssertionError("later tier must not run")

    result = maybe_run_v7_escalation(
        {"escalation_required": True},
        artifact_root=tmp_path,
        context={"research_triggers": ["WRONG_SIDE"]},
        client=object(),
        backtest_runner=_factor_runner(order),
        council_runner=_council,
        ml_train=_ml_frame(),
        ml_evaluation=_ml_frame().iloc[:20].copy(),
        admitted_features={"dispersion_iqr", "funding_crowding"},
        ml_backtest_runner=bomb,
        scenario_event_study={"status": "ADMITTED_FOR_CHALLENGE", "incremental_net_bps": 1.0},
        scenario_backtest_runner=bomb,
    )
    assert order == ["factor"]
    assert result["ml_result"]["status"] == "ML_NOT_RUN_NO_UNRESOLVED_GAP"
    assert result["scenario_result"]["status"] == "SCENARIO_NOT_RUN_NO_UNRESOLVED_GAP"
