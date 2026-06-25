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

# Provenance dichiarata di BETA_STR (REVIEW #1 — BLOCKER risolto).
# Status: i tre valori sopra sono ILLUSTRATIVI / CONDIZIONALI in attesa
# dell'esecuzione reale del pacchetto 07_protocollo_v2_signflip sui dati.
# Origine immediata: prompt di pre-registrazione delle strategie del 2026-06-23.
# Non sono ancora stime confermate dal 07 (che NON è stato eseguito sui reali
# per ordine della catena di custodia). Il +0.95 di CPI compare in un
# appendix che la memoria utente segna come results.md inventato (2026-05).
# I −1.40 (NFP) e +0.87 (FOMC) non hanno riscontro nei documenti del vault.
#
# CONSEGUENZA: i risultati del pacchetto 14 vanno letti come CONDIZIONALI:
# "se il 07 confermerà β di questa magnitudine, allora il portafoglio dà
# Sharpe X". NON sono "performance di trading su findings reali del 07".
# L'esecutore deve riportare lo Sharpe insieme alla dichiarazione di
# provenance dei β (vedi manifest.replicability_assumption punto 8).
BETA_STR_PROVENANCE = {
    "status": "illustrative_pending_07_estimation",
    "source_immediate": "prompt strategie event-driven 2026-06-23",
    "source_authoritative": "07_protocollo_v2_signflip — NON ANCORA ESEGUITO sui dati reali",
    "disclaimer": ("I β_str di config sono valori di pre-registrazione "
                   "delle strategie, non stime confermate. Risultati di "
                   "questo pacchetto sono CONDIZIONALI alla conferma di "
                   "questi β nella stima strutturale futura."),
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
