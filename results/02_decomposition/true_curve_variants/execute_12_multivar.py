"""execute_12_multivar.py — Variante F: regressione MULTIVARIATA per il proxy intraday.

Costruisce Δy_bond_intraday come combinazione lineare degli shock intraday
disponibili, calibrata via OLS su ΔDGS10 daily nel giorno evento:

    ΔDGS10_daily = β_1·delta_rate_1 + β_2·delta_rate_2 + β_3·delta_rate_3 + β_m·m_e
                   + ε    (senza const, eventi cross-leg)

poi Δy_bond_intraday = β_1·delta_rate_1 + β_2·delta_rate_2 + β_3·delta_rate_3
                       + β_m·m_e   (per evento, in decimale 10Y)

Atteso: R² globale migliorato vs solo delta_rate_3 → proxy intraday più informativo
→ shrink in [0,1] + banda di costruzione più stretta → più celle robuste.
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

EVENTS_CSV = ROOT / "DATASET_TESI" / "01_eventi_hfi" / "events_with_regime_classifier.csv"
CONT_CSV = Path("/home/francesco/TESI/Dati/calendari/contaminants_build_2026-06-22/contaminants_v2_2026-06-22.csv")
PARQ = Path("/home/francesco/TESI/Dati/external_data/fred_yields_snapshot.parquet")

D_BOND_FUTURE = 8.970865529245179
DP_BAR = -3.85
N_HORIZON = 100
BPS_TO_DEC = 1.0 / 1e4
PP_TO_DEC = 1.0 / 100.0
TS = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
SEED = "decomp_12_multivar_2026-06-24"


def delta_daily(s: pd.Series, day):
    if day not in s.index: return float("nan")
    idx = s.index.get_indexer([day])[0]
    if idx < 1: return float("nan")
    return float(s.iloc[idx] - s.iloc[idx - 1])


def main():
    print(f"=== execute_12_multivar.py — {TS} ===")
    events_full = data07.load_events(EVENTS_CSV)
    prices = run07.load_prices()
    regs = run07.compute_regimes(prices)
    cont = set()
    with open(CONT_CSV) as f:
        for r in csv.DictReader(f): cont.add(pd.Timestamp(r["center_utc"]))
    reject = run07.build_calendar_reject(set(pd.to_datetime(events_full["timestamp"], utc=True)), cont)
    per_type, _ = run07.assemble(events_full, prices, regs, reject)
    per_type, _ = win07.dedup_shared_controls(per_type)

    ev_csv = pd.read_csv(EVENTS_CSV,
                          usecols=["timestamp", "event_class", "delta_rate_1",
                                    "delta_rate_2", "delta_rate_3", "m_e"])
    ev_csv["timestamp"] = pd.to_datetime(ev_csv["timestamp"], utc=True)
    par = pd.read_parquet(PARQ)
    par["date"] = pd.to_datetime(par["date"]).dt.normalize()
    dgs10 = par[par["series_id"] == "DGS10"].set_index("date")["value"].astype(float).sort_index()

    df = ev_csv.dropna(subset=["delta_rate_1", "delta_rate_2", "delta_rate_3", "m_e"]).copy()
    df["day"] = df["timestamp"].dt.normalize().dt.tz_convert(None)
    df["d1_dec"] = df["delta_rate_1"] * BPS_TO_DEC
    df["d2_dec"] = df["delta_rate_2"] * BPS_TO_DEC
    df["d3_dec"] = df["delta_rate_3"] * BPS_TO_DEC
    df["me_z"] = df["m_e"]   # già in unità standardizzate
    df["dgs10_chg_dec"] = df["day"].map(lambda d: delta_daily(dgs10, d)).astype(float) * PP_TO_DEC
    df = df.dropna(subset=["dgs10_chg_dec"])
    print(f"  joint match (4 vars + ΔDGS10): {len(df)} eventi")

    # Multivariata OLS senza const
    X = df[["d1_dec", "d2_dec", "d3_dec", "me_z"]].values
    y = df["dgs10_chg_dec"].values
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    fitted = X @ beta
    r2 = float(1 - np.var(y - fitted) / np.var(y)) if np.var(y) > 0 else float("nan")
    print(f"  β multivar = {dict(zip(['d1','d2','d3','m_e'], [round(float(x),4) for x in beta]))}")
    print(f"  R² multivar = {r2:.4f}  (vs univariata 0.057)")

    # Construct proxy per evento + rilancia 12
    rng = cfg12.make_rng(SEED)
    CELLS = [(leg, reg) for leg in cfg07.EVENT_TYPES for reg in ("pos", "neg")]
    results = {}
    by_ts = {ts: (d1, d2, d3, me) for ts, d1, d2, d3, me in
              zip(ev_csv["timestamp"], ev_csv["delta_rate_1"], ev_csv["delta_rate_2"],
                  ev_csv["delta_rate_3"], ev_csv["m_e"])}

    print("\n--- VARIANT F_multivar ---")
    for (leg, reg) in CELLS:
        clusters = per_type[leg][reg]
        events_list = []
        for cl in clusters:
            ts_event = pd.Timestamp(cl["event"]["center"])
            if ts_event not in by_ts: continue
            d1, d2, d3, me = by_ts[ts_event]
            if any(np.isnan([d1, d2, d3, me])): continue
            ctrls = cl.get("controls") or []
            if not ctrls: continue
            delta_y = (beta[0] * d1 * BPS_TO_DEC + beta[1] * d2 * BPS_TO_DEC
                        + beta[2] * d3 * BPS_TO_DEC + beta[3] * me)
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
            results[f"{leg}/{reg}"] = {"n_events": n_ev, "verdict": "channel_not_identified"}
            continue
        surprise = np.array([by_ts[pd.Timestamp(c["event"]["center"])][3]
                              for c in clusters[:n_ev] if pd.Timestamp(c["event"]["center"]) in by_ts], float)
        try:
            out = CP.run_cell(events_list, dp_bar=DP_BAR, N=N_HORIZON,
                                rng=rng, surprise_per_event=surprise if len(surprise)==n_ev else None)
            results[f"{leg}/{reg}"] = {
                "n_events": n_ev,
                "F_MOP": float(out["F_MOP"]),
                "shrink": float(out["shrink"]),
                "gate_a": str(out["gate_a"]),
                "beta_str_central": float(out["beta_str_central"]),
                "construction_band_width": float(out["construction_band"]["width"]),
                "precheck_status": str(out["precheck"]["status"]),
                "verdict": str(out["verdict"]),
            }
            print(f"  {leg:5s}/{reg:3s}: n={n_ev:4d}  F_MOP={out['F_MOP']:7.2f}  shrink={out['shrink']:.4f}"
                  f"  gate_a={out['gate_a']:>4s}  band_w={out['construction_band']['width']:6.3f}"
                  f"  verdict={out['verdict']}")
        except Exception as e:
            results[f"{leg}/{reg}"] = {"n_events": n_ev, "error": f"{type(e).__name__}: {e}"}

    n_robust = sum(1 for v in results.values() if v.get("verdict") == "identified_robust")
    n_fragile = sum(1 for v in results.values() if v.get("verdict") == "identified_fragile")
    n_notid = sum(1 for v in results.values() if v.get("verdict") == "channel_not_identified")
    print(f"\n  → robust={n_robust}, fragile={n_fragile}, not_identified={n_notid}")
    robust_cells = [k for k, v in results.items() if v.get("verdict") == "identified_robust"]
    print(f"  robust cells: {robust_cells}")

    payload = {
        "task_timestamp": TS, "seed_name": SEED,
        "config_hash_12": cfg12.config_hash(),
        "beta_multivar": {"d1": float(beta[0]), "d2": float(beta[1]),
                            "d3": float(beta[2]), "m_e": float(beta[3]), "R2": r2,
                            "joint_match_n": int(len(df))},
        "variant_F_results": results,
        "sintesi": {"n_robust": n_robust, "n_fragile": n_fragile,
                     "n_not_identified": n_notid, "robust_cells": robust_cells},
    }
    (OUT / "results_multivar.json").write_bytes(
        json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8"))
    print(f"\nDONE → {OUT}/results_multivar.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
