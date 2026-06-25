"""manifest.py — Manifest di provenienza del run pratico.

Per ogni run l'esecutore deve scrivere il manifest: hash input, parametri
congelati, seed, conteggi per cella, ASSUNZIONE DI REPLICABILITÀ dichiarata,
timestamp esterno, hash codice. Timestamp passato dall'esterno (no clock interno).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import config


_REPLICABILITY_NOTE = (
    "Assunzione di replicabilità (covariance-swap-like): il payoff di una "
    "posizione long sulla covarianza realizzata equity-bond su un evento è "
    "la covarianza realizzata stessa. La replicazione esatta richiederebbe "
    "un portafoglio dinamico di opzioni (fuori scope). I risultati sono "
    "payoff teorico LORDO, non Sharpe eseguibile."
)


def _sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(*, run_output: dict,
                   input_paths,
                   code_paths,
                   seed_name: str,
                   timestamp: str) -> dict:
    """Manifest da serializzare a fine run.

    `timestamp` ISO PASSATO DALL'ESTERNO (no clock interno).
    `run_output` = dict ritornato da `run.run_strategy`.
    """
    inputs = []
    for p in input_paths:
        p = Path(p)
        inputs.append({"path": str(p),
                       "sha256": _sha256_file(p) if p.exists() else None,
                       "status": "ok" if p.exists() else "missing — non colmato"})
    code = []
    for p in code_paths:
        p = Path(p)
        code.append({"path": str(p),
                     "sha256": _sha256_file(p) if p.exists() else None})
    # Conteggi per cella (gamba × regime × periodo)
    cell_counts = {}
    for period_key, period in (("training", run_output.get("training_metrics", {})),
                                ("test", run_output.get("test_metrics", {}))):
        for k, v in period.items():
            if isinstance(k, tuple) and len(k) == 2:
                cell_counts[f"{period_key}/{k[0]}/{k[1]}"] = int(v.get("n", 0))
    return {
        "config_version": config.CONFIG_VERSION,
        "config_hash": config.config_hash(),
        "config_snapshot": config.config_snapshot(),
        "split_date": run_output.get("split_date"),
        "n_train": run_output.get("n_train"),
        "n_test": run_output.get("n_test"),
        "cell_counts": cell_counts,
        "calibration_e_gk": {f"{k[0]}/{k[1]}": float(v)
                              for k, v in run_output.get("calibration", {}).get("e_gk", {}).items()},
        "seed": {"name": seed_name, "value": config.seed_for(seed_name)},
        "inputs": inputs,
        "code": code,
        "replicability_assumption": _REPLICABILITY_NOTE,
        "timestamp": timestamp,
    }


def write_manifest(path, manifest: dict) -> str:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2, sort_keys=True, default=str).encode("utf-8")
    p.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()
