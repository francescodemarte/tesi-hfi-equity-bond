"""equity_pb.py — Componente di tasso dell'equity (Campbell–Shiller, tail-dependent).

ΔP^B_eq = − Σ_{n=1..N} ρ^{n-1} · Δf_n
  - n ≤ m: Δf_n OSSERVATI dalla curva (m = len(delta_f));
  - n > m: COD A dalla griglia §2:
       T0       → Δf_n = 0
       TC       → Δf_n = Δf_m  (costante a Δf_m)
       TD_λ     → Δf_n = Δf_m · λ^(n-m)

Asimmetria con il bond:
  - bond = lettura diretta (cash-flow finiti).
  - equity = COSTRUZIONE: la coda domina quando m è corto e ρ→1.
  Il cancello (b) esiste per propagare l'incertezza di coda + ρ in β_str.
"""
from __future__ import annotations

import math

import numpy as np

import config


def rho_from_dp_bar(dp_bar: float) -> float:
    """ρ annuale dalla media di log(D/P): ρ_a = 1/(1 + exp(dp_bar))."""
    return 1.0 / (1.0 + math.exp(float(dp_bar)))


def rho_quarterly(rho_annual: float) -> float:
    """ρ_q = ρ_a^(1/4) (forward a passo trimestrale)."""
    if not (0.0 < rho_annual < 1.0):
        raise ValueError(f"rho_annual deve essere in (0,1), ricevuto {rho_annual}")
    return rho_annual ** 0.25


def _build_delta_f_extended(delta_f: np.ndarray, tail: str, N: int) -> np.ndarray:
    m = len(delta_f)
    if N < m:
        raise ValueError(f"N={N} < m={m}: non si tronca sotto le scadenze osservate")
    out = np.zeros(N, dtype=float)
    out[:m] = delta_f
    if N == m:
        return out
    if tail == "T0":
        # zero per n > m (già zero per costruzione)
        return out
    if tail == "TC":
        out[m:] = float(delta_f[-1])
        return out
    if tail in config.TAIL_DECAY_LAMBDA:
        lam = float(config.TAIL_DECAY_LAMBDA[tail])
        if not (0.0 < lam < 1.0):
            raise ValueError(f"λ {lam} fuori (0,1) per tail {tail}")
        # Δf_n = Δf_m · λ^(n-m) per n = m+1..N
        for j in range(m, N):
            out[j] = float(delta_f[-1]) * (lam ** (j - m + 1))
        return out
    raise ValueError(
        f"tail sconosciuto: {tail!r}. Disponibili: {tuple(config.TAIL_GRID)}"
    )


def delta_pb_equity(delta_f, rho: float, tail: str, N: int) -> float:
    """ΔP^B equity = − Σ_{n=1..N} ρ^{n-1} · Δf_n (Δf esteso secondo `tail`).

    Solleva su tail sconosciuto o N < len(delta_f). N≥len(delta_f) sempre;
    per T0 la coda è zero ma la somma include comunque i pesi ρ^{n-1}=0·Δf_n=0.
    """
    delta_f = np.asarray(delta_f, dtype=float)
    if len(delta_f) == 0:
        raise ValueError("delta_f vuoto")
    if not (0.0 < rho < 1.0):
        raise ValueError(f"rho deve essere in (0,1), ricevuto {rho}")
    full = _build_delta_f_extended(delta_f, tail=tail, N=N)
    weights = rho ** np.arange(N, dtype=float)
    return float(-np.dot(weights, full))


def delta_pb_equity_full_grid(delta_f, dp_bar: float, N: int,
                              tails=None, rho_offsets=None) -> list:
    """Profilo ΔP^B_equity sulla griglia coda × ρ (12 punti default).

    Restituisce lista di dict {tail, dp_bar_used, rho, value}.
    """
    tails = tails if tails is not None else config.TAIL_GRID
    offsets = rho_offsets if rho_offsets is not None else config.RHO_OFFSETS
    out = []
    for t in tails:
        for off in offsets:
            dp = float(dp_bar) + float(off)
            rho = rho_from_dp_bar(dp)
            v = delta_pb_equity(delta_f, rho=rho, tail=t, N=N)
            out.append({"tail": t, "dp_bar_used": dp, "rho": rho, "value": v})
    return out
