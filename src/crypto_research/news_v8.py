"""Causal news ingestion, deduplication, and structured-label validation for V8."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

import pandas as pd

_REQUIRED_EXTRACTION = {
    "event_type",
    "asset_scope",
    "sentiment",
    "confidence",
    "uncertainty",
    "novelty",
    "impact_horizon_hours",
    "source_quality",
}
_FORBIDDEN_TRADE_KEYS = {"action", "trade", "signal", "side", "leverage", "position", "order"}
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("article timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def normalize_article(
    *,
    source: str,
    source_id: str,
    title: str,
    content: str,
    published_at: datetime,
    first_seen_at: datetime,
    author: str | None = None,
) -> dict[str, Any]:
    published = _utc(published_at)
    first_seen = _utc(first_seen_at)
    content_hash = hashlib.sha256(f"{title.strip()}\n{content.strip()}".encode("utf-8")).hexdigest()
    return {
        "source": source,
        "source_id": source_id,
        "author": author,
        "published_at": published.isoformat(),
        "first_seen_at": first_seen.isoformat(),
        "available_at": first_seen.isoformat(),
        "decision_time": first_seen.isoformat(),
        "title": title.strip(),
        "content": content.strip(),
        "content_hash": content_hash,
        "entities": [],
        "assets": [],
        "event_type": None,
        "sentiment": None,
        "confidence": None,
        "impact_horizon_hours": None,
        "novelty": None,
        "source_reliability": None,
        "causal_status": "FIRST_SEEN_ONLY",
    }


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _similar(left: pd.Series, right: pd.Series) -> bool:
    if str(left["title"]).strip().lower() == str(right["title"]).strip().lower():
        return True
    a = _tokens(f"{left['title']} {left['content']}")
    b = _tokens(f"{right['title']} {right['content']}")
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= 0.8


def assign_narrative_clusters(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"source_id", "title", "content", "content_hash"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing news columns: {', '.join(sorted(missing))}")
    out = frame.copy().reset_index(drop=True)
    representatives: list[int] = []
    clusters: list[str] = []
    # ponytail: O(n²) near-duplicate matching is intentional for small research batches;
    # upgrade to MinHash/LSH once a batch routinely exceeds ~10k stories.
    for index, row in out.iterrows():
        cluster_id: str | None = None
        for representative in representatives:
            if _similar(row, out.loc[representative]):
                cluster_id = clusters[representative]
                break
        if cluster_id is None:
            cluster_id = "nar_" + hashlib.sha256(str(row["content_hash"]).encode("utf-8")).hexdigest()[:16]
            representatives.append(index)
        clusters.append(cluster_id)
    out["narrative_cluster_id"] = clusters
    return out


def causal_news_for_decision(frame: pd.DataFrame, *, decision_time: pd.Timestamp) -> pd.DataFrame:
    if "available_at" not in frame.columns:
        raise ValueError("news frame requires available_at")
    decision = pd.Timestamp(decision_time)
    decision = decision.tz_localize("UTC") if decision.tzinfo is None else decision.tz_convert("UTC")
    available = pd.to_datetime(frame["available_at"], utc=True, errors="raise")
    return frame.loc[available <= decision].copy().reset_index(drop=True)


def validate_llm_extraction(payload: dict[str, Any]) -> dict[str, Any]:
    forbidden = _FORBIDDEN_TRADE_KEYS & set(payload)
    if forbidden:
        raise ValueError(f"LLM extraction may not contain trade instructions: {', '.join(sorted(forbidden))}")
    missing = _REQUIRED_EXTRACTION - set(payload)
    extra = set(payload) - _REQUIRED_EXTRACTION
    if missing:
        raise ValueError(f"missing extraction fields: {', '.join(sorted(missing))}")
    if extra:
        raise ValueError(f"unexpected extraction fields: {', '.join(sorted(extra))}")
    if not isinstance(payload["event_type"], str) or not payload["event_type"].strip():
        raise ValueError("event_type must be a non-empty string")
    if not isinstance(payload["asset_scope"], list) or not all(isinstance(item, str) for item in payload["asset_scope"]):
        raise ValueError("asset_scope must be a list of strings")
    sentiment = float(payload["sentiment"])
    if not -1.0 <= sentiment <= 1.0:
        raise ValueError("sentiment must be between -1 and 1")
    for field in ("confidence", "uncertainty", "novelty", "source_quality"):
        value = float(payload[field])
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{field} must be between 0 and 1")
    horizon = float(payload["impact_horizon_hours"])
    if horizon <= 0.0:
        raise ValueError("impact_horizon_hours must be positive")
    return payload
