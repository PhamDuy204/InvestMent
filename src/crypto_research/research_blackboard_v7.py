from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class EvidenceCard:
    card_id: str
    author_agent: str
    claim: str
    source_ids: tuple[str, ...]
    timestamp_utc: str
    data_cutoff_utc: str
    causal: bool
    target_error: str
    expected_mechanism: str
    confidence: float
    supporting_evidence: tuple[str, ...]
    contradictory_evidence: tuple[str, ...]
    data_required: tuple[str, ...]
    recommended_action: str

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        for field_name in (
            "card_id",
            "author_agent",
            "claim",
            "timestamp_utc",
            "data_cutoff_utc",
            "target_error",
            "expected_mechanism",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must be non-empty")
        for field_name in ("timestamp_utc", "data_cutoff_utc"):
            timestamp = pd.Timestamp(getattr(self, field_name))
            if timestamp.tzinfo is None:
                raise ValueError(f"{field_name} must be timezone-aware UTC")
            if timestamp.tz_convert("UTC").utcoffset().total_seconds() != 0:
                raise ValueError(f"{field_name} must be UTC")


def append_evidence_card(card: EvidenceCard, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(card), sort_keys=True, default=str) + "\n")


def load_evidence_cards(path: str | Path) -> list[EvidenceCard]:
    target = Path(path)
    if not target.exists():
        return []
    cards: list[EvidenceCard] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        for key in (
            "source_ids",
            "supporting_evidence",
            "contradictory_evidence",
            "data_required",
        ):
            payload[key] = tuple(payload[key])
        cards.append(EvidenceCard(**payload))
    return cards
