"""decomposition.py — Decomposizione in canali a frequenza GIORNALIERA.

ATTENZIONE — FREQUENZA E RUOLO. Questa è evidenza SECONDARIA, esplicitamente
etichettata a frequenza GIORNALIERA (daily). NON è la frequenza-evento dello
stimatore principale b_H (Rigobon-Sack a due regimi): va tenuta SEPARATA da
quello. Serve solo come lettura descrittivo-strutturale dei canali.

Qui vive SOLO l'aritmetica pura dei canali, testabile su input sintetici.
Il caricamento dei file reali (FRED, SDA, dividend futures) NON sta qui:
è demandato a run.py.

Tutte le funzioni sono vettorizzabili: accettano scalari o np.array e
operano elemento-per-elemento.
"""
from __future__ import annotations

import numpy as np


def bond_channels(r_b, delta_r_real, delta_pi, d_bond) -> dict:
    """Decomposizione (daily, secondaria) del rendimento bond in canali.

    Canale tasso reale, canale inflazione (breakeven) e residuo:
      c_b_rate = -delta_r_real * d_bond
      c_b_pi   = -delta_pi     * d_bond
      c_b_res  = r_b - c_b_rate - c_b_pi   (identità additiva esatta).

    Vettorizzata: r_b == c_b_rate + c_b_pi + c_b_res elemento-per-elemento.
    """
    c_b_rate = -delta_r_real * d_bond
    c_b_pi = -delta_pi * d_bond
    c_b_res = r_b - c_b_rate - c_b_pi
    return {"c_b_rate": c_b_rate, "c_b_pi": c_b_pi, "c_b_res": c_b_res}


def equity_partial_duration(weights, horizons) -> float:
    """Duration parziale equity = sum(weights*horizons) / sum(weights).

    Nan-safe: i NaN nei pesi sono ignorati (np.nansum). Ritorna np.nan se la
    somma dei pesi (validi) e' <= 0. Frequenza daily, evidenza secondaria.
    """
    weights = np.asarray(weights, dtype=float)
    horizons = np.asarray(horizons, dtype=float)
    den = np.nansum(weights)
    if den <= 0:
        return np.nan
    num = np.nansum(weights * horizons)
    return float(num / den)


def equity_channels(r_e, delta_r_real, duration_partial) -> dict:
    """Decomposizione (daily, secondaria) del rendimento equity in canali.

    Canale tasso reale e residuo:
      c_e_rate = -delta_r_real * duration_partial
      c_e_res  = r_e - c_e_rate   (identità additiva esatta).

    Vettorizzata: r_e == c_e_rate + c_e_res elemento-per-elemento.
    """
    c_e_rate = -delta_r_real * duration_partial
    c_e_res = r_e - c_e_rate
    return {"c_e_rate": c_e_rate, "c_e_res": c_e_res}


def twin_cov(c_e_res, c_b_res) -> float:
    """Covarianza "gemella" residuo-residuo per cella (ddof=1).

    = np.cov(c_e_res, c_b_res, ddof=1)[0, 1]. Misura il comovimento dei
    residui dei due canali a frequenza daily (evidenza secondaria).
    """
    c_e_res = np.asarray(c_e_res, dtype=float)
    c_b_res = np.asarray(c_b_res, dtype=float)
    return float(np.cov(c_e_res, c_b_res, ddof=1)[0, 1])
