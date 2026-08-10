from __future__ import annotations

import io
import zipfile
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd

AGGTRADE_COLUMNS = ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "transact_time", "is_buyer_maker"]


def parse_aggtrade_csv(raw: bytes) -> pd.DataFrame:
    frame = pd.read_csv(io.BytesIO(raw), header=None, names=AGGTRADE_COLUMNS)
    frame["timestamp"] = pd.to_datetime(frame["transact_time"], unit="ms", utc=True)
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame["quantity"] = pd.to_numeric(frame["quantity"], errors="coerce")
    frame["notional"] = frame["price"] * frame["quantity"]
    frame["signed_notional"] = np.where(frame["is_buyer_maker"].astype(bool), -frame["notional"], frame["notional"])
    return frame


def load_daily_aggtrades(symbol: str, date: str, cache_dir: str | Path | None = None) -> pd.DataFrame:
    filename = f"{symbol}-aggTrades-{date}.zip"
    url = f"https://data.binance.vision/data/futures/um/daily/aggTrades/{symbol}/{filename}"
    if cache_dir is not None:
        cache = Path(cache_dir)
        cache.mkdir(parents=True, exist_ok=True)
        path = cache / filename
        if not path.exists():
            path.write_bytes(urlopen(url, timeout=60).read())
        payload = path.read_bytes()
    else:
        payload = urlopen(url, timeout=60).read()
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if not names:
            raise ValueError("archive has no file")
        return parse_aggtrade_csv(zf.read(names[0]))


def build_quarter_hour_features(trades: pd.DataFrame) -> pd.DataFrame:
    """Build first-10/30/60-second features at each UTC quarter-hour event."""
    if trades.empty:
        return pd.DataFrame()
    x = trades.copy().sort_values("timestamp")
    x["quarter"] = x["timestamp"].dt.floor("15min")
    outputs = []
    for quarter, grp in x.groupby("quarter", sort=True):
        row = {"timestamp": quarter}
        total_15m = float(grp["notional"].sum())
        for sec in (10, 30, 60):
            cut = grp[grp["timestamp"] < quarter + pd.Timedelta(seconds=sec)]
            notional = float(cut["notional"].sum())
            signed = float(cut["signed_notional"].sum())
            row[f"trade_count_{sec}s"] = float(len(cut))
            row[f"notional_{sec}s"] = notional
            row[f"signed_notional_{sec}s"] = signed
            row[f"imbalance_{sec}s"] = signed / notional if notional else 0.0
            row[f"share_of_15m_{sec}s"] = notional / total_15m if total_15m else 0.0
            row[f"price_impact_{sec}s"] = float(cut["price"].iloc[-1] / cut["price"].iloc[0] - 1.0) if len(cut) >= 2 else 0.0
        outputs.append(row)
    result = pd.DataFrame(outputs).sort_values("timestamp")
    for sec in (10, 30, 60):
        prior = result[f"notional_{sec}s"].shift(1).replace(0, np.nan)
        result[f"notional_vs_prior_quarter_{sec}s"] = (result[f"notional_{sec}s"] / prior).replace([np.inf, -np.inf], np.nan)
    return result
