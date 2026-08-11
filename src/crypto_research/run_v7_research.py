from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from crypto_research.diagnostics_v7 import load_do_not_repeat
from crypto_research.factor_observatory_v7 import (
    FactorEvidence,
    admit_factor,
    write_factor_observatory,
)
from crypto_research.forward_v7 import verify_v7_freeze
from crypto_research.groq_v7 import run_v7_research_council
from crypto_research.hypotheses_v7 import ResearchHypothesis
from crypto_research.reliability_ml_v7 import (
    ReliabilityModelConfig,
    fit_reliability_model,
    predict_reliability,
)
from crypto_research.trials_v7 import V7TrialRegistry

CouncilRunner = Callable[..., dict[str, Any]]
BacktestRunner = Callable[..., dict[str, Any]]


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def _hypothesis_from_dict(payload: dict[str, Any]) -> ResearchHypothesis:
    return ResearchHypothesis(
        hypothesis_id=str(payload["hypothesis_id"]),
        target_error=str(payload["target_error"]),
        observation=str(payload["observation"]),
        causal_inputs=tuple(str(item) for item in payload["causal_inputs"]),
        expected_mechanism=str(payload["expected_mechanism"]),
        single_change=str(payload["single_change"]),
        expected_effect=str(payload["expected_effect"]),
        cost_risk=str(payload["cost_risk"]),
        invalidation_condition=str(payload["invalidation_condition"]),
        required_test=str(payload["required_test"]),
        factor_family=str(payload["factor_family"]),
        source_ids=tuple(str(item) for item in payload["source_ids"]),
        materially_new_evidence=bool(payload.get("materially_new_evidence", False)),
    )


def _factor_evidence_from_dict(payload: dict[str, Any]) -> FactorEvidence:
    data = dict(payload)
    data["source_ids"] = tuple(str(item) for item in data["source_ids"])
    return FactorEvidence(**data)


def _load_observatory_rows(path: Path) -> list[FactorEvidence]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    rows: list[FactorEvidence] = []
    for item in payload.get("factors", []):
        if not isinstance(item, dict):
            continue
        data = {
            key: value
            for key, value in item.items()
            if key not in {"admitted", "rejection_reasons"}
        }
        try:
            rows.append(_factor_evidence_from_dict(data))
        except (KeyError, TypeError, ValueError):
            continue
    return rows


def run_factor_family_challenge(
    context: dict[str, Any],
    hypothesis: ResearchHypothesis,
    *,
    registry: V7TrialRegistry,
    backtest_runner: BacktestRunner,
    artifact_root: str | Path,
) -> dict[str, Any]:
    if registry.total_count >= 917:
        return {"status": "V7_TRIAL_BUDGET_EXHAUSTED"}
    outcome = backtest_runner(context=context, hypothesis=hypothesis)
    if "factor_evidence" not in outcome:
        raise ValueError("factor backtest must return factor_evidence")
    raw_evidence = outcome["factor_evidence"]
    evidence = (
        raw_evidence
        if isinstance(raw_evidence, FactorEvidence)
        else _factor_evidence_from_dict(dict(raw_evidence))
    )
    admitted = admit_factor(evidence)
    status = "ADMITTED" if admitted else "REJECTED"
    registry.record(
        "FACTOR",
        hypothesis.hypothesis_id,
        status,
        phase="escalation",
        config={
            "hypothesis": asdict(hypothesis),
            "backtest_config": outcome.get("config", {}),
        },
        metrics={
            "strategy": outcome.get("metrics", {}),
            "factor_evidence": asdict(evidence),
        },
    )
    root = Path(artifact_root)
    observatory_path = root / "factor_observatory.json"
    rows = _load_observatory_rows(observatory_path)
    rows.append(evidence)
    write_factor_observatory(rows, observatory_path)
    return {
        "status": status,
        "hypothesis_id": hypothesis.hypothesis_id,
        "factor_family": hypothesis.factor_family,
        "feature_name": evidence.feature_name,
        "factor_evidence": asdict(evidence),
        "metrics": outcome.get("metrics", {}),
    }


def run_research_event_loop(
    context: dict[str, Any],
    *,
    client: Any,
    backtest_runner: BacktestRunner,
    artifact_root: str | Path,
    council_runner: CouncilRunner = run_v7_research_council,
) -> dict[str, Any]:
    triggers = list(context.get("research_triggers", []))
    if not triggers:
        return {"status": "NO_RESEARCH_TRIGGER", "factor_results": []}

    root = Path(artifact_root)
    registry_path = root / "experiment_registry.csv"
    registry = V7TrialRegistry(registry_path)
    if registry.total_count >= 917:
        return {"status": "V7_TRIAL_BUDGET_EXHAUSTED", "factor_results": []}

    if client is None and council_runner is run_v7_research_council:
        result = {"status": "BLOCKED_GROQ_CLIENT_NOT_AVAILABLE", "factor_results": []}
        _append_jsonl(root / "agent_research_log.jsonl", result)
        return result

    blocked = load_do_not_repeat(root / "do_not_repeat.json")
    council = council_runner(
        context,
        client=client,
        blocked_fingerprints=blocked,
    )
    _append_jsonl(root / "agent_research_log.jsonl", council)

    approved_raw = [
        item for item in council.get("approved_hypotheses", []) if isinstance(item, dict)
    ]
    for raw in approved_raw:
        _append_jsonl(
            root / "hypothesis_registry.jsonl",
            {"status": "APPROVED_FOR_SINGLE_CHALLENGE", "hypothesis": raw},
        )
    for raw in council.get("locally_rejected_hypotheses", []):
        _append_jsonl(
            root / "hypothesis_registry.jsonl",
            {"status": "LOCALLY_REJECTED", "hypothesis": raw},
        )

    if not approved_raw:
        return {
            "status": "COMPLETED_NO_APPROVED_HYPOTHESIS",
            "factor_results": [],
            "council": council,
        }

    hypothesis = _hypothesis_from_dict(approved_raw[0])
    factor_result = run_factor_family_challenge(
        context,
        hypothesis,
        registry=registry,
        backtest_runner=backtest_runner,
        artifact_root=root,
    )
    registry.to_csv()
    return {
        "status": "COMPLETED",
        "factor_results": [factor_result],
        "council": council,
        "trial_count_after": registry.total_count,
        "uninspected_approved_hypothesis_count": max(len(approved_raw) - 1, 0),
    }


def run_nonlinear_challenger(
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    *,
    admitted_features: set[str],
    registry: V7TrialRegistry,
    strategy_backtest_runner: BacktestRunner,
) -> dict[str, Any]:
    if len(admitted_features) < 2:
        return {"status": "ML_NOT_ELIGIBLE", "reason": "fewer_than_two_admitted_features"}
    if registry.total_count >= 917:
        return {"status": "V7_TRIAL_BUDGET_EXHAUSTED"}
    feature_names = tuple(sorted(admitted_features))
    config = ReliabilityModelConfig(feature_names=feature_names)
    model = fit_reliability_model(
        train,
        config,
        admitted_features=admitted_features,
    )
    probabilities = predict_reliability(model, evaluation, config)
    outcome = strategy_backtest_runner(
        probabilities=probabilities,
        config=config,
        evaluation=evaluation,
    )
    status = str(outcome.get("status", "INSPECTED"))
    registry.record(
        "ML",
        "fixed_hist_gradient_boosting_reliability",
        status,
        phase="escalation",
        config=asdict(config),
        metrics=outcome.get("metrics", {}),
    )
    return {
        "status": status,
        "metrics": outcome.get("metrics", {}),
        "feature_names": list(feature_names),
        "probability_threshold": config.probability_threshold,
    }


def run_scenario_challenge(
    event_study: dict[str, Any],
    *,
    registry: V7TrialRegistry,
    backtest_runner: BacktestRunner,
) -> dict[str, Any]:
    if event_study.get("status") != "ADMITTED_FOR_CHALLENGE":
        return {"status": "SCENARIO_NOT_ELIGIBLE"}
    if registry.total_count >= 917:
        return {"status": "V7_TRIAL_BUDGET_EXHAUSTED"}
    outcome = backtest_runner(event_study=event_study)
    status = str(outcome.get("status", "INSPECTED"))
    registry.record(
        "SCENARIO",
        "scenario_swarm_event_risk_context",
        status,
        phase="escalation",
        config={"action": "event_risk_context", "direction_creation": False},
        metrics={
            "event_study": event_study,
            "strategy": outcome.get("metrics", {}),
        },
    )
    return {"status": status, "metrics": outcome.get("metrics", {})}


def maybe_run_v7_escalation(
    core_result: dict[str, Any],
    *,
    artifact_root: str | Path,
    context: dict[str, Any],
    client: Any,
    backtest_runner: BacktestRunner,
    council_runner: CouncilRunner = run_v7_research_council,
    ml_train: pd.DataFrame | None = None,
    ml_evaluation: pd.DataFrame | None = None,
    admitted_features: set[str] | None = None,
    ml_backtest_runner: BacktestRunner | None = None,
    scenario_event_study: dict[str, Any] | None = None,
    scenario_backtest_runner: BacktestRunner | None = None,
) -> dict[str, Any]:
    root = Path(artifact_root)
    freeze_path = root / "forward_freeze.json"
    if verify_v7_freeze(freeze_path):
        return {"status": "V7_FROZEN_NO_RETUNING"}
    if not bool(core_result.get("escalation_required", False)):
        return {"status": "SIMPLE_FIRST_NO_ESCALATION"}

    result = run_research_event_loop(
        context,
        client=client,
        backtest_runner=backtest_runner,
        artifact_root=root,
        council_runner=council_runner,
    )
    result["ml_result"] = {"status": "ML_NOT_RUN_NO_UNRESOLVED_GAP"}
    result["scenario_result"] = {"status": "SCENARIO_NOT_RUN_NO_UNRESOLVED_GAP"}
    if result.get("status") != "COMPLETED":
        return result

    registry_path = root / "experiment_registry.csv"
    if bool(context.get("unresolved_after_factor", False)):
        if (
            ml_train is not None
            and ml_evaluation is not None
            and admitted_features is not None
            and ml_backtest_runner is not None
        ):
            registry = V7TrialRegistry(registry_path)
            result["ml_result"] = run_nonlinear_challenger(
                ml_train,
                ml_evaluation,
                admitted_features=admitted_features,
                registry=registry,
                strategy_backtest_runner=ml_backtest_runner,
            )
            registry.to_csv()
        else:
            result["ml_result"] = {"status": "ML_NOT_RUN_MISSING_ELIGIBLE_INPUTS"}

    if bool(context.get("unresolved_after_ml", False)):
        if scenario_event_study is not None and scenario_backtest_runner is not None:
            registry = V7TrialRegistry(registry_path)
            result["scenario_result"] = run_scenario_challenge(
                scenario_event_study,
                registry=registry,
                backtest_runner=scenario_backtest_runner,
            )
            registry.to_csv()
        else:
            result["scenario_result"] = {"status": "SCENARIO_NOT_RUN_MISSING_ELIGIBLE_INPUTS"}

    final_registry = V7TrialRegistry(registry_path)
    result["trial_count_after"] = final_registry.total_count
    return result
