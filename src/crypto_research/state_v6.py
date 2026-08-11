from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np
import pandas as pd


def _rolling_tercile(series: pd.Series, window: int = 168) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    ranks = values.rolling(window=window, min_periods=12).apply(
        lambda x: float(pd.Series(x).rank(pct=True).iloc[-1]), raw=False
    )
    out = pd.Series("mid", index=series.index, dtype="object")
    out.loc[ranks <= 1.0 / 3.0] = "low"
    out.loc[ranks >= 2.0 / 3.0] = "high"
    return out


def _global_session(hour: int) -> str:
    if 0 <= hour < 7:
        return "ASIA"
    if 7 <= hour < 9:
        return "ASIA_EUROPE"
    if 9 <= hour < 13:
        return "EUROPE"
    if 13 <= hour < 16:
        return "EUROPE_US"
    if 16 <= hour < 22:
        return "US"
    return "OFF_HOURS"


def add_session_state(frame: pd.DataFrame) -> pd.DataFrame:
    if "decision_timestamp" not in frame.columns:
        raise ValueError("decision_timestamp is required")
    out = frame.copy()
    out["decision_timestamp"] = pd.to_datetime(out["decision_timestamp"], utc=True)
    out = out.sort_values([c for c in ("symbol", "decision_timestamp") if c in out.columns]).copy()
    ts = out["decision_timestamp"]
    out["utc_hour"] = ts.dt.hour
    out["vietnam_hour"] = (out["utc_hour"] + 7) % 24
    out["vn_day_session"] = out["vietnam_hour"].between(8, 16)
    out["vn_session"] = np.where(out["vn_day_session"], "VN_08_17", "VN_17_08")
    out["weekend"] = ts.dt.weekday >= 5
    out["weekday"] = ts.dt.weekday
    out["global_session"] = out["utc_hour"].map(_global_session)

    group_keys: Iterable[str] = ["symbol"] if "symbol" in out.columns else []
    # V5's diagnostic terciles were global qcut labels over the completed log. Rebuild
    # state from causal raw trailing features instead of trusting those convenience columns.
    if "realized_vol_24" in out.columns:
        if group_keys:
            out["vol_state"] = out.groupby(list(group_keys), sort=False)["realized_vol_24"].transform(_rolling_tercile)
        else:
            out["vol_state"] = _rolling_tercile(out["realized_vol_24"])
    else:
        out["vol_state"] = "mid"

    activity_col = next((c for c in ("trade_count_z24", "quote_volume_z24") if c in out.columns), None)
    if activity_col is None:
        out["activity_state"] = "mid"
    elif group_keys:
        out["activity_state"] = out.groupby(list(group_keys), sort=False)[activity_col].transform(_rolling_tercile)
    else:
        out["activity_state"] = _rolling_tercile(out[activity_col])

    if "burst_probability" in out.columns:
        burst = pd.to_numeric(out["burst_probability"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
        out["burst_state"] = pd.cut(
            burst,
            bins=[-math.inf, 0.35, 0.65, math.inf],
            labels=["low", "mid", "high"],
        ).astype(str)
    else:
        out["burst_probability"] = 0.0
        out["burst_state"] = "unknown"

    if "taker_imbalance" in out.columns:
        flow = pd.to_numeric(out["taker_imbalance"], errors="coerce").fillna(0.0)
        out["flow_state"] = np.select([flow <= -0.15, flow >= 0.15], ["sell", "buy"], default="neutral")
    else:
        out["flow_state"] = "unknown"

    if "trend_state" not in out.columns:
        trend_col = next((c for c in ("ret_24", "market_ret_4") if c in out.columns), None)
        if trend_col is None:
            out["trend_state"] = "unknown"
        else:
            trend = pd.to_numeric(out[trend_col], errors="coerce").fillna(0.0)
            out["trend_state"] = np.select([trend < -1e-12, trend > 1e-12], ["down", "up"], default="flat")
    return out.sort_index()


def _group_summary(frame: pd.DataFrame, key: str) -> dict[str, object]:
    metrics = [
        c
        for c in (
            "realized_vol_24",
            "quote_volume_z24",
            "trade_count_z24",
            "burst_probability",
            "funding_rate",
            "realized_position_contribution_label",
        )
        if c in frame.columns
    ]
    result: dict[str, object] = {}
    for value, group in frame.groupby(key, dropna=False, sort=True):
        row: dict[str, object] = {"count": int(len(group))}
        for metric in metrics:
            numeric = pd.to_numeric(group[metric], errors="coerce")
            finite = numeric[np.isfinite(numeric)]
            row[f"mean_{metric}"] = float(finite.mean()) if len(finite) else None
        result[str(value)] = row
    return result


def summarize_session_state(frame: pd.DataFrame) -> dict[str, object]:
    required = {"decision_timestamp", "vn_session", "utc_hour"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing session-state columns: {sorted(missing)}")
    return {
        "rows": int(len(frame)),
        "start": str(pd.to_datetime(frame["decision_timestamp"], utc=True).min()) if len(frame) else None,
        "end": str(pd.to_datetime(frame["decision_timestamp"], utc=True).max()) if len(frame) else None,
        "vn_session": _group_summary(frame, "vn_session"),
        "utc_hour": _group_summary(frame, "utc_hour"),
        "global_session": _group_summary(frame, "global_session") if "global_session" in frame.columns else {},
        "vol_state": _group_summary(frame, "vol_state") if "vol_state" in frame.columns else {},
        "activity_state": _group_summary(frame, "activity_state") if "activity_state" in frame.columns else {},
    }
