"""manifest.py — Provenance (pattern uniforme 07/08/11/12/13)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import config


_REPLICABILITY_NOTE = (
    "Pre-registrazione delle 4 strategie event-driven (spec congelata):\n"
    "1) β_str (CPI=+0.95, NFP=-1.40, FOMC=+0.87) presi dalla stima strutturale\n"
    "   pre-esistente — NON ottimizzati sui rendimenti di strategia.\n"
    "2) Tutte le strategie attive SOLO in regime negativo (corr 63gg, lag t-1).\n"
    "3) Direzione momentum: equity nel verso della sorpresa, bond nel verso\n"
    "   coerente con sign(β_str). Sizing = |β_str|.\n"
    "4) Due orizzonti riportati ENTRAMBI: event_window (±15 min) + end_of_day.\n"
    "   Nessuna selezione del migliore.\n"
    "5) Sottocampione FOMC: ≤ 2024-01-31 (limite serie Jarociński-Karadi).\n"
    "6) Portafoglio: pesi pre-dichiarati (equal o inverse_vol_on_training);\n"
    "   schemi tipo 'maximize_sharpe' SOLLEVANO (anti-overfitting).\n"
    "7) Sharpe è LORDO di costi di transazione — l'inclusione di costi\n"
    "   (dipendente da assunzioni su liquidità/slippage) ridurrebbe le cifre.\n"
    "   Dichiarato esplicitamente nel capitolo.\n"
    "8) ⚠️ PROVENANCE β_str (REVIEW #1, BLOCKER risolto): i valori in\n"
    "   config.BETA_STR (+0.95 CPI, -1.40 NFP, +0.87 FOMC) sono\n"
    "   ILLUSTRATIVI / CONDIZIONALI. Origine immediata: prompt di pre-\n"
    "   registrazione 2026-06-23. Origine autoritativa: stima del 07_\n"
    "   protocollo_v2_signflip — NON ANCORA ESEGUITO sui dati reali.\n"
    "   Il +0.95 (CPI) compare in un appendix che la memoria utente segna\n"
    "   come results.md inventato (2026-05); i -1.40 (NFP) e +0.87 (FOMC)\n"
    "   non hanno riscontro in documenti del vault.\n"
    "   CONSEGUENZA INTERPRETATIVA: lo Sharpe di questo pacchetto va letto\n"
    "   come CONDIZIONALE: 'se il 07 confermerà β di questa magnitudine,\n"
    "   allora le strategie danno Sharpe X'. NON è performance di trading\n"
    "   su findings reali del 07.\n"
    "9) Pesi inverse_vol_on_training: l'esecutore DEVE dichiarare lunghezza\n"
    "   del training set e σ_training per ciascuna strategia, altrimenti il\n"
    "   portafoglio appare arbitrario (REVIEW #4)."
)


def _file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(*, run_output: dict, input_paths, code_paths,
                   seed_name: str, timestamp: str) -> dict:
    """`run_output`: dict di `run_strategies.run_all`. `timestamp`: ISO ESTERNO."""
    inputs = []
    for p in (input_paths or []):
        p = Path(p)
        inputs.append({"path": str(p),
                       "sha256": _file_sha256(p) if p.exists() else None,
                       "status": "ok" if p.exists() else "missing — non colmato"})
    code = []
    for p in (code_paths or []):
        p = Path(p)
        code.append({"path": str(p),
                     "sha256": _file_sha256(p) if p.exists() else None})

    # Sharpe per (strategia, orizzonte) e per il portafoglio
    sharpe_table = {}
    for s, st in run_output.get("per_strategy", {}).items():
        for h, m in st.get("metrics", {}).items():
            if h in ("event_window", "end_of_day"):
                sharpe_table[f"{s}/{h}"] = {"sharpe": m["sharpe"],
                                              "n": m["n"], "period": st["period"]}
    pm = run_output.get("portfolio", {})
    for h, m in pm.get("metrics", {}).items():
        if h in ("event_window", "end_of_day"):
            sharpe_table[f"PORTFOLIO/{h}"] = {"sharpe": m["sharpe"],
                                                "n": m["n"], "period": pm["period"]}

    return {
        "config_version": config.CONFIG_VERSION,
        "config_hash": config.config_hash(),
        "config_snapshot": config.config_snapshot(),
        "seed": {"name": seed_name, "value": config.seed_for(seed_name)},
        "inputs": inputs,
        "code": code,
        "sharpe_table": sharpe_table,
        "portfolio_weights": pm.get("weights", {}),
        "portfolio_scheme": pm.get("scheme"),
        "fomc_subsample_end": run_output.get("fomc_subsample_end"),
        "replicability_assumption": _REPLICABILITY_NOTE,
        "timestamp": timestamp,
    }


def write_manifest(path, manifest_dict: dict) -> str:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest_dict, indent=2, sort_keys=True, default=str).encode("utf-8")
    p.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()
