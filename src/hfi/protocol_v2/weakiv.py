"""weakiv.py — Strumento debole (R2, R5, T1).

- `mop_critical_value`: cv di Montiel Olea–Pflueger (2013), TSLS, criterio
  **bias relativo (Nagar)** — NON size — via approssimazione di Patnaik (1949),
  forma semplificata conservativa. Riproduce i valori pubblicati (τ=10%→23.109,
  5%→37.42, ecc.), NON lo Stock–Yogo omoschedastico (K=1 = 16.38). NB: il mean
  bias non esiste con K=1 (just-identified), ma il Nagar bias sì — per questo la
  soglia è definita anche a strumento singolo. Vedi SPEC §2bis E1.
- `mop_effective_f`: F efficace = (ΔVar)²/V̂ (V̂ robusto-clusterizzato, calcolato altrove).
- `ar_set`: insieme di Anderson–Rubin per inversione di g(β)=ΔCov−β·ΔVar, con se
  dal bootstrap clusterizzato; estremi della griglia → aperto/illimitato.

Algoritmo MOP (Pflueger–Wang 2015, step 4): cv = ncx2.ppf(1-α, K_eff, x·K_eff)/K_eff,
con non-centralità semplificata conservativa x = 1/τ e K_eff il dof efficace.
Per K=1 (strumento singolo) K_eff = 1: lo scalare W₂ si cancella nella formula
del dof efficace di MOP. (Validato in tests/test_weakiv.py contro i valori pubblicati.)
"""
from __future__ import annotations

import numpy as np
from scipy.stats import ncx2, norm, chi2


def mop_critical_value(K: int = 1, worst_case_size: float = 0.10,
                       nominal: float = 0.05,
                       effective_dof: float | None = None) -> float:
    """cv MOP per la configurazione realizzata.

    τ = `worst_case_size` = soglia di **bias relativo worst-case (Nagar)**, NON
    size (il «10%» del protocollo); `nominal` = livello del test debole-IV (5%).
    Non-centralità semplificata conservativa x = 1/τ.
    K_eff = `effective_dof` se passato; altrimenti 1 per K=1 (la formula MOP del
    dof efficace dà esattamente 1 quando c'è un solo strumento). Per K>1 va
    passato `effective_dof` (la config del protocollo è K=1).
    """
    tau = worst_case_size
    x = 1.0 / tau
    if effective_dof is not None:
        k_eff = float(effective_dof)
    elif K == 1:
        k_eff = 1.0
    else:
        raise NotImplementedError(
            "Per K>1 passare effective_dof (formula MOP del dof efficace su W₂). "
            "La configurazione del protocollo è K=1."
        )
    return float(ncx2.ppf(1.0 - nominal, k_eff, x * k_eff) / k_eff)


def mop_effective_f(dVar_hat: float, var_dVar_hat: float) -> float:
    """F efficace MOP per K=1: (ΔVar)² / V̂.

    V̂ è la varianza di ΔVar (differenza di varianze campionarie → quarti momenti),
    stimata robusta e clusterizzata per evento altrove (inference.event_cluster_bootstrap).
    """
    return float(dVar_hat ** 2 / var_dVar_hat)


def ar_set(dCov_hat, dVar_hat, dCov_bs, dVar_bs, beta_grid,
           z_crit: float = 1.96) -> dict:
    """Insieme di Anderson–Rubin per β, inversione di g(β)=ΔCov−β·ΔVar.

    Per ogni β: g(β) = dCov_hat − β·dVar_hat (stima puntuale);
    se(β) = std (ddof=1) del bootstrap clusterizzato di (dCov_bs − β·dVar_bs);
    β è accettato se |g(β)/se(β)| ≤ z_crit. Se l'insieme accettato tocca un
    estremo della griglia, è riportato come APERTO/ILLIMITATO su quel lato
    (non troncato all'estremo). `empty=True` se nessun β è accettato.
    """
    grid = np.asarray(beta_grid, dtype=float)
    dCov_bs = np.asarray(dCov_bs, dtype=float)
    dVar_bs = np.asarray(dVar_bs, dtype=float)

    accept = np.empty(grid.size, dtype=bool)
    for i, b in enumerate(grid):
        g = dCov_hat - b * dVar_hat
        se = (dCov_bs - b * dVar_bs).std(ddof=1)
        z = (g / se) if se > 0 else np.inf
        accept[i] = abs(z) <= z_crit

    if not accept.any():
        return {"empty": True, "low": None, "high": None,
                "unbounded_low": False, "unbounded_high": False}

    idx = np.flatnonzero(accept)
    lo_i, hi_i = int(idx[0]), int(idx[-1])
    return {
        "empty": False,
        "low": float(grid[lo_i]),
        "high": float(grid[hi_i]),
        "unbounded_low": lo_i == 0,
        "unbounded_high": hi_i == grid.size - 1,
    }


# --- AR per inferenza T4/T5 (E2: inferenza primaria su AR) --------------

def ar_pvalue(dCov_hat, dVar_hat, dCov_bs, dVar_bs, beta0) -> float:
    """p-value AR (bilaterale) per H0: β=β0.

    g(β0)=ΔCov−β0·ΔVar; se(β0)=std (ddof=1) del bootstrap clusterizzato di
    (ΔCov_bs−β0·ΔVar_bs); z=g/se; p=2(1−Φ(|z|)). NaN se se≤0.
    """
    g = dCov_hat - beta0 * dVar_hat
    se = np.std(np.asarray(dCov_bs, float) - beta0 * np.asarray(dVar_bs, float), ddof=1)
    if se <= 0:
        return float("nan")
    return float(2.0 * (1.0 - norm.cdf(abs(g / se))))


def ar_one_side(ar: dict):
    """Lato dello zero su cui giace INTERAMENTE un AR-set: '+' / '-' / None.

    '+' se interamente positivo (limite inferiore finito > 0), '-' se interamente
    negativo (limite superiore finito < 0); None se attraversa lo zero, è vuoto o
    illimitato dal lato che includerebbe lo zero.
    """
    if ar.get("empty"):
        return None
    if (not ar["unbounded_low"]) and ar["low"] is not None and ar["low"] > 0:
        return "+"
    if (not ar["unbounded_high"]) and ar["high"] is not None and ar["high"] < 0:
        return "-"
    return None


def _ar_z(cell, b):
    dCh, dVh, dCb, dVb = cell
    g = dCh - b * dVh
    se = np.std(np.asarray(dCb, float) - b * np.asarray(dVb, float), ddof=1)
    return (g / se) if se > 0 else np.inf


def delta_ar_pvalue(pos, neg, beta_grid) -> float:
    """p-value AR per H0: β(pos)=β(neg) (Δ_H=0), via proiezione (E2).

    pos, neg = (ΔCov_hat, ΔVar_hat, ΔCov_bs, ΔVar_bs) di due celle INDIPENDENTI.
    Statistica AR combinata in un β comune: T(b)=S_pos(b)²+S_neg(b)²; il minimo
    T*=min_b T(b) testa l'esistenza di un β comune (2 momenti − 1 parametro
    comune → 1 grado di libertà). p = 1 − χ²₁(T*). Δ_H≠0 quando p è piccolo.
    """
    grid = np.asarray(beta_grid, float)
    T = np.array([_ar_z(pos, b) ** 2 + _ar_z(neg, b) ** 2 for b in grid])
    Tstar = float(np.min(T))
    return float(1.0 - chi2.cdf(Tstar, 1))
