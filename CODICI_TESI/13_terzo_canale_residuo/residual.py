"""residual.py — Costruzione del residuo dai netti (spec §2).

Per cella robusta e per evento i:
  ũ_e,i = r̃_e,i − β̂_str · r̃_b,i        (residuo lato equity)
  ũ_b,i = r̃_b,i − (1/β̂_str) · r̃_e,i    (residuo lato bond, "simmetrico")

⚠️ ATTENZIONE — PATOLOGIA STRUTTURALE DELLA DEFINIZIONE SPEC §2 (DA RIPORTARE
AL RICERCATORE, scoperta dalla validazione sintetica §9):

  Sotto questa definizione, λ_e e λ_b stimati dalle regressioni del residuo
  su ΔZ sono ANTISIMMETRICI per costruzione:

      coef(ũ_b, Z) = −coef(ũ_e, Z) / β

  Prova algebrica: sia r̃_e = γ_e·s + λ_e·Z + ε_e, r̃_b = γ_b·s + λ_b·Z + ε_b.
  Allora ũ_e ha carico (λ_e − β·λ_b) su Z; ũ_b ha carico (λ_b − λ_e/β).
  β·(λ_b − λ_e/β) = β·λ_b − λ_e = −(λ_e − β·λ_b). ∎

  CONSEGUENZA: la regola di segno §3 — "concordant" per L, "both_negative"
  per V — è MATEMATICAMENTE IMPOSSIBILE da soddisfare sotto questa
  definizione (i due carichi sono sempre di segno opposto per β>0).
  Solo "ambiguous" è coerente, ma diventa banale (sempre vero).

  Il codice resta FEDELE alla spec (no patch); i test che esercitano
  "concordant"/"both_negative" sono `xfail` con questa motivazione.
  La risoluzione è del ricercatore: rivedere la definizione di ũ_b o
  rivedere la regola di segno della comunalità.
"""
from __future__ import annotations

import numpy as np


def residuals(r_e_tilde, r_b_tilde, beta_str: float) -> dict:
    """ũ_e, ũ_b dai rendimenti netti e β̂_str. Solleva se β_str ≈ 0."""
    if not np.isfinite(beta_str) or abs(beta_str) < 1e-20:
        raise ValueError(f"beta_str ≈ 0 o non finito ({beta_str}): residuo lato bond non definito")
    r_e_tilde = np.asarray(r_e_tilde, dtype=float)
    r_b_tilde = np.asarray(r_b_tilde, dtype=float)
    if r_e_tilde.shape != r_b_tilde.shape:
        raise ValueError("r_e_tilde e r_b_tilde devono avere stessa lunghezza")
    u_e = r_e_tilde - beta_str * r_b_tilde
    u_b = r_b_tilde - (1.0 / beta_str) * r_e_tilde
    return {"u_e": u_e, "u_b": u_b}
