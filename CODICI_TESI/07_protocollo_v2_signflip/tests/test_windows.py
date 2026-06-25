"""Test di windows.py (C0.1, C0.2) — TDD stretto.

Punti delicati: (1) gli edge della finestra sono basati sul TEMPO (primi/ultimi
5 minuti), non sulle prime/ultime righe; (2) i centri dei controlli sono allineati
sul TEMPO LOCALE di mercato → UTC per-data con DST (§13bis), e l'estensione
5/3/10 si attiva solo quando i sopravvissuti scendono sotto il minimo.
"""
from datetime import time

import numpy as np
import pandas as pd
import pytest

import config
import windows


# --- extract_window (C0.1) ---------------------------------------------

def test_extract_window_log_return_of_edge_medians():
    t_center = pd.Timestamp("2020-06-01 13:30:00", tz="UTC")
    t0 = t_center - pd.Timedelta(minutes=15)
    idx = pd.date_range(t0, periods=31, freq="1min", tz="UTC")  # 13:15..13:45
    prices = pd.Series(100.0, index=idx)
    prices.iloc[-5:] = 101.0  # ultimi 5 min
    r = windows.extract_window(prices, t_center, half_min=15, edge_min=5)
    assert r == pytest.approx(np.log(101.0 / 100.0))


def test_extract_window_edges_are_time_based_not_row_based():
    t_center = pd.Timestamp("2020-06-01 13:30:00", tz="UTC")
    t0 = t_center - pd.Timedelta(minutes=15)   # 13:15
    t1 = t_center + pd.Timedelta(minutes=15)   # 13:45
    times = [
        t0, t0 + pd.Timedelta(minutes=1),               # 13:15,13:16 → 100 (pre-edge)
        t0 + pd.Timedelta(minutes=8),                   # 13:23 → 999 (centro, fuori edge)
        t1 - pd.Timedelta(minutes=2),
        t1 - pd.Timedelta(minutes=1), t1,               # 13:43,13:44,13:45 → 101 (post-edge)
    ]
    prices = pd.Series([100, 100, 999, 101, 101, 101], index=pd.DatetimeIndex(times))
    r = windows.extract_window(prices, t_center, half_min=15, edge_min=5)
    # mediana pre = 100 (il 999 a 13:23 è fuori dai primi 5 min), mediana post = 101
    assert r == pytest.approx(np.log(101.0 / 100.0))


def test_extract_window_none_when_empty():
    t_center = pd.Timestamp("2020-06-01 13:30:00", tz="UTC")
    empty = pd.Series([], index=pd.DatetimeIndex([], tz="UTC"), dtype=float)
    assert windows.extract_window(empty, t_center) is None


def test_extract_window_none_when_one_edge_missing():
    t_center = pd.Timestamp("2020-06-01 13:30:00", tz="UTC")
    t0 = t_center - pd.Timedelta(minutes=15)
    times = pd.date_range(t0, t0 + pd.Timedelta(minutes=3), freq="1min", tz="UTC")  # solo pre-edge
    prices = pd.Series(100.0, index=times)
    assert windows.extract_window(prices, t_center) is None


# --- control_window_centers (C0.2) -------------------------------------

def test_control_centers_five_when_no_exclusions():
    ev = pd.Timestamp("2021-06-09 12:30:00", tz="UTC")  # mer, 08:30 EDT
    centers = windows.control_window_centers(ev, "America/New_York", reject=lambda t: False)
    assert len(centers) == config.K_CONTROL_TARGET
    for c in centers:
        assert c < ev
        local = c.tz_convert("America/New_York")
        assert local.time() == time(8, 30)
        assert local.weekday() < 5


def test_control_centers_dst_boundary_keeps_local_time():
    # 2021-11-08 lun: DST USA finita il 7 nov → EST (UTC-5) → 08:30 ET = 13:30Z
    ev = pd.Timestamp("2021-11-08 13:30:00", tz="UTC")
    centers = windows.control_window_centers(ev, "America/New_York", reject=lambda t: False)
    by_date = {c.tz_convert("America/New_York").date().isoformat(): c for c in centers}
    # 2021-11-05 ven era EDT (UTC-4) → 08:30 ET = 12:30Z, NON 13:30Z (matching DST-aware)
    assert by_date["2021-11-05"] == pd.Timestamp("2021-11-05 12:30:00", tz="UTC")
    for c in centers:
        assert c.tz_convert("America/New_York").time() == time(8, 30)


def test_control_centers_ecb_cet_dst_boundary():
    # Verifica che il fuso sia quello PASSATO (per-tipo): ECB in ora europea.
    # 2021-11-01 13:45 CET (CET=UTC+1 dopo il 31 ott) = 12:45Z
    ev = pd.Timestamp("2021-11-01 12:45:00", tz="UTC")
    centers = windows.control_window_centers(ev, "Europe/Berlin", reject=lambda t: False)
    by_date = {c.tz_convert("Europe/Berlin").date().isoformat(): c for c in centers}
    # 2021-10-29 ven era CEST (UTC+2) → 13:45 CET = 11:45Z, NON 12:45Z
    assert by_date["2021-10-29"] == pd.Timestamp("2021-10-29 11:45:00", tz="UTC")
    for c in centers:
        assert c.tz_convert("Europe/Berlin").time() == time(13, 45)


def test_control_centers_no_extension_when_min_met():
    ev = pd.Timestamp("2021-06-09 12:30:00", tz="UTC")
    base = windows.control_window_centers(ev, "America/New_York", reject=lambda t: False)
    excluded = {base[0]}  # ne escludo 1 → 4 sopravvivono (≥3) → nessuna estensione
    centers = windows.control_window_centers(
        ev, "America/New_York", reject=lambda t: t in excluded)
    assert len(centers) == 4
    assert set(centers) == set(base[1:])


def test_control_centers_extends_when_below_min():
    ev = pd.Timestamp("2021-06-09 12:30:00", tz="UTC")
    base = windows.control_window_centers(ev, "America/New_York", reject=lambda t: False)
    excluded = set(base[:3])  # solo 2 nei 5 giorni base → deve estendere fino al target
    centers = windows.control_window_centers(
        ev, "America/New_York", reject=lambda t: t in excluded)
    assert len(centers) == config.K_CONTROL_TARGET  # ripristina verso 5
    assert all(c not in excluded for c in centers)


# --- assemble_event_controls (C0.2 + drop-log per provenienza) ---------

_TZ_US = "America/New_York"


def _bars_around(centers, price=100.0):
    """Barre 1-min costanti su ±15 min attorno a ciascun centro (returns = 0.0, validi)."""
    parts = []
    for c in centers:
        idx = pd.date_range(c - pd.Timedelta(minutes=15), c + pd.Timedelta(minutes=15),
                            freq="1min")
        parts.append(pd.Series(price, index=idx))
    return pd.concat(parts).sort_index()


def _ev_and_base(ev):
    return [ev] + windows.control_window_centers(ev, _TZ_US, reject=lambda t: False)


def test_assemble_happy_path_event_plus_five_controls():
    ev = pd.Timestamp("2021-06-09 12:30:00", tz="UTC")
    s = _bars_around(_ev_and_base(ev))
    out = windows.assemble_event_controls(ev, _TZ_US, s, s)
    assert out["event"]["r_e"] == 0.0 and out["event"]["r_b"] == 0.0
    assert out["n_controls"] == config.K_CONTROL_TARGET
    assert out["dropped"] == []


def test_assemble_one_missing_drops_no_extension():
    ev = pd.Timestamp("2021-06-09 12:30:00", tz="UTC")
    base = windows.control_window_centers(ev, _TZ_US, reject=lambda t: False)
    have = [ev] + base[1:]            # manca base[0] (nessuna barra)
    s = _bars_around(have)
    out = windows.assemble_event_controls(ev, _TZ_US, s, s)
    assert out["n_controls"] == 4    # 4 sopravvissuti ≥ 3 → niente estensione
    assert [d["reason"] for d in out["dropped"]] == ["no_data_eq"]


def test_assemble_below_min_extends_with_droplog():
    ev = pd.Timestamp("2021-06-09 12:30:00", tz="UTC")
    base = windows.control_window_centers(ev, _TZ_US, reject=lambda t: False)
    ev_local = ev.tz_convert(_TZ_US)
    extra_dates = windows._preceding_trading_days(ev_local.date(), 8)[5:]  # giorni 6,7,8
    extra = [windows._same_local_time_utc(d, ev_local.time(), _TZ_US) for d in extra_dates]
    have = [ev] + base[3:] + extra   # mancano base[0..2] → 2 sopravvissuti < 3 → estende
    s = _bars_around(have)
    out = windows.assemble_event_controls(ev, _TZ_US, s, s)
    assert [d["reason"] for d in out["dropped"]].count("no_data_eq") == 3
    assert out["n_controls"] == config.K_CONTROL_TARGET  # 2 + 3 extra = 5


def test_assemble_calendar_exclusion_logged():
    ev = pd.Timestamp("2021-06-09 12:30:00", tz="UTC")
    base = windows.control_window_centers(ev, _TZ_US, reject=lambda t: False)
    s = _bars_around([ev] + base)
    excl = {base[0]}
    out = windows.assemble_event_controls(ev, _TZ_US, s, s,
                                          is_calendar_excluded=lambda c: c in excl)
    assert out["n_controls"] == 4
    assert any(d["reason"] == "calendar" for d in out["dropped"])


# --- R3: diagnostica controlli condivisi tra regimi opposti -----------

def test_shared_control_diagnostic_counts_overlap():
    t = pd.Timestamp
    pos = [t("2021-06-01 12:30", tz="UTC"), t("2021-06-02 12:30", tz="UTC"),
           t("2021-06-03 12:30", tz="UTC")]
    neg = [t("2021-06-03 12:30", tz="UTC"),  # condiviso
           t("2021-06-08 12:30", tz="UTC")]
    d = windows.shared_control_diagnostic(pos, neg)
    assert d["n_shared"] == 1
    assert d["n_pos"] == 3 and d["n_neg"] == 2
    assert t("2021-06-03 12:30", tz="UTC") in d["shared"]


def test_dedup_shared_controls_removes_cross_regime_overlap():
    t = pd.Timestamp("2021-06-03 12:30", tz="UTC")          # controllo condiviso
    other = pd.Timestamp("2021-06-02 12:30", tz="UTC")
    pos = [{"event": {"center": pd.Timestamp("2021-06-10 12:30", tz="UTC"), "r_e": 0.0, "r_b": 0.0},
            "controls": [{"center": t, "r_e": 0.0, "r_b": 0.0},
                         {"center": other, "r_e": 0.0, "r_b": 0.0}]}]
    neg = [{"event": {"center": pd.Timestamp("2021-06-17 12:30", tz="UTC"), "r_e": 0.0, "r_b": 0.0},
            "controls": [{"center": t, "r_e": 0.0, "r_b": 0.0}]}]
    ptc = {"NFP": {"pos": pos, "neg": neg}, "CPI": {"pos": None, "neg": None},
           "FOMC": {"pos": None, "neg": None}, "ECB": {"pos": None, "neg": None}}
    cleaned, report = windows.dedup_shared_controls(ptc)
    assert report["NFP"] == 1
    pos_c = [c["center"] for cl in cleaned["NFP"]["pos"] for c in cl["controls"]]
    neg_c = [c["center"] for cl in cleaned["NFP"]["neg"] for c in cl["controls"]]
    assert t not in pos_c and t not in neg_c       # rimosso da entrambi
    assert other in pos_c                           # i non-condivisi restano
    assert windows.shared_control_diagnostic(pos_c, neg_c)["n_shared"] == 0


def test_shared_control_diagnostic_zero_when_disjoint():
    t = pd.Timestamp
    pos = [t("2021-06-01 12:30", tz="UTC")]
    neg = [t("2021-06-08 12:30", tz="UTC")]
    d = windows.shared_control_diagnostic(pos, neg)
    assert d["n_shared"] == 0
    assert d["shared"] == []
