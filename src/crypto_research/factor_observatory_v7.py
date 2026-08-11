from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

FACTOR_FAMILIES = {
    "microstructure",
    "derivatives",
    "cross_asset_macro",
    "on_chain",
    "news_event",
    "attention_sentiment",
    "cross_sectional",
    "execution_risk",
    "scenario_swarm",
}
_ALLOWED_SOURCE_QUALITY = {"primary", "official", "peer_reviewed"}


@dataclass(frozen=True)
class FactorEvidence:
    factor_family: str
    feature_name: str
    source_ids: tuple[str, ...]
    coverage_fraction: float
    causal_available: bool
    source_quality: str
    stability_score: float
    target_error: str
    association_value: float
    incremental_net_bps: float
    incremental_sharpe_delta: float
    turnover_delta: float
    evaluation_fold_count: int
    reverse_causality_checked: bool
    status: str

    def __post_init__(self) -> None:
        if self.factor_family not in FACTOR_FAMILIES:
            raise ValueError(f"unknown factor_family: {self.factor_family}")
        if not self.feature_name.strip() or not self.target_error.strip():
            raise ValueError("feature_name and target_error must be non-empty")
        if not self.source_ids:
            raise ValueError("source_ids must be non-empty")
        if not 0.0 <= float(self.coverage_fraction) <= 1.0:
            raise ValueError("coverage_fraction must be in [0, 1]")
        if not 0.0 <= float(self.stability_score) <= 1.0:
            raise ValueError("stability_score must be in [0, 1]")
        if int(self.evaluation_fold_count) < 0:
            raise ValueError("evaluation_fold_count must be non-negative")


def factor_rejection_reasons(evidence: FactorEvidence) -> list[str]:
    reasons: list[str] = []
    if not evidence.causal_available:
        reasons.append("not_causally_available")
    if float(evidence.coverage_fraction) < 0.70:
        reasons.append("coverage_below_0_70")
    if evidence.source_quality not in _ALLOWED_SOURCE_QUALITY:
        reasons.append("source_quality_not_primary_official_or_peer_reviewed")
    if float(evidence.stability_score) < 0.50:
        reasons.append("stability_below_0_50")
    if int(evidence.evaluation_fold_count) < 2:
        reasons.append("fewer_than_two_evaluation_folds")
    if float(evidence.incremental_net_bps) <= 0.0:
        reasons.append("nonpositive_incremental_net_bps")
    if float(evidence.incremental_sharpe_delta) < 0.0:
        reasons.append("negative_incremental_sharpe_delta")
    if evidence.factor_family == "attention_sentiment" and not evidence.reverse_causality_checked:
        reasons.append("reverse_causality_not_checked")
    return reasons


def admit_factor(evidence: FactorEvidence) -> bool:
    return not factor_rejection_reasons(evidence)


def write_factor_observatory(
    rows: list[FactorEvidence],
    path: str | Path,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    factors = []
    for evidence in rows:
        reasons = factor_rejection_reasons(evidence)
        payload = asdict(evidence)
        payload["source_ids"] = list(evidence.source_ids)
        payload["admitted"] = not reasons
        payload["rejection_reasons"] = reasons
        factors.append(payload)
    target.write_text(
        json.dumps(
            {
                "status": "EVALUATED",
                "admission_rule": {
                    "minimum_coverage_fraction": 0.70,
                    "allowed_source_quality": sorted(_ALLOWED_SOURCE_QUALITY),
                    "minimum_stability_score": 0.50,
                    "minimum_evaluation_fold_count": 2,
                    "incremental_net_bps": ">0",
                    "incremental_sharpe_delta": ">=0",
                    "attention_sentiment_requires_reverse_causality_check": True,
                },
                "factors": factors,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return target
