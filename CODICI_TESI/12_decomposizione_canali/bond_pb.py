"""bond_pb.py — Componente di tasso del bond.

Due formulazioni:

1) Lettura via duration (legacy, backward-compat coi 46 test sintetici):
   ΔP^B_bond = − D · Δy

2) Rivalutazione del CTD lungo la curva osservata (2026-06-23, fix Bug 2 v2):
   ΔP^B_bond = − Σ_{n=1..N_b} Δf_n,
   con Δf_n estesa secondo `tail` per n > m (m = len(delta_f)), N_b = round(D)
   in unità di Δf (per FFc1/2/3 ⇒ quarter ⇒ N_b ≈ 4·D_anni).
   Simmetrica al lato equity (`equity_pb`) ma SENZA discount ρ^(n-1) perché
   il bond ha cash-flow finiti. Estrapolazione tail (T0/TC/TD_λ) gestita
   riusando `equity_pb._build_delta_f_extended` per coerenza di codice.
"""
from __future__ import annotations

import numpy as np

import equity_pb


def delta_pb_bond(D: float, delta_y: float) -> float:
    """LEGACY: ΔP^B del bond come duration × (variazione yield). Solleva su D<0."""
    if D < 0:
        raise ValueError(f"duration D negativa non ammessa: {D}")
    return -float(D) * float(delta_y)


def delta_pb_bond_from_curve(delta_f, D_periods: float, tail: str) -> float:
    """ΔP^B del bond come somma dei Δf lungo la curva fino a N_b = round(D_periods).

    delta_f: array osservato lungo la front-curve (es. 3 punti per FFc1/2/3).
    D_periods: duration del bond in unità coerenti con delta_f (per FFc quarter,
      D_periods ≈ 4·D_anni). N_b = round(D_periods) — segno e magnitudine
      dell'output dipendono sia dai Δf osservati sia dall'estrapolazione tail.
    tail: stessa griglia di equity_pb — T0 (zero post-bordo), TC (costante a
      Δf_m post-bordo), TD_λ (decay λ post-bordo).

    Nessun ρ-discount: il bond ha maturità finita ⇒ pesi unitari.
    """
    delta_f = np.asarray(delta_f, dtype=float)
    if delta_f.size == 0:
        raise ValueError("delta_f vuoto")
    if D_periods < 0:
        raise ValueError(f"D_periods negativo non ammesso: {D_periods}")
    N_b = max(int(round(float(D_periods))), len(delta_f))
    full = equity_pb._build_delta_f_extended(delta_f, tail=tail, N=N_b)
    return float(-np.sum(full))
