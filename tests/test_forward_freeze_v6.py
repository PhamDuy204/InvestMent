import json

from crypto_research.run_v6 import freeze_candidate, verify_frozen_candidate


def test_freeze_hash_verifies_canonical_config(tmp_path):
    freeze_candidate(
        {"horizon": 720, "risk": 1.0},
        artifact_root=tmp_path,
        timestamp="2026-08-11T00:00:00Z",
        total_trial_count=800,
    )
    assert verify_frozen_candidate(tmp_path / "forward_freeze.json")


def test_freeze_hash_detects_config_mutation(tmp_path):
    path = tmp_path / "forward_freeze.json"
    freeze_candidate(
        {"horizon": 720, "risk": 1.0},
        artifact_root=tmp_path,
        timestamp="2026-08-11T00:00:00Z",
        total_trial_count=800,
    )
    payload = json.loads(path.read_text())
    payload["candidate_config"]["risk"] = 2.0
    path.write_text(json.dumps(payload))
    assert not verify_frozen_candidate(path)
