"""synthetic.py — 4 DGP a verità nota per la validazione coder (spec §9).

  1) terzo canale presente   — atteso: RILEVA Z, recupera carichi entro banda.
  2) nessun terzo canale     — atteso: NON dichiara (falsificazione, BY controlla FPR).
  3) fattore solo-equity     — atteso: comunalità FALLISCE.
  4) Z correlato a sorpresa  — atteso: dopo ortogonalizzazione, potere svanisce.

Modello a tre fattori (per la cella):
  r̃_e = γ_e · s + λ_e · Z + ε_e
  r̃_b = γ_b · s + λ_b · Z + ε_b
con s ⟂ ε (cases 1/3/4); Z indipendente o correlato secondo il DGP.
"""
from __future__ import annotations

import numpy as np


def _bivariate_noise(rng, n, sd_e, sd_b):
    return rng.normal(0, sd_e, n), rng.normal(0, sd_b, n)


def dgp_case1_third_channel_present(rng, n=400,
                                    gamma_e=2.0, gamma_b=1.0,
                                    lambda_e=1.5, lambda_b=1.2,
                                    sd_e=0.5, sd_b=0.3) -> dict:
    """Z osservato, λ_e e λ_b ≠ 0, segno concordant (entrambi positivi).
    Sorpresa s ⟂ Z ⟂ ε. Atteso: test rileva Z come terzo canale comune.
    """
    s = rng.standard_normal(n)
    z = rng.standard_normal(n)         # Z ⟂ s
    eps_e, eps_b = _bivariate_noise(rng, n, sd_e, sd_b)
    r_e_tilde = gamma_e * s + lambda_e * z + eps_e
    r_b_tilde = gamma_b * s + lambda_b * z + eps_b
    return {"r_e_tilde": r_e_tilde, "r_b_tilde": r_b_tilde,
            "s": s, "z": z,
            "truth": {"gamma_e": gamma_e, "gamma_b": gamma_b,
                       "lambda_e": lambda_e, "lambda_b": lambda_b}}


def dgp_case2_no_third_channel(rng, n=400,
                               gamma_e=2.0, gamma_b=1.0,
                               sd_e=0.5, sd_b=0.3) -> dict:
    """Z puro rumore SCORRELATO; nessun carico genuino. Atteso: test NON
    dichiara terzo canale; BY controlla i falsi positivi.
    """
    s = rng.standard_normal(n)
    z = rng.standard_normal(n)
    eps_e, eps_b = _bivariate_noise(rng, n, sd_e, sd_b)
    r_e_tilde = gamma_e * s + eps_e   # nessun λ
    r_b_tilde = gamma_b * s + eps_b
    return {"r_e_tilde": r_e_tilde, "r_b_tilde": r_b_tilde,
            "s": s, "z": z,
            "truth": {"gamma_e": gamma_e, "gamma_b": gamma_b,
                       "lambda_e": 0.0, "lambda_b": 0.0}}


def dgp_case3_equity_only(rng, n=400,
                          gamma_e=2.0, gamma_b=1.0,
                          lambda_e=1.5,
                          sd_e=0.5, sd_b=0.3) -> dict:
    """Z carica SOLO sull'equity (λ_b = 0). Atteso: comunalità FALLISCE,
    Z NON dichiarato canale comune.
    """
    s = rng.standard_normal(n)
    z = rng.standard_normal(n)
    eps_e, eps_b = _bivariate_noise(rng, n, sd_e, sd_b)
    r_e_tilde = gamma_e * s + lambda_e * z + eps_e
    r_b_tilde = gamma_b * s + eps_b   # λ_b = 0
    return {"r_e_tilde": r_e_tilde, "r_b_tilde": r_b_tilde,
            "s": s, "z": z,
            "truth": {"gamma_e": gamma_e, "gamma_b": gamma_b,
                       "lambda_e": lambda_e, "lambda_b": 0.0}}


def dgp_case4_z_correlated_with_surprise(rng, n=400,
                                         gamma_e=2.0, gamma_b=1.0,
                                         alpha_zs=1.5,
                                         sd_e=0.5, sd_b=0.3) -> dict:
    """Z = α·s + η (correlato con s) ma NESSUN carico genuino sul residuo.
    Atteso: prima dell'ortogonalizzazione Z sembra esplicare; dopo
    ortogonalizzazione (§4) il potere svanisce → no terzo canale.
    """
    s = rng.standard_normal(n)
    z = alpha_zs * s + rng.standard_normal(n) * 0.5
    eps_e, eps_b = _bivariate_noise(rng, n, sd_e, sd_b)
    r_e_tilde = gamma_e * s + eps_e
    r_b_tilde = gamma_b * s + eps_b
    return {"r_e_tilde": r_e_tilde, "r_b_tilde": r_b_tilde,
            "s": s, "z": z,
            "truth": {"gamma_e": gamma_e, "gamma_b": gamma_b,
                       "lambda_e": 0.0, "lambda_b": 0.0,
                       "alpha_zs": alpha_zs}}
