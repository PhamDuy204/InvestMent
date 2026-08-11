from pathlib import Path

REQUIRED_V7_ARTIFACTS = {
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


def ensure_v7_artifact_contract(root: str | Path) -> list[str]:
    base = Path(root)
    return sorted(name for name in REQUIRED_V7_ARTIFACTS if not (base / name).exists())
