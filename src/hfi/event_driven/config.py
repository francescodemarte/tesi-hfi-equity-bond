"""config.py — Parametri congelati delle 4 strategie event-driven (spec).

PRE-REGISTRATO. Tutti i numeri vengono dalla spec, non dai dati.
NESSUN parametro è ottimizzato sui rendimenti. Cambiarne uno cambia il
config_hash ⇒ tracciabile.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

CONFIG_VERSION = "strategie-event-driven-v1-2026-06-23"
MASTER_SEED = 20260621

# Strategie e regime ammesso (tutte negativo, spec)
STRATEGIES = ("CPI", "NFP", "FOMC")
ACTIVE_REGIME = {"CPI": "neg", "NFP": "neg", "FOMC": "neg"}

# β_str dalla stima strutturale (spec, non dai dati di strategia)
BETA_STR = {"CPI": +0.95, "NFP": -1.40, "FOMC": +0.87}

# Provenance dichiarata di BETA_STR — REFRESH 2026-06-25.
#
# RIPARAZIONE CRITICA: la versione precedente di questo blocco diceva che i
# valori sopra fossero "illustrativi pending 07 estimation". Quel commento era
# OBSOLETO: il pacchetto 12 (decomposition) era già stato eseguito sui dati
# reali, e i valori +0.95 / -1.40 / +0.87 corrispondono al run autoritativo.
#
# I valori sopra (arrotondati a 2 decimali) coincidono con beta_str_central del
# RUN AUTORITATIVO del pacchetto 12, eseguito sui dati reali il 2026-06-23.
# Provenance verificabile in:
#   - results/02_decomposition/baseline/decomp_canali.report.json
#     (campo table_section_6_per_cell[*].beta_str_central)
#   - results/02_decomposition/baseline/decomp_canali.manifest.json
#     (config_hash 12: 907eb0ff..., seed_name: decomp_canali_2026-06-23,
#      timestamp 2026-06-23T22:21:46Z)
#
# Valori effettivi a 4 decimali (per la stesura della tesi usare questi):
#   NFP/neg  beta_str_central = -1.4036  (sampling band 95% [-1.893, -0.888])
#   CPI/neg  beta_str_central = +0.9509  (sampling band 95% [+0.514, +1.402])
#   FOMC/neg beta_str_central = +0.8748  (sampling band 95% [+0.337, +1.425])
#   CPI/pos  beta_str_central = +2.2404  (sampling band 95% [+1.602, +2.856])
#
# DISTINZIONE IMPORTANTE — beta_str vs beta_H:
#   - beta_str (questo file, pacchetto 12): stima STRUTTURALE sui rendimenti
#     NETTI dal canale tasso (post-decomposizione equity_pb / bond_pb).
#     I numeri del config sono questi.
#   - beta_H (pacchetto 07, Rigobon-Sack): stima sui rendimenti GREZZI
#     (comovimento totale, prima della decomposizione canale tasso).
#     File results/01_protocol_v2/beta_H_robust_cells_w15.json:
#       beta_H = -0.808 (NFP), +1.163 (CPI/neg), +0.926 (FOMC/neg), +1.899 (CPI/pos)
#
# La tesi riporta beta_str (finding strutturale-identificativo) e dichiara
# nel testo la differenza con beta_H (finding di comovimento totale).
BETA_STR_PROVENANCE = {
    "status": "from_authoritative_12_run",
    "source_authoritative": "results/02_decomposition/baseline/decomp_canali.report.json",
    "source_run_timestamp": "2026-06-23T22:21:46Z",
    "source_seed_name": "decomp_canali_2026-06-23",
    "source_config_hash_12_prefix": "907eb0ff",
    "window_half_min": 15,
    "bond_proxy": "delta_rate_3 (front money-market FFc3 for US legs, FEIc3 for ECB)",
    "values_exact_4dec": {
        "NFP/neg": -1.4036,
        "CPI/neg": +0.9509,
        "FOMC/neg": +0.8748,
        "CPI/pos": +2.2404,
    },
    "rounding_note": (
        "I valori +0.95 / -1.40 / +0.87 in BETA_STR sopra (2 decimali) "
        "coincidono con beta_str_central del run autoritativo del 12 entro "
        "errore di arrotondamento. Per il testo della tesi usare i valori a "
        "4 decimali sopra (chiave values_exact_4dec)."
    ),
    "distinction_from_beta_H": (
        "beta_str (questo file): stimatore strutturale sui rendimenti NETTI "
        "dal canale tasso (pacchetto 12). "
        "beta_H (Rigobon-Sack, pacchetto 07): stimatore sui rendimenti "
        "GREZZI, comovimento totale. I due valori sono diversi per "
        "costruzione e misurano cose diverse. Vedi "
        "results/01_protocol_v2/beta_H_robust_cells_w15.json per beta_H."
    ),
    "fix_history": (
        "Versione precedente di questo blocco (2026-06-23) diceva "
        "'illustrative_pending_07_estimation'. Quel commento era stato "
        "scritto PRIMA del run autoritativo del 12 (stesso giorno, ore 22:21) "
        "e non era stato aggiornato. Il referee lo ha letto come dichiarazione "
        "di numeri inventati: errore di refresh, non sostanziale. Refresh "
        "applicato il 2026-06-25 a chiusura sessione di scrittura tesi."
    ),
}

# Orizzonti — ENTRAMBI obbligatori, nessuna selezione (spec)
HORIZONS = ("event_window", "end_of_day")
EVENT_WINDOW_MIN = 15

# Regime classifier (anti-look-ahead, protocollo)
REGIME_WINDOW_DAYS = 63
REGIME_LAG_BDAYS = 1

# Sottocampione FOMC (limite serie Jarociński-Karadi, spec)
FOMC_SUBSAMPLE_END = pd.Timestamp("2024-01-31")

# Portafoglio: 2 schemi PRE-REGISTRATI, mai post-hoc
PORTFOLIO_WEIGHT_SCHEMES = ("equal", "inverse_vol_on_training")
PORTFOLIO_WEIGHT_DEFAULT = "equal"

# Costi di transazione: NON inclusi (Sharpe è LORDO, dichiarato in tesi).
INCLUDE_TRANSACTION_COSTS = False


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
        "strategies": list(STRATEGIES),
        "active_regime": dict(ACTIVE_REGIME),
        "beta_str": dict(BETA_STR),
        "beta_str_provenance": dict(BETA_STR_PROVENANCE),
        "horizons": list(HORIZONS),
        "event_window_min": EVENT_WINDOW_MIN,
        "regime_window_days": REGIME_WINDOW_DAYS,
        "regime_lag_bdays": REGIME_LAG_BDAYS,
        "fomc_subsample_end": str(FOMC_SUBSAMPLE_END.date()),
        "portfolio_weight_default": PORTFOLIO_WEIGHT_DEFAULT,
        "portfolio_weight_schemes": list(PORTFOLIO_WEIGHT_SCHEMES),
        "include_transaction_costs": INCLUDE_TRANSACTION_COSTS,
    }


def config_hash() -> str:
    return hashlib.sha256(json.dumps(config_snapshot(), sort_keys=True).encode()).hexdigest()
