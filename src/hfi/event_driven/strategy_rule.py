"""strategy_rule.py — Regola di attivazione e di posizione (spec, congelata).

- Attivazione: solo se regime == ACTIVE_REGIME[strategy] (tutte negativo).
- Direzione: momentum sulla SORPRESA. Equity nel verso della sorpresa,
  bond nel verso *coerente con il comovimento strutturale* (β_str positivo →
  stessa direzione, β_str negativo → versi opposti).
- Sizing: |β_str| sulla coppia (proporzionale al comovimento strutturale).
"""
from __future__ import annotations

import math

import config


def is_active(strategy: str, regime: str) -> bool:
    if strategy not in config.STRATEGIES:
        raise KeyError(f"strategia {strategy!r} non in {config.STRATEGIES}")
    return regime == config.ACTIVE_REGIME[strategy]


def skip_if_inactive(strategy: str, regime: str) -> bool:
    """True ⇒ evento da saltare; False ⇒ evento da processare."""
    return not is_active(strategy, regime)


def position(strategy: str, surprise: float) -> dict:
    """Verso (segno) ed entità (size) della posizione sulla coppia (equity, bond).

    Convenzioni:
      - sign_equity = sign(surprise)
      - sign_bond   = sign(surprise) · sign(β_str)
        (β_str>0 → comovimento positivo → stessa direzione;
         β_str<0 → comovimento negativo → versi opposti.)
      - size = |β_str|: applicato uniformemente a equity e bond per coerenza
        col coefficiente di proiezione strutturale.
      - Sorpresa = 0 → posizione zero (momentum richiede un verso).
    """
    if strategy not in config.STRATEGIES:
        raise KeyError(f"strategia {strategy!r} non in {config.STRATEGIES}")
    beta = float(config.BETA_STR[strategy])
    if surprise == 0.0 or math.isnan(surprise):
        return {"sign_equity": 0, "sign_bond": 0, "size": 0.0, "beta_str": beta}
    s_surp = 1 if surprise > 0 else -1
    s_beta = 1 if beta > 0 else -1
    return {"sign_equity": s_surp,
            "sign_bond": s_surp * s_beta,
            "size": abs(beta),
            "beta_str": beta}
