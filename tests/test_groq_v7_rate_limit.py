import json
from types import SimpleNamespace

import pytest

from crypto_research.groq_v7 import _chat_json


class _RateLimitOnceCompletions:
    def __init__(self) -> None:
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            error = RuntimeError("rate limit")
            error.status_code = 429
            error.response = SimpleNamespace(headers={"retry-after": "0"})
            raise error
        payload = {"evidence_cards": [], "evidence_gaps": []}
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
        )


def test_chat_json_retries_one_transient_429_without_changing_model() -> None:
    completions = _RateLimitOnceCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    result = _chat_json(
        client,
        model="openai/gpt-oss-120b",
        role="evidence_scout",
        context={},
    )

    assert result == {"evidence_cards": [], "evidence_gaps": []}
    assert completions.calls == 2


def test_chat_json_does_not_retry_non_rate_limit_errors() -> None:
    class _Failing:
        def create(self, **kwargs):
            del kwargs
            raise RuntimeError("boom")

    client = SimpleNamespace(chat=SimpleNamespace(completions=_Failing()))
    with pytest.raises(RuntimeError, match="boom"):
        _chat_json(
            client,
            model="openai/gpt-oss-120b",
            role="evidence_scout",
            context={},
        )
