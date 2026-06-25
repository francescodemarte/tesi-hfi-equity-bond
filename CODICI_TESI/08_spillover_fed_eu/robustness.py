"""robustness.py — Stadio 3: Rigobon binario (subordinato), poor man's check,
calendario, finestra.

- Rigobon (3.1): confronto var/cov tra giorni FOMC e controlli, b_H = ΔCov/ΔVar.
  Marcato `priority="subordinate"` come da spec — il primario è la regressione
  con Z_mp/Z_cbi (Stadio 2). Se concorda corrobora, se diverge prevale il
  primario; l'esecutore lo cabla nel report.
- Poor man's check (3.2): wrapper di concordanza già definito in `surprises`.
- Calendario / Finestra (3.3, 3.4): firme/etichette che l'orchestratore usa
  per produrre due esecuzioni della pipeline da confrontare (le esecuzioni
  vere le fa l'esecutore, non questo modulo).
"""
from __future__ import annotations

import numpy as np

import surprises as su


def rigobon_two_regime(re_evt, rb_evt, re_ctl, rb_ctl,
                       *, B: int = 1000, alpha: float = 0.05, rng=None) -> dict:
    """Identificazione per eteroschedasticità a due regimi (Rigobon 2003).

    `priority = "subordinate"` esplicito (spec §3.1). Se ΔVar ≤ 0 o non
    significativamente positiva → b_H NaN e `identifiable=False`.

    **Gate di significatività (review agente 4 #3).** `identifiable=True`
    richiede che il bound inferiore monolaterale 100·(1-α)% bootstrap di ΔVar
    sia STRETTAMENTE positivo (non solo dVar campionario > 0, che su rumore
    iso-varianza accade ~50% per pura fluttuazione). `dVar_lb` è esposto.
    """
    re_e = np.asarray(re_evt, float); rb_e = np.asarray(rb_evt, float)
    re_c = np.asarray(re_ctl, float); rb_c = np.asarray(rb_ctl, float)
    n_e, n_c = len(rb_e), len(rb_c)
    var_e = float(np.var(rb_e, ddof=1)); var_c = float(np.var(rb_c, ddof=1))
    cov_e = float(np.cov(re_e, rb_e, ddof=1)[0, 1])
    cov_c = float(np.cov(re_c, rb_c, ddof=1)[0, 1])
    dVar = var_e - var_c; dCov = cov_e - cov_c

    # Bootstrap LB monolaterale di ΔVar (paired-resample dei due regimi)
    if rng is None:
        import config as _c
        rng = _c.make_rng("rigobon_two_regime")
    dVar_bs = np.empty(B)
    for b in range(B):
        ie = rng.integers(0, n_e, n_e); ic = rng.integers(0, n_c, n_c)
        dVar_bs[b] = float(np.var(rb_e[ie], ddof=1) - np.var(rb_c[ic], ddof=1))
    dVar_lb = float(np.quantile(dVar_bs, alpha))   # monolaterale: H1: ΔVar > 0

    if abs(dVar) < 1e-20:
        b_H = float("nan"); identifiable = False
    else:
        b_H = dCov / dVar
        identifiable = bool(dVar_lb > 0.0)   # significativa, non solo campionaria

    return {"var_e": var_e, "var_c": var_c, "dVar": dVar, "dVar_lb": dVar_lb,
            "cov_e": cov_e, "cov_c": cov_c, "dCov": dCov,
            "b_H": b_H, "identifiable": identifiable,
            "priority": "subordinate"}


def poor_mans_check(m, s) -> dict:
    """Wrapper della concordanza di segno fra rotazione e poor man's."""
    return su.sign_concordance(su.separate_jk(m, s), su.poor_mans(m, s))


def calendar_robustness_pair_signature() -> dict:
    """Le due varianti di calendario che l'orchestratore deve eseguire.

    Le esecuzioni vere passano per `calendar_clean.filter_events(mode=...)`;
    qui sta solo l'etichetta (firma) della coppia che entra nel report.
    """
    return {"baseline": "comunicazione Fed T+1 inclusa",
            "robust_drop_fed_t1": "comunicazione Fed major in T+1 rimossa"}


def window_robustness_pair_signature() -> dict:
    """Le due finestre di risposta EU che l'orchestratore deve eseguire."""
    return {"close_to_close_T+1": "baseline (Stadio 1)",
            "intraday_open_T+1": "finestra stretta all'apertura EU"}
