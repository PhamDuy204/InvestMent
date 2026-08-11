from crypto_research.v7_cycle import REQUIRED_V7_ARTIFACTS, ensure_v7_artifact_contract


def test_required_v7_artifacts_cover_full_contract(tmp_path):
    expected = {
        "v7_protocol.json",
        "literature_registry.json",
        "hypothesis_registry.jsonl",
        "experiment_registry.csv",
        "agent_research_log.jsonl",
        "research_blackboard.jsonl",
        "factor_observatory.json",
        "failure_ledger.csv.gz",
        "do_not_repeat.json",
        "qh_imbalance_results.json",
        "dispersion_results.json",
        "weak_edge_results.json",
        "combination_results.json",
        "error_attribution.json",
        "stress_results.json",
        "dsr_results.json",
        "pbo_results.json",
        "final_candidate.json",
        "forward_freeze.json",
        "forward_observations.csv.gz",
        "readiness_gate.json",
        "final_report.md",
    }
    assert expected == REQUIRED_V7_ARTIFACTS
    assert ensure_v7_artifact_contract(tmp_path) == sorted(expected)
