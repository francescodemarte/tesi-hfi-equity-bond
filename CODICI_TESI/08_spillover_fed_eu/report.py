"""report.py — Contratto di output del run + manifest finale.

Ogni numero porta agganciata la DOPPIA LETTURA esplicita (esistenza vs
attribuzione) come imposto dalla spec.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import config


_READING_EXISTENCE = (
    "Esistenza: γ̂ come effetto del Z^MP costruito; vale per "
    "precedenza temporale (verificabile dalla finestra W^US) e per "
    "no-confondente standard (assunto)."
)
_READING_ATTRIBUTION = (
    "Attribuzione a pura politica monetaria: condizionale alla "
    "separazione di segno (Ass. 2). Il claim di attribuzione è il "
    "test di canale H4; H1–H3 sono claim di esistenza."
)


def build_asset_row(asset: str, fit: dict, hypothesis_test: dict,
                    by_decision) -> dict:
    """Riga del report per un asset: coefficienti, SE, t, p, esito BY, due letture."""
    names = fit["names"]
    j_mp = names.index("Z_mp") if "Z_mp" in names else None
    j_cbi = names.index("Z_cbi") if "Z_cbi" in names else None
    return {
        "asset": asset,
        "hypothesis": hypothesis_test.get("hypothesis"),
        "gamma": float(fit["coef"][j_mp]) if j_mp is not None else None,
        "delta": float(fit["coef"][j_cbi]) if j_cbi is not None else None,
        "gamma_se": float(fit["se"][j_mp]) if j_mp is not None else None,
        "delta_se": float(fit["se"][j_cbi]) if j_cbi is not None else None,
        "t": hypothesis_test.get("t"),
        "p_one_sided": hypothesis_test.get("p_one_sided"),
        "side": hypothesis_test.get("side"),
        "by_decision": by_decision,
        "n": int(fit["n"]),
        "cov_type": fit["cov_type"],
        "reading_existence": _READING_EXISTENCE,
        "reading_attribution": _READING_ATTRIBUTION,
    }


def build_manifest(*, included_events: int, excluded_events: int,
                   seed_name: str, timestamp: str) -> dict:
    """Manifest finale: events conta, seed dichiarato, B, config_hash, version.

    `timestamp` è obbligatorio e PASSATO DALL'ESTERNO (no clock interno).
    """
    return {
        "config_version": config.CONFIG_VERSION,
        "config_hash": config.config_hash(),
        "b_boot": config.B_BOOT,
        "seed": {"name": seed_name, "value": config.seed_for(seed_name)},
        "n_events_included": int(included_events),
        "n_events_excluded": int(excluded_events),
        "timestamp": timestamp,
    }


def write_report(path, *, asset_rows, manifest: dict, timestamp: str) -> dict:
    """Scrive il report json (crea cartelle mancanti) e ritorna `{path, sha256}`."""
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"asset_rows": list(asset_rows), "manifest": manifest,
               "generated": timestamp}
    raw = json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8")
    p.write_bytes(raw)
    return {"path": str(p), "sha256": hashlib.sha256(raw).hexdigest()}
