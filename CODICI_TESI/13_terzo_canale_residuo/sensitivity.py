"""sensitivity.py — Sensibilità del cancello di forza a soglie multiple (spec §7).

Per ciascuna cella si riporta a quali soglie il gate_a passa:
  - bias_10pct (23.1085, protocollo)
  - bias_15pct (17.866 verificato da MOP-Patnaik)
  - bias_20pct (15.062)
  - practical_F10 (10.0)

Robustezza: 'strong' se passa la più stretta; 'weak' se passa solo soglie più basse;
'fail' se non passa neanche la pratica. NON è ammorbidimento del criterio: serve
SOLO a dichiarare la sensibilità, non a sostituire il verdetto pre-registrato.
"""
from __future__ import annotations

import math

import config


def gate_a_sensitivity(F_MOP: float) -> dict:
    """Pass/Fail a ciascuna soglia + classificazione di robustezza."""
    if not math.isfinite(F_MOP):
        passes = {k: False for k in config.GATE_A_THRESHOLDS}
        return {"F_MOP": F_MOP, "passes": passes, "robustness": "fail",
                "reason": "F_MOP non finito"}
    passes = {k: bool(F_MOP >= cv) for k, cv in config.GATE_A_THRESHOLDS.items()}
    if passes["bias_10pct"]:
        rob = "strong"
    elif passes["practical_F10"]:
        rob = "weak"
    else:
        rob = "fail"
    return {"F_MOP": float(F_MOP), "passes": passes, "robustness": rob}
