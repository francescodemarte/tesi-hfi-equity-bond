"""config.py — Parametri congelati della strategia "eccesso di comovimento".

Spec: capitolo operativo NFP+CPI condizionato al regime, no spillover.
- Calibrazione su training 2010-2020.
- Congelamento + UNA SOLA OCCHIATA al test 2021-2025.
- Anti-fabbricazione: tutti i numeri da `config_snapshot()` entrano nel manifest.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

CONFIG_VERSION = "pratica-eccesso-comov-v1-2026-06-22"
MASTER_SEED = 20260622

# Gambe (no spillover, dichiarato fuori scope dalla spec)
LEGS = ("NFP", "CPI")

# Finestre disgiunte (presidio anti-look-ahead intra-evento)
REGIME_WINDOW_DAYS = 63        # finestra mobile per la corr equity-bond
REGIME_END_OFFSET_DAYS = 4     # regime calcolato fino a t-4 (ancora la spec)
EXPECTATION_WINDOW = (-3, -1)  # t-3..t-1 inclusi per a_i, σ²_pre,i

# Split temporale (presidio anti-look-ahead inter-temporale)
TRAINING_START = pd.Timestamp("2010-01-01")
SPLIT_DATE = pd.Timestamp("2021-01-01")
TEST_END = pd.Timestamp("2025-12-31")

# Pesatura inverse-vol fra le due gambe
INV_VOL_ROLLING_EVENTS = 20    # finestra rolling sull'eccesso ε (eventi passati)

# Soglie regola di posizione
MIN_ABS_E_FOR_POSITION = 0.0   # default: nessuna soglia (posizione = sign)

# Verdetto su celle a basso n
MIN_CELL_N_FOR_VERDICT = 20    # sotto questa soglia, dichiarare "inconcludente"


def _name_int(name: str) -> int:
    return int.from_bytes(hashlib.blake2b(name.encode(), digest_size=8).digest(), "big")


def make_rng(name: str) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([MASTER_SEED, _name_int(name)]))


def seed_for(name: str) -> int:
    """Intero di seed DICHIARATO per il manifest (REVIEW #2).

    Stesso schema di make_rng, ma estrae un intero stabile da scrivere nel
    manifest: due esecutori con stesso `name` possono VERIFICARE di aver
    usato lo stesso seed effettivo, non solo lo stesso nome.
    """
    seq = np.random.SeedSequence([MASTER_SEED, _name_int(name)])
    return int(seq.generate_state(1)[0])


def config_snapshot() -> dict:
    return {
        "config_version": CONFIG_VERSION,
        "master_seed": MASTER_SEED,
        "legs": list(LEGS),
        "regime_window_days": REGIME_WINDOW_DAYS,
        "regime_end_offset_days": REGIME_END_OFFSET_DAYS,
        "expectation_window": list(EXPECTATION_WINDOW),
        "training_start": str(TRAINING_START.date()),
        "split_date": str(SPLIT_DATE.date()),
        "test_end": str(TEST_END.date()),
        "inv_vol_rolling_events": INV_VOL_ROLLING_EVENTS,
        "min_abs_e_for_position": MIN_ABS_E_FOR_POSITION,
        "min_cell_n_for_verdict": MIN_CELL_N_FOR_VERDICT,
    }


def config_hash() -> str:
    return hashlib.sha256(json.dumps(config_snapshot(), sort_keys=True).encode()).hexdigest()
