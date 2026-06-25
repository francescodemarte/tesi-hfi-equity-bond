"""whitening.py — Diagnostica di bianchezza del residuo (spec §5).

Tre dimensioni:
  - autocorrelazione (lag-1 di default)
  - dipendenza dal regime (F-test fra medie / varianze per regime)
  - correlazione coi tre ΔZ⊥ (cross-channel residual leakage)

`is_white` = TUTTE le dimensioni hanno p ≥ α.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import f as f_dist, t as t_dist


def autocorrelation(u, lag: int = 1) -> dict:
    """ρ_lag e p-value approssimato (Ljung–Box-like, t-test su ρ scalato √n)."""
    u = np.asarray(u, dtype=float)
    n = u.size
    if n < lag + 2:
        return {"rho": float("nan"), "p_value": float("nan"), "lag": lag, "n": n}
    u_c = u - u.mean()
    num = float((u_c[lag:] * u_c[:-lag]).sum())
    den = float((u_c ** 2).sum())
    rho = num / den if den > 0 else float("nan")
    # SE asintotico ~ 1/√n; t = ρ·√n; p bilaterale via t_{n-2}
    if not np.isfinite(rho) or n - 2 <= 0:
        return {"rho": rho, "p_value": float("nan"), "lag": lag, "n": n}
    t = rho * np.sqrt(n)
    p = float(2 * (1 - t_dist.cdf(abs(t), df=n - 2)))
    return {"rho": float(rho), "p_value": p, "lag": lag, "n": int(n)}


def regime_dependence(u, regimes) -> dict:
    """F-test su uguaglianza delle medie nei due regimi (1-way ANOVA su 2 gruppi)."""
    u = np.asarray(u, dtype=float)
    g = np.asarray(regimes)
    if u.shape != g.shape:
        raise ValueError("u e regimes devono avere stessa lunghezza")
    cats = np.unique(g)
    if len(cats) < 2:
        return {"f_stat": float("nan"), "p_value": float("nan"),
                "reason": "un solo regime"}
    n = u.size
    grand = u.mean()
    ss_between = 0.0; ss_within = 0.0; k = len(cats)
    for c in cats:
        sub = u[g == c]
        ss_between += sub.size * (sub.mean() - grand) ** 2
        ss_within += float(((sub - sub.mean()) ** 2).sum())
    df_b = k - 1; df_w = n - k
    if df_w <= 0 or ss_within == 0:
        return {"f_stat": float("nan"), "p_value": float("nan"), "df_b": df_b, "df_w": df_w}
    F = (ss_between / df_b) / (ss_within / df_w)
    p = float(1 - f_dist.cdf(F, df_b, df_w))
    return {"f_stat": float(F), "p_value": p, "df_b": int(df_b), "df_w": int(df_w)}


def whiteness_summary(*, autocorr_p, regime_dep_p, cross_corr_p,
                      alpha: float = 0.05) -> dict:
    """is_white se TUTTI i p-value ≥ α."""
    checks = {"autocorr": float(autocorr_p) >= alpha if np.isfinite(autocorr_p) else None,
              "regime": float(regime_dep_p) >= alpha if np.isfinite(regime_dep_p) else None}
    for k, p in cross_corr_p.items():
        checks[f"cross_{k}"] = float(p) >= alpha if np.isfinite(p) else None
    is_white = all(v for v in checks.values() if v is not None)
    return {"is_white": bool(is_white), "checks": checks, "alpha": float(alpha)}
