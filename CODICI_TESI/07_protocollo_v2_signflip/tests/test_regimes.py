"""Test di regimes.py (C0.3) — TDD stretto.

Regime = SEGNO della correlazione mobile a 63 giorni dei rendimenti daily,
calcolata sul RAW (correzione #2), con lag t-1 (anti-look-ahead).
"""
import numpy as np
import pandas as pd

import regimes


def test_label_sign_boundaries():
    assert regimes.label_sign(0.5) == "positivo"
    assert regimes.label_sign(-0.5) == "negativo"
    assert regimes.label_sign(0.0) == "negativo"     # >0 stretto → 0 è negativo
    assert regimes.label_sign(float("nan")) is None


def test_rolling_regime_nan_during_warmup_then_sign():
    n = 200
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    rng = np.random.default_rng(0)
    base = rng.standard_normal(n)
    eq = base.copy()
    bond = np.empty(n)
    bond[:100] = base[:100] + 0.01 * rng.standard_normal(100)    # corr ≈ +1
    bond[100:] = -base[100:] + 0.01 * rng.standard_normal(100)   # corr ≈ -1
    daily = pd.DataFrame({"eq": eq, "bond": bond}, index=idx)

    out = regimes.rolling_sign_regime(daily, "eq", "bond", window=63, lag=1)

    # i primi `window` valori di corr sono NaN → regime None
    assert out["regime"].iloc[:63].isna().all()
    # ben dentro il primo blocco (finestra interamente nel blocco +) → positivo
    assert out["regime"].iloc[90] == "positivo"
    # ben dentro il secondo blocco (finestra interamente nel blocco -) → negativo
    assert out["regime"].iloc[190] == "negativo"


def test_regime_uses_lagged_correlation():
    idx = pd.date_range("2020-01-01", periods=80, freq="B")
    rng = np.random.default_rng(1)
    daily = pd.DataFrame({"eq": rng.standard_normal(80),
                          "bond": rng.standard_normal(80)}, index=idx)
    out = regimes.rolling_sign_regime(daily, "eq", "bond", window=10, lag=1)
    # corr_lag è esattamente corr shiftata di 1 (anti-look-ahead)
    pd.testing.assert_series_equal(out["corr_lag"], out["corr"].shift(1),
                                   check_names=False)


def test_assign_regime_backward_fill_preserves_order():
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    regime = pd.Series(["negativo"] * 10, index=idx)
    regime.iloc[5:] = "positivo"   # da 2020-01-06 in poi
    ev = pd.to_datetime(["2020-01-03", "2020-01-08", "2020-01-06"])  # ordine non monotono
    out = regimes.assign_regime(ev, regime)
    assert list(out) == ["negativo", "positivo", "positivo"]


def test_no_lookahead_future_returns_dont_change_event_regime():
    # ANTI-LOOK-AHEAD: cambiare i rendimenti DOPO l'evento non deve cambiare il
    # regime assegnato a quell'evento (smaschera bfill o corr non laggata).
    n = 150
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    rng = np.random.default_rng(7)
    base = rng.standard_normal(n)
    daily = pd.DataFrame({"eq": base, "bond": base + 0.05 * rng.standard_normal(n)},
                         index=idx)
    event_date = idx[100]

    reg0 = regimes.rolling_sign_regime(daily, "eq", "bond", window=63, lag=1)["regime"]
    r0 = regimes.assign_regime([event_date], reg0)[0]
    assert r0 is not None

    # perturbo TUTTI i rendimenti strettamente DOPO l'evento (segno invertito ×100)
    daily2 = daily.copy()
    post = daily2.index > event_date
    daily2.loc[post, "bond"] = -daily2.loc[post, "bond"] * 100.0
    reg1 = regimes.rolling_sign_regime(daily2, "eq", "bond", window=63, lag=1)["regime"]
    r1 = regimes.assign_regime([event_date], reg1)[0]

    assert r1 == r0  # invariato → nessun look-ahead


def test_build_exogenous_regime_high_when_value_geq_causal_median():
    # E3 T7: regime esogeno binario, mediana rolling CAUSALE, lag t-1, split "≥"→alto.
    n = 200
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    s = pd.Series(np.arange(n, dtype=float), index=idx)   # strettamente crescente
    out = regimes.build_exogenous_regime(s, window=20, lag=1)
    # warmup: i primi `window` (≥) sono NaN (la mediana causale richiede 20 punti)
    assert out["regime"].iloc[:20].isna().all()
    # in serie monotona crescente, valore a t-1 è sempre ≥ mediana causale → "alto"
    assert (out["regime"].iloc[25:] == "alto").all()


def test_build_exogenous_regime_low_when_value_below():
    # serie monotona DECRESCENTE: valore a t-1 è sempre < mediana causale → "basso"
    n = 200
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    s = pd.Series(np.arange(n, 0, -1, dtype=float), index=idx)
    out = regimes.build_exogenous_regime(s, window=20, lag=1)
    assert (out["regime"].iloc[25:] == "basso").all()


def test_build_exogenous_regime_no_lookahead():
    # ANTI-LOOK-AHEAD: alterare i valori DOPO t non cambia il regime a t.
    n = 80
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    rng = np.random.default_rng(3)
    s = pd.Series(rng.standard_normal(n), index=idx)
    out0 = regimes.build_exogenous_regime(s, window=20, lag=1)
    label0 = out0["regime"].iloc[40]

    s2 = s.copy()
    s2.iloc[41:] = s2.iloc[41:] * 100.0 + 50.0   # shock POST t=40
    out1 = regimes.build_exogenous_regime(s2, window=20, lag=1)
    assert out1["regime"].iloc[40] == label0


def test_assign_regime_handles_duplicate_event_dates():
    # BUG REALE (Esecutore 2026-06-22): event_dates con duplicati su dati reali
    # (FOMC decision+press conf stesso giorno, FOMC+CPI sovrapposti) ⇒ reindex falliva.
    # Comportamento atteso: output di stessa lunghezza dell'input, stesso valore per
    # date duplicate (il regime è una proprietà del GIORNO, non del singolo annuncio).
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    regime = pd.Series(["negativo"] * 10, index=idx)
    regime.iloc[5:] = "positivo"
    ev = pd.to_datetime([
        "2020-01-08",     # positivo
        "2020-01-08",     # duplicato (es. FOMC decision + press stesso giorno)
        "2020-01-03",     # negativo
        "2020-01-08",     # triplo (es. + CPI)
    ])
    out = regimes.assign_regime(ev, regime)
    assert len(out) == 4
    assert list(out) == ["positivo", "positivo", "negativo", "positivo"]


def test_assign_regime_duplicates_with_warmup_returns_none():
    # date duplicate ANTECEDENTI al primo regime disponibile → None su tutti
    idx = pd.date_range("2020-02-01", periods=5, freq="D")
    regime = pd.Series(["positivo"] * 5, index=idx)
    ev = pd.to_datetime(["2020-01-15", "2020-01-15"])  # duplicato in warmup
    out = regimes.assign_regime(ev, regime)
    assert len(out) == 2
    for v in out:
        assert v is None or (isinstance(v, float) and np.isnan(v))


def test_assign_regime_robust_to_duplicate_dates_in_input_series():
    # presidio difensivo: anche se la serie regime fosse passata con date duplicate
    # (caso patologico ma plausibile), assign_regime non deve sollevare.
    idx = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-02", "2020-01-05"])
    regime = pd.Series(["negativo", "negativo", "positivo", "positivo"], index=idx)
    ev = pd.to_datetime(["2020-01-03", "2020-01-06"])
    out = regimes.assign_regime(ev, regime)
    assert len(out) == 2     # non solleva, restituisce un valore per ciascun evento


def test_assign_regime_handles_tz_aware_event_dates():
    # BUG REALE 2 (Esecutore 2026-06-22): events["timestamp"] è UTC tz-aware,
    # regime_series (da FRED) è tz-naive ⇒ assign_regime restituiva tutto allo
    # stesso valore (l'ULTIMO valore ffill-ato) per gli eventi tz-aware,
    # silenziosamente, perché pandas considera tz-aware > tz-naive in confronto.
    # Presidio: output su tz-aware deve coincidere con output sui corrispondenti tz-naive.
    idx = pd.date_range("2013-01-01", "2024-12-31", freq="D")  # tz-naive (regime daily)
    reg = pd.Series(["alto"] * len(idx), index=idx)
    reg.iloc[-200:] = "basso"

    ev_naive = pd.to_datetime(["2013-07-31", "2015-09-17", "2020-03-15", "2022-07-27"])
    ev_aware = pd.to_datetime(["2013-07-31 18:00:00", "2015-09-17 18:00:00",
                                "2020-03-15 21:00:00", "2022-07-27 18:00:00"], utc=True)

    out_naive = regimes.assign_regime(ev_naive, reg)
    out_aware = regimes.assign_regime(ev_aware, reg)
    assert list(out_aware) == list(out_naive)


def test_assign_regime_tz_aware_preserves_duplicate_semantics():
    # combina Bug 1 (duplicati) + Bug 2 (tz-aware): le date duplicate tz-aware
    # devono restituire lo stesso regime e con la stessa lunghezza.
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    reg = pd.Series(["negativo"] * 10, index=idx)
    reg.iloc[5:] = "positivo"
    ev = pd.to_datetime(["2020-01-08 14:00", "2020-01-08 14:30",
                          "2020-01-03 12:00"], utc=True)
    out = regimes.assign_regime(ev, reg)
    assert len(out) == 3
    assert list(out) == ["positivo", "positivo", "negativo"]


def test_relabel_per_type_with_regime_distributes_real_tz_aware_events():
    # Replica esattamente la sezione T7 di run.py:_relabel_per_type_with_regime
    # con cluster i cui event.center sono tz-aware UTC (come dai dati reali);
    # i regimi devono essere distribuiti, non tutti in 'neg' come col bug 2.
    import run
    idx = pd.date_range("2018-01-01", periods=2000, freq="D")
    reg_series = pd.Series(np.where(np.arange(2000) % 2 == 0, "alto", "basso"),
                            index=idx)
    # 10 eventi tz-aware UTC distribuiti nel range
    centers = pd.to_datetime(
        ["2018-03-15 18:00", "2018-07-25 18:00", "2019-01-30 19:00",
         "2019-06-19 18:00", "2020-03-15 21:00", "2020-09-16 18:00",
         "2021-03-17 18:00", "2021-12-15 19:00", "2022-07-27 18:00",
         "2023-02-01 19:00"], utc=True)
    ptc = {"NFP": {"pos": [{"event": {"center": c, "r_e": 0.0, "r_b": 0.0}, "controls": []}
                            for c in centers],
                    "neg": []},
            "CPI": {"pos": [], "neg": []},
            "FOMC": {"pos": [], "neg": []},
            "ECB": {"pos": [], "neg": []}}
    relabel = run._relabel_per_type_with_regime(ptc, reg_series)
    n_pos = len(relabel["NFP"]["pos"]); n_neg = len(relabel["NFP"]["neg"])
    assert n_pos + n_neg == 10
    # Non tutti in neg (era il sintomo del Bug 2: 0 / 10)
    assert n_pos > 0 and n_neg > 0


def test_assign_regime_none_before_first_available():
    idx = pd.date_range("2020-02-01", periods=5, freq="D")
    regime = pd.Series(["positivo"] * 5, index=idx)
    ev = pd.to_datetime(["2020-01-15"])  # prima di qualsiasi regime disponibile
    out = regimes.assign_regime(ev, regime)
    assert out[0] is None or (isinstance(out[0], float) and np.isnan(out[0]))
