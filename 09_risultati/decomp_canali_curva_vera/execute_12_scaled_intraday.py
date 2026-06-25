"""execute_12_scaled_intraday.py — Variante D: proxy INTRADAY scalata a 10Y.

Problema delle varianti A/B (curva vera daily): shrink >> 1 perché ΔDGS10 daily
e' quasi ortogonale a r_b intraday → il netting aggiunge rumore invece di
sottrarre il canale tasso, e il gate (a) passa "per finto".

Idea variante D:
  - Stimo empiricamente la trasmissione front money-market → 10Y sui giorni evento:
        ΔDGS10_daily_eve ≈ β · delta_rate_3_intraday   (regression senza const)
  - Uso β · delta_rate_3 come proxy INTRADAY di Δy_10Y per ciascun evento:
        Δy_bond_scaled = β · delta_rate_3 / 1e4    (decimale, scala 10Y)
  - Rilancio cell_pipeline.run_cell. Atteso: shrink torna in [0,1], F_MOP cresce
    per netting effettivo, gate_a passa con DECIVITA (non per fabbricazione di varianza).

Bonus variante E: β condizionato per leg (FOMC, CPI, NFP, ECB) — la trasmissione
front→long-end potrebbe variare per tipo annuncio.
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
PARQ = Path("/home/francesco/TESI/Dati/external_data/fred_yields_snapshot.parquet")
DGS2 = Path("/home/francesco/TESI/Dati/external_data/DGS2.csv")
DGS5 = Path("/home/francesco/TESI/Dati/external_data/DGS5.csv")

D_BOND_FUTURE = 8.970865529245179
DP_BAR = -3.85
N_HORIZON = 100
BPS_TO_DEC = 1.0 / 1e4
PP_TO_DEC = 1.0 / 100.0

TS = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
SEED = "decomp_12_scaled_intraday_2026-06-24"


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def load_dgs10():
    par = pd.read_parquet(PARQ)
    par["date"] = pd.to_datetime(par["date"]).dt.normalize()
    return par[par["series_id"] == "DGS10"].set_index("date")["value"].astype(float).sort_index()


def delta_daily(s: pd.Series, day):
    if day not in s.index: return float("nan")
    idx = s.index.get_indexer([day])[0]
    if idx < 1: return float("nan")
    return float(s.iloc[idx] - s.iloc[idx - 1])


def main():
    print(f"=== execute_12_scaled_intraday.py — {TS} ===")
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
    dgs10 = load_dgs10()

    # ---- STIMA β EMPIRICA: ΔDGS10_daily ~ delta_rate_3_intraday (no const) ----
    df = ev_csv[["timestamp", "event_class", "delta_rate_3"]].copy()
    df = df.dropna(subset=["delta_rate_3"])
    df["day"] = df["timestamp"].dt.normalize().dt.tz_convert(None)
    df["dr3_dec"] = df["delta_rate_3"] * BPS_TO_DEC   # decimale
    df["dgs10_chg_dec"] = df["day"].map(lambda d: delta_daily(dgs10, d)).astype(float) * PP_TO_DEC
    valid = df.dropna(subset=["dr3_dec", "dgs10_chg_dec"])
    print(f"  joint match (delta_rate_3 + ΔDGS10): {len(valid)} eventi")

    # β globale
    x_all = valid["dr3_dec"].values
    y_all = valid["dgs10_chg_dec"].values
    if np.dot(x_all, x_all) > 0:
        beta_global = float(np.dot(x_all, y_all) / np.dot(x_all, x_all))
    else:
        beta_global = float("nan")
    r2_global = float(1 - np.var(y_all - beta_global * x_all) / np.var(y_all)) if np.var(y_all) > 0 else float("nan")
    print(f"  β global (Δy_10Y / Δfront) = {beta_global:.4f}  R² = {r2_global:.4f}")

    # β per leg
    beta_by_leg = {}
    for leg in ("FOMC", "CPI", "NFP", "ECB"):
        sub = valid[valid["event_class"] == leg]
        if len(sub) >= 5:
            x = sub["dr3_dec"].values; y = sub["dgs10_chg_dec"].values
            b = float(np.dot(x, y) / np.dot(x, x)) if np.dot(x, x) > 0 else float("nan")
            r2 = float(1 - np.var(y - b * x) / np.var(y)) if np.var(y) > 0 else float("nan")
            beta_by_leg[leg] = {"beta": b, "R2": r2, "n": int(len(sub))}
            print(f"    {leg}: β={b:+.4f}  R²={r2:.4f}  n={len(sub)}")
        else:
            beta_by_leg[leg] = {"beta": beta_global, "R2": float("nan"), "n": int(len(sub)),
                                 "note": "fallback β_global"}

    # ---- VARIANTI D, E ----
    by_ts = {ts: (d1, d2, d3) for ts, d1, d2, d3 in
              zip(ev_csv["timestamp"], ev_csv["delta_rate_1"], ev_csv["delta_rate_2"], ev_csv["delta_rate_3"])}
    me_by_ts = dict(zip(ev_csv["timestamp"], ev_csv["m_e"]))

    rng = cfg12.make_rng(SEED)
    CELLS = [(leg, reg) for leg in cfg07.EVENT_TYPES for reg in ("pos", "neg")]
    results = {}
    for variant in ("D_scaled_global", "E_scaled_by_leg"):
        print(f"\n--- VARIANT {variant} ---")
        per_variant = {}
        for (leg, reg) in CELLS:
            clusters = per_type[leg][reg]
            beta_used = beta_by_leg[leg]["beta"] if variant == "E_scaled_by_leg" else beta_global
            events_list = []
            for cl in clusters:
                ts_event = pd.Timestamp(cl["event"]["center"])
                if ts_event not in by_ts: continue
                d1, d2, d3 = by_ts[ts_event]
                if any(np.isnan([d1, d2, d3])): continue
                ctrls = cl.get("controls") or []
                if not ctrls: continue
                delta_y_scaled = beta_used * (float(d3) * BPS_TO_DEC)   # decimale, scala 10Y
                events_list.append({
                    "r_e_event": float(cl["event"]["r_e"]),
                    "r_e_control": float(np.mean([c["r_e"] for c in ctrls])),
                    "r_b_event": float(cl["event"]["r_b"]),
                    "r_b_control": float(np.mean([c["r_b"] for c in ctrls])),
                    "delta_f_curve": np.array([d1, d2, d3], float) * BPS_TO_DEC,
                    "D_bond": D_BOND_FUTURE,
                    "delta_y_bond": float(delta_y_scaled),
                })
            n_ev = len(events_list)
            if n_ev < 5:
                per_variant[f"{leg}/{reg}"] = {"n_events": n_ev, "verdict": "channel_not_identified",
                                                "gate_a": "FAIL", "reason": "n<5"}
                continue
            surprise = np.array([me_by_ts.get(pd.Timestamp(c["event"]["center"]), np.nan)
                                  for c in clusters[:n_ev]], float)
            if np.isnan(surprise).any():
                surprise = None
            try:
                out = CP.run_cell(events_list, dp_bar=DP_BAR, N=N_HORIZON,
                                    rng=rng, surprise_per_event=surprise)
                per_variant[f"{leg}/{reg}"] = {
                    "n_events": n_ev,
                    "F_MOP": float(out["F_MOP"]),
                    "shrink": float(out["shrink"]),
                    "gate_a": str(out["gate_a"]),
                    "beta_str_central": float(out["beta_str_central"]),
                    "construction_band_width": float(out["construction_band"]["width"]),
                    "precheck_status": str(out["precheck"]["status"]),
                    "verdict": str(out["verdict"]),
                    "beta_used_for_delta_y": float(beta_used),
                }
                print(f"  {leg:5s}/{reg:3s}: n={n_ev:4d}  F_MOP={out['F_MOP']:7.2f}  shrink={out['shrink']:.4f}"
                      f"  gate_a={out['gate_a']:>4s}  band_w={out['construction_band']['width']:6.3f}"
                      f"  verdict={out['verdict']}")
            except Exception as e:
                per_variant[f"{leg}/{reg}"] = {"n_events": n_ev, "error": f"{type(e).__name__}: {e}"}
        results[variant] = per_variant
        n_robust = sum(1 for v in per_variant.values() if v.get("verdict") == "identified_robust")
        n_fragile = sum(1 for v in per_variant.values() if v.get("verdict") == "identified_fragile")
        n_notid = sum(1 for v in per_variant.values() if v.get("verdict") == "channel_not_identified")
        print(f"  → robust={n_robust}, fragile={n_fragile}, not_identified={n_notid}")

    sintesi = {}
    for variant in ("D_scaled_global", "E_scaled_by_leg"):
        d = results[variant]
        sintesi[variant] = {
            "n_robust": sum(1 for v in d.values() if v.get("verdict") == "identified_robust"),
            "n_fragile": sum(1 for v in d.values() if v.get("verdict") == "identified_fragile"),
            "n_not_identified": sum(1 for v in d.values() if v.get("verdict") == "channel_not_identified"),
            "robust_cells": [k for k, v in d.items() if v.get("verdict") == "identified_robust"],
        }

    payload = {
        "task_timestamp": TS, "seed_name": SEED,
        "config_hash_12": cfg12.config_hash(),
        "beta_estimation": {
            "method": "regression ΔDGS10_daily ~ β · delta_rate_3_intraday (no const)",
            "joint_match_n": int(len(valid)),
            "beta_global": beta_global, "R2_global": r2_global,
            "beta_by_leg": beta_by_leg,
        },
        "external_constants": {"D_bond_future": D_BOND_FUTURE, "dp_bar": DP_BAR, "N_horizon": N_HORIZON},
        "inputs_sha256": {"events_csv": sha(EVENTS_CSV), "fred_parquet": sha(PARQ)},
        "results_per_variant": results,
        "sintesi": sintesi,
    }
    (OUT / "results_scaled.json").write_bytes(
        json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8"))

    print("\n=== SINTESI ===")
    for v, s in sintesi.items():
        print(f"  {v:18s}: robust={s['n_robust']:2d}/8  fragile={s['n_fragile']:2d}  "
              f"not_id={s['n_not_identified']:2d}  cells={s['robust_cells']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
