"""synthetic.py — Generatori di dati SINTETICI per lo smoke-test (SPEC §10).

Tre DGP per lo smoke-test della pipeline Rigobon-Sack a due regimi. NESSUN
dato reale. Modello:

    r^e = β · r^b + u

Le finestre EVENTO hanno varianza di r^b maggiore (σ_e) delle finestre
CONTROLLO (σ_c) ⇒ ΔVar = σ_e² − σ_c² > 0. Lo shock comune è σ_eb = Cov(u, r^b);
si inietta generando la coppia (r^b, u) come normale bivariata con covarianza
ASSEGNATA, separatamente per le finestre evento (c_event) e di controllo
(c_control). La b_H trasversale di una cella risulta

    b_H = ΔCov/ΔVar = β + (c_event − c_control)/ΔVar.

STRUTTURA DATI (consumata da tests_protocol.cell_moments):
  CELLA      = lista di cluster (uno per evento);
  cluster    = {"event": {"r_e": float, "r_b": float},
                "controls": [{"r_e": float, "r_b": float}, ...]};
  per_type   = {tipo: {"pos": <cella>, "neg": <cella>}} per i 4 tipi evento.

Riproducibilità: tutta l'aleatorietà passa per il np.random.Generator `rng`.
"""
from __future__ import annotations

import numpy as np

# Tipi evento (coerenti con config.EVENT_TYPES, qui esplicitati per non
# accoppiare i DGP sintetici alla config congelata della pipeline reale).
EVENT_TYPES = ("NFP", "CPI", "FOMC", "ECB")


def _bivariate(rng, n, sigma, c, var_u):
    """Genera (r_b, u) ~ N(0, Σ) con Var(r_b)=σ², Cov(r_b,u)=c, Var(u)=var_u.

    La matrice deve essere semidefinita positiva: |c| ≤ σ·√var_u. Se la
    covarianza richiesta sfora il bound, var_u viene alzato quel tanto che
    basta (con un piccolo margine) a renderla PSD. Restituisce (r_b, u).
    """
    var_b = sigma ** 2
    min_var_u = (c ** 2) / var_b if var_b > 0 else 0.0
    if var_u <= min_var_u:
        var_u = min_var_u * 1.5 + 1e-12
    cov = np.array([[var_b, c], [c, var_u]], dtype=float)
    draws = rng.multivariate_normal(mean=[0.0, 0.0], cov=cov, size=n)
    return draws[:, 0], draws[:, 1]


def _make_cell(rng, n_events, k, beta, sigma_e, sigma_c, c_event, c_control,
               var_u=None):
    """Costruisce una CELLA (n_events cluster) per un dato regime.

    Per ogni evento: 1 finestra evento (varianza σ_e, covarianza c_event) e
    k finestre di controllo (varianza σ_c, covarianza c_control). In ogni
    finestra r^e = β·r^b + u. `var_u` di default è scelto ampio così da
    garantire la PSD della normale bivariata in entrambi i regimi.
    """
    if var_u is None:
        # Rumore idiosincratico sulla scala del SEGNALE (≈ var di r^b), NON enorme:
        # un var_u grande gonfierebbe l'errore campionario di Cov(r^e,r^b) e
        # renderebbe instabile il segno della b_H trasversale. Il floor PSD
        # (|c|≤σ·√var_u) è comunque garantito dentro _bivariate.
        var_u = max(sigma_e, sigma_c) ** 2

    cell = []
    for _ in range(n_events):
        # finestra evento (1 sola)
        rb_e, u_e = _bivariate(rng, 1, sigma_e, c_event, var_u)
        event = {"r_e": float(beta * rb_e[0] + u_e[0]), "r_b": float(rb_e[0])}
        # finestre di controllo (k)
        rb_c, u_c = _bivariate(rng, k, sigma_c, c_control, var_u)
        controls = [{"r_e": float(beta * rb_c[i] + u_c[i]), "r_b": float(rb_c[i])}
                    for i in range(k)]
        cell.append({"event": event, "controls": controls})
    return cell


def structural_flip_truth() -> dict:
    """Ground-truth (per costruzione) del DGP A per NFP — FONTE UNICA usata sia da
    `dgp_structural_flip` per generare sia dal meta-controllo per asserire.
    Qui è β a flippare e σ_eb è invariante (Δσ_eb=0 ⇒ plim b_H = β)."""
    return {"beta_pos": +2.0, "beta_neg": -2.0,
            "delta_sigma_eb_pos": 0.0, "delta_sigma_eb_neg": 0.0,
            "plim_bH_pos": +2.0, "plim_bH_neg": -2.0}


def bias_flip_truth(beta0=0.5, sigma_e=0.02, sigma_c=0.005) -> dict:
    """Ground-truth (per costruzione) del DGP C per NFP — FONTE UNICA (vedi sopra).

    β IDENTICO nei due regimi (= beta0); il flip viene dal bias: plim b_H =
    β + Δσ_eb/ΔVar, con Δσ_eb scelto a multipli di ΔVar (pos +1.0, neg −1.5).
    Il meta-controllo asserisce su QUESTI parametri: β costante e plim a segni opposti.
    """
    dVar = sigma_e ** 2 - sigma_c ** 2
    mult_pos, mult_neg = +1.0, -1.5
    return {"beta_pos": beta0, "beta_neg": beta0, "dVar": dVar,
            "delta_sigma_eb_pos": mult_pos * dVar, "delta_sigma_eb_neg": mult_neg * dVar,
            "plim_bH_pos": beta0 + mult_pos, "plim_bH_neg": beta0 + mult_neg}


def dgp_structural_flip(rng, n_events=300, k=5, sigma_e=0.02, sigma_c=0.005) -> dict:
    """DGP A — flip STRUTTURALE: il sign-flip di b_H viene da un flip di β.

    NFP: β=+2 nel regime pos, β=−2 nel neg, σ_eb INVARIANTE (c_event=c_control=0)
         ⇒ b_H = β flippa perché flippa β.
    CPI: stesso β (−1.5) nei due regimi, σ_eb invariante ⇒ niente flip.
    FOMC, ECB: stesso β (1.0) nei due regimi ⇒ niente flip.
    """
    common = dict(n_events=n_events, k=k, sigma_e=sigma_e, sigma_c=sigma_c,
                  c_event=0.0, c_control=0.0)
    _t = structural_flip_truth()   # fonte unica condivisa col meta-controllo
    per_type = {
        "NFP": {
            "pos": _make_cell(rng, beta=_t["beta_pos"], **common),
            "neg": _make_cell(rng, beta=_t["beta_neg"], **common),
        },
        "CPI": {
            "pos": _make_cell(rng, beta=-1.5, **common),
            "neg": _make_cell(rng, beta=-1.5, **common),
        },
        "FOMC": {
            "pos": _make_cell(rng, beta=1.0, **common),
            "neg": _make_cell(rng, beta=1.0, **common),
        },
        "ECB": {
            "pos": _make_cell(rng, beta=1.0, **common),
            "neg": _make_cell(rng, beta=1.0, **common),
        },
    }
    return per_type


def dgp_null(rng, n_events=300, k=5, sigma_e=0.02, sigma_c=0.005) -> dict:
    """DGP B — NULLO: nessuna stato-dipendenza, b_H NON flippa per nessun tipo.

    Tutti i tipi hanno lo STESSO β nei due regimi e σ_eb invariante: b_H mantiene
    lo stesso segno tra pos e neg (entro l'errore campionario; n_events grande lo
    stabilizza). Serve a controllare la size (falsi-positivi ~ α).
    """
    common = dict(n_events=n_events, k=k, sigma_e=sigma_e, sigma_c=sigma_c,
                  c_event=0.0, c_control=0.0)
    betas = {"NFP": 1.5, "CPI": -1.5, "FOMC": 1.0, "ECB": 1.0}
    per_type = {}
    for t, beta in betas.items():
        per_type[t] = {
            "pos": _make_cell(rng, beta=beta, **common),
            "neg": _make_cell(rng, beta=beta, **common),
        }
    return per_type


def dgp_bias_flip(rng, beta0=0.5, n_events=300, k=5, sigma_e=0.02, sigma_c=0.005) -> dict:
    """DGP C — flip DEL BIAS: b_H flippa pur con β COSTANTE tra i regimi.

    NFP: β = beta0 IDENTICO nei due regimi, ma Δσ_eb cambia segno. Poiché
         b_H = β + (c_event−c_control)/ΔVar con ΔVar ≈ σ_e²−σ_c² > 0:
           regime pos: (c_event−c_control) scelto > 0 abbastanza da dare b_H_pos>0;
           regime neg: (c_event−c_control) scelto < 0 abbastanza da dare b_H_neg<0.
         Il flip OSSERVATO viene dal bias, NON da β: il codice non lo distingue
         dal flip strutturale (DGP A) — è il cardine epistemico del protocollo.
    Altri tipi: stesso β nei due regimi, σ_eb invariante ⇒ niente flip.
    """
    # FONTE UNICA: gli stessi parametri usati dal meta-controllo (β, Δσ_eb per regime).
    # Lo scarto si realizza interamente sulla finestra evento (c_control=0), così
    # σ_eb dei controlli resta nullo e Δσ_eb = c_event.
    truth = bias_flip_truth(beta0=beta0, sigma_e=sigma_e, sigma_c=sigma_c)
    nfp = {
        "pos": _make_cell(rng, n_events=n_events, k=k, beta=truth["beta_pos"],
                          sigma_e=sigma_e, sigma_c=sigma_c,
                          c_event=truth["delta_sigma_eb_pos"], c_control=0.0),
        "neg": _make_cell(rng, n_events=n_events, k=k, beta=truth["beta_neg"],
                          sigma_e=sigma_e, sigma_c=sigma_c,
                          c_event=truth["delta_sigma_eb_neg"], c_control=0.0),
    }

    common = dict(n_events=n_events, k=k, sigma_e=sigma_e, sigma_c=sigma_c,
                  c_event=0.0, c_control=0.0)
    other_betas = {"CPI": -1.5, "FOMC": 1.0, "ECB": 1.0}
    per_type = {"NFP": nfp}
    for t, beta in other_betas.items():
        per_type[t] = {
            "pos": _make_cell(rng, beta=beta, **common),
            "neg": _make_cell(rng, beta=beta, **common),
        }
    return per_type
