"""Test di data.py — loader I/O, su FIXTURE sintetiche (mai sui file reali).

Verifica: caricamento minute-bar in Series UTC ordinata; rendimenti daily
derivati dalla chiusura (ultimo prezzo) per data; parsing eventi.
"""
import numpy as np
import pandas as pd
import pytest

import data


def test_load_minute_returns_sorted_utc_series(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("Datetime_UTC,PX_LAST\n"
                 "2020-01-02 20:00:00+00:00,100\n"
                 "2020-01-02 14:00:00+00:00,99\n")
    s = data.load_minute(p)
    assert s.index.tz is not None
    assert list(s.values) == [99.0, 100.0]          # ordinato per tempo
    assert s.name == "PX_LAST"


def test_load_minute_custom_price_col(tmp_path):
    p = tmp_path / "stxe.csv"
    p.write_text("Datetime_UTC,Mid_raw\n2020-01-02 14:00:00+00:00,3000\n")
    s = data.load_minute(p, price_col="Mid_raw")
    assert s.iloc[0] == 3000.0
    assert s.name == "Mid_raw"


def test_daily_log_returns_from_minute(tmp_path):
    idx = pd.to_datetime([
        "2020-01-02 14:00:00", "2020-01-02 20:00:00",   # close day1 = 100
        "2020-01-03 14:00:00", "2020-01-03 20:00:00",   # close day2 = 110
        "2020-01-06 20:00:00",                          # close day3 = 121
    ]).tz_localize("UTC")
    s = pd.Series([99, 100, 105, 110, 121], index=idx)
    r = data.daily_log_returns_from_minute(s)
    assert pd.isna(r.iloc[0])                           # primo giorno → NaN
    assert r.iloc[1] == pytest.approx(np.log(110 / 100))
    assert r.iloc[2] == pytest.approx(np.log(121 / 110))


def test_load_events_parses_timestamp(tmp_path):
    p = tmp_path / "ev.csv"
    p.write_text("date,timestamp,event_class\n"
                 "2020-01-02,2020-01-02 13:30:00+00:00,NFP\n")
    ev = data.load_events(p)
    assert ev["timestamp"].dt.tz is not None
    assert ev.iloc[0]["event_class"] == "NFP"
    assert "date" in ev.columns
