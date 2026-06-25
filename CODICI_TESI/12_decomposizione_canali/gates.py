"""gates.py — Doppio cancello del protocollo decomp-canali.

(a) Cancello strumento debole: F-MOP effettivo su ΔVar(r̃_b) ≥ MOP_CV.
(b) Cancello banda di costruzione: min/max di β_str sulla griglia coda×ρ.
Pre-check §3.3: Δf_m al bordo della curva osservata significativo ⇒ WARN.
Verdetto per cella: identified_robust / identified_fragile / channel_not_identified.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.stats import ttest_1samp

import config


# ----- Cancello (a): F-MOP --------------------------------------------------

def F_MOP_effective(dVar_hat: float, var_dVar_hat: float) -> float:
    """F efficace Montiel Olea–Pflueger (K=1): (ΔVar)² / V̂(ΔVar)."""
    if var_dVar_hat <= 0:
        return float("nan")
    return float(dVar_hat ** 2 / var_dVar_hat)


def gate_a(F_MOP: float, cv: float = config.MOP_CV,
           shrink: float | None = None,
           shrink_floor: float = config.SHRINK_FLOOR_DEFAULT) -> dict:
    """Cancello (a): F-MOP ≥ cv AND (se shrink passato) shrink ≥ shrink_floor.

    Lo shrink-floor protegge da F-MOP numericamente alti su quantità minuscole
    (caso "bond svuotato"): la spec dice esplicitamente shrink→0 ⇒ FAIL.
    """
    if math.isnan(F_MOP):
        return {"gate_a": "FAIL", "F_MOP": F_MOP, "cv": cv,
                "shrink": shrink, "reason": "F_MOP NaN (denominatore degenere)"}
    f_ok = F_MOP >= cv
    if shrink is None or math.isnan(shrink):
        status = "PASS" if f_ok else "FAIL"
        reason = None if f_ok else f"F_MOP={F_MOP:.3f} < cv={cv}"
    else:
        s_ok = shrink >= shrink_floor
        status = "PASS" if (f_ok and s_ok) else "FAIL"
        reason = None
        if not f_ok:
            reason = f"F_MOP={F_MOP:.3f} < cv={cv}"
        elif not s_ok:
            reason = f"shrink={shrink:.4f} < floor={shrink_floor} (bond svuotato)"
    return {"gate_a": status, "F_MOP": float(F_MOP), "cv": float(cv),
            "shrink": (float(shrink) if shrink is not None else None),
            "shrink_floor": float(shrink_floor),
            "reason": reason}


# ----- Cancello (b): banda di costruzione + banda totale -------------------

def construction_band(profile: list) -> dict:
    """Min/max di β_str sui punti griglia (lista di dict con chiave 'beta_str')."""
    vals = [float(p["beta_str"]) for p in profile if "beta_str" in p
            and not math.isnan(float(p["beta_str"]))]
    if not vals:
        return {"min": float("nan"), "max": float("nan"), "width": float("nan")}
    lo = float(min(vals)); hi = float(max(vals))
    return {"min": lo, "max": hi, "width": hi - lo}


def total_band(construction: dict, sampling: dict) -> dict:
    """Inviluppo di banda costruzione + banda campionaria (AR-set o CI bootstrap)."""
    lo = min(construction["min"], sampling["low"])
    hi = max(construction["max"], sampling["high"])
    return {"low": float(lo), "high": float(hi), "width": float(hi - lo)}


# ----- Pre-check §3.3: Δf_m al bordo della curva ---------------------------

def tail_border_precheck(delta_f_m_per_event, surprise_per_event=None,
                         alpha: float = config.TAIL_BORDER_SIGNIFICANCE_ALPHA) -> dict:
    """Pre-check §3.3 (Nagel–Xu Tab A.1) — la curva si muove al bordo?

    Due test possibili:
      (a) `surprise_per_event` PASSATA → regressione semplice Δf_m ~ surprise,
          test t sulla slope (H0: slope=0). p < α ⇒ WARN ("la coda comova
          con la sorpresa monetaria").
      (b) `surprise_per_event` None → fallback t-test sulla MEDIA di Δf_m.
          NB: questo fallback ha bassa potenza se la curva si muove ma in modo
          simmetrico (mean ≈ 0 anche con varianza condizionale grande); è una
          limitazione documentata, l'esecutore dovrebbe passare la sorpresa.

    Non pesa il verdetto da solo: alimenta `cell_verdict`.
    """
    x = np.asarray(delta_f_m_per_event, dtype=float)
    if surprise_per_event is not None:
        s = np.asarray(surprise_per_event, dtype=float)
        if x.shape != s.shape:
            raise ValueError(f"delta_f_m ({x.shape}) ≠ surprise ({s.shape})")
        mask = ~(np.isnan(x) | np.isnan(s))
        x = x[mask]; s = s[mask]
        if x.size < 3:
            return {"status": "PASS", "method": "regression",
                    "slope": float("nan"), "p": float("nan"), "n": int(x.size),
                    "reason": "campione insufficiente (<3)"}
        # OLS scalar: slope = Cov(x,s)/Var(s); SE = √(MSE/Σ(s-s̄)²)
        s_mean = float(s.mean())
        s_dev = s - s_mean
        denom = float((s_dev ** 2).sum())
        if denom == 0:
            return {"status": "PASS", "method": "regression",
                    "slope": 0.0, "p": float("nan"), "n": int(x.size),
                    "reason": "varianza sorpresa nulla"}
        slope = float((s_dev * (x - x.mean())).sum() / denom)
        x_hat = x.mean() + slope * s_dev
        resid = x - x_hat
        n = x.size
        if n <= 2:
            return {"status": "PASS", "method": "regression",
                    "slope": slope, "p": float("nan"), "n": int(n)}
        sigma2 = float((resid ** 2).sum() / (n - 2))
        se = float(np.sqrt(sigma2 / denom))
        t = slope / se if se > 0 else float("inf")
        from scipy.stats import t as t_dist
        p = float(2 * (1 - t_dist.cdf(abs(t), df=n - 2)))
        status = "WARN" if p < alpha else "PASS"
        return {"status": status, "method": "regression",
                "slope": slope, "se": se, "t": t, "p": p, "n": int(n)}

    # fallback senza sorpresa: t su mean=0 (basso potere se simmetrico)
    x = x[~np.isnan(x)]
    if x.size < 2:
        return {"status": "PASS", "method": "mean_only",
                "mean": float("nan"), "p": float("nan"),
                "reason": "campione insufficiente (<2)"}
    stat = ttest_1samp(x, 0.0)
    p = float(stat.pvalue)
    status = "WARN" if p < alpha else "PASS"
    return {"status": status, "method": "mean_only",
            "mean": float(x.mean()), "p": p, "n": int(x.size)}


# ----- Verdetto per cella ---------------------------------------------------

def cell_verdict(gate_a: str, precheck: str, band_width: float,
                 band_threshold: float = 0.30) -> str:
    """Decisione spec §6:
      - gate(a) FAIL → 'channel_not_identified'
      - gate(a) PASS ma banda ampia o pre_check WARN → 'identified_fragile'
      - gate(a) PASS, banda stretta, pre_check PASS → 'identified_robust'
    """
    if gate_a == "FAIL":
        return "channel_not_identified"
    if precheck == "WARN" or band_width > band_threshold:
        return "identified_fragile"
    return "identified_robust"
