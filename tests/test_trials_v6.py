from crypto_research.trials_v6 import TrialRegistry


def test_registry_starts_from_v5_count_and_persists(tmp_path):
    path = tmp_path / "registry.csv"
    registry = TrialRegistry(path, prior_count=779)
    registry.record("B", "session_low_vol_h1", "REJECTED", metrics={"sharpe": 0.9})
    assert registry.total_count == 780
    registry.to_csv()
    loaded = TrialRegistry(path, prior_count=779)
    assert loaded.total_count == 780
    loaded.record("C", "burst_exit", "REJECTED")
    assert loaded.total_count == 781
