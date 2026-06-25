"""pipeline.py — Orchestratore per cella robusta (spec §1, §4, §5, §6).

Per ogni cella (leg, regime) ∈ ROBUST_CELLS, per ciascun candidato Z ∈ {L,V,C}:
  1) residui ũ_e, ũ_b (residual.residuals)
  2) ortogonalizzazione ΔZ_perp = OLS-residual(z su [const, sorpresa, controlli])
  3) regressioni HC u_e ~ ΔZ_perp e u_b ~ ΔZ_perp → λ_e, λ_b, p_e, p_b
  4) BY su famiglia di 12 (3 cand × 4 celle) usando, per cella×candidato, il
     p-value della COMUNALITÀ (= max(p_e, p_b): entrambi devono essere bassi
     per la comunalità)
  5) verdetto = comunalità (post-BY) AND segno atteso AND ortogonalizzazione

L'esecutore passa per cella: r_e_tilde, r_b_tilde, beta_str, dict di proxies
{label → {z, expected_sign, mechanism}}, sorpresa per cella.
"""
from __future__ import annotations

import numpy as np

import config
import multiplicity as M
import proxies as PR
import residual as R
import tests_channel as TC
import whitening as W


def run_cell_for_candidate(*, r_e_tilde, r_b_tilde, beta_str: float,
                            z, surprise, expected_sign: str,
                            extra_controls=None, alpha: float = 0.05) -> dict:
    """Per una cella e un candidato: residui + ortogonalizzazione + regressioni
    + verdetto pre-BY (la correzione BY avviene a livello di famiglia).
    """
    res = R.residuals(r_e_tilde, r_b_tilde, beta_str=beta_str)
    z_perp = PR.orthogonalize(z, surprise=surprise, extra_controls=extra_controls)
    reg_e = TC.loading_regression(res["u_e"], z_perp=z_perp)
    reg_b = TC.loading_regression(res["u_b"], z_perp=z_perp)
    comm = TC.commonality(lambda_e=reg_e["lambda"], p_e=reg_e["p_value"],
                           lambda_b=reg_b["lambda"], p_b=reg_b["p_value"],
                           expected_sign=expected_sign, alpha=alpha)
    # p-value comunalità: max dei due (entrambi devono essere bassi)
    p_comm = float(max(reg_e["p_value"], reg_b["p_value"]))
    return {
        "u_e": res["u_e"], "u_b": res["u_b"], "z_perp": z_perp,
        "lambda_e": reg_e["lambda"], "p_e": reg_e["p_value"],
        "lambda_b": reg_b["lambda"], "p_b": reg_b["p_value"],
        "commonality": comm["commonality"], "sign_ok": comm["sign_ok"],
        "p_commonality": p_comm,
        "expected_sign": expected_sign,
    }


def run_full_protocol(cell_inputs: dict,
                      candidate_proxies: dict,
                      *, alpha: float = 0.05,
                      q: float = config.BY_Q) -> dict:
    """Esecuzione completa su TUTTE le celle robuste × candidati.

    `cell_inputs`: dict (leg, regime) → {r_e_tilde, r_b_tilde, beta_str, surprise}.
    `candidate_proxies`: dict (leg, regime) → {label: {z, expected_sign}}.
        I label DEVONO essere in config.CANDIDATES (L, V, C).

    Restituisce per ogni (cell, candidate) il dict di `run_cell_for_candidate`,
    + verdetto finale post-BY.
    """
    expected_cells = set(tuple(c) for c in config.ROBUST_CELLS)
    if set(cell_inputs.keys()) != expected_cells:
        raise ValueError(f"cell_inputs deve coprire ESATTAMENTE {expected_cells}")
    for c, props in candidate_proxies.items():
        if c not in expected_cells:
            raise ValueError(f"cella non robusta in candidate_proxies: {c}")
        if set(props.keys()) != set(config.CANDIDATES):
            raise ValueError(
                f"candidates per {c}: attesi {config.CANDIDATES}, ricevuti {set(props.keys())}"
            )

    # Esegui la cella×candidato + raccoglie p-value della comunalità
    per_pair = {}
    p_values_family = []
    pair_order = []
    for cell in config.ROBUST_CELLS:
        cell = tuple(cell)
        ci = cell_inputs[cell]
        for cand in config.CANDIDATES:
            cp = candidate_proxies[cell][cand]
            out = run_cell_for_candidate(
                r_e_tilde=ci["r_e_tilde"], r_b_tilde=ci["r_b_tilde"],
                beta_str=ci["beta_str"], z=cp["z"],
                surprise=ci["surprise"],
                expected_sign=cp.get("expected_sign", config.EXPECTED_SIGN[cand]),
                alpha=alpha,
            )
            per_pair[(cell, cand)] = out
            p_values_family.append(out["p_commonality"])
            pair_order.append((cell, cand))

    # BY sulla famiglia di 12
    by_out = M.benjamini_yekutieli(p_values_family, q=q,
                                    m=config.BY_FAMILY_SIZE)
    rejected = list(by_out["rejected"])
    verdicts = {}
    for k, (cell, cand) in enumerate(pair_order):
        pair = per_pair[(cell, cand)]
        passed_by = bool(rejected[k])
        # Verdetto pre-registrato: comunalità DOPO BY ∧ sign_ok
        is_third = bool(passed_by and pair["commonality"] and pair["sign_ok"])
        verdicts[(cell, cand)] = {
            "third_channel": is_third,
            "passed_by": passed_by,
            "commonality": pair["commonality"],
            "sign_ok": pair["sign_ok"],
            "lambda_e": pair["lambda_e"],
            "lambda_b": pair["lambda_b"],
            "p_commonality": pair["p_commonality"],
        }
    return {
        "per_pair": per_pair,
        "verdicts": verdicts,
        "by": {"c_m": by_out["c_m"], "crit": by_out["crit"],
               "family_size": by_out["m"]},
        "config_hash": config.config_hash(),
    }
