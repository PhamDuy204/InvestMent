import pandas as pd

from crypto_research.state_v6 import add_session_state, summarize_session_state


def test_vietnam_session_uses_utc_plus_seven_without_future_data():
    frame = pd.DataFrame(
        {
            "decision_timestamp": pd.to_datetime(
                ["2026-01-01T00:00Z", "2026-01-01T01:00Z", "2026-01-01T09:00Z", "2026-01-01T10:00Z"]
            ),
            "realized_vol_24": [0.01, 0.01, 0.02, 0.02],
        }
    )
    out = add_session_state(frame)
    assert out["vietnam_hour"].tolist() == [7, 8, 16, 17]
    assert out["vn_day_session"].tolist() == [False, True, True, False]


def test_future_mutation_does_not_change_prior_state():
    frame = pd.DataFrame(
        {
            "decision_timestamp": pd.date_range("2026-01-01", periods=30, freq="h", tz="UTC"),
            "realized_vol_24": [float(i + 1) for i in range(30)],
            "quote_volume_z24": [float(i % 5) for i in range(30)],
        }
    )
    before = add_session_state(frame).iloc[:20].copy()
    changed = frame.copy()
    changed.loc[25:, "realized_vol_24"] = 10_000.0
    changed.loc[25:, "quote_volume_z24"] = 10_000.0
    after = add_session_state(changed).iloc[:20]
    pd.testing.assert_frame_equal(before, after)


def test_summary_has_session_and_hour_groups():
    frame = pd.DataFrame(
        {
            "decision_timestamp": pd.date_range("2026-01-01", periods=8, freq="h", tz="UTC"),
            "realized_vol_24": [0.01] * 8,
            "realized_position_contribution_label": [0.001, -0.001] * 4,
        }
    )
    summary = summarize_session_state(add_session_state(frame))
    assert "vn_session" in summary
    assert "utc_hour" in summary


def test_precomputed_global_terciles_are_not_trusted_when_raw_causal_features_exist():
    frame = pd.DataFrame(
        {
            "decision_timestamp": pd.date_range("2026-01-01", periods=20, freq="h", tz="UTC"),
            "realized_vol_24": [float(i + 1) for i in range(20)],
            "quote_volume_z24": [float(i + 1) for i in range(20)],
            "vol_tercile": ["high"] * 20,
            "activity_tercile": ["high"] * 20,
        }
    )
    out = add_session_state(frame)
    assert out.loc[0, "vol_state"] == "mid"
    assert out.loc[0, "activity_state"] == "mid"
