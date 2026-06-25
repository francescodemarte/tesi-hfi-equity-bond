"""execute_12_true_curve.py — Rifa il pacchetto 12 con CURVA TREASURY VERA.

Tre varianti del bond piece ΔP^B_b:
  A: ΔP^B_b = -D_10 · ΔDGS10                  (cash 10Y vero, singola scadenza)
  B: ΔP^B_b = -Σ D_n · ΔDGS_n   weighted     (multi-curva 2/5/10, peso ∝ D_n)
  C: ΔP^B_b = -D_bond · delta_rate_3 / 1e4   (baseline, front money-market proxy)

Per ciascuna variante: esegue cell_pipeline.run_cell su tutte le 10 celle
(4 robust + 6 non-robust) e riporta verdetto.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/francesco/TESI/tesi-hfi-equity-bond")
PKG07 = ROOT / "CODICI_TESI" / "07_protocollo_v2_signflip"
PKG12 = ROOT / "CODICI_TESI" / "12_decomposizione_canali"

sys.path.insert(0, str(PKG07))
import config as cfg07           # noqa: E402
import data as data07            # noqa: E402
import run as run07              # noqa: E402
import windows as win07          # noqa: E402

for m in ("config",):
    sys.modules.pop(m, None)
sys.path.remove(str(PKG07))
sys.path.insert(0, str(PKG12))
import cell_pipeline as CP       # noqa: E402
import config as cfg12           # noqa: E402

OUT = ROOT / "09_risultati" / "decomp_canali_curva_vera"
OUT.mkdir(parents=True, exist_ok=True)

EVENTS_CSV = ROOT / "DATASET_TESI" / "01_eventi_hfi" / "events_with_regime_classifier.csv"
CONT_CSV = Path("/home/francesco/TESI/Dati/calendari/contaminants_build_2026-06-22/contaminants_v2_2026-06-22.csv")
DGS2 = Path("/home/francesco/TESI/Dati/external_data/DGS2.csv")
DGS5 = Path("/home/francesco/TESI/Dati/external_data/DGS5.csv")
DGS30 = Path("/home/francesco/TESI/Dati/external_data/DGS30.csv")
PARQ = Path("/home/francesco/TESI/Dati/external_data/fred_yields_snapshot.parquet")

D_BOND_FUTURE = 8.970865529245179
DP_BAR = -3.85
N_HORIZON = 100
BPS_TO_DEC = 1.0 / 1e4
PP_TO_DEC = 1.0 / 100.0  # DGS yields are in pp (e.g. 4.5 = 4.5%)

DURATIONS_CASH = {"DGS2": 1.92, "DGS5": 4.65, "DGS10": 8.50, "DGS30": 18.0}

TS = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
SEED = "decomp_12_true_curve_2026-06-24"

# Le 10 celle (4 leg × 2 reg + ECB decomposto in decision/press? no, qui aggreghiamo)
CELLS = [(leg, reg) for leg in cfg07.EVENT_TYPES for reg in ("pos", "neg")]


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def load_dgs_daily():
    par = pd.read_parquet(PARQ)
    par["date"] = pd.to_datetime(par["date"]).dt.normalize()
    dgs10 = par[par["series_id"] == "DGS10"].set_index("date")["value"].astype(float).sort_index()
    def load_csv(p, col):
        df = pd.read_csv(p)
        df["observation_date"] = pd.to_datetime(df["observation_date"]).dt.normalize()
        df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=[col]).set_index("observation_date")[col].sort_index()
    dgs2 = load_csv(DGS2, "DGS2")
    dgs5 = load_csv(DGS5, "DGS5")
    dgs30 = load_csv(DGS30, "DGS30")
    return {"DGS2": dgs2, "DGS5": dgs5, "DGS10": dgs10, "DGS30": dgs30}


def delta_at_date(series: pd.Series, day):
    if day not in series.index:
        return float("nan")
    idx = series.index.get_indexer([day])[0]
    if idx < 1:
        return float("nan")
    return float(series.iloc[idx] - series.iloc[idx - 1])


def delta_y_bond_variant(variant: str, ts_event, delta_rate_3_bps, dgs_dict):
    """Ritorna delta_y_bond in DECIMALE per la variante richiesta."""
    day = ts_event.normalize().tz_convert(None)
    if variant == "C_baseline":
        return float(delta_rate_3_bps) * BPS_TO_DEC if not np.isnan(delta_rate_3_bps) else float("nan")
    if variant == "A_DGS10":
        dy10 = delta_at_date(dgs_dict["DGS10"], day)
        return dy10 * PP_TO_DEC if not np.isnan(dy10) else float("nan")
    if variant == "B_multi":
        dy2 = delta_at_date(dgs_dict["DGS2"], day)
        dy5 = delta_at_date(dgs_dict["DGS5"], day)
        dy10 = delta_at_date(dgs_dict["DGS10"], day)
        if any(np.isnan([dy2, dy5, dy10])):
            return float("nan")
        # Media ponderata per duration: ΔP^B_b_multi = -Σ D_n·Δy_n / Σ D_n
        # Per restare compatibile con il kernel che usa Δy * D_bond, mappiamo
        # delta_y_bond = Σ D_n·Δy_n / D_bond_future ·(PP_TO_DEC)
        # (così -D_bond_future · delta_y_bond = -Σ D_n·Δy_n · PP_TO_DEC)
        num = (DURATIONS_CASH["DGS2"] * dy2 + DURATIONS_CASH["DGS5"] * dy5
               + DURATIONS_CASH["DGS10"] * dy10)
        return (num / D_BOND_FUTURE) * PP_TO_DEC
    raise ValueError(f"variant sconosciuta: {variant}")


def main():
    print(f"=== execute_12_true_curve.py — {TS} ===")
    events_full = data07.load_events(EVENTS_CSV)
    prices = run07.load_prices()
    regs = run07.compute_regimes(prices)
    cont = set()
    with open(CONT_CSV) as f:
        for r in csv.DictReader(f): cont.add(pd.Timestamp(r["center_utc"]))
    reject = run07.build_calendar_reject(set(pd.to_datetime(events_full["timestamp"], utc=True)), cont)
    per_type, _ = run07.assemble(events_full, prices, regs, reject)
    per_type, _ = win07.dedup_shared_controls(per_type)
    print("  per_type assembled")

    ev_csv = pd.read_csv(EVENTS_CSV,
                          usecols=["timestamp", "delta_rate_1", "delta_rate_2", "delta_rate_3", "m_e"])
    ev_csv["timestamp"] = pd.to_datetime(ev_csv["timestamp"], utc=True)
    by_ts = {ts: (d1, d2, d3, me) for ts, d1, d2, d3, me in
              zip(ev_csv["timestamp"], ev_csv["delta_rate_1"], ev_csv["delta_rate_2"],
                  ev_csv["delta_rate_3"], ev_csv["m_e"])}

    dgs_dict = load_dgs_daily()
    print(f"  DGS daily: DGS2 n={len(dgs_dict['DGS2'])}, DGS5 n={len(dgs_dict['DGS5'])}, DGS10 n={len(dgs_dict['DGS10'])}")

    rng = cfg12.make_rng(SEED)
    results = {}
    for variant in ("C_baseline", "A_DGS10", "B_multi"):
        print(f"\n--- VARIANT {variant} ---")
        per_variant = {}
        for (leg, reg) in CELLS:
            clusters = per_type[leg][reg]
            events_list = []
            n_drop = 0
            for cl in clusters:
                ts_event = pd.Timestamp(cl["event"]["center"])
                if ts_event not in by_ts: continue
                d1, d2, d3, me = by_ts[ts_event]
                if any(np.isnan([d1, d2, d3])): continue
                ctrls = cl.get("controls") or []
                if not ctrls: continue
                delta_y = delta_y_bond_variant(variant, ts_event, d3, dgs_dict)
                if np.isnan(delta_y):
                    n_drop += 1; continue
                events_list.append({
                    "r_e_event": float(cl["event"]["r_e"]),
                    "r_e_control": float(np.mean([c["r_e"] for c in ctrls])),
                    "r_b_event": float(cl["event"]["r_b"]),
                    "r_b_control": float(np.mean([c["r_b"] for c in ctrls])),
                    "delta_f_curve": np.array([d1, d2, d3], float) * BPS_TO_DEC,
                    "D_bond": D_BOND_FUTURE,
                    "delta_y_bond": float(delta_y),
                })
            n_ev = len(events_list)
            if n_ev < 5:
                per_variant[f"{leg}/{reg}"] = {
                    "n_clusters": len(clusters), "n_dropped_no_yield": n_drop,
                    "n_events": n_ev, "verdict": "channel_not_identified",
                    "gate_a": "FAIL", "reason": "n<5_after_yield_match",
                }
                print(f"  {leg}/{reg}: n={n_ev} → channel_not_identified (n<5)")
                continue
            # Surprise per il pre-check Nagel-Xu: m_e (PC1 money-market) per coerenza col run originale
            surprise = np.array([by_ts[pd.Timestamp(c["event"]["center"])][3]
                                  for c in clusters if pd.Timestamp(c["event"]["center"]) in by_ts][:n_ev], float)
            if len(surprise) != n_ev:
                surprise = None
            try:
                out = CP.run_cell(events_list, dp_bar=DP_BAR, N=N_HORIZON,
                                    rng=rng, surprise_per_event=surprise)
                per_variant[f"{leg}/{reg}"] = {
                    "n_clusters": len(clusters), "n_dropped_no_yield": n_drop,
                    "n_events": n_ev,
                    "F_MOP": float(out["F_MOP"]),
                    "shrink": float(out["shrink"]),
                    "gate_a": str(out["gate_a"]),
                    "beta_str_central": float(out["beta_str_central"]),
                    "construction_band_min": float(out["construction_band"]["min"]),
                    "construction_band_max": float(out["construction_band"]["max"]),
                    "construction_band_width": float(out["construction_band"]["width"]),
                    "precheck_status": str(out["precheck"]["status"]),
                    "verdict": str(out["verdict"]),
                }
                print(f"  {leg:5s}/{reg:3s}: n={n_ev:4d}  F_MOP={out['F_MOP']:7.2f}  shrink={out['shrink']:.4f}"
                      f"  gate_a={out['gate_a']:>4s}  band_width={out['construction_band']['width']:6.3f}"
                      f"  verdict={out['verdict']}")
            except Exception as e:
                per_variant[f"{leg}/{reg}"] = {"n_events": n_ev, "error": f"{type(e).__name__}: {e}"}
                print(f"  {leg}/{reg}: FAIL: {e}")
        results[variant] = per_variant
        n_robust = sum(1 for v in per_variant.values() if v.get("verdict") == "identified_robust")
        n_fragile = sum(1 for v in per_variant.values() if v.get("verdict") == "identified_fragile")
        n_notid = sum(1 for v in per_variant.values() if v.get("verdict") == "channel_not_identified")
        print(f"  → robust={n_robust}, fragile={n_fragile}, not_identified={n_notid}")

    # Sintesi comparativa
    sintesi = {"by_variant": {}}
    for variant in ("C_baseline", "A_DGS10", "B_multi"):
        d = results[variant]
        sintesi["by_variant"][variant] = {
            "n_robust": sum(1 for v in d.values() if v.get("verdict") == "identified_robust"),
            "n_fragile": sum(1 for v in d.values() if v.get("verdict") == "identified_fragile"),
            "n_not_identified": sum(1 for v in d.values() if v.get("verdict") == "channel_not_identified"),
            "robust_cells": [k for k, v in d.items() if v.get("verdict") == "identified_robust"],
        }

    payload = {
        "task_timestamp": TS,
        "seed_name": SEED,
        "config_hash_12": cfg12.config_hash(),
        "external_constants": {"D_bond_future": D_BOND_FUTURE, "dp_bar": DP_BAR,
                                 "N_horizon": N_HORIZON,
                                 "durations_cash": DURATIONS_CASH},
        "variants_definition": {
            "C_baseline": "delta_y_bond = delta_rate_3 (front money-market FFc3) in decimale; D_bond=8.97 (originale 12)",
            "A_DGS10": "delta_y_bond = ΔDGS10 daily in decimale; D_bond=8.97 (cash 10Y vero)",
            "B_multi": "delta_y_bond = (D_2·ΔDGS2 + D_5·ΔDGS5 + D_10·ΔDGS10) / D_bond_future in decimale; multi-curva",
        },
        "inputs_sha256": {
            "events_csv": sha(EVENTS_CSV), "DGS2": sha(DGS2), "DGS5": sha(DGS5),
            "DGS30": sha(DGS30), "fred_parquet": sha(PARQ),
        },
        "results_per_variant": results,
        "sintesi": sintesi,
    }
    (OUT / "results.json").write_bytes(
        json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8"))
    print(f"\nDONE → {OUT}/results.json")

    print("\n=== SINTESI ===")
    for v, s in sintesi["by_variant"].items():
        print(f"  {v:12s}: robust={s['n_robust']:2d}/10  fragile={s['n_fragile']:2d}  "
              f"not_id={s['n_not_identified']:2d}  cells={s['robust_cells']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
