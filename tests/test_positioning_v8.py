from __future__ import annotations

from datetime import datetime, timezone

from crypto_research.positioning_v8 import normalize_positioning_payload


def test_positioning_history_download_is_forward_only_at_first_seen_time() -> None:
    first_seen = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)
    payload = [
        {
            "symbol": "BTCUSDT",
            "longAccount": "0.61",
            "shortAccount": "0.39",
            "longShortRatio": "1.5641",
            "timestamp": 1787133600000,
        }
    ]

    rows = normalize_positioning_payload(
        "global_long_short_account_ratio",
        "BTCUSDT",
        payload,
        first_seen_at=first_seen,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["feature_name"] == "global_long_short_account_ratio"
    assert row["derived_value"] == 1.5641
    assert row["available_at"] == first_seen.isoformat()
    assert row["causal_status"] == "FORWARD_ONLY"
    assert row["event_time"] < row["available_at"]
    assert row["checksum"]


def test_positioning_open_interest_normalization_uses_public_timestamp() -> None:
    first_seen = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)
    payload = {"symbol": "BTCUSDT", "openInterest": "104904.829", "time": 1787139859147}

    rows = normalize_positioning_payload(
        "open_interest",
        "BTCUSDT",
        payload,
        first_seen_at=first_seen,
    )

    assert rows[0]["derived_value"] == 104904.829
    assert rows[0]["source"] == "binance_public_usdm"
    assert rows[0]["symbol"] == "BTCUSDT"


def test_fetch_positioning_stamps_availability_after_each_response(monkeypatch) -> None:
    from datetime import timedelta

    import crypto_research.positioning_v8 as positioning_v8

    class FakeDateTime(datetime):
        current = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz=None):
            value = cls.current
            return value if tz is None else value.astimezone(tz)

    def fake_public_json(path: str, params: dict[str, object]):
        FakeDateTime.current += timedelta(seconds=1)
        event_ms = int(FakeDateTime.current.timestamp() * 1000)
        feature = next(name for name, spec in positioning_v8._ENDPOINTS.items() if spec[0] == path)
        _, time_field, value_field = positioning_v8._ENDPOINTS[feature]
        payload = {time_field: event_ms, value_field: "1.0", "symbol": params["symbol"]}
        return [payload] if feature in positioning_v8._HISTORY_ENDPOINTS else payload

    monkeypatch.setattr(positioning_v8, "datetime", FakeDateTime)
    monkeypatch.setattr(positioning_v8, "_public_json", fake_public_json)

    rows = positioning_v8.fetch_positioning_snapshot("BTCUSDT")

    assert rows
    assert {row["data_version"] for row in rows} == {"v8-positioning-2"}
    assert all(
        datetime.fromisoformat(row["available_at"]) >= datetime.fromisoformat(row["event_time"])
        for row in rows
    )
