import pytest

from crypto_research.trials_v7 import V7TrialRegistry


def test_registry_starts_at_858_and_persists(tmp_path):
    path = tmp_path / "experiment_registry.csv"
    registry = V7TrialRegistry(path)
    row = registry.record("A", "exact_v6_control", "CONTROL", phase="first_line")
    assert row["trial_number"] == 858
    registry.to_csv()
    loaded = V7TrialRegistry(path)
    assert loaded.total_count == 858


def test_first_line_cap_blocks_25th_trial(tmp_path):
    registry = V7TrialRegistry(tmp_path / "registry.csv", first_line_cap=24)
    for index in range(24):
        registry.record("H", f"first-{index}", "INSPECTED", phase="first_line")
    with pytest.raises(RuntimeError, match="first-line"):
        registry.record("H", "overflow", "INSPECTED", phase="first_line")


def test_total_cap_blocks_61st_v7_trial(tmp_path):
    registry = V7TrialRegistry(tmp_path / "registry.csv", total_cap=60)
    for index in range(60):
        registry.record("X", f"trial-{index}", "INSPECTED", phase="escalation")
    with pytest.raises(RuntimeError, match="total"):
        registry.record("X", "overflow", "INSPECTED", phase="escalation")
