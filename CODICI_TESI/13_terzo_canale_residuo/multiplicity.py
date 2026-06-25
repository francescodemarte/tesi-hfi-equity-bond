"""multiplicity.py — Benjamini–Yekutieli su famiglia 12 (spec §6).

Step-up con c(m) = Σ_{i=1..m} 1/i (test dipendenti). Soglia rank i =
i·q/(m·c(m)); rigetta il massimo rank i con p_(i) ≤ soglia_i e tutti i p
con rank ≤ i.
"""
from __future__ import annotations

import numpy as np


def benjamini_yekutieli(p, q: float, m: int) -> dict:
    """BY step-up. Solleva se len(p) ≠ m (famiglia FISSA a priori)."""
    p_arr = np.asarray(p, dtype=float)
    if len(p_arr) != m:
        raise ValueError(f"len(p)={len(p_arr)} ≠ m={m}: famiglia fissa a priori")
    c_m = float(sum(1.0 / i for i in range(1, m + 1)))
    order = np.argsort(p_arr, kind="stable")
    p_sorted = p_arr[order]
    thresholds = np.array([i * q / (m * c_m) for i in range(1, m + 1)])
    passed = p_sorted <= thresholds
    if not passed.any():
        rejected = np.zeros(m, dtype=bool); crit = None
    else:
        i_max = int(np.max(np.where(passed)[0]))
        rs = np.zeros(m, dtype=bool); rs[: i_max + 1] = True
        rejected = np.zeros(m, dtype=bool); rejected[order] = rs
        crit = float(thresholds[i_max])
    return {"rejected": rejected, "m": m, "c_m": c_m, "crit": crit}
