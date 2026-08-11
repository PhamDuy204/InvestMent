import pandas as pd

from crypto_research.run_v6 import run_hierarchical_replay


def _log():
    times = pd.date_range("2026-01-01", periods=20, freq="12h", tz="UTC")
    rows = []
    for i, ts in enumerate(times):
        rows.append(
            {
                "decision_timestamp": ts,
                "symbol": "A",
                "previous_weight": 0.0,
                "target_weight": 0.2,
                "holding_return_label": 0.01 if i % 4 else -0.02,
                "funding_sum_label": 0.0,
                "effective_score": 0.01,
                "vol_state": "high" if i % 4 == 0 else "low",
                "burst_probability": 0.0,
                "flow_state": "neutral",
                "trend_state": "up",
            }
        )
    return pd.DataFrame(rows)


def test_hierarchical_replay_counts_candidates_from_779_and_writes_results(tmp_path):
    result = run_hierarchical_replay(
        _log(),
        artifact_root=tmp_path,
        candidate_specs=[
            {"stage": "B", "name": "high_vol_50", "high_vol_scale": 0.5},
            {"stage": "G", "name": "reserve_20", "reserve_fraction": 0.2},
        ],
        selection_fraction=0.6,
        complexity_penalty=0.0,
        prior_trials=779,
    )
    assert result["trial_count_after"] == 782
    assert (tmp_path / "experiment_registry.csv").exists()
    assert (tmp_path / "incremental_ablation.json").exists()
    assert "A" in result["stages"]
    assert "H" in result["stages"]
