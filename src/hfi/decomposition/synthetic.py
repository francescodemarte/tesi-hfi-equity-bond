"""synthetic.py — DGP a verità nota per la validazione (spec §7).

Modello a due canali:
  r_e = γ_e·s + δ_e·s_r + ε_e
  r_b = γ_b·s + δ_b·s_r + ε_b
con s ⟂ s_r ⟂ ε. Curva sintetica coerente con s_r: forward Δf_n = c_n · s_r,
con caricamenti c_n noti. La "coda vera" è data dai c_n per n > m_observed.

Build events with windows event/control (event ha sorpresa s + s_r, control no).
"""
from __future__ import annotations

import numpy as np


def _draw_event_returns(n_events, sigma_e_evt, sigma_e_ctl, sigma_b_evt, sigma_b_ctl,
                       gamma_e, delta_e, gamma_b, delta_b,
                       loadings, m_observed, D_bond, rng):
    """Genera eventi (con sorpresa s e s_r) e controlli (senza sorpresa)."""
    out = []
    for _ in range(n_events):
        # Sorprese
        s = float(rng.standard_normal())
        s_r = float(rng.standard_normal())
        # rendimenti evento (con ε)
        eps_e_evt = float(rng.normal(0, sigma_e_evt))
        eps_b_evt = float(rng.normal(0, sigma_b_evt))
        r_e_evt = gamma_e * s + delta_e * s_r + eps_e_evt
        r_b_evt = gamma_b * s + delta_b * s_r + eps_b_evt
        # rendimenti controllo (no sorprese strutturali, solo ε di varianza minore)
        eps_e_ctl = float(rng.normal(0, sigma_e_ctl))
        eps_b_ctl = float(rng.normal(0, sigma_b_ctl))
        r_e_ctl = eps_e_ctl
        r_b_ctl = eps_b_ctl
        # Δf osservati: Δf_n = c_n · s_r per n=1..m_observed
        delta_f_curve = np.array([loadings[n] * s_r for n in range(m_observed)], dtype=float)
        # Δy del bond: legato a s_r tramite duration ⇒ Δy_b = − r_b_rate_only / D_bond
        # Approssimazione: Δy_b * D_bond = quota di r_b dovuta a s_r (= δ_b · s_r) cambiata di segno
        # ⇒ Δy_b = (δ_b · s_r) / (-D_bond) ⇒ -D · Δy = δ_b · s_r
        delta_y_bond = -(delta_b * s_r) / D_bond
        out.append({
            "r_e_event": r_e_evt, "r_e_control": r_e_ctl,
            "r_b_event": r_b_evt, "r_b_control": r_b_ctl,
            "delta_f_curve": delta_f_curve,
            "D_bond": D_bond,
            "delta_y_bond": delta_y_bond,
            "_truth": {"s": s, "s_r": s_r,
                       "ratio_gamma_e_over_gamma_b": gamma_e / gamma_b if gamma_b != 0 else float("inf")},
        })
    return out


def dgp_case1_bond_with_structure(rng, n_events=300, m_observed=4):
    """Caso 1: γ_b NON piccolo, δ_b moderato. Atteso gate(a) PASS;
    β̂_str ≈ γ_e / γ_b dentro banda."""
    # Carichi c_n decadono: c_n = 0.8^n (coda vera DECADE rapidamente)
    loadings = {n: 0.8 ** (n + 1) for n in range(m_observed + 50)}
    return _draw_event_returns(n_events,
        sigma_e_evt=0.005, sigma_e_ctl=0.003,
        sigma_b_evt=0.003, sigma_b_ctl=0.0015,
        gamma_e=2.0, delta_e=1.0,
        gamma_b=1.0, delta_b=0.5,
        loadings=loadings, m_observed=m_observed, D_bond=7.0, rng=rng)


def dgp_case2_bond_pure_rate(rng, n_events=300, m_observed=4):
    """Caso 2: γ_b → 0, δ_b grande. Atteso gate(a) FAIL (bond quasi puro tasso)."""
    loadings = {n: 0.8 ** (n + 1) for n in range(m_observed + 50)}
    return _draw_event_returns(n_events,
        sigma_e_evt=0.005, sigma_e_ctl=0.003,
        sigma_b_evt=0.001, sigma_b_ctl=0.0008,
        gamma_e=2.0, delta_e=1.0,
        gamma_b=0.05, delta_b=3.0,
        loadings=loadings, m_observed=m_observed, D_bond=7.0, rng=rng)


def dgp_case3_informative_tail(rng, n_events=300, m_observed=4):
    """Caso 3: coda VERA non zero ma osservabile solo fino a m. La banda di
    costruzione DEVE coprire la verità. Anche pre-check WARN atteso (Δf_m
    sistematicamente diverso da 0 perché s_r genera Δf_m grande)."""
    # Carichi: c_n = 0.95^n (decadono lentamente ⇒ coda informativa)
    loadings = {n: 0.95 ** (n + 1) for n in range(m_observed + 200)}
    return _draw_event_returns(n_events,
        sigma_e_evt=0.005, sigma_e_ctl=0.003,
        sigma_b_evt=0.003, sigma_b_ctl=0.0015,
        gamma_e=2.0, delta_e=1.0,
        gamma_b=1.0, delta_b=0.5,
        loadings=loadings, m_observed=m_observed, D_bond=7.0, rng=rng)


def dgp_case4_single_channel(rng, n_events=300, m_observed=4):
    """Caso 4: UN SOLO canale (δ ≡ 0). β_str ≈ β_H, banda costruzione ≈ degenere.
    La procedura non deve creare un secondo canale dove non c'è.
    """
    loadings = {n: 0.0 for n in range(m_observed + 50)}   # nessuna curva
    return _draw_event_returns(n_events,
        sigma_e_evt=0.005, sigma_e_ctl=0.003,
        sigma_b_evt=0.003, sigma_b_ctl=0.0015,
        gamma_e=2.0, delta_e=0.0,
        gamma_b=1.0, delta_b=0.0,
        loadings=loadings, m_observed=m_observed, D_bond=7.0, rng=rng)
