"""provenance.py — Manifest di provenienza (C0.6, R4).

Ogni cifra/tabella prodotta ↔ script (path+hash) + input (path+hash) +
seed dichiarato + impronta della config + timestamp. Disciplina:
- il timestamp è **passato dall'esterno** (nessun clock interno: la
  riproducibilità non deve dipendere dall'ora di esecuzione);
- il seed è **dichiarato** via lo stesso schema di config.seed_for;
- gli hash sono sha256 del contenuto, deterministici.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping

import config


def file_sha256(path) -> str:
    """sha256 del contenuto di un file (letto a blocchi)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def text_sha256(s: str) -> str:
    """sha256 di una stringa utf-8."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def make_entry(*, figure: str, script, inputs: Iterable, seed_name: str,
               timestamp: str) -> dict:
    """Costruisce una voce di manifest per una cifra/tabella.

    figure    : nome della cifra/tabella.
    script    : path dello script che la produce (registra path + sha256).
    inputs    : iterable di path di input (path + sha256 ciascuno).
    seed_name : nome logico del seed (l'intero risolto da config entra nel manifest).
    timestamp : stringa (ISO) passata dall'esterno.
    """
    return {
        "figure": figure,
        "script": {"path": str(script), "sha256": file_sha256(script)},
        "inputs": [{"path": str(p), "sha256": file_sha256(p)} for p in inputs],
        "seed": {"name": seed_name, "value": config.seed_for(seed_name)},
        "config_version": config.CONFIG_VERSION,
        "config_hash": config.config_hash(),
        "timestamp": timestamp,
    }


def control_accounting_record(event_id: str, assembled: Mapping) -> dict:
    """Riassunto di provenienza per i controlli di un evento (verify-2).

    Dice come la cella è arrivata al suo numero di controlli: quanti tenuti e
    quali candidati scartati con la ragione ('calendar' | 'no_data_eq' |
    'no_data_bond'). I center sono serializzati come stringhe (json-safe).
    """
    return {
        "event": event_id,
        "n_controls": assembled["n_controls"],
        "dropped": [{"center": str(d["center"]), "reason": d["reason"]}
                    for d in assembled["dropped"]],
    }


def write_manifest(path, entries: Iterable[Mapping], *, timestamp: str,
                   diagnostics: Mapping | None = None) -> dict:
    """Scrive il manifest json (creando le cartelle mancanti) e lo restituisce.

    `diagnostics` (opzionale) ospita la diagnostica di provenienza, es.
    {'control_accounting': [...]} con un record per evento.
    """
    manifest = {
        "config_version": config.CONFIG_VERSION,
        "config_hash": config.config_hash(),
        "generated": timestamp,
        "entries": list(entries),
    }
    if diagnostics is not None:
        manifest["diagnostics"] = dict(diagnostics)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    return manifest
