"""estimators.py — Stimatori del comovimento equity-bond.

Tre stimatori, tutti su momenti campionari (ddof=1):
  - b_OLS = Cov(re, rb) / Var(rb) sulle finestre evento;
  - b_H   = ΔCov / ΔVar (Rigobon-Sack a due regimi: evento vs controllo),
            stimatore via eteroschedasticità dello shock comune;
  - b_L   = Cov(Zc, re*rb) / Cov(Zc, rb**2) (Lewbel), Zc = Z centrata.

Denominatori troppo vicini a zero → np.nan (stimatore non identificato),
non eccezione: a valle il routing/AR decide cosa farne.
"""
from __future__ import annotations

import numpy as np

_EPS = 1e-20


def _cov(x, y) -> float:
    """Covarianza campionaria (ddof=1) tra due array della stessa lunghezza."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    return float(np.cov(x, y, ddof=1)[0, 1])


def _var(x) -> float:
    """Varianza campionaria (ddof=1)."""
    return float(np.var(np.asarray(x, dtype=float), ddof=1))


def b_ols(r_e, r_b) -> float:
    """Stima OLS del comovimento: Cov(r_e, r_b) / Var(r_b), ddof=1."""
    return _cov(r_e, r_b) / _var(r_b)


def rs_two_regime(re_e, rb_e, re_c, rb_c) -> dict:
    """Stimatore Rigobon-Sack a due regimi: b_H = ΔCov / ΔVar.

    Suffisso _e = finestre evento, _c = finestre controllo. Restituisce i
    momenti e gli stimatori; b_H = nan se |ΔVar| < 1e-20, r_hat = nan se
    var_c <= 0.
    """
    var_e = _var(rb_e)
    var_c = _var(rb_c)
    dVar = var_e - var_c
    cov_e = _cov(re_e, rb_e)
    cov_c = _cov(re_c, rb_c)
    dCov = cov_e - cov_c

    b_OLS = cov_e / var_e if var_e > 0 else np.nan
    b_H = dCov / dVar if abs(dVar) >= _EPS else np.nan
    r_hat = var_e / var_c if var_c > 0 else np.nan

    return {
        "var_e": var_e,
        "var_c": var_c,
        "dVar": dVar,
        "cov_e": cov_e,
        "cov_c": cov_c,
        "dCov": dCov,
        "b_OLS": b_OLS,
        "b_H": b_H,
        "r_hat": r_hat,
    }


def lewbel(Z, r_e, r_b) -> dict:
    """Stimatore di Lewbel via eteroschedasticità: b_L = Cov(Zc, re*rb) / tau.

    Z funge da strumento generato; Zc = Z - mean(Z); tau = Cov(Zc, rb**2).
    b_L = nan se |tau| < 1e-20 (strumento muto, Lewbel non identifica).
    """
    Z = np.asarray(Z, dtype=float)
    r_e = np.asarray(r_e, dtype=float)
    r_b = np.asarray(r_b, dtype=float)

    Zc = Z - Z.mean()
    tau = _cov(Zc, r_b ** 2)
    cov_Zeb = _cov(Zc, r_e * r_b)
    b_L = cov_Zeb / tau if abs(tau) >= _EPS else np.nan

    return {"tau": tau, "cov_Zeb": cov_Zeb, "b_L": b_L}
