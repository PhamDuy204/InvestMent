from __future__ import annotations

import io
import time
import urllib.error
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

BASE_URL = "https://data.binance.vision/data/futures/um/monthly"
DAILY_BASE_URL = "https://data.binance.vision/data/futures/um/daily"
BAR_MS = {"1m": 60_000, "15m": 15 * 60_000, "30m": 30 * 60_000, "1h": 60 * 60_000, "4h": 4 * 60 * 60_000}
KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trade_count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "ignore",
]


def _timeframe_ms(timeframe: str) -> int:
    try:
        return BAR_MS[timeframe]
    except KeyError as exc:
        raise ValueError(f"unsupported timeframe: {timeframe}") from exc


def parse_kline_csv(payload: io.BytesIO, *, symbol: str, timeframe: str, now_ms: int) -> pd.DataFrame:
    bar_ms = _timeframe_ms(timeframe)
    payload.seek(0)
    frame = pd.read_csv(payload)
    if "count" in frame.columns and "trade_count" not in frame.columns:
        frame = frame.rename(columns={"count": "trade_count"})
    expected = set(KLINE_COLUMNS) - {"trade_count"}
    expected.add("trade_count")
    if not expected.issubset(frame.columns):
        payload.seek(0)
        frame = pd.read_csv(payload, header=None, names=KLINE_COLUMNS)
    if frame.empty:
        return pd.DataFrame(columns=["timestamp", "symbol", *KLINE_COLUMNS[1:6], *KLINE_COLUMNS[7:11]])

    frame["open_time"] = pd.to_numeric(frame["open_time"], errors="raise").astype("int64")
    frame = frame.loc[frame["open_time"] + bar_ms <= now_ms].copy()
    frame = frame.drop_duplicates("open_time", keep="last").sort_values("open_time")
    numeric = ["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_volume", "taker_buy_quote_volume"]
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(float)
    frame["trade_count"] = pd.to_numeric(frame["trade_count"], errors="raise").astype("int64")
    frame["timestamp"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["symbol"] = symbol
    return frame[
        [
            "timestamp",
            "symbol",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_volume",
            "trade_count",
            "taker_buy_volume",
            "taker_buy_quote_volume",
        ]
    ].reset_index(drop=True)


def parse_funding_csv(payload: io.BytesIO, *, symbol: str) -> pd.DataFrame:
    payload.seek(0)
    frame = pd.read_csv(payload)
    expected = {"calc_time", "funding_interval_hours", "last_funding_rate"}
    if not expected.issubset(frame.columns):
        raise ValueError(f"funding archive missing columns: {sorted(expected.difference(frame.columns))}")
    frame["timestamp"] = pd.to_datetime(pd.to_numeric(frame["calc_time"], errors="raise"), unit="ms", utc=True)
    frame["funding_rate"] = pd.to_numeric(frame["last_funding_rate"], errors="raise").astype(float)
    frame["funding_interval_hours"] = pd.to_numeric(frame["funding_interval_hours"], errors="raise").astype(float)
    frame["symbol"] = symbol
    return frame[["timestamp", "symbol", "funding_rate", "funding_interval_hours"]].drop_duplicates(
        ["timestamp", "symbol"], keep="last"
    ).sort_values("timestamp").reset_index(drop=True)


def _day_starts(start: str | pd.Timestamp, end: str | pd.Timestamp) -> pd.DatetimeIndex:
    start_ts = pd.Timestamp(start, tz="UTC") if pd.Timestamp(start).tzinfo is None else pd.Timestamp(start).tz_convert("UTC")
    end_ts = pd.Timestamp(end, tz="UTC") if pd.Timestamp(end).tzinfo is None else pd.Timestamp(end).tz_convert("UTC")
    return pd.date_range(start_ts.floor("D"), end_ts.floor("D"), freq="D")


def _month_starts(start: str | pd.Timestamp, end: str | pd.Timestamp) -> pd.DatetimeIndex:
    start_ts = pd.Timestamp(start, tz="UTC") if pd.Timestamp(start).tzinfo is None else pd.Timestamp(start).tz_convert("UTC")
    end_ts = pd.Timestamp(end, tz="UTC") if pd.Timestamp(end).tzinfo is None else pd.Timestamp(end).tz_convert("UTC")
    start_month = pd.Timestamp(year=start_ts.year, month=start_ts.month, day=1, tz="UTC")
    end_month = pd.Timestamp(year=end_ts.year, month=end_ts.month, day=1, tz="UTC")
    return pd.date_range(start_month, end_month, freq="MS")


def _download_zip(url: str, path: Path) -> bytes | None:
    if path.exists():
        return path.read_bytes()
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read()
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if attempt == 2:
                raise
        except urllib.error.URLError:
            if attempt == 2:
                raise
        time.sleep(0.25 * (attempt + 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _first_zip_member(data: bytes) -> io.BytesIO:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if not names:
            raise ValueError("empty Binance archive")
        return io.BytesIO(archive.read(names[0]))


def load_daily_klines(
    symbol: str,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    *,
    timeframe: str = "1h",
    cache_dir: str | Path = "data/binance_futures_v2/cache",
    now_ms: int | None = None,
) -> pd.DataFrame:
    _timeframe_ms(timeframe)
    now_ms = now_ms or int(datetime.now(UTC).timestamp() * 1000)
    cache = Path(cache_dir)
    parts = []
    for day in _day_starts(start, end):
        label = day.strftime("%Y-%m-%d")
        filename = f"{symbol}-{timeframe}-{label}.zip"
        url = f"{DAILY_BASE_URL}/klines/{symbol}/{timeframe}/{filename}"
        data = _download_zip(url, cache / "daily_klines" / symbol / timeframe / filename)
        if data:
            parts.append(parse_kline_csv(_first_zip_member(data), symbol=symbol, timeframe=timeframe, now_ms=now_ms))
    if not parts:
        return pd.DataFrame()
    frame = pd.concat(parts, ignore_index=True).drop_duplicates(["timestamp", "symbol"], keep="last")
    start_ts = pd.Timestamp(start, tz="UTC") if pd.Timestamp(start).tzinfo is None else pd.Timestamp(start).tz_convert("UTC")
    end_ts = pd.Timestamp(end, tz="UTC") if pd.Timestamp(end).tzinfo is None else pd.Timestamp(end).tz_convert("UTC")
    return frame.loc[(frame["timestamp"] >= start_ts) & (frame["timestamp"] <= end_ts)].sort_values("timestamp").reset_index(drop=True)


def load_monthly_klines(
    symbol: str,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    *,
    timeframe: str = "1h",
    cache_dir: str | Path = "data/binance_futures_v2/cache",
    now_ms: int | None = None,
) -> pd.DataFrame:
    _timeframe_ms(timeframe)
    now_ms = now_ms or int(datetime.now(UTC).timestamp() * 1000)
    cache = Path(cache_dir)
    parts = []
    for month in _month_starts(start, end):
        label = month.strftime("%Y-%m")
        filename = f"{symbol}-{timeframe}-{label}.zip"
        url = f"{BASE_URL}/klines/{symbol}/{timeframe}/{filename}"
        data = _download_zip(url, cache / "klines" / symbol / timeframe / filename)
        if data:
            parts.append(parse_kline_csv(_first_zip_member(data), symbol=symbol, timeframe=timeframe, now_ms=now_ms))
    if not parts:
        return pd.DataFrame()
    frame = pd.concat(parts, ignore_index=True).drop_duplicates(["timestamp", "symbol"], keep="last")
    start_ts = pd.Timestamp(start, tz="UTC") if pd.Timestamp(start).tzinfo is None else pd.Timestamp(start).tz_convert("UTC")
    end_ts = pd.Timestamp(end, tz="UTC") if pd.Timestamp(end).tzinfo is None else pd.Timestamp(end).tz_convert("UTC")
    return frame.loc[(frame["timestamp"] >= start_ts) & (frame["timestamp"] <= end_ts)].sort_values("timestamp").reset_index(drop=True)


def load_monthly_mark_price_klines(
    symbol: str,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    *,
    timeframe: str = "1h",
    cache_dir: str | Path = "data/binance_futures_v2/cache",
    now_ms: int | None = None,
) -> pd.DataFrame:
    _timeframe_ms(timeframe)
    now_ms = now_ms or int(datetime.now(UTC).timestamp() * 1000)
    cache = Path(cache_dir)
    parts = []
    for month in _month_starts(start, end):
        label = month.strftime("%Y-%m")
        filename = f"{symbol}-{timeframe}-{label}.zip"
        url = f"{BASE_URL}/markPriceKlines/{symbol}/{timeframe}/{filename}"
        data = _download_zip(url, cache / "markPriceKlines" / symbol / timeframe / filename)
        if data:
            parts.append(parse_kline_csv(_first_zip_member(data), symbol=symbol, timeframe=timeframe, now_ms=now_ms))
    if not parts:
        return pd.DataFrame()
    frame = pd.concat(parts, ignore_index=True).drop_duplicates(["timestamp", "symbol"], keep="last")
    start_ts = pd.Timestamp(start, tz="UTC") if pd.Timestamp(start).tzinfo is None else pd.Timestamp(start).tz_convert("UTC")
    end_ts = pd.Timestamp(end, tz="UTC") if pd.Timestamp(end).tzinfo is None else pd.Timestamp(end).tz_convert("UTC")
    return frame.loc[(frame["timestamp"] >= start_ts) & (frame["timestamp"] <= end_ts)].sort_values("timestamp").reset_index(drop=True)


def load_monthly_premium_index_klines(
    symbol: str,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    *,
    timeframe: str = "1h",
    cache_dir: str | Path = "data/binance_futures_v2/cache",
    now_ms: int | None = None,
) -> pd.DataFrame:
    _timeframe_ms(timeframe)
    now_ms = now_ms or int(datetime.now(UTC).timestamp() * 1000)
    cache = Path(cache_dir)
    parts = []
    for month in _month_starts(start, end):
        label = month.strftime("%Y-%m")
        filename = f"{symbol}-{timeframe}-{label}.zip"
        url = f"{BASE_URL}/premiumIndexKlines/{symbol}/{timeframe}/{filename}"
        data = _download_zip(url, cache / "premiumIndexKlines" / symbol / timeframe / filename)
        if data:
            parts.append(parse_kline_csv(_first_zip_member(data), symbol=symbol, timeframe=timeframe, now_ms=now_ms))
    if not parts:
        return pd.DataFrame()
    frame = pd.concat(parts, ignore_index=True).drop_duplicates(["timestamp", "symbol"], keep="last")
    start_ts = pd.Timestamp(start, tz="UTC") if pd.Timestamp(start).tzinfo is None else pd.Timestamp(start).tz_convert("UTC")
    end_ts = pd.Timestamp(end, tz="UTC") if pd.Timestamp(end).tzinfo is None else pd.Timestamp(end).tz_convert("UTC")
    return frame.loc[(frame["timestamp"] >= start_ts) & (frame["timestamp"] <= end_ts)].sort_values("timestamp").reset_index(drop=True)


def load_monthly_funding(
    symbol: str,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    *,
    cache_dir: str | Path = "data/binance_futures_v2/cache",
) -> pd.DataFrame:
    cache = Path(cache_dir)
    parts = []
    for month in _month_starts(start, end):
        label = month.strftime("%Y-%m")
        filename = f"{symbol}-fundingRate-{label}.zip"
        url = f"{BASE_URL}/fundingRate/{symbol}/{filename}"
        data = _download_zip(url, cache / "funding" / symbol / filename)
        if data:
            parts.append(parse_funding_csv(_first_zip_member(data), symbol=symbol))
    if not parts:
        return pd.DataFrame()
    frame = pd.concat(parts, ignore_index=True).drop_duplicates(["timestamp", "symbol"], keep="last")
    start_ts = pd.Timestamp(start, tz="UTC") if pd.Timestamp(start).tzinfo is None else pd.Timestamp(start).tz_convert("UTC")
    end_ts = pd.Timestamp(end, tz="UTC") if pd.Timestamp(end).tzinfo is None else pd.Timestamp(end).tz_convert("UTC")
    return frame.loc[(frame["timestamp"] >= start_ts) & (frame["timestamp"] <= end_ts)].sort_values("timestamp").reset_index(drop=True)


def validate_panel(frame: pd.DataFrame, *, timeframe: str = "1h") -> dict[str, object]:
    bar_ms = _timeframe_ms(timeframe)
    required = {"timestamp", "symbol"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    duplicates = int(pd.DataFrame({"timestamp": timestamps, "symbol": frame["symbol"]}).duplicated().sum())
    missing_bars = 0
    gaps = []
    for symbol, group in frame.assign(timestamp=timestamps).groupby("symbol", sort=False):
        unique = group["timestamp"].drop_duplicates().sort_values()
        if len(unique) < 2:
            continue
        delta_ms = unique.diff().dropna().dt.total_seconds().mul(1000).astype("int64")
        symbol_missing = int(((delta_ms // bar_ms) - 1).clip(lower=0).sum())
        missing_bars += symbol_missing
        for ts, delta in zip(unique.iloc[1:], delta_ms):
            if delta > bar_ms:
                gaps.append({"symbol": str(symbol), "timestamp": ts.isoformat(), "gap_bars": int(delta // bar_ms - 1)})
    return {
        "rows": int(len(frame)),
        "symbols": int(frame["symbol"].nunique()),
        "timezone": "UTC",
        "duplicates": duplicates,
        "missing_bars": missing_bars,
        "gaps": gaps[:100],
        "timeframe": timeframe,
    }
