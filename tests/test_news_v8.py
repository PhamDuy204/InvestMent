from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from crypto_research.news_v8 import (
    assign_narrative_clusters,
    causal_news_for_decision,
    normalize_article,
    validate_llm_extraction,
)


def test_article_first_seen_controls_causal_availability_and_future_mutation() -> None:
    early = normalize_article(
        source="official",
        source_id="a",
        title="ETF filing approved",
        content="A regulator published an approval notice.",
        published_at=datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc),
        first_seen_at=datetime(2026, 8, 19, 10, 1, tzinfo=timezone.utc),
        author="Regulator",
    )
    future = normalize_article(
        source="newswire",
        source_id="b",
        title="Market reacts",
        content="Bitcoin moved after the filing.",
        published_at=datetime(2026, 8, 19, 11, 0, tzinfo=timezone.utc),
        first_seen_at=datetime(2026, 8, 19, 11, 1, tzinfo=timezone.utc),
        author="Reporter",
    )
    frame = pd.DataFrame([early, future])
    decision = pd.Timestamp("2026-08-19T10:30:00Z")

    before = causal_news_for_decision(frame, decision_time=decision)
    mutated = frame.copy()
    mutated.loc[1, "content"] = "future outcome rewritten"
    after = causal_news_for_decision(mutated, decision_time=decision)

    assert before["source_id"].tolist() == ["a"]
    pd.testing.assert_frame_equal(before, after)


def test_narrative_cluster_groups_copied_story_but_not_unrelated_story() -> None:
    rows = [
        normalize_article(
            source="wire-a",
            source_id="a",
            title="Bitcoin ETF approval sends crypto higher",
            content="Regulator approves the bitcoin ETF after a long review process.",
            published_at=datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc),
            first_seen_at=datetime(2026, 8, 19, 10, 1, tzinfo=timezone.utc),
        ),
        normalize_article(
            source="wire-b",
            source_id="b",
            title="Bitcoin ETF approval sends crypto higher",
            content="Regulator approves the bitcoin ETF after a long review process today.",
            published_at=datetime(2026, 8, 19, 10, 2, tzinfo=timezone.utc),
            first_seen_at=datetime(2026, 8, 19, 10, 3, tzinfo=timezone.utc),
        ),
        normalize_article(
            source="other",
            source_id="c",
            title="Exchange maintenance scheduled",
            content="A trading venue will perform wallet maintenance this weekend.",
            published_at=datetime(2026, 8, 19, 10, 4, tzinfo=timezone.utc),
            first_seen_at=datetime(2026, 8, 19, 10, 5, tzinfo=timezone.utc),
        ),
    ]

    clustered = assign_narrative_clusters(pd.DataFrame(rows))

    assert clustered.loc[0, "narrative_cluster_id"] == clustered.loc[1, "narrative_cluster_id"]
    assert clustered.loc[0, "narrative_cluster_id"] != clustered.loc[2, "narrative_cluster_id"]


def test_llm_extraction_rejects_trade_instruction_and_bounds_features() -> None:
    valid = {
        "event_type": "regulatory_approval",
        "asset_scope": ["BTC"],
        "sentiment": 0.7,
        "confidence": 0.82,
        "uncertainty": 0.2,
        "novelty": 0.9,
        "impact_horizon_hours": 12,
        "source_quality": 0.95,
    }
    assert validate_llm_extraction(valid) == valid

    with pytest.raises(ValueError, match="trade"):
        validate_llm_extraction({**valid, "action": "BUY BTC"})

    with pytest.raises(ValueError, match="sentiment"):
        validate_llm_extraction({**valid, "sentiment": 2.0})
