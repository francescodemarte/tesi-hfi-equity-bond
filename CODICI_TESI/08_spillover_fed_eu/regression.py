"""regression.py — Stadio 2: OLS con SE HC + bootstrap a coppie (pair).

Convenzioni:
- intercept aggiunta automaticamente come prima colonna di X.
- `cov_type ∈ {"HC0","HC1","HC2","HC3"}`: HC1 di default (Eicker-Huber-White
  con la correzione n/(n−k) di MacKinnon-White; coerente con statsmodels).
- `bootstrap_se`: ricampiona righe (Z, x, y) con rimessa, ri-stima OLS,
  ritorna le std bootstrap dei coefficienti (incluso intercept).
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm


def _design(X: np.ndarray) -> np.ndarray:
    """Aggiunge intercept come prima colonna."""
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    n = X.shape[0]
    return np.hstack([np.ones((n, 1)), X])


def _ols_fit(X_with_const: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    XtX = X_with_const.T @ X_with_const
    if np.linalg.matrix_rank(XtX) < XtX.shape[0]:
        raise np.linalg.LinAlgError("design collineare (XtX singolare)")
    XtX_inv = np.linalg.inv(XtX)
    beta = XtX_inv @ X_with_const.T @ y
    return beta, XtX_inv


def ols_hc(y, X, names: tuple = (), cov_type: str = "HC1") -> dict:
    """OLS con errori standard robusti all'eteroschedasticità.

    Restituisce: `coef`, `se`, `t` (= coef/se), `names` (con 'intercept' in
    prima posizione), `cov` (varianza-covarianza dei coefficienti), `n`, `k`.
    """
    y = np.asarray(y, dtype=float)
    Xd = _design(X)
    n, k = Xd.shape
    beta, XtX_inv = _ols_fit(Xd, y)
    resid = y - Xd @ beta

    # Cov HC0: (X'X)^{-1} X' diag(u_i^2) X (X'X)^{-1}
    omega = resid ** 2
    # piccola correzione di scala per HC1..HC3
    if cov_type == "HC0":
        scale = 1.0
        u = omega
    elif cov_type == "HC1":
        scale = n / (n - k)
        u = omega * scale
    elif cov_type in ("HC2", "HC3"):
        # leverage h_ii = diag(X (X'X)^{-1} X')
        h = np.einsum("ij,jk,ik->i", Xd, XtX_inv, Xd)
        if cov_type == "HC2":
            u = omega / (1.0 - h)
        else:
            u = omega / (1.0 - h) ** 2
    else:
        raise ValueError(f"cov_type sconosciuto: {cov_type!r}")

    XtuX = Xd.T @ (Xd * u[:, None])
    cov = XtX_inv @ XtuX @ XtX_inv
    se = np.sqrt(np.diag(cov))
    t = beta / se

    full_names = ("intercept",) + tuple(names) if names else \
                 ("intercept",) + tuple(f"x{i}" for i in range(k - 1))
    return {"coef": beta, "se": se, "t": t, "names": full_names,
            "cov": cov, "n": n, "k": k, "cov_type": cov_type}


def p_one_sided(t: float, side: str) -> float:
    """p-value unilaterale per il t-score."""
    if side == "greater":
        return float(1.0 - norm.cdf(t))
    if side == "less":
        return float(norm.cdf(t))
    raise ValueError(f"side {side!r}: usare 'greater' o 'less'")


def bootstrap_se(y, X, B: int, rng, cov_type: str = "HC1") -> np.ndarray:
    """SE bootstrap a coppie: ricampiona righe (X_i, y_i) con rimessa.

    Restituisce un vettore di SE dei coefficienti (incluso intercept).
    Onesto: ogni replica è una vera ri-stima OLS, niente shortcut.
    """
    y = np.asarray(y, dtype=float); Xd = _design(X)
    n, k = Xd.shape
    betas = np.empty((B, k))
    for b in range(B):
        idx = rng.integers(0, n, n)
        Xb, yb = Xd[idx], y[idx]
        XtX = Xb.T @ Xb
        if np.linalg.matrix_rank(XtX) < k:
            betas[b] = np.nan
            continue
        betas[b] = np.linalg.solve(XtX, Xb.T @ yb)
    return np.nanstd(betas, axis=0, ddof=1)
