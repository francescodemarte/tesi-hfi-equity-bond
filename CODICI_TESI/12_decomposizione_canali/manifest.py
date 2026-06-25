"""manifest.py — Manifest di provenienza, pattern uniforme con 07/08/11.

L'esecutore aggrega gli output di `cell_pipeline.run_cell` per cella, poi
chiama `build_manifest(cell_outputs, input_paths, code_paths, seed_name,
timestamp)` per congelare la provenienza. Timestamp PASSATO DALL'ESTERNO
(no clock interno).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import config


_REPLICABILITY_ASSUMPTION = (
    "Assunti dichiarati della decomposizione in canali (chained):\n"
    "1) Log-linearizzazione di Campbell–Shiller per il prezzo dell'equity\n"
    "   (ΔP^B_e = −Σ ρ^(n−1)·Δf_n) — non esatta, approssima il valore attuale "
    "dei dividendi attesi.\n"
    "2) ρ_a calibrato esternamente come 1/(1+exp(dp_bar)), con dp_bar = media\n"
    "   di log(D/P) dell'indice azionario sul campione; banda di ρ (3 valori)\n"
    "   per propagare l'incertezza di stima del d/p medio.\n"
    "3) Coda della curva discreta dalla griglia {T0, TC, TD(λ=0.5), TD(λ=0.8)}\n"
    "   per scadenze n > m osservate. La banda di costruzione cattura la\n"
    "   sensibilità a questa scelta.\n"
    "4) Bond: ΔP^B_b = −D·Δy (cash-flow finiti, niente coda) — letto direttamente\n"
    "   dalla curva, asimmetrico vs l'equity per costruzione.\n"
    "5) Controlli con ΔP^B = 0 by construction (non hanno l'annuncio):\n"
    "   l'asimmetria è voluta — il bond NETTO di controllo resta col rumore\n"
    "   di tasso non legato all'annuncio, mentre l'evento è 'depurato'."
)


def _file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(*, cell_outputs: dict,
                   input_paths,
                   code_paths,
                   seed_name: str,
                   timestamp: str) -> dict:
    """Manifest per il run completo (tutte le celle).

    `cell_outputs`: dict {(leg, regime) -> dict ritornato da `cell_pipeline.run_cell`}.
    `input_paths`: lista di path dei dati congelati (curve, eventi, controls).
    `code_paths`: lista di path dei moduli pacchetto (hash del codice eseguito).
    `seed_name`: chiave logica del seed; `seed.value` derivato via config.seed_for.
    `timestamp`: ISO PASSATO DALL'ESTERNO (no clock interno).
    """
    inputs = []
    for p in (input_paths or []):
        p = Path(p)
        inputs.append({
            "path": str(p),
            "sha256": _file_sha256(p) if p.exists() else None,
            "status": "ok" if p.exists() else "missing — non colmato",
        })
    code = []
    for p in (code_paths or []):
        p = Path(p)
        code.append({"path": str(p),
                     "sha256": _file_sha256(p) if p.exists() else None})

    cell_counts = {f"{leg}/{reg}": int(o.get("n", 0))
                   for (leg, reg), o in cell_outputs.items()}
    verdicts = {f"{leg}/{reg}": o.get("verdict")
                for (leg, reg), o in cell_outputs.items()}
    gate_a_per_cell = {f"{leg}/{reg}": o.get("gate_a")
                       for (leg, reg), o in cell_outputs.items()}

    return {
        "config_version": config.CONFIG_VERSION,
        "config_hash": config.config_hash(),
        "config_snapshot": config.config_snapshot(),
        "seed": {"name": seed_name, "value": config.seed_for(seed_name)},
        "inputs": inputs,
        "code": code,
        "cell_counts": cell_counts,
        "verdicts_per_cell": verdicts,
        "gate_a_per_cell": gate_a_per_cell,
        "replicability_assumption": _REPLICABILITY_ASSUMPTION,
        "timestamp": timestamp,
    }


def write_manifest(path, manifest_dict: dict) -> str:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest_dict, indent=2, sort_keys=True, default=str).encode("utf-8")
    p.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()
