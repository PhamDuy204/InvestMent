import json

import pandas as pd

from crypto_research.core_cycle_v7 import run_v7_core_cycle
from crypto_research.v7_cycle import ensure_v7_artifact_contract


def _inputs():
    times = pd.date_range("2026-01-01", periods=12, freq="12h", tz="UTC")
    decision_rows = []
    qh_rows = []
    for index, timestamp in enumerate(times):
        for symbol, side in (("A", 1.0), ("B", -1.0)):
            realized = 0.01 if index % 3 else -0.015
            score = 0.04 * side
            decision_rows.append(
                {
                    "decision_timestamp": timestamp,
                    "symbol": symbol,
                    "target_weight": 0.2 * side,
                    "holding_return_label": realized * side,
                    "funding_sum_label": 0.0,
                    "effective_score": score,
                    "realized_net_contribution": realized * 0.2,
                    "fold": index // 4,
                }
            )
            qh_rows.append(
                {
                    "decision_timestamp": timestamp,
                    "symbol": symbol,
                    "qh_order_imbalance": score * 5.0,
                    "qh_abs_order_imbalance": abs(score * 5.0),
                    "qh_trade_count": 5,
                }
            )
    decisions = pd.DataFrame(decision_rows)
    qh = pd.DataFrame(qh_rows)
    dispersion = pd.DataFrame(
        {
            "decision_timestamp": times,
            "dispersion_iqr": [0.01 + index * 0.001 for index in range(len(times))],
            "eligible_symbol_count": [2] * len(times),
        }
    )
    return decisions, qh, dispersion


def test_core_cycle_writes_full_auditable_contract_without_fabricating_evidence(tmp_path):
    decisions, qh, dispersion = _inputs()
    result = run_v7_core_cycle(
        decisions,
        qh,
        dispersion,
        artifact_root=tmp_path,
        source_sha="deadbeef",
        freeze_timestamp="2026-08-11T00:00:00Z",
    )
    assert result["escalation_required"] is True
    assert ensure_v7_artifact_contract(tmp_path) == []

    protocol = json.loads((tmp_path / "v7_protocol.json").read_text())
    assert protocol["starting_trial_count"] == 857
    assert protocol["first_line_trial_cap"] == 24
    assert protocol["total_v7_trial_cap"] == 60
    assert protocol["execution_mode"] == "MARKET"
    assert protocol["recommended_effective_leverage"] == 1.0

    candidate = json.loads((tmp_path / "final_candidate.json").read_text())
    freeze = json.loads((tmp_path / "forward_freeze.json").read_text())
    readiness = json.loads((tmp_path / "readiness_gate.json").read_text())
    stress = json.loads((tmp_path / "stress_results.json").read_text())
    dsr = json.loads((tmp_path / "dsr_results.json").read_text())
    pbo = json.loads((tmp_path / "pbo_results.json").read_text())

    assert candidate["status"] == "PRE_FREEZE_ESCALATION_REQUIRED"
    assert freeze["status"] == "NOT_FROZEN_ESCALATION_PENDING"
    assert readiness["verdict"] == "NEEDS_MORE_RESEARCH"
    assert "candidate_not_frozen" in readiness["failed_gates"]
    assert stress["status"] == "NOT_EVALUATED_ACCOUNT_PATH_NOT_SUPPLIED"
    assert dsr["status"] == "NOT_EVALUATED_ALIGNED_CANDIDATE_RETURNS_NOT_SUPPLIED"
    assert pbo["status"] == "NOT_EVALUATED_ALIGNED_CANDIDATE_RETURNS_NOT_SUPPLIED"

    forward = pd.read_csv(tmp_path / "forward_observations.csv.gz")
    assert forward.empty
    assert set(forward.columns) == {
        "decision_timestamp",
        "eligible_h12",
        "candidate_hash_sha256",
        "net_return",
    }
    report = (tmp_path / "final_report.md").read_text()
    assert "untouched forward evidence" in report.lower()
    assert report.rstrip().endswith("NEEDS_MORE_RESEARCH")


def test_core_cycle_writes_explicit_core_only_research_placeholders(tmp_path):
    decisions, qh, dispersion = _inputs()
    run_v7_core_cycle(
        decisions,
        qh,
        dispersion,
        artifact_root=tmp_path,
        source_sha="deadbeef",
        freeze_timestamp="2026-08-11T00:00:00Z",
    )
    literature = json.loads((tmp_path / "literature_registry.json").read_text())
    factors = json.loads((tmp_path / "factor_observatory.json").read_text())
    assert literature["status"] == "NOT_RUN_CORE_ONLY"
    assert factors["status"] == "NOT_RUN_CORE_ONLY"
    for name in ("hypothesis_registry.jsonl", "agent_research_log.jsonl", "research_blackboard.jsonl"):
        first = json.loads((tmp_path / name).read_text().splitlines()[0])
        assert first["status"] == "NOT_RUN_CORE_ONLY"
