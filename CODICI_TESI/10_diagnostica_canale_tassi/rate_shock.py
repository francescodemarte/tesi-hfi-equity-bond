"""rate_shock.py — Intensità dello shock di tasso nella finestra evento.

Per ciascun evento: variazione del contratto sui tassi nella finestra ±15 min
attorno al timestamp dell'annuncio, in valore ASSOLUTO (interessa la varianza
del fattore tasso, non il segno).

`extract_event_window` ricalca la disciplina di `07_protocollo_v2_signflip/
windows.extract_window`: edge time-based (mediana dei primi/ultimi `edge_min`
minuti), NaN se la finestra è insufficiente — niente fabbricazione.

Esogenità: il contratto di tasso (FFc2/FFc3 default, FEIc1-c4 alt.) NON è
componente di equity o bond → è una dimensione separata, a differenza del
breakeven (vietato altrove perché componente del bond).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config


def extract_event_window(prices: pd.Series, t_center: pd.Timestamp,
                         half_min: int = config.HALF_MIN_WINDOW,
                         edge_min: int = config.MEDIAN_EDGE_MIN) -> dict:
    """Estrae pre/post (mediana 5 min) sulla finestra ±15 min.

    Restituisce dict {pre, post, n_obs}. NaN se la finestra ha edge mancanti.
    """
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise TypeError("prices.index deve essere DatetimeIndex (timestamps)")
    t0 = t_center - pd.Timedelta(minutes=half_min)
    t1 = t_center + pd.Timedelta(minutes=half_min)
    w = prices.loc[t0:t1].dropna()
    if w.empty:
        return {"pre": float("nan"), "post": float("nan"), "n_obs": 0}
    pre_w = w.loc[t0:t0 + pd.Timedelta(minutes=edge_min)]
    post_w = w.loc[t1 - pd.Timedelta(minutes=edge_min):t1]
    if pre_w.empty or post_w.empty:
        return {"pre": float("nan"), "post": float("nan"), "n_obs": int(w.size)}
    return {"pre": float(pre_w.median()),
            "post": float(post_w.median()),
            "n_obs": int(w.size)}


def rate_shock_intensity(prices: pd.Series, t_center: pd.Timestamp,
                         half_min: int = config.HALF_MIN_WINDOW,
                         edge_min: int = config.MEDIAN_EDGE_MIN) -> float:
    """|Δprice| sulla finestra ±half_min minuti (intensità = |post − pre|).

    NaN se la finestra non è alimentabile (no fallback su valore costante).
    """
    w = extract_event_window(prices, t_center, half_min=half_min, edge_min=edge_min)
    if np.isnan(w["pre"]) or np.isnan(w["post"]):
        return float("nan")
    return float(abs(w["post"] - w["pre"]))


def build_event_intensity_table(events: pd.DataFrame, rate_prices: pd.Series,
                                contract_label: str,
                                half_min: int = config.HALF_MIN_WINDOW,
                                edge_min: int = config.MEDIAN_EDGE_MIN
                                ) -> pd.DataFrame:
    """Per ogni evento (timestamp, leg, regime): calcola intensità tasso.

    `events` deve avere colonne 'timestamp' (UTC), 'leg', 'regime'.
    Eventi non alimentabili → intensity = NaN; segnalati ma NON rimossi
    (la rimozione è dell'esecutore, secondo soglia dichiarata).
    """
    required = {"timestamp", "leg", "regime"}
    if not required.issubset(events.columns):
        raise ValueError(f"events deve avere colonne {required}, ha {set(events.columns)}")
    rows = []
    for _, ev in events.iterrows():
        ts = pd.Timestamp(ev["timestamp"])
        intensity = rate_shock_intensity(rate_prices, ts, half_min=half_min, edge_min=edge_min)
        rows.append({
            "timestamp": ts, "leg": str(ev["leg"]), "regime": str(ev["regime"]),
            "intensity_raw": intensity,
            "contract": contract_label,
        })
    return pd.DataFrame(rows)
