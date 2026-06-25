"""netting.py — Passo 2: rendimenti netti dal canale di tasso.

  r̃_e,i(g) = r_e,i − ΔP^B_e,i(g)     g = punto griglia coda×ρ (12 punti)
  r̃_b,i    = r_b,i − ΔP^B_b,i         (bond unico, no coda)

Funzione: netting per evento. L'orchestrator passa per-evento i ΔP^B costruiti
in `equity_pb` / `bond_pb`.
"""
from __future__ import annotations

import numpy as np


def net_equity(r_e, delta_pb_e) -> np.ndarray:
    """r̃_e = r_e − ΔP^B_e (vettorizzato per-evento)."""
    return np.asarray(r_e, float) - np.asarray(delta_pb_e, float)


def net_bond(r_b, delta_pb_b) -> np.ndarray:
    """r̃_b = r_b − ΔP^B_b (unico, no coda)."""
    return np.asarray(r_b, float) - np.asarray(delta_pb_b, float)
