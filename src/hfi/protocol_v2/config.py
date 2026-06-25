"""config.py — Parametri CONGELATI del protocollo v2 sign-flip.

Autorità: SPEC_codice_v2_signflip_2026-06-21.md (§5). I valori sono
**pre-registrati**: NON modificarli dopo il congelamento — ogni soglia scelta
dopo aver visto i risultati invaliderebbe la pre-registrazione.

Espone anche lo schema di seeding riproducibile (make_rng / seed_for) e lo
snapshot/hash della config per il manifest di provenienza (R4, C0.6).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

CONFIG_VERSION = "v2-signflip-2026-06-21"

# --- Path ---------------------------------------------------------------
ROOT = Path("/home/francesco/TESI/tesi-hfi-equity-bond")
DATA = ROOT / "DATASET_TESI"
BRIDGE_DATA = ROOT / "bridge" / "data"
INTRADAY_DIR = Path("/home/francesco/TESI/Dati/data_processed")
CALENDAR_DIR = Path("/home/francesco/TESI/Dati/calendari")
OUT_DIR = ROOT / "09_risultati" / "v2_signflip"

# --- Finestre (C0.1) ----------------------------------------------------
HALF_MIN_WINDOW = 15        # ±15 min → finestra 30 min
MEDIAN_EDGE_MIN = 5         # pre = mediana primi 5 min, post = mediana ultimi 5 min

# --- Controlli (C0.2) ---------------------------------------------------
K_CONTROL_TARGET = 5        # controlli desiderati per evento
K_CONTROL_MIN = 3           # se ne sopravvivono < 3 → estendi lookback
K_CONTROL_MAX = 10          # tetto controlli (vincolo di omogeneità di regime)
LOOKBACK_CAP_DAYS = 10      # lookback massimo (giorni di trading) — baseline
LOOKBACK_CAP_DAYS_SENS = 20  # sensibilità pre-dichiarata C0.2.4 (raddoppio, tetto 20)

# --- Campione (C0.5) ----------------------------------------------------
N_MIN = 30

# --- Strumento debole / MOP (R5) ---------------------------------------
MOP_K = 1                   # un solo strumento
MOP_WORST_CASE_SIZE = 0.10  # tolleranza size worst-case
MOP_NOMINAL_LEVEL = 0.05    # test nominale
# NB: cv_MOP è CALCOLATO in weakiv.py, non hard-coded.
# Mai il valore omoschedastico Stock–Yogo (16.38); ≈23 solo sanity, non firmato.

# --- Molteplicità gerarchica (R7) --------------------------------------
NFP_PRIMARY = "NFP"
NFP_ALPHA = 0.05            # NFP primario confermativo, NON corretto
BY_SECONDARY_FAMILY = ("CPI", "FOMC", "ECB")
BY_Q = 0.10
BY_M = 3                    # cardinalità FISSA a priori (i tre secondari = sempre tre)

# --- Bootstrap / seed (R4) ---------------------------------------------
B_BOOT = 10000
MASTER_SEED = 20260621

# --- Regime (C0.3) ------------------------------------------------------
REGIME_WINDOW_DAYS = 63          # 3m (baseline)
REGIME_WINDOW_DAYS_ROBUST = 126  # 6m (robustezza T8c)
REGIME_LAG_BDAYS = 1             # anti-look-ahead
REGIME_THRESHOLD = 0.0           # split sul SEGNO della correlazione

# --- E3: T7 regimi esogeni a ρ (CONGELATI) ------------------------------
# Criteri esogeni binari (alto/basso vs mediana rolling causale).
T7_EXOGENOUS_REQUIRED = ("T10Y2Y", "VIXCLS")   # obbligatori (FRED)
T7_EXOGENOUS_OPTIONAL = ("MOVE",)              # opzionale-se-disponibile
T7_ROLLING_DAYS = 252                          # finestra mediana causale (giorni lavorativi)
T7_LAG_BDAYS = 1                               # anti-look-ahead

# --- E3: T8(d) soglia inflazionistica (CONGELATA) -----------------------
# Ancora a priori: 2x target Fed (2%). YoY ricavato per via canonica dal livello.
T8D_CPI_YOY_THRESHOLD = 0.04
T8D_CPI_LEVEL_SERIES = "CPIAUCSL"   # FRED, livello CPI US (12m-pct-change → YoY)

# --- Griglia AR (R2) ----------------------------------------------------
AR_BETA_LOW = -3.0
AR_BETA_HIGH = 7.0
AR_STEP = 0.005
# Se l'insieme accettato tocca un estremo → aperto/illimitato, non troncato.

# --- Tipi evento e strumenti -------------------------------------------
EVENT_TYPES = ("FOMC", "CPI", "NFP", "ECB")
# (equity, bond) per tipo: US su ES/TY, EU su STXE/FGBL
INSTRUMENT_MAP = {
    "FOMC": ("ES", "TY"),
    "CPI": ("ES", "TY"),
    "NFP": ("ES", "TY"),
    "ECB": ("STXE", "FGBL"),
}
# Fuso di mercato per il matching DST-aware dei controlli (C0.2 / §13bis)
EVENT_TZ = {
    "FOMC": "America/New_York",
    "CPI": "America/New_York",
    "NFP": "America/New_York",
    "ECB": "Europe/Berlin",
}
# File intraday processati (simbolo → (nome_file, colonna_prezzo)) in INTRADAY_DIR
INTRADAY_FILES = {
    "ES": ("ESc1_1min.csv", "PX_LAST"),
    "TY": ("TYc1_1min.csv", "PX_LAST"),
    "FGBL": ("FGBLc1_1min.csv", "PX_LAST"),
    "STXE": ("STXE_continuous_1min.csv", "Mid_raw"),
    # Aggiunti 2026-06-23 per Bug 1 (netting simmetrico equity-side, pkg 12):
    # delta_f_curve_control = Δrate FFc1/2/3 sui control window dei cluster del 07,
    # con stessa convenzione mediana 5min pre/post del 07. Solo i symbol US
    # (per pacchetto 12 ramo US); per EU si aggiungerà FEIc1/2/3 quando servirà.
    "FFc1": ("FFc1_1min.csv", "PX_LAST"),
    "FFc2": ("FFc2_1min.csv", "PX_LAST"),
    "FFc3": ("FFc3_1min.csv", "PX_LAST"),
    # 2026-06-23 estensione curva: SOFR 3M (US) e Euribor 3M (EU) per portare
    # il bordo osservato da 3 a 5 trimestri (US: FF1-3 + SR1-2) e a 4 trimestri
    # (EU: FEI1-4). Riduce il bias del tail extrapolation in equity_pb/bond_pb.
    "SRc1": ("SRc1_1min.csv", "PX_LAST"),
    "SRc2": ("SRc2_1min.csv", "PX_LAST"),
    "FEIc1": ("FEIc1_1min.csv", "PX_LAST"),
    "FEIc2": ("FEIc2_1min.csv", "PX_LAST"),
    "FEIc3": ("FEIc3_1min.csv", "PX_LAST"),
    "FEIc4": ("FEIc4_1min.csv", "PX_LAST"),
}


# --- Seeding riproducibile (R4) ----------------------------------------

def _name_int(name: str) -> int:
    """Intero stabile da una stringa (blake2b — NON l'hash di Python, che è salato)."""
    return int.from_bytes(hashlib.blake2b(name.encode("utf-8"), digest_size=8).digest(), "big")


def make_rng(name: str) -> np.random.Generator:
    """RNG riproducibile e DICHIARATO per una data cifra/test.

    Seed derivato da MASTER_SEED + hash stabile del nome. Stessa stringa →
    stesso flusso in ogni processo; stringhe diverse → flussi indipendenti.
    """
    seq = np.random.SeedSequence([MASTER_SEED, _name_int(name)])
    return np.random.default_rng(seq)


def seed_for(name: str) -> int:
    """Intero di seed dichiarato (stesso schema di make_rng) per il manifest."""
    seq = np.random.SeedSequence([MASTER_SEED, _name_int(name)])
    return int(seq.generate_state(1)[0])


# --- Snapshot / hash della config per il manifest (C0.6) ---------------

def config_snapshot() -> dict:
    """Dizionario dei parametri congelati (entra nel manifest di provenienza)."""
    return {
        "config_version": CONFIG_VERSION,
        "half_min_window": HALF_MIN_WINDOW,
        "median_edge_min": MEDIAN_EDGE_MIN,
        "k_control_target": K_CONTROL_TARGET,
        "k_control_min": K_CONTROL_MIN,
        "k_control_max": K_CONTROL_MAX,
        "lookback_cap_days": LOOKBACK_CAP_DAYS,
        "lookback_cap_days_sens": LOOKBACK_CAP_DAYS_SENS,
        "n_min": N_MIN,
        "mop_k": MOP_K,
        "mop_worst_case_size": MOP_WORST_CASE_SIZE,
        "mop_nominal_level": MOP_NOMINAL_LEVEL,
        "nfp_primary": NFP_PRIMARY,
        "nfp_alpha": NFP_ALPHA,
        "by_secondary_family": list(BY_SECONDARY_FAMILY),
        "by_q": BY_Q,
        "by_m": BY_M,
        "b_boot": B_BOOT,
        "master_seed": MASTER_SEED,
        "regime_window_days": REGIME_WINDOW_DAYS,
        "regime_window_days_robust": REGIME_WINDOW_DAYS_ROBUST,
        "regime_lag_bdays": REGIME_LAG_BDAYS,
        "regime_threshold": REGIME_THRESHOLD,
        "ar_beta_low": AR_BETA_LOW,
        "ar_beta_high": AR_BETA_HIGH,
        "ar_step": AR_STEP,
        "event_types": list(EVENT_TYPES),
        # E3 — T7
        "t7_exogenous_required": list(T7_EXOGENOUS_REQUIRED),
        "t7_exogenous_optional": list(T7_EXOGENOUS_OPTIONAL),
        "t7_rolling_days": T7_ROLLING_DAYS,
        "t7_lag_bdays": T7_LAG_BDAYS,
        # E3 — T8(d)
        "t8d_cpi_yoy_threshold": T8D_CPI_YOY_THRESHOLD,
        "t8d_cpi_level_series": T8D_CPI_LEVEL_SERIES,
    }


def config_hash() -> str:
    """sha256 dello snapshot (chiavi ordinate) — impronta della config nel manifest."""
    blob = json.dumps(config_snapshot(), sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
