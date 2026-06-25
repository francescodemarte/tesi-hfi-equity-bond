"""manifest.py — Provenance del run (pattern uniforme 07/08/11/12)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import config


_REPLICABILITY_ASSUMPTION = (
    "Assunti del test del residuo:\n"
    "1) Le 4 celle robuste sono FISSATE a priori (spec §1): {FOMC/neg, NFP/neg,\n"
    "   CPI/neg, CPI/pos}. Su celle non robuste il residuo è contaminato dall'\n"
    "   errore di stima di β_str e NON è diagnostico.\n"
    "2) I 3 candidati (L, V, C) sono fissati a priori con meccanismo e segno\n"
    "   atteso CONGELATI. Nessuna sostituzione di proxy post-hoc.\n"
    "3) Ortogonalizzazione ΔZ_perp alla sorpresa (e tasso) PRIMA del test: un\n"
    "   carico genuino del terzo canale non deve essere residuo dei primi due.\n"
    "4) Comunalità: λ_e e λ_b entrambi significativi POST-BY (q=0.10, c(m)).\n"
    "5) Segno atteso (§3): L concorde, V entrambi negativi, C ambiguo.\n"
    "6) Soglie sensibilità gate_a (§7) CALCOLATE alla fonte via MOP-Patnaik\n"
    "   K=1 (scipy.stats.ncx2), non a memoria. Servono solo a dichiarare la\n"
    "   robustezza, NON a sostituire il criterio pre-registrato.\n"
    "7) PATOLOGIA SPEC §2/§3 (vedi residual.py docstring): coef(ũ_b,Z) =\n"
    "   −coef(ũ_e,Z)/β per costruzione. CONSEGUENZA INTERPRETATIVA: L e V\n"
    "   sono INASCOLTABILI sui dati reali finché la spec non è risolta —\n"
    "   un verdetto 'L third_channel=False ovunque' NON è evidenza empirica\n"
    "   di non-canale, è l'algebra della spec a renderlo impossibile.\n"
    "   Solo C (ambiguous) può tecnicamente passare, con valore informativo\n"
    "   nullo (sign rule banalmente True). Risoluzione = del ricercatore."
)


def _file_sha256(path) -> str:
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
    """Manifest del run completo.

    `run_output`: dict di `pipeline.run_full_protocol`.
    `timestamp`: ISO PASSATO DALL'ESTERNO (no clock interno).
    """
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

    # Dichiariamo nei manifest i verdetti per (cell, candidate)
    third_channel_findings = {}
    for (cell, cand), v in run_output.get("verdicts", {}).items():
        third_channel_findings[f"{cell[0]}/{cell[1]}/{cand}"] = {
            "third_channel": v["third_channel"],
            "passed_by": v["passed_by"],
            "commonality": v["commonality"],
            "sign_ok": v["sign_ok"],
            "lambda_e": v["lambda_e"],
            "lambda_b": v["lambda_b"],
            "p_commonality": v["p_commonality"],
        }

    return {
        "config_version": config.CONFIG_VERSION,
        "config_hash": config.config_hash(),
        "config_snapshot": config.config_snapshot(),
        "seed": {"name": seed_name, "value": config.seed_for(seed_name)},
        "inputs": inputs,
        "code": code,
        "by": run_output.get("by", {}),
        "third_channel_findings": third_channel_findings,
        "replicability_assumption": _REPLICABILITY_ASSUMPTION,
        "timestamp": timestamp,
    }


def write_manifest(path, manifest_dict: dict) -> str:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest_dict, indent=2, sort_keys=True, default=str).encode("utf-8")
    p.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()
