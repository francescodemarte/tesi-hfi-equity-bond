"""regimes.py — Classificazione di regime dal RAW (C0.3, correzione #2).

Il regime di un evento è il SEGNO della correlazione mobile a `window` (63)
giorni dei rendimenti daily equity~bond, calcolata sui rendimenti grezzi (NON
dalle colonne `corr3m_US`/`rho_tilde` del CSV eventi), con lag t-1 per evitare
look-ahead. Soglia = 0 (ρ>0 → positivo, altrimenti negativo).
"""
from __future__ import annotations

import pandas as pd

from config import (REGIME_WINDOW_DAYS, REGIME_LAG_BDAYS, REGIME_THRESHOLD,
                    T7_ROLLING_DAYS, T7_LAG_BDAYS)


def label_sign(x, threshold: float = REGIME_THRESHOLD):
    """Etichetta dal segno: ρ>soglia → 'positivo', ρ≤soglia → 'negativo', NaN → None."""
    if pd.isna(x):
        return None
    return "positivo" if x > threshold else "negativo"


def rolling_sign_regime(daily: pd.DataFrame, eq_col: str, bond_col: str,
                        window: int = REGIME_WINDOW_DAYS,
                        lag: int = REGIME_LAG_BDAYS,
                        threshold: float = REGIME_THRESHOLD) -> pd.DataFrame:
    """Correlazione mobile a `window` giorni, laggata di `lag`, etichettata per segno.

    Restituisce un DataFrame con colonne: `corr` (corr mobile), `corr_lag`
    (corr shiftata di `lag`, = informazione fino a t-lag), `regime` (etichetta).
    """
    daily = daily.sort_index()
    corr = daily[eq_col].rolling(window).corr(daily[bond_col])
    corr_lag = corr.shift(lag)
    regime = corr_lag.map(lambda x: label_sign(x, threshold))
    return pd.DataFrame({"corr": corr, "corr_lag": corr_lag, "regime": regime})


def build_exogenous_regime(daily_series: pd.Series,
                           window: int = T7_ROLLING_DAYS,
                           lag: int = T7_LAG_BDAYS) -> pd.DataFrame:
    """E3 T7 — regime esogeno BINARIO da serie macro daily.

    Valore a t-lag ≥ MEDIANA rolling CAUSALE su finestra `window` (calcolata
    fino a t-lag) ⇒ etichetta «alto»; altrimenti «basso». Lo split è ≥ (a parità
    si attribuisce «alto»). NaN durante il warmup. Lag t-lag su entrambi (valore
    e mediana) per anti-look-ahead.
    """
    s = daily_series.sort_index()
    val_lag = s.shift(lag)
    med_causal = s.rolling(window).median().shift(lag)
    high = val_lag >= med_causal
    regime = high.map(lambda x: ("alto" if x else "basso") if not pd.isna(x) else None)
    # dove val_lag o med_causal sono NaN (warmup), `>=` produce False ma vogliamo None
    warmup = val_lag.isna() | med_causal.isna()
    regime = regime.where(~warmup, None)
    return pd.DataFrame({"value_lag": val_lag, "median_causal_lag": med_causal,
                         "regime": regime})


def assign_regime(event_dates, regime_series: pd.Series):
    """Regime per ciascuna data evento = ultimo regime noto in data ≤ evento.

    As-of *all'indietro nel tempo* (= merge_asof direction='backward'): si propaga
    in avanti l'ULTIMO valore con data ≤ evento (pandas `ffill`), NON il prossimo
    valore futuro (`bfill` sarebbe look-ahead). Il lag t-1 è già dentro
    `regime_series`, quindi nessun rendimento successivo all'evento entra nel suo
    regime. Preserva l'ordine di `event_dates`; None/NaN prima del primo regime
    disponibile.
    """
    rs = regime_series.copy()
    rs.index = pd.to_datetime(rs.index)
    if rs.index.tz is not None:
        rs.index = rs.index.tz_convert("UTC").tz_localize(None)
    rs.index = rs.index.normalize()
    rs = rs.sort_index()
    # Dedup difensivo della serie regime (input patologico ma plausibile).
    rs = rs[~rs.index.duplicated(keep="last")]
    # NORMALIZZAZIONE TZ (Bug 2, Esecutore 2026-06-22): l'input può essere
    # tz-aware (events.timestamp è UTC dal CSV) mentre la serie regime è
    # tz-naive (da FRED). Mix tz-naive/tz-aware nel `union`+`reindex` produce
    # un match silenziosamente sbagliato (tz-aware confrontato > tz-naive →
    # ffill all'ultimo valore). Il kernel porta a tz-naive (UTC) qualunque
    # input, e successivamente normalizza al giorno.
    ev = pd.to_datetime(pd.Index(event_dates))
    if ev.tz is not None:
        ev = ev.tz_convert("UTC").tz_localize(None)
    ev = ev.normalize()
    # Union su `ev.unique()`: l'asse di reindex resta UNIQUE; il regime è una
    # proprietà del GIORNO, quindi date duplicate in `ev` propagano la stessa
    # etichetta (FOMC decision+press lo stesso giorno → stesso regime).
    full = rs.reindex(rs.index.union(pd.Index(ev.unique()))).ffill()
    # `.loc[ev]` ammette selector con duplicati e li replica.
    return full.loc[ev].values
