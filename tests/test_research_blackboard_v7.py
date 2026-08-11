import pytest

from crypto_research.research_blackboard_v7 import (
    EvidenceCard,
    append_evidence_card,
    load_evidence_cards,
)


def _card(card_id: str, claim: str, contradictory=()):
    return EvidenceCard(
        card_id=card_id,
        author_agent="evidence_scout",
        claim=claim,
        source_ids=("paper-1",),
        timestamp_utc="2026-08-11T04:00:00Z",
        data_cutoff_utc="2026-08-11T03:59:59Z",
        causal=True,
        target_error="WRONG_SIDE",
        expected_mechanism="conditional reliability",
        confidence=0.7,
        supporting_evidence=("support",),
        contradictory_evidence=tuple(contradictory),
        data_required=("causal_feature",),
        recommended_action="test one factor family",
    )


def test_evidence_card_rejects_out_of_range_confidence():
    with pytest.raises(ValueError, match="confidence"):
        EvidenceCard(
            card_id="x",
            author_agent="a",
            claim="c",
            source_ids=("s",),
            timestamp_utc="2026-08-11T04:00:00Z",
            data_cutoff_utc="2026-08-11T03:00:00Z",
            causal=True,
            target_error="WRONG_SIDE",
            expected_mechanism="m",
            confidence=1.5,
            supporting_evidence=(),
            contradictory_evidence=(),
            data_required=(),
            recommended_action="test",
        )


def test_blackboard_preserves_support_and_dissent_in_append_order(tmp_path):
    path = tmp_path / "research_blackboard.jsonl"
    append_evidence_card(_card("c1", "factor may help"), path)
    append_evidence_card(_card("c2", "factor may fail", contradictory=("c1",)), path)
    cards = load_evidence_cards(path)
    assert [card.card_id for card in cards] == ["c1", "c2"]
    assert cards[1].contradictory_evidence == ("c1",)
