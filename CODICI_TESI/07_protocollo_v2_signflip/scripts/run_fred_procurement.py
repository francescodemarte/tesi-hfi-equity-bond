"""Script di procurement FRED (autorizzato): scarica E3 + calendario US lato FRED
e congela in external_data/snapshots/. NON esegue alcuna stima.
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS = Path(__file__).resolve()
PKG = THIS.parent.parent
sys.path.insert(0, str(PKG))

import argparse
import time

import fred_fetch as ff


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot-dir", default=str(PKG / "external_data" / "snapshots"))
    ap.add_argument("--cache-dir", default=str(PKG / "external_data" / "cache"))
    ap.add_argument("--fetched-at", required=True,
                    help="Timestamp ISO del momento del fetch (passato dall'esterno)")
    args = ap.parse_args(argv)

    snap = Path(args.snapshot_dir)
    cache = Path(args.cache_dir)
    snap.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)

    plan = ff.procurement_plan()
    print(f"[plan] {len(plan)} serie da scaricare e congelare")
    for it in plan:
        sid = it["series_id"]
        print(f"  - {sid:14s}  {it['purpose']}")

    results = []; failures = []
    for i, it in enumerate(plan):
        sid = it["series_id"]
        if i > 0:
            time.sleep(2)   # cortesia + evita rate-limit HTTP/2 sui burst
        try:
            text, url = ff.fetch_series(sid, cache_dir=cache)
            s = ff.parse_fredgraph_csv(text, sid)
            out = ff.freeze_series(s, snap, name=sid, source_url=url, fetched_at=args.fetched_at)
            print(f"[ok] {sid:14s}  rows={out['provenance']['n_rows']:>6}  "
                  f"{out['provenance']['date_min']}..{out['provenance']['date_max']}", flush=True)
            results.append((sid, out))
        except Exception as exc:
            print(f"[FAIL] {sid:14s}  {exc}", flush=True)
            failures.append((sid, str(exc)))

    # Deriva CPI YoY da CPIAUCSL e congela come serie a sé (T8(d))
    cpi_path = snap / "CPIAUCSL.csv"
    if cpi_path.exists():
        cpi_level = ff.parse_fredgraph_csv(cpi_path, "CPIAUCSL")
        cpi_yoy = ff.cpi_yoy_from_level(cpi_level).dropna()
        yoy_out = ff.freeze_series(cpi_yoy, snap, name="CPI_YoY",
                                   source_url="derived://CPIAUCSL.pct_change(12)",
                                   fetched_at=args.fetched_at)
        print(f"[ok] {'CPI_YoY':14s}  rows={yoy_out['provenance']['n_rows']:>6}  "
              f"{yoy_out['provenance']['date_min']}..{yoy_out['provenance']['date_max']}  (derivata)")
    else:
        print("[skip] CPI_YoY: CPIAUCSL.csv non disponibile (fetch fallito)")

    print()
    print(f"=== completato: {len(results)} ok, {len(failures)} falliti ===")
    for sid, exc in failures:
        print(f"  FAIL {sid}: {exc}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main() or 0)
