import json
from pathlib import Path

import pandas as pd


ART = Path("artifacts/multi_asset_v7")


def test_v7_real_research_registry_is_append_only_through_trial_868() -> None:
    registry = pd.read_csv(ART / "experiment_registry.csv")
    trials = registry["trial_number"].astype(int).tolist()

    assert trials == list(range(858, 869))
    assert registry["trial_number"].is_unique
    assert registry.loc[registry["trial_number"] == 868, "hypothesis"].item() == "H7_lagged_rv_inverse_vol_ablation"
    assert registry.loc[registry["trial_number"] == 868, "status"].item() == "REJECTED_INNER"


def test_v7_synced_research_evidence_has_no_admitted_factor_or_frozen_candidate() -> None:
    h7 = json.loads((ART / "h7_lagvol_ablation_results.json").read_text(encoding="utf-8"))
    observatory = json.loads((ART / "factor_observatory.json").read_text(encoding="utf-8"))
    council = json.loads((ART / "council_iteration_4_summary.json").read_text(encoding="utf-8"))

    assert h7["trial_number"] == 868
    assert h7["status"] == "REJECTED_INNER"
    assert not any(item["admitted"] for item in observatory["factors"])
    assert council["approved_hypothesis_ids"] == []
    assert council["performance_trial_count_after"] == 868
    assert not list(ART.glob("*freeze*"))
