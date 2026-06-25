"""excess.py — Comovimento realizzato, atteso, varianza pre-annuncio, eccesso ε.

Per evento i (gamba k, regime g_i):
  c_i = r_{e,i} · r_{b,i}                   (covarianza realizzata per-evento)
  a_i = media giornaliera di r_eq·r_bond su t-3..t-1
  σ²_pre,i = media combinata dei quadrati dei rendimenti giornalieri su t-3..t-1
  ε_i = (c_i - a_i) / σ²_pre,i              (eccesso normalizzato adimensionale)
"""
from __future__ import annotations

import numpy as np


def realized_comovement(r_eq_event: float, r_bo_event: float) -> float:
    """c_i = r_e,i · r_b,i (covarianza realizzata per-evento, media zero assunta)."""
    return float(r_eq_event) * float(r_bo_event)


def expected_comovement(r_eq_proxy, r_bo_proxy) -> float:
    """a_i = media giornaliera del prodotto r_eq·r_bond su finestra di aspettativa."""
    eq = np.asarray(r_eq_proxy, dtype=float)
    bo = np.asarray(r_bo_proxy, dtype=float)
    if eq.shape != bo.shape:
        raise ValueError("r_eq_proxy e r_bo_proxy devono avere stessa lunghezza")
    if eq.size == 0:
        raise ValueError("finestra di aspettativa vuota")
    return float(np.mean(eq * bo))


def pre_variance(r_eq_proxy, r_bo_proxy) -> float:
    """σ²_pre,i = media combinata dei quadrati dei rendimenti giornalieri.

    Convenzione esplicita (la spec dice "proxy della varianza pre-evento"):
        σ²_pre = (mean(r_eq²) + mean(r_bo²)) / 2.
    Adimensionalizza ε rispetto a una scala comune equity+bond — coerente
    con il significato di ε come correlazione-like.
    """
    eq = np.asarray(r_eq_proxy, dtype=float)
    bo = np.asarray(r_bo_proxy, dtype=float)
    if eq.size == 0:
        raise ValueError("finestra di aspettativa vuota")
    return float((np.mean(eq ** 2) + np.mean(bo ** 2)) / 2.0)


def epsilon(c: float, a: float, sigma2_pre: float) -> float:
    """ε_i = (c_i - a_i) / σ²_pre,i. NaN se σ²_pre ≤ 0 (no fallback inventato)."""
    if not (sigma2_pre > 0):
        return float("nan")
    return float((c - a) / sigma2_pre)
