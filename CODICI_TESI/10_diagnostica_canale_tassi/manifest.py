"""manifest.py — Manifest di provenienza del cancello descrittivo.

Per ogni run del cancello: contratto tasso usato, finestra, seed, hash di
config, timestamp (esterno), hash degli input.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

import config


def _file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_gate_manifest(*, rate_contract: str, window_half_min: int,
                       partition_mode: str, min_cell: int,
                       seed_name: str, timestamp: str,
                       input_paths: Iterable | None = None,
                       thresholds: dict | None = None) -> dict:
    """Manifest del cancello. `timestamp` ISO è PASSATO DALL'ESTERNO."""
    inputs = []
    for p in (input_paths or []):
        p = Path(p)
        if p.exists():
            inputs.append({"path": str(p), "sha256": _file_sha256(p)})
        else:
            inputs.append({"path": str(p), "sha256": None,
                            "status": "missing — non colmato"})
    return {
        "config_version": config.CONFIG_VERSION,
        "config_hash": config.config_hash(),
        "rate_contract": rate_contract,
        "window_half_min": window_half_min,
        "partition_mode": partition_mode,
        "min_cell": min_cell,
        "thresholds": thresholds or {},
        "seed": {"name": seed_name},
        "inputs": inputs,
        "timestamp": timestamp,
    }


def write_manifest(path, manifest: dict) -> str:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2, sort_keys=True, default=str).encode("utf-8")
    p.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()
