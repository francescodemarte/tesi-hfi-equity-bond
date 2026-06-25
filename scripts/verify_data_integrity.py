"""verify_data_integrity.py — Verifica sha256 dei dati esterni e in-repo.

Confronta hash effettivi contro `data_manifest.json`. Output: report
per ciascun file (MATCH/MISMATCH/MISSING). Exit code 0 = OK, 1 = anomalia.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    manifest = json.loads((ROOT / "data_manifest.json").read_text())
    anomalies = 0
    print(f"=== Data Integrity Check ===")
    print(f"Repo root: {ROOT}\n")

    # Datasets in-repo
    print("[1/3] Datasets in-repo (DATASET_TESI, 09_risultati/*/result_authoritative.pkl):")
    for rel_path, spec in manifest.get("datasets_in_repo", {}).items():
        p = ROOT / rel_path
        expected = spec.get("sha256_expected")
        if not p.exists():
            print(f"  [MISSING] {rel_path}")
            anomalies += 1
            continue
        actual = sha256_file(p)
        if expected and actual != expected:
            print(f"  [MISMATCH] {rel_path}")
            print(f"      expected: {expected}")
            print(f"      actual:   {actual}")
            anomalies += 1
        else:
            print(f"  [OK] {rel_path}  ({actual[:16]}...)")

    # External public data
    print("\n[2/3] External public data (data/external_public/):")
    for fname, spec in manifest.get("data_external_public", {}).items():
        clean = fname.replace("fred_", "")
        p = ROOT / "data" / "external_public" / clean
        if not p.exists():
            print(f"  [NOT-DOWNLOADED] {clean}  (run bash scripts/setup_data.sh)")
            continue
        expected = spec.get("sha256_expected")
        actual = sha256_file(p)
        if expected:
            tag = "OK" if actual == expected else "MISMATCH"
            print(f"  [{tag}] {clean}  ({actual[:16]}...)")
            if tag == "MISMATCH":
                anomalies += 1
        else:
            print(f"  [PRESENT, no expected hash] {clean}  ({actual[:16]}...)")

    # Refinitiv proprietary
    print("\n[3/3] Refinitiv intraday data (data/intraday/) — proprietary, NOT in repo:")
    for fname, spec in manifest.get("data_processed_refinitiv_proprietary", {}).items():
        if fname.startswith("_"): continue
        p = ROOT / "data" / "intraday" / fname
        if not p.exists():
            print(f"  [ABSENT] {fname}  (expected via own Refinitiv/WRDS subscription)")
            continue
        expected = spec.get("sha256_expected")
        actual = sha256_file(p)
        if expected:
            tag = "OK" if actual == expected else "MISMATCH"
            print(f"  [{tag}] {fname}  ({actual[:16]}...)")
            if tag == "MISMATCH":
                anomalies += 1
        else:
            print(f"  [PRESENT, no expected hash] {fname}  ({actual[:16]}...)")

    print(f"\n=== Summary: anomalies = {anomalies} ===")
    return 1 if anomalies > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
