import json
from types import SimpleNamespace

from crypto_research.v4_research import run_v4_research


class FakeCompletions:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(reply)))]
        )


class FakeClient:
    def __init__(self, replies):
        self.chat = SimpleNamespace(completions=FakeCompletions(replies))


def hypothesis(name="turnover hysteresis"):
    return {
        "name": name,
        "experiment_family": "turnover_control",
        "mechanism": "avoid small target changes",
        "minimum_change": "add a no-trade band",
        "expected_effect": "lower turnover",
        "falsification": "reject if frozen validation or delay stress worsens",
        "action_scope": "research_only",
    }


def test_runner_chains_scout_audit_synthesis_and_writes_registry(tmp_path):
    h = hypothesis()
    client = FakeClient(
        [
            {"hypotheses": [h]},
            {"accepted": [h], "rejected": []},
            {"ranked_hypotheses": [h]},
        ]
    )
    result = run_v4_research(
        client,
        {"api_key": "must disappear", "failure_codes": ["COST_SENSITIVE"]},
        artifact_dir=tmp_path,
    )
    assert result["status"] == "COMPLETED"
    assert result["ranked_hypotheses"] == [h]
    assert [call["model"] for call in client.chat.completions.calls] == [
        "qwen/qwen3.6-27b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
    ]
    registry = json.loads((tmp_path / "v4_trial_registry.json").read_text())
    assert registry["llm_hypothesis_trials"] == 1
    assert registry["rows"][0]["status"] == "PROPOSED_AND_ACCEPTED"
    assert "must disappear" not in (tmp_path / "v4_research_log.json").read_text()


def test_scout_falls_back_to_gpt_oss_when_qwen_payload_is_invalid(tmp_path):
    h = hypothesis("fallback")
    client = FakeClient(
        [
            {"not_hypotheses": []},
            {"hypotheses": [h]},
            {"accepted": [h], "rejected": []},
            {"ranked_hypotheses": [h]},
        ]
    )
    result = run_v4_research(client, {"failure_codes": []}, artifact_dir=tmp_path)
    assert result["status"] == "COMPLETED"
    assert [call["model"] for call in client.chat.completions.calls[:2]] == [
        "qwen/qwen3.6-27b",
        "openai/gpt-oss-120b",
    ]


def test_rejected_scout_hypothesis_still_counts_as_trial(tmp_path):
    h = hypothesis("rejected")
    client = FakeClient(
        [
            {"hypotheses": [h]},
            {"accepted": [], "rejected": [{"name": "rejected", "reason": "not causal"}]},
            {"ranked_hypotheses": []},
        ]
    )
    run_v4_research(client, {"failure_codes": []}, artifact_dir=tmp_path)
    registry = json.loads((tmp_path / "v4_trial_registry.json").read_text())
    assert registry["llm_hypothesis_trials"] == 1
    assert registry["rows"][0]["status"] == "PROPOSED_AND_REJECTED"
