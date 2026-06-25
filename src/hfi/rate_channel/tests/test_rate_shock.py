"""Test rate_shock: estrazione finestra ±15 min e intensità |Δprice|."""
import numpy as np
import pandas as pd
import pytest

import rate_shock as rs


def _series_with_jump(t_center, jump):
    """Costruisce una serie minute-bar con prezzo 100 prima del centro e
    100+jump dopo. Edge-bound time-based: 5 min di prezzi prima/dopo."""
    idx = pd.date_range(t_center - pd.Timedelta(minutes=20),
                        t_center + pd.Timedelta(minutes=20), freq="1min")
    vals = np.where(idx <= t_center, 100.0, 100.0 + jump)
    return pd.Series(vals, index=idx)


def test_intensity_equals_absolute_price_change():
    t = pd.Timestamp("2024-06-10 14:00:00")
    s = _series_with_jump(t, jump=+0.5)
    assert rs.rate_shock_intensity(s, t) == pytest.approx(0.5)


def test_intensity_sign_is_absolute_value():
    t = pd.Timestamp("2024-06-10 14:00:00")
    s_up = _series_with_jump(t, jump=+0.7)
    s_down = _series_with_jump(t, jump=-0.7)
    assert rs.rate_shock_intensity(s_up, t) == pytest.approx(0.7)
    assert rs.rate_shock_intensity(s_down, t) == pytest.approx(0.7)


def test_intensity_nan_when_window_empty():
    t = pd.Timestamp("2024-06-10 14:00:00")
    far = pd.date_range(t + pd.Timedelta(hours=5), periods=10, freq="1min")
    s = pd.Series(100.0, index=far)
    assert np.isnan(rs.rate_shock_intensity(s, t))


def test_build_event_intensity_table_requires_columns():
    bad_events = pd.DataFrame({"event_time": [pd.Timestamp("2024-01-01")]})
    s = pd.Series([1.0], index=[pd.Timestamp("2024-01-01")])
    with pytest.raises(ValueError):
        rs.build_event_intensity_table(bad_events, s, contract_label="FFc2")


def test_build_event_intensity_table_output_schema():
    t = pd.Timestamp("2024-06-10 14:00:00")
    events = pd.DataFrame({"timestamp": [t], "leg": ["FOMC"], "regime": ["positivo"]})
    s = _series_with_jump(t, jump=+0.3)
    out = rs.build_event_intensity_table(events, s, contract_label="FFc2")
    assert list(out.columns) == ["timestamp", "leg", "regime", "intensity_raw", "contract"]
    assert out.iloc[0]["intensity_raw"] == pytest.approx(0.3)
    assert out.iloc[0]["contract"] == "FFc2"
