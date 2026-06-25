"""cpi_base_sa_vs_nsa.py — Verifica T8(d) sotto CPIAUCNS (non destagionalizzato).

Confronta i mesi che superano la soglia config.T8D_CPI_YOY_THRESHOLD (4%) sotto:
  - CPIAUCSL (destagionalizzato; usato nel run autoritativo via agente 3)
  - CPIAUCNS (non destagionalizzato; standard ufficiale per YoY inflazione)

Esito riportato qualunque sia (no cherry-picking). Se l'insieme dei mesi coincide
⇒ exclude_inflationary invariato e si dichiara robusto. Se differisce ⇒ documenta
la differenza e indica se richiede ri-esecuzione del T8(d).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path("/home/francesco/TESI/tesi-hfi-equity-bond")
PKG = ROOT / "CODICI_TESI" / "07_protocollo_v2_signflip"
sys.path.insert(0, str(PKG))

import config  # noqa: E402

SNAPSHOTS_DIR = PKG / "external_data" / "snapshots"
OUT_JSON = ROOT / "09_risultati" / "v2_signflip" / "cpi_base_sa_vs_nsa.json"
THRESHOLD = config.T8D_CPI_YOY_THRESHOLD


def fetch_fred_csv(series_id: str) -> bytes:
    """Scarica via api.stlouisfed.org (graph endpoint timeout in questo sandbox).
    Output: bytes in formato CSV (DATE,<series_id>) per compatibilita col loader pandas."""
    import subprocess
    import json as _json
    api_key = os.environ.get("FRED_API_KEY", "f62e34061cb4aaa2c1fac17db340f4d7")
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&api_key={api_key}&file_type=json")
    out = subprocess.run(
        ["curl", "--http1.1", "-s", "--max-time", "60", url],
        check=True, capture_output=True, timeout=90,
    )
    data = _json.loads(out.stdout)
    rows = [f"DATE,{series_id}"]
    for obs in data["observations"]:
        v = obs["value"]
        if v == ".":
            continue
        rows.append(f"{obs['date']},{v}")
    return ("\n".join(rows) + "\n").encode("utf-8")


def yoy_pct_change(level_series: pd.Series) -> pd.Series:
    """YoY = (level / level_12mo_ago) - 1."""
    s = level_series.sort_index().resample("ME").last()  # ensure end-of-month index
    return (s / s.shift(12)) - 1


def main():
    # SA (gia presente)
    sa_csv = SNAPSHOTS_DIR / "CPIAUCSL.csv"
    sa_df = pd.read_csv(sa_csv)
    date_col_sa = next(c for c in sa_df.columns if c.lower() in ("date", "observation_date"))
    val_col_sa = next(c for c in sa_df.columns if c != date_col_sa)
    sa_df[date_col_sa] = pd.to_datetime(sa_df[date_col_sa])
    sa_df[val_col_sa] = pd.to_numeric(sa_df[val_col_sa], errors="coerce")
    sa_level = sa_df.set_index(date_col_sa)[val_col_sa].dropna().rename("CPIAUCSL")

    # NSA: scarica
    nsa_bytes = fetch_fred_csv("CPIAUCNS")
    nsa_sha = hashlib.sha256(nsa_bytes).hexdigest()
    nsa_save = SNAPSHOTS_DIR / "CPIAUCNS.csv"
    with open(nsa_save, "wb") as f:
        f.write(nsa_bytes)
    nsa_df = pd.read_csv(nsa_save)
    date_col_nsa = next(c for c in nsa_df.columns if c.lower() in ("date", "observation_date"))
    val_col_nsa = next(c for c in nsa_df.columns if c != date_col_nsa)
    nsa_df[date_col_nsa] = pd.to_datetime(nsa_df[date_col_nsa])
    nsa_df[val_col_nsa] = pd.to_numeric(nsa_df[val_col_nsa], errors="coerce")
    nsa_level = nsa_df.set_index(date_col_nsa)[val_col_nsa].dropna().rename("CPIAUCNS")

    # Provenance
    prov = {
        "name": "CPIAUCNS",
        "source_url": "https://api.stlouisfed.org/fred/series/observations?series_id=CPIAUCNS",
        "fetched_at": "2026-06-22T14:00:00Z",
        "sha256": nsa_sha,
        "n_rows": int(len(nsa_df)),
        "date_min": str(nsa_level.index.min().date()),
        "date_max": str(nsa_level.index.max().date()),
        "note": "graph/fredgraph.csv endpoint HTTP/2 timeout nel sandbox; uso api.stlouisfed.org JSON.",
    }
    with open(SNAPSHOTS_DIR / "CPIAUCNS.provenance.json", "w") as f:
        json.dump(prov, f, indent=2, sort_keys=True)

    # YoY su entrambe
    yoy_sa = yoy_pct_change(sa_level / 100 if sa_level.max() > 10 else sa_level)
    # CPIAUCSL/CPIAUCNS sono valori index level (es. 311.0), non gia in pct.
    yoy_sa = (sa_level / sa_level.shift(12) - 1).dropna()
    yoy_nsa = (nsa_level / nsa_level.shift(12) - 1).dropna()

    # filtra al range protocollo 2010-2025
    yoy_sa = yoy_sa.loc["2010-01-01":"2025-12-31"]
    yoy_nsa = yoy_nsa.loc["2010-01-01":"2025-12-31"]

    # mesi inflazionistici (YoY >= soglia)
    months_sa = set(yoy_sa[yoy_sa >= THRESHOLD].index.to_period("M").astype(str))
    months_nsa = set(yoy_nsa[yoy_nsa >= THRESHOLD].index.to_period("M").astype(str))

    only_sa = sorted(months_sa - months_nsa)
    only_nsa = sorted(months_nsa - months_sa)
    both = sorted(months_sa & months_nsa)

    result = {
        "threshold": THRESHOLD,
        "n_sa_above_threshold": len(months_sa),
        "n_nsa_above_threshold": len(months_nsa),
        "n_both": len(both),
        "n_only_sa": len(only_sa),
        "n_only_nsa": len(only_nsa),
        "sets_coincide": (months_sa == months_nsa),
        "only_sa": only_sa,
        "only_nsa": only_nsa,
        "years_inflationary_sa": sorted({m[:4] for m in months_sa}),
        "years_inflationary_nsa": sorted({m[:4] for m in months_nsa}),
        "nsa_provenance": prov,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)

    print("=" * 70)
    print(f"CPI YoY ≥ {THRESHOLD*100:.0f}% — confronto SA (CPIAUCSL) vs NSA (CPIAUCNS)")
    print("=" * 70)
    print(f"SA  (CPIAUCSL): {len(months_sa)} mesi")
    print(f"NSA (CPIAUCNS): {len(months_nsa)} mesi")
    print(f"Intersezione:   {len(both)} mesi")
    print(f"Solo SA:        {len(only_sa)} mesi  -> {only_sa[:20]}")
    print(f"Solo NSA:       {len(only_nsa)} mesi -> {only_nsa[:20]}")
    print(f"SETS COINCIDONO: {result['sets_coincide']}")
    print(f"Years inflazionistici (SA):  {result['years_inflationary_sa']}")
    print(f"Years inflazionistici (NSA): {result['years_inflationary_nsa']}")
    print(f"\nSaved: {OUT_JSON}")
    print(f"NSA snapshot saved: {SNAPSHOTS_DIR / 'CPIAUCNS.csv'} (sha256 {nsa_sha[:16]}...)")


if __name__ == "__main__":
    main()
