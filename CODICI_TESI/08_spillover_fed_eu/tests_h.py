"""tests_h.py — Stadio 2: T-H1..T-H4 + Benjamini–Yekutieli locale.

Nome `tests_h` (non `tests.py`) per evitare collisione con la cartella `tests/`
di pytest. La gerarchia: H1 primaria a soglia piena 0.05 senza correzione;
{H2, H3, H4} famiglia secondaria a BY q=0.10 con m=3 FISSO a priori.

Anti-fabbricazione: ogni test produce p-value coerente coi suoi input o
SOLLEVA. Nessun esito "neutro" inventato.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm

import config
from regression import p_one_sided


def _coef_se(fit: dict, name: str) -> tuple[float, float, float]:
    names = fit["names"]
    if name not in names:
        raise KeyError(f"coefficiente {name!r} assente. Disponibili: {names}")
    j = names.index(name)
    return float(fit["coef"][j]), float(fit["se"][j]), float(fit["t"][j])


# --- T-H1: primaria, γ_yB > 0, p < 0.05 NON corretto ----------------------

def T_H1(fit: dict, coef: str, alpha: float = config.T_H1_ALPHA) -> dict:
    """T-H1 (esistenza, trasmissione di tasso): H0: γ ≤ 0 contro H1: γ > 0."""
    g, se, t = _coef_se(fit, coef)
    p = p_one_sided(t, side="greater")
    return {"hypothesis": "H1", "coef_name": coef, "gamma": g, "se": se, "t": t,
            "side": "greater", "p_one_sided": p, "alpha": alpha,
            "reject": bool(p < alpha)}


# --- T-H2: γ_rES < 0, unilaterale, famiglia secondaria BY -----------------

def T_H2(fit: dict, coef: str) -> dict:
    g, se, t = _coef_se(fit, coef)
    p = p_one_sided(t, side="less")
    return {"hypothesis": "H2", "coef_name": coef, "gamma": g, "se": se, "t": t,
            "side": "less", "p_one_sided": p,
            "reject_uncorrected_alpha05": bool(p < 0.05)}


# --- T-H3: γ_sp > 0, unilaterale, famiglia secondaria BY ------------------

def T_H3(fit: dict, coef: str) -> dict:
    g, se, t = _coef_se(fit, coef)
    p = p_one_sided(t, side="greater")
    return {"hypothesis": "H3", "coef_name": coef, "gamma": g, "se": se, "t": t,
            "side": "greater", "p_one_sided": p,
            "reject_uncorrected_alpha05": bool(p < 0.05)}


# --- T-H4: attribuzione via Wald sulla differenza γ - δ -------------------

def T_H4(fit: dict, coef_mp: str, coef_cbi: str) -> dict:
    """Wald su (γ − δ): H0: γ = δ contro H1: γ ≠ δ, BILATERALE.

    se(γ − δ)² = Var(γ̂) + Var(δ̂) − 2·Cov(γ̂, δ̂).
    Riporta anche il rapporto |γ̂|/|δ̂| (proxy di magnitudo relativa).
    """
    names = fit["names"]
    j = names.index(coef_mp); k = names.index(coef_cbi)
    g = float(fit["coef"][j]); d = float(fit["coef"][k])
    cov = fit["cov"]
    var_diff = float(cov[j, j] + cov[k, k] - 2 * cov[j, k])
    if var_diff <= 0:
        raise ValueError(f"var(γ−δ) ≤ 0 ({var_diff}): design pathologico, non fabbrico p.")
    se = np.sqrt(var_diff)
    t = (g - d) / se
    p_two = float(2.0 * (1.0 - norm.cdf(abs(t))))
    ratio = float(abs(g) / abs(d)) if abs(d) > 1e-20 else float("inf")
    return {"hypothesis": "H4", "gamma": g, "delta": d, "diff": g - d,
            "se_diff": se, "t": t, "p_two_sided": p_two, "ratio_abs": ratio,
            "reject_uncorrected_alpha05": bool(p_two < 0.05)}


# --- Benjamini–Yekutieli locale (m FISSO a priori) -------------------------

def benjamini_yekutieli(p, q: float, m: int) -> dict:
    """BY step-up con cardinalità della famiglia FISSA a `m` (a priori).

    Soglia rango i (1-based) = i·q/(m·c_m), c_m = Σ_{k=1..m} 1/k. Si trova il
    PIÙ GRANDE rango i con p_(i) ≤ soglia_i; si rigettano tutti i p con rango
    ≤ i. `rejected` torna nell'ordine ORIGINALE di `p`.
    """
    p_arr = np.asarray(p, dtype=float)
    if len(p_arr) != m:
        # Review #6: "famiglia FISSA a priori" ⇒ len(p) DEVE essere = m.
        # Per slot mancanti l'invocante riempie con 1.0 (test non rilevato),
        # esplicitamente, prima di chiamare BY. Niente silenzioso.
        raise ValueError(
            f"len(p)={len(p_arr)} ≠ m={m}: famiglia secondaria deve essere "
            "di cardinalità fissa (la spec lo impone). Riempire slot non "
            "computati con p=1.0 esplicito prima di invocare BY."
        )
    c_m = float(sum(1.0 / k for k in range(1, m + 1)))
    order = np.argsort(p_arr, kind="stable")
    p_sorted = p_arr[order]
    thresholds = np.array([i * q / (m * c_m) for i in range(1, len(p_arr) + 1)])
    passed = p_sorted <= thresholds
    if not passed.any():
        rejected_orig = np.zeros(len(p_arr), dtype=bool)
        crit = None
    else:
        i_max = int(np.max(np.where(passed)[0]))   # 0-based
        rejected_sorted = np.zeros(len(p_arr), dtype=bool)
        rejected_sorted[: i_max + 1] = True
        rejected_orig = np.zeros(len(p_arr), dtype=bool)
        rejected_orig[order] = rejected_sorted
        crit = float(thresholds[i_max])
    return {"rejected": rejected_orig, "m": m, "c_m": c_m, "crit": crit}


# --- Gerarchia integrata: H1 primaria + BY su {H2, H3, H4} -----------------

def hierarchy(h1: dict, h2: dict, h3: dict, h4: dict,
              q: float = config.BY_Q) -> dict:
    """Combina H1 (NON corretto) + BY sui 3 secondari (m=3 fisso).

    Ogni hX deve essere un dict con almeno `p` (o `p_one_sided`/`p_two_sided`).
    Se la chiave standard manca, solleva — niente p inventato.
    """
    def _pick_p(d: dict) -> float:
        for key in ("p", "p_one_sided", "p_two_sided"):
            if key in d:
                return float(d[key])
        raise KeyError("nessun p-value ('p'/'p_one_sided'/'p_two_sided') nel dict")

    h1_p = _pick_p(h1)
    secondary_ps = [_pick_p(h2), _pick_p(h3), _pick_p(h4)]
    by = benjamini_yekutieli(secondary_ps, q=q, m=config.BY_M)
    return {
        "h1_p": h1_p,
        "h1_reject": bool(h1_p < config.T_H1_ALPHA),
        "secondary": {"H2": bool(by["rejected"][0]),
                       "H3": bool(by["rejected"][1]),
                       "H4": bool(by["rejected"][2])},
        "m_secondary": by["m"],
        "by_crit": by["crit"],
    }
