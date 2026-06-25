"""config.py — Parametri CONGELATI dello spillover Fed→area euro.

Autorità: `derivazione_test_spillover.md` (la spec consegnata dall'anello
precedente). I valori sono **pre-registrati**: non modificarli dopo il
congelamento. Lo schema di seeding è dedicato (`SPILLOVER_MASTER_SEED`) per
separare la provenance da quella del protocollo principale (CODICI_TESI/07_).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

CONFIG_VERSION = "spillover-fed-eu-v1-2026-06-22"

# --- Finestra sorpresa W^US_j -----------------------------------------------
TAU_PRE_MIN = 10
TAU_POST_MIN = 20

# --- Paniere tassi US (PC1 → m_j) -------------------------------------------
US_SHORT_RATE_BASKET = ("FF_c1", "FF_c2", "ED_q2", "ED_q3", "ED_q4")
SP500_INSTRUMENT = "ES"

# --- Assets EU di risposta (Stadio 1) ---------------------------------------
EU_ASSETS = {
    "BUND_10Y": "yield_bp",            # Δy^B in p.b.
    "ESTOXX50": "log_return",          # r^ES log-return
    "BTP_BUND_SPREAD": "yield_bp",     # Δsp in p.b.
}

# --- Bootstrap & seeding (Stadio 2) -----------------------------------------
B_BOOT = 10_000
SPILLOVER_MASTER_SEED = 20260622

# --- Molteplicità (Stadio 2) ------------------------------------------------
T_H1_ALPHA = 0.05                      # H1 primaria, senza correzione
BY_Q = 0.10
BY_SECONDARY_FAMILY = ("H2", "H3", "H4")
BY_M = 3                               # cardinalità FISSA a priori

# --- Sorgenti VIETATE come strumento ----------------------------------------
# Coerente col protocollo principale: ΔT5YIE / breakeven non vanno mai usati
# come strumento (sono componenti del bond → circolarità + mismatch frequenza).
FORBIDDEN_SOURCES = ("dT5YIE", "T5YIE", "breakeven", "dBreakeven", "T10YIE")


# --- Seeding riproducibile --------------------------------------------------

def _name_int(name: str) -> int:
    """Intero stabile da una stringa (blake2b — non l'hash salato di Python)."""
    return int.from_bytes(hashlib.blake2b(name.encode("utf-8"), digest_size=8).digest(), "big")


def make_rng(name: str) -> np.random.Generator:
    """RNG dichiarato per una specifica cifra/test.

    Seed = SeedSequence([SPILLOVER_MASTER_SEED, blake2b(name)]). Stessa stringa
    → stesso flusso in ogni processo; stringhe diverse → flussi indipendenti.
    """
    seq = np.random.SeedSequence([SPILLOVER_MASTER_SEED, _name_int(name)])
    return np.random.default_rng(seq)


def seed_for(name: str) -> int:
    """Intero di seed dichiarato (stesso schema di make_rng) per il manifest."""
    seq = np.random.SeedSequence([SPILLOVER_MASTER_SEED, _name_int(name)])
    return int(seq.generate_state(1)[0])


# --- Snapshot / hash per provenance -----------------------------------------

def config_snapshot() -> dict:
    return {
        "config_version": CONFIG_VERSION,
        "tau_pre_min": TAU_PRE_MIN,
        "tau_post_min": TAU_POST_MIN,
        "us_short_rate_basket": list(US_SHORT_RATE_BASKET),
        "sp500_instrument": SP500_INSTRUMENT,
        "eu_assets": dict(EU_ASSETS),
        "b_boot": B_BOOT,
        "spillover_master_seed": SPILLOVER_MASTER_SEED,
        "t_h1_alpha": T_H1_ALPHA,
        "by_q": BY_Q,
        "by_secondary_family": list(BY_SECONDARY_FAMILY),
        "by_m": BY_M,
        "forbidden_sources": list(FORBIDDEN_SOURCES),
    }


def config_hash() -> str:
    blob = json.dumps(config_snapshot(), sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
