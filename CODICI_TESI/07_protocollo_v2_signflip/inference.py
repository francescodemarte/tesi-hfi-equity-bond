"""inference.py — Bootstrap clusterizzato (T1), routing R5, BY R7, Cochran Q (T6).

Kernel CONGELATI dal protocollo v2 (§5/§9 spec). Solo numpy/pandas/scipy.

  - `event_cluster_bootstrap`: unità di ricampionamento = EVENTO (porta con sé
    il suo grappolo 3–10 controlli, opaco), così la covarianza intra-evento
    (annuncio + controlli non indipendenti) entra nella V̂ (T1).
  - `route_cell`: instradamento puntuale vs AR-only (R5) — puntuale solo se
    ΔVar significativo ∧ F_eff>cv_MOP ∧ n≥N_MIN; altrimenti AR-only.
  - `benjamini_yekutieli`: step-up BY (NON BH) per test dipendenti — soglia del
    rango i = i·q/(m·c_m), c_m = Σ_{k=1}^m 1/k.
  - `hierarchical_by`: gerarchia R7 — NFP primario fuori correzione (α=0.05);
    famiglia secondaria {CPI,FOMC,ECB} con m=3 FISSO; T4-fail = flip-non-rilevato
    (p=1.0, non-rigetto) ma occupa comunque uno slot (m resta 3).
  - `cochran_q`: eterogeneità inverse-variance-weighted (T6 NFP-vs-CPI).
"""
from __future__ import annotations

import numpy as np
from scipy.stats import chi2

import config


def event_cluster_bootstrap(clusters, stat_fn, B, rng) -> np.ndarray:
    """Bootstrap a livello di CLUSTER (T1).

    Ogni elemento di `clusters` è un evento col suo grappolo di controlli ed è
    trattato come opaco: si ricampiona l'INTERO cluster con reinserimento.
    `stat_fn` riceve la lista dei cluster ricampionati e ne restituisce la
    statistica scalare. `rng` è un np.random.Generator dichiarato (config.make_rng).
    """
    n = len(clusters)
    stats = []
    for _ in range(B):
        idx = rng.integers(0, n, n)
        resampled = [clusters[i] for i in idx]
        stats.append(stat_fn(resampled))
    return np.asarray(stats, dtype=float)


def route_cell(dvar_significant, f_eff, cv_mop, n, n_min=config.N_MIN) -> str:
    """Instradamento R5: «pointwise» sse tutte e tre le condizioni; altrimenti «ar_only».

    Puntuale richiede: ΔVar significativo (lower-bound CI 95%), strumento forte
    (F_eff > cv_MOP, STRETTO) e campione sufficiente (n ≥ n_min). La cella
    rilevante-ma-debole (F_eff ≤ cv_MOP) finisce in AR-only.
    """
    if dvar_significant and f_eff > cv_mop and n >= n_min:
        return "pointwise"
    return "ar_only"


def benjamini_yekutieli(pvalues, q, m=None) -> dict:
    """Procedura step-up Benjamini–Yekutieli (test dipendenti, NON BH standard).

    m = m se fornito, altrimenti len(pvalues); c_m = Σ_{k=1}^m 1/k. Soglia del
    rango i (1-based, p crescenti) = i·q/(m·c_m). Si cerca il PIÙ GRANDE i con
    p_(i) ≤ soglia_i e si rigettano tutti i p di rango ≤ i; se nessuno, nessun
    rigetto. `rejected` è nell'ordine ORIGINALE; `crit` è la soglia del rango
    massimo rigettato (None se nessun rigetto).
    """
    p = np.asarray(pvalues, dtype=float)
    n = p.size
    m = int(m) if m is not None else n
    c_m = float(np.sum(1.0 / np.arange(1, m + 1)))

    order = np.argsort(p, kind="stable")          # indici in ordine crescente di p
    ranks = np.arange(1, n + 1)                    # 1-based
    thresholds = ranks * q / (m * c_m)
    passed = p[order] <= thresholds                # passa la soglia al proprio rango

    rejected = [False] * n
    crit = None
    if passed.any():
        max_rank = int(np.max(np.nonzero(passed)[0]) + 1)  # più grande i che passa
        crit = float(max_rank * q / (m * c_m))
        for j in range(max_rank):                  # rigetta ranghi 1..max_rank
            rejected[int(order[j])] = True

    return {"rejected": rejected, "m": m, "c_m": c_m, "crit": crit}


def hierarchical_by(results, q=config.BY_Q) -> dict:
    """Gerarchia di molteplicità R7.

    `results`: dict {tipo -> {"p": float, "testable": bool}} con chiavi
    "NFP" (primario) e i tre secondari config.BY_SECONDARY_FAMILY (CPI/FOMC/ECB).

    - NFP (primario, NON corretto): nfp_reject = testable ∧ (p < NFP_ALPHA).
    - Secondari con m = BY_M = 3 FISSO: se non testabile (testable False) il tipo
      è «flip non rilevato» → p=1.0 (mai rigettato) MA occupa comunque uno slot
      (m resta 3). Si applica BY ai tre p (i fail sostituiti da 1.0) con q.
    """
    nfp = results[config.NFP_PRIMARY]
    nfp_reject = bool(nfp["testable"] and (nfp["p"] < config.NFP_ALPHA))

    fam = list(config.BY_SECONDARY_FAMILY)
    pvals = [results[t]["p"] if results[t]["testable"] else 1.0 for t in fam]

    by = benjamini_yekutieli(pvals, q=q, m=config.BY_M)
    secondary = {t: bool(rej) for t, rej in zip(fam, by["rejected"])}

    return {"nfp_reject": nfp_reject, "secondary": secondary, "m_used": by["m"]}


def cochran_q(betas, ses) -> dict:
    """Statistica Q di Cochran (eterogeneità inverse-variance-weighted, T6).

    w = 1/se²; b_pooled = Σw·b / Σw; Q = Σ w·(b − b_pooled)²; df = len(betas) − 1;
    p = 1 − χ²_df.cdf(Q). Chiavi: Q, df, p, b_pooled.
    """
    b = np.asarray(betas, dtype=float)
    se = np.asarray(ses, dtype=float)
    w = 1.0 / se ** 2
    b_pooled = float(np.sum(w * b) / np.sum(w))
    Q = float(np.sum(w * (b - b_pooled) ** 2))
    df = int(b.size - 1)
    p = float(1.0 - chi2.cdf(Q, df))
    return {"Q": Q, "df": df, "p": p, "b_pooled": b_pooled}
