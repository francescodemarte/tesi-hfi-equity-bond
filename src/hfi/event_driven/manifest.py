"""manifest.py — Provenance (pattern uniforme 07/08/11/12/13)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import config


_REPLICABILITY_NOTE = (
    "Pre-registrazione delle 4 strategie event-driven (spec congelata):\n"
    "1) β_str (CPI=+0.95, NFP=-1.40, FOMC=+0.87) presi dal RUN AUTORITATIVO\n"
    "   del pacchetto decomposition (12) sui dati reali — NON ottimizzati sui\n"
    "   rendimenti di strategia. Provenance: vedi nota 8 sotto.\n"
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
    "8) PROVENANCE β_str (refresh 2026-06-25): i valori in config.BETA_STR\n"
    "   (+0.95 CPI, -1.40 NFP, +0.87 FOMC, arrotondati a 2 decimali)\n"
    "   coincidono con beta_str_central del RUN AUTORITATIVO del pacchetto 12\n"
    "   (decomposition), eseguito il 2026-06-23T22:21:46Z sui dati reali.\n"
    "   Provenance: results/02_decomposition/baseline/decomp_canali.report.json,\n"
    "   campo table_section_6_per_cell[*].beta_str_central. Config hash 12\n"
    "   prefix: 907eb0ff. Valori esatti a 4 decimali:\n"
    "     NFP/neg  -1.4036  (sampling band 95% [-1.893, -0.888])\n"
    "     CPI/neg  +0.9509  (sampling band 95% [+0.514, +1.402])\n"
    "     FOMC/neg +0.8748  (sampling band 95% [+0.337, +1.425])\n"
    "     CPI/pos  +2.2404  (sampling band 95% [+1.602, +2.856])\n"
    "   DISTINZIONE da beta_H (Rigobon-Sack pacchetto 07, sui rendimenti\n"
    "   grezzi): beta_str (qui) e beta_H sono stimatori diversi su dati\n"
    "   diversi (netti vs grezzi del canale tasso). I valori del pacchetto 07\n"
    "   sono in results/01_protocol_v2/beta_H_robust_cells_w15.json:\n"
    "     beta_H = -0.808 (NFP), +1.163 (CPI/neg), +0.926 (FOMC/neg),\n"
    "              +1.899 (CPI/pos).\n"
    "9) Pesi inverse_vol_on_training: l'esecutore DEVE dichiarare lunghezza\n"
    "   del training set e σ_training per ciascuna strategia, altrimenti il\n"
    "   portafoglio appare arbitrario."
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
