"""weighting.py — Combinazione inverse-vol fra gambe NFP/CPI.

`rolling_vol_at` calcola σ_roll,k SOLO su eventi PASSATI della gamba k,
finestra di N eventi (lunghezza CONGELATA sul training: nel run reale il
chiamante passa `window_events=config.INV_VOL_ROLLING_EVENTS`).
"""
from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd


def rolling_vol_at(eps_series: pd.Series, t: pd.Timestamp,
                   window_events: int) -> float:
    """σ stimata sulla finestra di `window_events` eventi STRETTAMENTE precedenti `t`.

    Solleva se ci sono meno di `window_events` osservazioni passate (no
    fallback: la spec impone lunghezza congelata, non adattata).
    """
    eps = eps_series.sort_index()
    past = eps.loc[eps.index < t]
    if len(past) < window_events:
        raise ValueError(
            f"solo {len(past)} eventi passati a {t}, servono {window_events} (lunghezza congelata)"
        )
    window = past.iloc[-window_events:]
    return float(window.std(ddof=1))


def combine_legs(payoffs: Mapping[str, float], sigmas: Mapping[str, float]) -> dict:
    """Combinazione inverse-vol: ω_k ∝ 1/σ_k. Se manca una gamba a quell'evento,
    pesa solo le altre. Solleva se i set di chiavi non coincidono.
    """
    if set(payoffs.keys()) != set(sigmas.keys()):
        raise ValueError(f"payoffs {set(payoffs)} ≠ sigmas {set(sigmas)}")
    if not payoffs:
        return {"payoff_combined": float("nan"), "weights": {}}
    inv = {k: 1.0 / s for k, s in sigmas.items() if s > 0}
    if not inv:
        return {"payoff_combined": float("nan"), "weights": {}}
    total = sum(inv.values())
    w = {k: v / total for k, v in inv.items()}
    pc = float(sum(w[k] * payoffs[k] for k in w))
    return {"payoff_combined": pc, "weights": w}
