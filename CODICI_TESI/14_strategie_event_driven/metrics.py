"""metrics.py — Sharpe per-evento ai due orizzonti (entrambi riportati)."""
from __future__ import annotations

import math

import numpy as np


def sharpe(payoffs) -> float:
    """Sharpe per-evento (LORDO di costi). NaN se n<2 o std praticamente 0.

    Tolleranza assoluta 1e-12 (margine ~10⁸–10¹⁰ ordini sopra l'errore IEEE
    ~1e-17 per payoff costanti come [0.1]*n, e ~10⁸–10¹⁰ sotto la scala
    tipica dei payoff event-driven di 1e-2 / 1e-4) per evitare Sharpe
    spurii enormi quando std è praticamente — non esattamente — zero.
    """
    p = np.asarray(payoffs, dtype=float)
    if p.size < 2:
        return float("nan")
    sd = float(p.std(ddof=1))
    if sd <= 1e-12:
        return float("nan")
    return float(p.mean() / sd)


def sharpe_per_horizon(payoffs_by_horizon: dict) -> dict:
    """Sharpe per ciascun orizzonte (entrambi riportati, mai selezione)."""
    out = {}
    for h, arr in payoffs_by_horizon.items():
        a = np.asarray(arr, dtype=float)
        out[h] = {
            "sharpe": sharpe(a),
            "mean": float(a.mean()) if a.size else float("nan"),
            "vol": float(a.std(ddof=1)) if a.size >= 2 else float("nan"),
            "n": int(a.size),
        }
    return out


def summary(payoffs_by_horizon: dict, *, period: str) -> dict:
    """Sommario per strategia/portafoglio: include il periodo coperto."""
    per_h = sharpe_per_horizon(payoffs_by_horizon)
    # n è lo stesso per i due orizzonti per costruzione (un evento per riga)
    n_vals = [v["n"] for v in per_h.values()]
    n = n_vals[0] if n_vals and all(x == n_vals[0] for x in n_vals) else max(n_vals or [0])
    return {"period": period, "n": int(n), **per_h}
