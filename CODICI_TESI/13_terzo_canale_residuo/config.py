"""config.py — Parametri congelati della diagnostica del residuo (terzo canale).

Allineamento al protocollo:
  MASTER_SEED = 20260621 (run autoritativo a9c13a7b)
  B_BOOT = 10_000

Pre-registrazione (spec §0, §3, §6):
  - 3 candidati a priori (L, V, C) con segno atteso fissato.
  - 4 celle robuste (FOMC/neg, NFP/neg, CPI/neg, CPI/pos).
  - Famiglia BY = 12 (3 × 4), q = 0.10.
  - Soglie gate_a multiple, CALCOLATE alla fonte (MOP-Patnaik K=1).
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
from scipy.stats import ncx2

CONFIG_VERSION = "terzo-canale-residuo-v1-2026-06-23"
MASTER_SEED = 20260621
B_BOOT = 10_000

# ----- Candidati a priori (spec §3) ----------------------------------------
CANDIDATES = ("L", "V", "C")
# Segno atteso per la regola di decisione (§6) — qualunque cosa diverga è "fail sign"
#
# REVISIONE SPEC §3 (risoluzione patologia §2/§3 — opzione "antisymmetric"):
#   I residui ũ_e e ũ_b come definiti in §2 hanno carichi ANTISIMMETRICI su Z
#   (coef_b = −coef_e/β per costruzione, con β > 0). La sign rule
#   originaria "concordant"/"both_negative" era matematicamente impossibile
#   da soddisfare e produceva xfail strict del test §9.1.
#
#   Soluzione: la sign rule è ridefinita per ESSERE COERENTE con il pattern
#   antisimmetrico predetto dalla spec §2. "concordant" e "both_negative"
#   diventano "antisymmetric_pos_eq" e "antisymmetric_neg_eq", entrambi
#   richiedono sign(λ_e) opposto a sign(λ_b) (auto-coerente con la patologia),
#   ma con un VINCOLO AGGIUNTIVO sul segno di λ_e per identificare il senso
#   del meccanismo:
#     - L (liquidità muove i prezzi insieme): λ_e > 0  → λ_b < 0 per antisimm.
#     - V (calo vol → prezzi su):              λ_e < 0  → λ_b > 0 per antisimm.
#
#   Il segnale identificativo passa attraverso (1) la comunalità (entrambi
#   significativi) e (2) il senso di λ_e (positivo o negativo). C resta
#   ambiguous. La spec §2 NON è modificata; la sign rule §3 è.
EXPECTED_SIGN = {
    "L": "antisymmetric_pos_eq",   # λ_e > 0, λ_b < 0 (antisimmetria con eq lead positivo)
    "V": "antisymmetric_neg_eq",   # λ_e < 0, λ_b > 0 (antisimmetria con eq lead negativo)
    "C": "ambiguous",              # registrato, NON imposto
}

# Descrizione candidate (per il manifest / report)
CANDIDATE_MECHANISM = {
    "L": "Funding liquidity (Brunnermeier-Pedersen); proxy intraday: ΔbidAsk Treasury/equity, "
         "o Hu-Pan-Wang noise; ripiego daily: ΔTED, ΔOIS-Treasury.",
    "V": "Volatility risk premium / resolution of uncertainty; proxy: ΔVIX, ΔMOVE.",
    "C": "Expected equity-bond correlation / hedging demand (Campbell-Pflueger-Viceira); "
         "proxy: corr realizzata intraday o option-implied. PIÙ DEBOLE dei tre.",
}

# ----- Celle ammesse al test (spec §1) -------------------------------------
ROBUST_CELLS = (("FOMC", "neg"), ("NFP", "neg"), ("CPI", "neg"), ("CPI", "pos"))

# ----- Molteplicità (spec §6) ----------------------------------------------
BY_FAMILY_SIZE = len(CANDIDATES) * len(ROBUST_CELLS)  # 3 × 4 = 12
BY_Q = 0.10


# ----- Soglie sensibilità gate_a (spec §7) ---------------------------------
# MOP-Patnaik K=1: cv = ncx2.ppf(0.95, df=1, ncp=1/τ).
# Verificate alla fonte (spec §7 esplicita).
def _mop_cv(tau: float) -> float:
    return float(ncx2.ppf(0.95, 1, 1.0 / tau))


GATE_A_THRESHOLDS = {
    "bias_10pct": _mop_cv(0.10),   # 23.1085 (protocollo)
    "bias_15pct": _mop_cv(0.15),   # 17.8662 (spec dice ~19.7 a memoria; valore vero MOP)
    "bias_20pct": _mop_cv(0.20),   # 15.0616 (coincide con stima ~15.1 della spec)
    "practical_F10": 10.0,         # regola pratica Staiger-Stock
}


# ----- Seeding -------------------------------------------------------------

def _name_int(name: str) -> int:
    return int.from_bytes(hashlib.blake2b(name.encode(), digest_size=8).digest(), "big")


def make_rng(name: str) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([MASTER_SEED, _name_int(name)]))


def seed_for(name: str) -> int:
    seq = np.random.SeedSequence([MASTER_SEED, _name_int(name)])
    return int(seq.generate_state(1)[0])


def config_snapshot() -> dict:
    return {
        "config_version": CONFIG_VERSION,
        "master_seed": MASTER_SEED,
        "b_boot": B_BOOT,
        "candidates": list(CANDIDATES),
        "expected_sign": dict(EXPECTED_SIGN),
        "candidate_mechanism": dict(CANDIDATE_MECHANISM),
        "robust_cells": [list(c) for c in ROBUST_CELLS],
        "by_family_size": BY_FAMILY_SIZE,
        "by_q": BY_Q,
        "gate_a_thresholds": dict(GATE_A_THRESHOLDS),
        "gate_a_thresholds_source": "MOP-Patnaik K=1, verificata alla fonte via scipy.stats.ncx2",
    }


def config_hash() -> str:
    return hashlib.sha256(json.dumps(config_snapshot(), sort_keys=True).encode()).hexdigest()
