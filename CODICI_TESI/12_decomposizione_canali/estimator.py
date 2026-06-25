"""estimator.py — β_str = ΔCov(r̃_e, r̃_b) / ΔVar(r̃_b) (Rigobon-Sack, sui NETTI).

I rendimenti netti r̃_e, r̃_b si ottengono in `netting.py` (Passo 2) sottraendo
ΔP^B_e e ΔP^B_b dai rendimenti grezzi. Qui solo l'estimatore + shrink.
"""
from __future__ import annotations

import numpy as np


def beta_str(re_e, rb_e, re_c, rb_c) -> dict:
    """β_str sui NETTI (entrambi i lati): ΔCov / ΔVar (ddof=1).

    Restituisce `dVar_b_tilde`, `dCov_eb_tilde`, `beta_str` (NaN se |ΔVar|<1e-20).
    """
    re_e = np.asarray(re_e, float); rb_e = np.asarray(rb_e, float)
    re_c = np.asarray(re_c, float); rb_c = np.asarray(rb_c, float)
    var_e = float(np.var(rb_e, ddof=1)); var_c = float(np.var(rb_c, ddof=1))
    cov_e = float(np.cov(re_e, rb_e, ddof=1)[0, 1])
    cov_c = float(np.cov(re_c, rb_c, ddof=1)[0, 1])
    dVar = var_e - var_c; dCov = cov_e - cov_c
    b = (dCov / dVar) if abs(dVar) >= 1e-20 else float("nan")
    return {"var_e_tilde": var_e, "var_c_tilde": var_c,
            "dVar_b_tilde": dVar, "dCov_eb_tilde": dCov,
            "beta_str": b}


def shrink_ratio(r_b_tilde_e, r_b_tilde_c, r_b_e_raw, r_b_c_raw) -> float:
    """shrink = ΔVar(r̃_b) / ΔVar(r_b) — quanto resta del bond dopo il netting.

    NaN se ΔVar grezzo è 0 (denominatore degenere).
    Convenzione: 0/0 viene gestito come 0 (bond piatto in entrambi i casi: il
    rapporto è indefinito ma il bond è puro tasso di fatto ⇒ shrink=0 onesto).
    """
    rb_e_raw = np.asarray(r_b_e_raw, float); rb_c_raw = np.asarray(r_b_c_raw, float)
    rb_e_t = np.asarray(r_b_tilde_e, float); rb_c_t = np.asarray(r_b_tilde_c, float)
    dvar_raw = float(np.var(rb_e_raw, ddof=1) - np.var(rb_c_raw, ddof=1))
    dvar_tilde = float(np.var(rb_e_t, ddof=1) - np.var(rb_c_t, ddof=1))
    if abs(dvar_raw) < 1e-20:
        return float("nan")
    return float(dvar_tilde / dvar_raw)
