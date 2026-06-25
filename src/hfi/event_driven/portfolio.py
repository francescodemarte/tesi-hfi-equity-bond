"""portfolio.py — Strategia 4 (portafoglio combinato), pesi PRE-DICHIARATI.

Due schemi a priori (config.PORTFOLIO_WEIGHT_SCHEMES):
  - "equal": pesi uguali su tutte le strategie presenti.
  - "inverse_vol_on_training": pesi ∝ 1/σ stimata SOLO sul training set
    della rispettiva strategia (l'esecutore passa i training payoffs).

ANTI-OVERFITTING: qualsiasi schema diverso da questi due solleva.
"""
from __future__ import annotations

from collections.abc import Mapping

import numpy as np

import config


def compute_weights(train_payoffs: Mapping[str, np.ndarray],
                    scheme: str = config.PORTFOLIO_WEIGHT_DEFAULT) -> dict:
    """Pesi delle strategie del portafoglio. Solleva su schema non in lista."""
    if scheme not in config.PORTFOLIO_WEIGHT_SCHEMES:
        raise ValueError(
            f"schema {scheme!r} fuori da {config.PORTFOLIO_WEIGHT_SCHEMES}: "
            "lista a priori, non si introducono schemi nuovi post-hoc"
        )
    strategies = [s for s in train_payoffs.keys()]
    if not strategies:
        raise ValueError("train_payoffs vuoto")
    if scheme == "equal":
        w = 1.0 / len(strategies)
        return {s: w for s in strategies}
    # inverse_vol_on_training
    vols = {}
    for s in strategies:
        arr = np.asarray(train_payoffs[s], dtype=float)
        if len(arr) < 2:
            raise ValueError(f"{s}: training troppo corto per σ")
        sd = float(arr.std(ddof=1))
        if sd <= 0:
            raise ValueError(f"{s}: volatilità nulla, peso indefinito")
        vols[s] = sd
    inv = {s: 1.0 / v for s, v in vols.items()}
    total = sum(inv.values())
    return {s: v / total for s, v in inv.items()}


def combine_payoffs(per_strat_payoffs: dict, weights: dict) -> dict:
    """Concatena i payoff per-evento delle strategie, ognuno scalato col proprio
    peso. Restituisce payoff aggregati per i due orizzonti.

    Il portafoglio è una SOMMA DI POSIZIONI: ogni evento di ogni strategia
    entra come w_s · payoff_evento.
    """
    if set(weights.keys()) != set(per_strat_payoffs.keys()):
        raise ValueError("strategie in weights ≠ strategie in payoffs")
    out = {"event_window": [], "end_of_day": []}
    for s in per_strat_payoffs:
        w = float(weights[s])
        for h in ("event_window", "end_of_day"):
            arr = np.asarray(per_strat_payoffs[s][h], dtype=float)
            out[h].append(w * arr)
    return {h: np.concatenate(out[h]) if out[h] else np.array([])
            for h in ("event_window", "end_of_day")}
