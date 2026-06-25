"""config.py — Parametri congelati del CANCELLO descrittivo per il canale tassi.

Cancello, non modulo: misura indipendenza fra dimensioni (tipo evento × regime ×
intensità-tasso). Non stima il canale. Seed dedicato per separazione provenance.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

CONFIG_VERSION = "rate-channel-gate-v1-2026-06-22"
MASTER_SEED = 20260622

# Finestra (stessa del protocollo v2 per equity/bond)
HALF_MIN_WINDOW = 15
MEDIAN_EDGE_MIN = 5

# Contratto tasso: dichiarato come parametro, default FFc2 (densità piena dal
# Fronte 1; FFc1 ha gaps di roll-over). FEIc1 alternativa per ECB se serve.
RATE_CONTRACT_DEFAULT = "FFc2"
RATE_CONTRACT_SUPPORTED = ("FFc2", "FFc3", "FEIc1", "FEIc2", "FEIc3", "FEIc4")

# Tipi evento (NFP/CPI/FOMC/ECB; ECB alimentabile solo via FEI o se FF copre)
EVENT_TYPES = ("NFP", "CPI", "FOMC", "ECB")

# Cancello (PARTE: criterio (c) — celle popolate sopra soglia)
MIN_CELL_EVENTS = 30

# Modalità di partizione dell'intensità-tasso
PARTITION_MODES = ("median", "tertile_extremes", "movement")
PARTITION_DEFAULT = "median"

# Soglia kappa per il verdetto (PARTE: "basso in valore assoluto" — soglia
# esplicita del ricercatore; default conservativo 0.20, modificabile via param).
KAPPA_LOW_THRESHOLD_DEFAULT = 0.20

# Soglia per "between piccolo" (varianza spiegata dal regime ≤ soglia)
ETA_SQUARED_LOW_THRESHOLD_DEFAULT = 0.20

# Soglia per "vettori distinti" (PARTE: criterio (d) — angolo ≥ threshold)
COSINE_HIGH_THRESHOLD_DEFAULT = 0.95   # |cos| > soglia ⇒ collineari

# ----- Estensione term-structure (Eurodollar FEIc1..c4) ---------------------
# Soglie CONGELATE per il PRIMO CANCELLO (degenerazione della pendenza):
#   (i)  PC2 spiega almeno questa frazione della varianza congiunta dei 4 Δ:
TS_PC2_VAR_EXPLAINED_MIN = 0.10
#   (ii) frazione di eventi con movimento non nullo sui CONTRATTI LUNGHI
#        (richiesto separatamente su c3 e su c4) sopra questa soglia:
TS_LONG_CONTRACT_MOVEMENT_MIN_FRAC = 0.30
#   (iii) la partizione mediana di |PC2| non deve essere degenere
#        (= entrambe le celle high/low devono esistere, soglia operativa = 1 evento).
# Contratti della struttura a termine (ordine fisso, breve→lungo):
TS_CONTRACTS = ("FEIc1", "FEIc2", "FEIc3", "FEIc4")
# Convenzioni di segno per togliere l'ambiguità: PC1 loading su c1 ≥ 0,
# PC2 loading su c4 (contratto lungo) ≥ 0. Standard, non discrezionale.
TS_PC1_SIGN_REF = "FEIc1"
TS_PC2_SIGN_REF = "FEIc4"


def make_rng(name: str) -> np.random.Generator:
    h = int.from_bytes(hashlib.blake2b(name.encode(), digest_size=8).digest(), "big")
    return np.random.default_rng(np.random.SeedSequence([MASTER_SEED, h]))


def config_snapshot() -> dict:
    return {
        "config_version": CONFIG_VERSION,
        "master_seed": MASTER_SEED,
        "half_min_window": HALF_MIN_WINDOW,
        "median_edge_min": MEDIAN_EDGE_MIN,
        "rate_contract_default": RATE_CONTRACT_DEFAULT,
        "event_types": list(EVENT_TYPES),
        "min_cell_events": MIN_CELL_EVENTS,
        "partition_default": PARTITION_DEFAULT,
        "kappa_low_threshold_default": KAPPA_LOW_THRESHOLD_DEFAULT,
        "eta_squared_low_threshold_default": ETA_SQUARED_LOW_THRESHOLD_DEFAULT,
        "cosine_high_threshold_default": COSINE_HIGH_THRESHOLD_DEFAULT,
        "ts_pc2_var_explained_min": TS_PC2_VAR_EXPLAINED_MIN,
        "ts_long_contract_movement_min_frac": TS_LONG_CONTRACT_MOVEMENT_MIN_FRAC,
        "ts_contracts": list(TS_CONTRACTS),
        "ts_pc1_sign_ref": TS_PC1_SIGN_REF,
        "ts_pc2_sign_ref": TS_PC2_SIGN_REF,
    }


def config_hash() -> str:
    return hashlib.sha256(json.dumps(config_snapshot(), sort_keys=True).encode()).hexdigest()
