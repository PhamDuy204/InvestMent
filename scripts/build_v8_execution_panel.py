"""Build the offline V8 execution-fragility panel from existing research artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from crypto_research.execution_v8 import (
    build_delay_damage_labels,
    lagged_impact_feature,
)

ART_V7 = Path("artifacts/multi_asset_v7")
ART_V8 = Path("artifacts/multi_asset_v8")
KEYS = ["decision_timestamp", "symbol"]


def candidate_feature_columns() -> list[str]:
    return ["lag_rv12", "log_impact_1h"]


def _utc(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["decision_timestamp"] = pd.to_datetime(out["decision_timestamp"], utc=True)
    return out


def build_execution_panel(
    immediate: pd.DataFrame,
    delayed: pd.DataFrame,
    hourly: pd.DataFrame,
    basis: pd.DataFrame,
) -> pd.DataFrame:
    immediate = _utc(immediate)
    delayed = _utc(delayed)
    hourly = _utc(hourly)
    basis = _utc(basis)

    if immediate.duplicated(KEYS).any():
        raise ValueError("immediate decisions must be one-to-one")

    labels = build_delay_damage_labels(immediate, delayed)
    features = hourly[KEYS + ["feature_cutoff", "lag_return_1h", "lag_quote_volume"]].copy()
    if features.duplicated(KEYS).any():
        raise ValueError("hourly factor panel must be one-to-one")
    features["log_impact_1h"] = lagged_impact_feature(features)

    lag_rv = basis[KEYS + ["lag_rv12"]].copy()
    if lag_rv.duplicated(KEYS).any():
        raise ValueError("basis factor panel must be one-to-one")

    out = immediate.merge(labels, on=KEYS, how="left", validate="one_to_one")
    out = out.merge(features, on=KEYS, how="left", validate="one_to_one")
    out = out.merge(lag_rv, on=KEYS, how="left", validate="one_to_one")
    return out


def main() -> None:
    immediate = pd.read_csv("artifacts/multi_asset_v4/decision_log.csv.gz")
    delayed = pd.read_csv(ART_V7 / "delay_1h_decision_log.csv.gz")
    hourly = pd.read_csv(ART_V7 / "hourly_factor_panel.csv.gz")
    basis = pd.read_csv(ART_V7 / "basis_factor_panel.csv.gz")

    panel = build_execution_panel(immediate, delayed, hourly, basis)
    features = candidate_feature_columns()
    feature_cutoff = pd.to_datetime(panel["feature_cutoff"], utc=True, errors="coerce")
    decision_time = pd.to_datetime(panel["decision_timestamp"], utc=True, errors="coerce")
    coverage = float(panel[features + ["delay_damage_per_unit"]].notna().all(axis=1).mean())
    causal_fraction = float((feature_cutoff <= decision_time).fillna(False).mean())
    duplicate_count = int(panel.duplicated(KEYS).sum())

    if coverage < 0.70:
        raise SystemExit(f"V8 execution panel coverage below 0.70: {coverage:.3f}")
    if causal_fraction < 1.0:
        raise SystemExit(f"V8 feature cutoff is not fully causal: {causal_fraction:.6f}")
    if duplicate_count:
        raise SystemExit(f"V8 execution panel has {duplicate_count} duplicate keys")

    ART_V8.mkdir(parents=True, exist_ok=True)
    panel.to_csv(ART_V8 / "execution_factor_panel.csv.gz", index=False, compression="gzip")
    integrity = {
        "rows": int(len(panel)),
        "symbols": int(panel["symbol"].nunique()),
        "coverage_fraction": coverage,
        "causal_feature_cutoff_fraction": causal_fraction,
        "duplicate_key_count": duplicate_count,
        "candidate_feature_columns": features,
        "outcome_only_columns": ["delay_damage_per_unit"],
        "source_artifacts": [
            "artifacts/multi_asset_v4/decision_log.csv.gz",
            "artifacts/multi_asset_v7/delay_1h_decision_log.csv.gz",
            "artifacts/multi_asset_v7/hourly_factor_panel.csv.gz",
            "artifacts/multi_asset_v7/basis_factor_panel.csv.gz",
        ],
        "inherited_trial_count": 868,
        "research_only": True,
    }
    (ART_V8 / "execution_factor_panel_integrity.json").write_text(
        json.dumps(integrity, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(integrity, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
