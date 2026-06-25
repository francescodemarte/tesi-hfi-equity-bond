"""tests_protocol.py — Orchestrazione dei test del protocollo (T1–T9).

Cuore del lavoro: la logica del flip (T5). Inferenza primaria su Anderson–Rubin
(SPEC §2bis E2); il b_H di Wald resta stima/leggibilità, non base del claim.

Struttura di una CELLA = lista di "cluster", uno per evento; ogni cluster =
{event: {r_e, r_b}, controls: [{r_e, r_b}, ...]}. Le statistiche di cella si
ottengono impilando le finestre evento e (in pool) le finestre di controllo; il
bootstrap ricampiona a livello di CLUSTER (evento + suo grappolo di controlli),
propagando la dipendenza intra-evento e il numero variabile di controlli (C0.2/T1).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config
import estimators
import inference
import surprises
import weakiv


def cell_moments(clusters):
    """Impila le finestre evento e mette in pool le finestre di controllo della cella."""
    re_e = np.array([c["event"]["r_e"] for c in clusters], dtype=float)
    rb_e = np.array([c["event"]["r_b"] for c in clusters], dtype=float)
    re_c, rb_c = [], []
    for c in clusters:
        for ct in c["controls"]:
            re_c.append(ct["r_e"]); rb_c.append(ct["r_b"])
    return re_e, rb_e, np.array(re_c, dtype=float), np.array(rb_c, dtype=float)


def cell_estimate(clusters, rng, B: int = config.B_BOOT) -> dict:
    """Stima RS per cella + bootstrap clusterizzato per evento di (ΔCov, ΔVar).

    F efficace = (ΔVar)²/V̂ con V̂ = varianza bootstrap di ΔVar (quarti momenti,
    robusta e clusterizzata per evento).
    """
    re_e, rb_e, re_c, rb_c = cell_moments(clusters)
    base = estimators.rs_two_regime(re_e, rb_e, re_c, rb_c)

    def stat(cl):
        a, b, c, d = cell_moments(cl)
        o = estimators.rs_two_regime(a, b, c, d)
        return (o["dCov"], o["dVar"], o["cov_e"], o["var_e"])

    bs = np.asarray(inference.event_cluster_bootstrap(clusters, stat, B, rng), dtype=float)
    dCov_bs, dVar_bs, cov_e_bs, var_e_bs = bs[:, 0], bs[:, 1], bs[:, 2], bs[:, 3]
    with np.errstate(divide="ignore", invalid="ignore"):
        b_H_bs = np.where(np.abs(dVar_bs) > 1e-20, dCov_bs / dVar_bs, np.nan)
        b_OLS_bs = np.where(var_e_bs > 0, cov_e_bs / var_e_bs, np.nan)
    var_dVar = float(np.var(dVar_bs, ddof=1))
    f_eff = weakiv.mop_effective_f(base["dVar"], var_dVar) if var_dVar > 0 else float("inf")
    se_bH = float(np.nanstd(b_H_bs, ddof=1))
    return {**base, "dCov_bs": dCov_bs, "dVar_bs": dVar_bs,
            "cov_e_bs": cov_e_bs, "var_e_bs": var_e_bs,
            "b_H_bs": b_H_bs, "b_OLS_bs": b_OLS_bs, "se_bH": se_bH,
            "n_e": len(clusters), "n_c": len(rb_c), "var_dVar": var_dVar, "f_eff": f_eff}


def t1_relevance(est: dict, cv_mop: float, n_min: int = config.N_MIN) -> dict:
    """T1 — rilevanza a due regimi + cancello di potenza (gate di tutto).

    H0: ΔVar≤0, H1: ΔVar>0 (monolaterale): bound inferiore 95% monolaterale del
    bootstrap di ΔVar > 0. Routing (R5): puntuale sse ΔVar sig. ∧ F_eff>cv_MOP ∧
    n≥n_min; altrimenti AR-only.
    """
    dvar_lb = float(np.quantile(est["dVar_bs"], 0.05))   # bound inferiore 95% monolaterale
    dvar_sig = dvar_lb > 0
    route = inference.route_cell(dvar_sig, est["f_eff"], cv_mop, est["n_e"], n_min)
    return {"dvar_sig": dvar_sig, "dvar_lb": dvar_lb, "f_eff": est["f_eff"], "route": route}


def t2_lewbel(re_e, rb_e, Z, rng, B: int = config.B_BOOT,
              source_label: str | None = None) -> dict:
    """T2 — rilevanza continua / Lewbel. τ=Cov(Z,(r^b)²); b_L=Cov(Z,r^e r^b)/τ.

    `feedable` dal gate C0.4 su Z (copertura/varianza). Se τ≈0 (t_tau piccolo) o
    non feedable → Lewbel muto, da registrare come *robustezza fallita dichiarata*.
    `source_label` (l'esecutore lo passa, es. da `surprises.surprise_source(t)`):
    se fornito è validato → la guardia ΔT5YIE blocca sorgenti vietate sul percorso
    inferenziale, non solo nella mappa.
    """
    if source_label is not None:
        surprises.validate_source(source_label)
    re_e = np.asarray(re_e, float); rb_e = np.asarray(rb_e, float); Z = np.asarray(Z, float)
    gate = surprises.coverage_variance_gate(Z)
    base = estimators.lewbel(Z, re_e, rb_e)
    n = len(Z)
    tau_bs = np.empty(B)
    for j in range(B):
        idx = rng.integers(0, n, n)
        tau_bs[j] = estimators.lewbel(Z[idx], re_e[idx], rb_e[idx])["tau"]
    se_tau = float(np.nanstd(tau_bs, ddof=1))
    t_tau = float(base["tau"] / se_tau) if se_tau > 0 else float("nan")
    return {"tau": base["tau"], "se_tau": se_tau, "t_tau": t_tau, "b_L": base["b_L"],
            "feedable": gate["feedable"], "gate": gate}


def t3_amplitude(est: dict) -> dict:
    """T3 — ampiezza dello shock comune (MISURA, non pass/fail): b_OLS − b_H + CI.

    diff = b_OLS − b_H; CI percentile bootstrap (2.5–97.5). In generale
    b_OLS−b_H confonde livello e differenza dello shock comune: nessuna conclusione
    forzata (caveat hard-coded del protocollo).
    """
    diff = est["b_OLS"] - est["b_H"]
    diff_bs = est["b_OLS_bs"] - est["b_H_bs"]
    ci_low = float(np.nanpercentile(diff_bs, 2.5))
    ci_high = float(np.nanpercentile(diff_bs, 97.5))
    return {"diff": diff, "ci_low": ci_low, "ci_high": ci_high,
            "caveat": "b_OLS-b_H confonde livello e differenza di sigma_eb; non discrimina flip di beta da flip del bias"}


def t6_type_specificity(t5_result: dict, est_by_regime: dict) -> dict:
    """T6 — specificità per tipo (CENTRALE). (a) contrasto NFP-vs-CPI sull'esito-flip;
    (b) eterogeneità di b_H tra tipi entro regime via Cochran Q (w=1/se²).
    """
    flips = t5_result["flip_detected"]
    nfp_vs_cpi = {"nfp_flips": bool(flips.get(config.NFP_PRIMARY)),
                  "cpi_flips": bool(flips.get("CPI")),
                  "specific": bool(flips.get(config.NFP_PRIMARY)) and not bool(flips.get("CPI"))}
    cq = {}
    for regime, by_type in est_by_regime.items():
        betas = [est["b_H"] for est in by_type.values()]
        ses = [est["se_bH"] for est in by_type.values()]
        cq[regime] = inference.cochran_q(betas, ses)
    return {"nfp_vs_cpi": nfp_vs_cpi, "cochran_q": cq}


def _ar_cell(est: dict, beta_grid):
    return weakiv.ar_set(est["dCov"], est["dVar"], est["dCov_bs"], est["dVar_bs"], beta_grid)


def _delta_p(pos: dict, neg: dict, beta_grid) -> float:
    return weakiv.delta_ar_pvalue(
        (pos["dCov"], pos["dVar"], pos["dCov_bs"], pos["dVar_bs"]),
        (neg["dCov"], neg["dVar"], neg["dCov_bs"], neg["dVar_bs"]),
        beta_grid)


def t4_state_dependence(pos: dict, neg: dict, beta_grid) -> float:
    """T4 — esistenza di stato-dipendenza: p-value di Δ_H≠0 via χ²₁ (proiezione AR).

    È LETTERALMENTE la stessa statistica usata da T5 (parte 2): così «T4 non
    passato» e «Δ_H non significativo» coincidono per costruzione.
    """
    return _delta_p(pos, neg, beta_grid)


def t5_signflip(per_type: dict, beta_grid, q: float = config.BY_Q,
                n_min: int = config.N_MIN) -> dict:
    """T5 — sign-flip dello stimatore (CENTRALE). Inferenza AR (E2), livelli per R1.

    Per tipo:
      parte 2 (peso inferenziale, controllo errore familiare): p di Δ_H (=T4) in
        gerarchia BY — NFP primario α=0.05 non corretto; {CPI,FOMC,BCE} BY q, m=3 fisso;
      parte 1 (qualifica la DIREZIONE, non un secondo test): AR-set dei due regimi
        interamente su lati opposti dello zero (al 95%, non corretto).
    flip rilevato = (Δ_H sopravvive a BY) ∧ (AR-set su lati opposti).
    `testable` = TESTABILITÀ (n≥n_min in entrambe le celle): un tipo non testabile
    è flip-non-rilevato (p=1.0) ma RESTA nella famiglia (m=3 fisso).
    """
    res = {}
    for t, cells in per_type.items():
        pos, neg = cells.get("pos"), cells.get("neg")
        testable = (pos is not None and neg is not None
                    and pos["n_e"] >= n_min and neg["n_e"] >= n_min)
        if testable:
            p = _delta_p(pos, neg, beta_grid)
            sp = weakiv.ar_one_side(_ar_cell(pos, beta_grid))
            sn = weakiv.ar_one_side(_ar_cell(neg, beta_grid))
            opposite = (sp is not None and sn is not None and sp != sn)
        else:
            p, opposite = 1.0, False
        res[t] = {"testable": testable, "delta_p": p, "opposite_sides": opposite}

    hb_in = {t: {"p": res[t]["delta_p"], "testable": res[t]["testable"]} for t in res}
    hb = inference.hierarchical_by(hb_in, q=q)

    flips = {config.NFP_PRIMARY: bool(hb["nfp_reject"]
                                      and res[config.NFP_PRIMARY]["opposite_sides"])}
    for t in config.BY_SECONDARY_FAMILY:
        flips[t] = bool(hb["secondary"][t] and res[t]["opposite_sides"])
    return {"per_type": res, "by": hb, "flip_detected": flips}


def estimate_per_type(per_type_clusters: dict, rng, B: int = config.B_BOOT) -> dict:
    """Stima ogni cella (cluster → est) per i 4 tipi × {pos, neg}.

    Una cella con meno di 2 cluster (varianza non definita) è restituita come
    None: tratta come «non testabile» a valle (resta nella famiglia, m=3).
    """
    out = {}
    for t, cells in per_type_clusters.items():
        out[t] = {}
        for reg in ("pos", "neg"):
            cl = cells.get(reg)
            out[t][reg] = cell_estimate(cl, rng, B) if cl and len(cl) >= 2 else None
    return out


def t7_exogenous(per_type_by_criterion: dict, beta_grid) -> dict:
    """T7 — non artefatto della classificazione. Ri-esegue T5 con regimi definiti
    da criteri ESOGENI a ρ (≥2). Se l'inversione svanisce sotto regimi esogeni →
    artefatto-classificazione. (NB: T7 chiude solo l'artefatto-classificazione, non
    l'artefatto-bias.) per_type_by_criterion = {nome_criterio: per_type_est}.
    """
    return {crit: t5_signflip(per_type, beta_grid) for crit, per_type in per_type_by_criterion.items()}


# --- T8: perturbazioni di robustezza (lista chiusa di QUATTRO) ---------

def per_cell_transform(cell_fn):
    """Costruisce una trasformazione per_type→per_type applicando `cell_fn` a ogni cella."""
    def transform(per_type_clusters):
        return {ty: {reg: (cell_fn(cells[reg]) if cells.get(reg) else None)
                     for reg in ("pos", "neg")}
                for ty, cells in per_type_clusters.items()}
    return transform


def exclude_extreme(cell, frac: float = 0.1):
    """(T8a) Scarta la frazione `frac` di finestre più estreme per |r^b| nella cella."""
    if not cell:
        return cell
    order = sorted(range(len(cell)), key=lambda i: abs(cell[i]["event"]["r_b"]))
    keep = set(order[:int(round(len(cell) * (1.0 - frac)))])
    return [c for i, c in enumerate(cell) if i in keep]


def leave_year_out(cell, year):
    """(T8b) Leave-one-year-out: scarta i cluster dell'anno `year` (da meta)."""
    return [c for c in (cell or []) if c.get("meta", {}).get("year") != year]


def exclude_years(cell, years):
    """(T8d, generico per anno-calendario) Scarta i cluster degli anni in `years`."""
    years = set(years)
    return [c for c in (cell or []) if c.get("meta", {}).get("year") not in years]


def t8d_is_inflationary(event_time, cpi_yoy: pd.Series,
                       threshold: float = config.T8D_CPI_YOY_THRESHOLD):
    """E3 T8(d) — classifica un evento come inflazionistico via YoY PREDETERMINATO.

    «Predeterminato» = ULTIMO YoY pubblicato STRETTAMENTE PRIMA del timestamp
    dell'evento (no look-ahead). Ritorna True/False, oppure None se nessun YoY
    è disponibile prima dell'evento (l'evento non è classificabile).
    """
    s = cpi_yoy.sort_index()
    t = pd.Timestamp(event_time)
    if s.index.tz is not None and t.tzinfo is None:
        t = t.tz_localize(s.index.tz)
    elif s.index.tz is None and t.tzinfo is not None:
        t = t.tz_localize(None)
    prior = s.loc[s.index < t]
    if prior.empty:
        return None
    return bool(prior.iloc[-1] >= threshold)


def t8d_exclude_inflationary(cell, cpi_yoy: pd.Series,
                             threshold: float = config.T8D_CPI_YOY_THRESHOLD):
    """E3 T8(d) — esclude dalla cella i cluster il cui evento è inflazionistico.

    Eventi non classificabili (None) restano nella cella (non li si scarta sulla
    base di un'informazione che non si aveva al tempo). La specularità «sotto-
    campione inflazionistico» è il complemento: si applica con `keep_only=True`.
    """
    out = []
    for cl in (cell or []):
        center = cl.get("event", {}).get("center")
        cls = t8d_is_inflationary(center, cpi_yoy, threshold)
        if cls is True:
            continue
        out.append(cl)
    return out


def t8_robustness(per_type_clusters: dict, rng, beta_grid, transforms: dict,
                  B: int = config.B_BOOT) -> dict:
    """T8 — robustezza, LISTA CHIUSA di quattro perturbazioni (esattamente queste):
    (a) esclusione finestre estreme; (b) leave-one-year-out; (c) variazione soglia
    di regime; (d) esclusione sotto-periodo inflazionistico. Il routing puntuale/AR
    si applica DENTRO ogni perturbazione (ogni cella è ri-stimata e ri-instradata).
    `transforms` = {nome: per_type→per_type}; vengono passate dall'orchestratore.
    """
    res = {"baseline": t5_signflip(estimate_per_type(per_type_clusters, rng, B), beta_grid)}
    for name, transform in transforms.items():
        pert = transform(per_type_clusters)
        res[name] = t5_signflip(estimate_per_type(pert, rng, B), beta_grid)
    return res
