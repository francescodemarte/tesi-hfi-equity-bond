"""data.py — Loader I/O (C0.1, C0.3 input).

Funzioni sottili di caricamento, separate dalla logica pura (windows/regimes)
così sono testabili su fixture e l'orchestrazione su file reali resta a run.py.

NB: i file minute-bar processati espongono una colonna prezzo già pronta
(`PX_LAST` per ES/TY/FGBL, `Mid_raw` per STXE); la costruzione del mid-quote
(Bid+Ask)/2 è a monte (process_refinitiv_data.py). Da confermare a esecuzione
che `PX_LAST` sia il mid.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def load_minute(path, price_col: str = "PX_LAST") -> pd.Series:
    """Carica un file minute-bar → Series prezzo indicizzata UTC, ordinata."""
    df = pd.read_csv(path, usecols=["Datetime_UTC", price_col])
    df["Datetime_UTC"] = pd.to_datetime(df["Datetime_UTC"], utc=True)
    s = df.set_index("Datetime_UTC")[price_col].sort_index()
    s.name = price_col
    return s


def daily_log_returns_from_minute(price_series: pd.Series) -> pd.Series:
    """Rendimenti log daily dalla chiusura (ultimo prezzo) per data UTC.

    Usato per ricalcolare la correlazione di regime dal RAW (correzione #2).
    Indice = date tz-naive (mezzanotte UTC normalizzata); primo giorno → NaN.
    """
    s = price_series.sort_index()
    dates = s.index.tz_convert("UTC").tz_localize(None).normalize()
    close = s.groupby(dates).last()
    close.index.name = "date"
    return np.log(close / close.shift(1))


def load_events(path) -> pd.DataFrame:
    """Carica il CSV eventi: parsa `timestamp` (UTC) e `date`."""
    ev = pd.read_csv(path)
    ev["timestamp"] = pd.to_datetime(ev["timestamp"], utc=True)
    if "date" in ev.columns:
        ev["date"] = pd.to_datetime(ev["date"])
    return ev
