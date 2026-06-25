"""tests_channel.py — Regressione residuo ~ ΔZ⊥ + comunalità + segno (spec §5).

Inferenza HAC (Newey-West lag=0 = HC, lag>0 = HAC) sulla slope λ.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import t as t_dist


def loading_regression(u, z_perp, hac_lag: int = 0) -> dict:
    """OLS univariata u ~ a + λ · z_perp con SE HC0 (lag=0) o HAC Newey-West."""
    u = np.asarray(u, dtype=float); z = np.asarray(z_perp, dtype=float)
    if u.shape != z.shape:
        raise ValueError(f"u {u.shape} ≠ z_perp {z.shape}")
    n = u.size
    if n < 3:
        raise ValueError(f"campione troppo piccolo: n={n}")
    z_dev = z - z.mean()
    denom = float((z_dev ** 2).sum())
    if denom == 0:
        return {"lambda": float("nan"), "se": float("nan"), "t": float("nan"),
                "p_value": float("nan"), "n": int(n)}
    lam = float((z_dev * (u - u.mean())).sum() / denom)
    intercept = float(u.mean() - lam * z.mean())
    resid = u - (intercept + lam * z)
    # HC0 / HAC sandwich: x_i = z_dev_i; Ω = Σ w_l Σ x_i x_{i-l} e_i e_{i-l}
    xe = z_dev * resid
    omega = float((xe ** 2).sum())
    if hac_lag > 0:
        for l in range(1, hac_lag + 1):
            w = 1.0 - l / (hac_lag + 1)
            omega += 2.0 * w * float((xe[l:] * xe[:-l]).sum())
    var_lam = omega / (denom ** 2)
    se = float(np.sqrt(var_lam)) if var_lam > 0 else float("nan")
    t = lam / se if se > 0 else float("nan")
    p = float(2 * (1 - t_dist.cdf(abs(t), df=n - 2))) if np.isfinite(t) else float("nan")
    return {"lambda": lam, "se": se, "t": t, "p_value": p, "n": int(n)}


def commonality(lambda_e: float, p_e: float, lambda_b: float, p_b: float,
                expected_sign: str, alpha: float = 0.05) -> dict:
    """Comunalità (entrambi significativi) + verifica segno atteso (§3)."""
    common = bool((p_e < alpha) and (p_b < alpha))
    if not common:
        return {"commonality": False, "sign_ok": None,
                "lambda_e": lambda_e, "lambda_b": lambda_b,
                "p_e": p_e, "p_b": p_b}
    # Segno atteso — spec §3 RIVISTA (vedi config.EXPECTED_SIGN docstring)
    # Le regole "antisymmetric_*_eq" sono coerenti col pattern coef_b=−coef_e/β
    # imposto dalla spec §2; identificano IL SENSO via il segno di λ_e.
    if expected_sign == "antisymmetric_pos_eq":
        sign_ok = (lambda_e > 0) and (lambda_b < 0)
    elif expected_sign == "antisymmetric_neg_eq":
        sign_ok = (lambda_e < 0) and (lambda_b > 0)
    elif expected_sign == "ambiguous":
        sign_ok = True
    # Le vecchie etichette "concordant"/"both_negative" non sono più ammesse.
    elif expected_sign in ("concordant", "both_negative"):
        raise ValueError(
            f"expected_sign={expected_sign!r}: regola §3 LEGACY, "
            "incompatibile con spec §2 (residui antisimmetrici). "
            "Usare 'antisymmetric_pos_eq' / 'antisymmetric_neg_eq' / 'ambiguous'."
        )
    else:
        raise ValueError(f"expected_sign sconosciuto: {expected_sign!r}")
    return {"commonality": True, "sign_ok": bool(sign_ok),
            "lambda_e": lambda_e, "lambda_b": lambda_b,
            "p_e": p_e, "p_b": p_b}
