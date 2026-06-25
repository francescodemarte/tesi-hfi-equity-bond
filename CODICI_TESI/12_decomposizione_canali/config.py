"""config.py — Parametri congelati della decomposizione in canali con doppio cancello.

ALLINEAMENTO al run autoritativo `a9c13a7b`:
  - MASTER_SEED = 20260621 (riusato per coerenza dei bootstrap clusterizzati)
  - B_BOOT = 10_000
  - MOP_CV = 23.1085 (Nagar bias, K=1, Patnaik semplificata conservativa)
  - BY_Q = 0.10 (FDR Benjamini–Yekutieli)
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

CONFIG_VERSION = "decomp-canali-doppio-cancello-v1-2026-06-22"

# Protocollo (a9c13a7b)
MASTER_SEED = 20260621
B_BOOT = 10_000
MOP_CV = 23.1085
BY_Q = 0.10

# Griglia di coda (4 punti per equity)
TAIL_GRID = ("T0", "TC", "TD_0.5", "TD_0.8")
# Per TD: λ associato al tag
TAIL_DECAY_LAMBDA = {"TD_0.5": 0.5, "TD_0.8": 0.8}

# Griglia di ρ (3 valori): offset additivi su dp_bar
RHO_DEFAULT_DELTA = 0.25
RHO_OFFSETS = (-RHO_DEFAULT_DELTA, 0.0, +RHO_DEFAULT_DELTA)

# Totale punti per evento sull'equity (bond unico, no coda)
GRID_POINTS_PER_EVENT = len(TAIL_GRID) * len(RHO_OFFSETS)

# Soglia (cancello b): pre-check §3.3 — significatività del Δf al bordo
TAIL_BORDER_SIGNIFICANCE_ALPHA = 0.05

# Soglia ausiliaria del cancello (a): shrink minimo per dichiarare il bond
# NETTO non svuotato. La spec dice "shrink → 0 ⇒ bond quasi puro tasso ⇒
# netto svuotato ⇒ FAIL atteso": F_MOP da solo può essere numericamente
# alto su quantità minuscole, quindi serve anche un floor su shrink.
# Default conservativo, esposto al ricercatore.
SHRINK_FLOOR_DEFAULT = 0.05

# Soglia banda di costruzione per il verdetto "robust" vs "fragile" (cancello b).
# Pre-registrata: entra nel config_hash. Default 0.30 (REVIEW #2).
BAND_WIDTH_THRESHOLD_DEFAULT = 0.30


# --- Seeding riproducibile + integer seed dichiarato per manifest ----------

def _name_int(name: str) -> int:
    return int.from_bytes(hashlib.blake2b(name.encode(), digest_size=8).digest(), "big")


def make_rng(name: str) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([MASTER_SEED, _name_int(name)]))


def seed_for(name: str) -> int:
    """Intero seed dichiarato per il manifest (pattern 07/08/11)."""
    seq = np.random.SeedSequence([MASTER_SEED, _name_int(name)])
    return int(seq.generate_state(1)[0])


def config_snapshot() -> dict:
    return {
        "config_version": CONFIG_VERSION,
        "master_seed": MASTER_SEED,
        "b_boot": B_BOOT,
        "mop_cv": MOP_CV,
        "by_q": BY_Q,
        "tail_grid": list(TAIL_GRID),
        "tail_decay_lambda": dict(TAIL_DECAY_LAMBDA),
        "rho_default_delta": RHO_DEFAULT_DELTA,
        "rho_offsets": list(RHO_OFFSETS),
        "grid_points_per_event": GRID_POINTS_PER_EVENT,
        "tail_border_significance_alpha": TAIL_BORDER_SIGNIFICANCE_ALPHA,
        "shrink_floor_default": SHRINK_FLOOR_DEFAULT,
        "band_width_threshold_default": BAND_WIDTH_THRESHOLD_DEFAULT,
    }


def config_hash() -> str:
    return hashlib.sha256(json.dumps(config_snapshot(), sort_keys=True).encode()).hexdigest()
