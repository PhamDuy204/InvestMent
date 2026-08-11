from __future__ import annotations

import numpy as np
import pandas as pd


def signed_aggressor_volume(quantity: float, is_buyer_maker: bool) -> float:
    qty = float(quantity)
    return -qty if bool(is_buyer_maker) else qty


def previous_completed_quarter_open(decision_timestamp: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(decision_timestamp)
    timestamp = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
    return timestamp.floor("15min") - pd.Timedelta(minutes=15)


def build_qh_opening_imbalance(
    trades: pd.DataFrame,
    decisions: pd.DataFrame,
    *,
    opening_seconds: int = 10,
) -> pd.DataFrame:
    if opening_seconds <= 0:
        raise ValueError("opening_seconds must be positive")
    required_trades = {"timestamp", "symbol", "quantity", "isBuyerMaker"}
    required_decisions = {"decision_timestamp", "symbol"}
    if missing := required_trades.difference(trades.columns):
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    if missing := required_decisions.difference(decisions.columns):
        raise ValueError(f"decisions missing columns: {sorted(missing)}")

    work = trades.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    work["quantity"] = pd.to_numeric(work["quantity"], errors="coerce")
    dec = decisions.copy()
    dec["decision_timestamp"] = pd.to_datetime(dec["decision_timestamp"], utc=True)

    rows: list[dict[str, object]] = []
    for item in dec.itertuples(index=False):
        decision_timestamp = pd.Timestamp(item.decision_timestamp)
        start = previous_completed_quarter_open(decision_timestamp)
        stop = start + pd.Timedelta(seconds=opening_seconds)
        part = work.loc[
            (work["symbol"] == item.symbol)
            & work["timestamp"].ge(start)
            & work["timestamp"].lt(stop)
        ].dropna(subset=["quantity"])
        signed = sum(
            signed_aggressor_volume(row.quantity, row.isBuyerMaker)
            for row in part.itertuples(index=False)
        )
        total = float(part["quantity"].abs().sum())
        imbalance = float(signed / total) if total > 0 else 0.0
        rows.append(
            {
                "decision_timestamp": decision_timestamp,
                "symbol": str(item.symbol),
                "qh_window_start": start,
                "qh_window_end": stop,
                "qh_order_imbalance": imbalance,
                "qh_abs_order_imbalance": abs(imbalance),
                "qh_trade_count": int(len(part)),
            }
        )
    return pd.DataFrame(rows)


def build_cross_sectional_dispersion(
    panel: pd.DataFrame,
    *,
    return_col: str = "ret_12",
    eligible_col: str = "in_universe",
) -> pd.DataFrame:
    required = {"decision_timestamp", return_col, eligible_col}
    if missing := required.difference(panel.columns):
        raise ValueError(f"panel missing columns: {sorted(missing)}")
    work = panel.copy()
    work["decision_timestamp"] = pd.to_datetime(work["decision_timestamp"], utc=True)
    work[return_col] = pd.to_numeric(work[return_col], errors="coerce")
    work = work.loc[work[eligible_col].fillna(False).astype(bool)].copy()

    rows: list[dict[str, object]] = []
    for timestamp, group in work.groupby("decision_timestamp", sort=True):
        values = group[return_col].to_numpy(dtype=float)
        values = values[np.isfinite(values)]
        dispersion = float(np.quantile(values, 0.75) - np.quantile(values, 0.25)) if len(values) >= 2 else float("nan")
        rows.append(
            {
                "decision_timestamp": pd.Timestamp(timestamp),
                "dispersion_iqr": dispersion,
                "eligible_symbol_count": int(len(values)),
            }
        )
    return pd.DataFrame(rows)
