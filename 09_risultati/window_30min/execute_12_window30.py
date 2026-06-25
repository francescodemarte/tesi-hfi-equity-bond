"""execute_12_window30.py — Pacchetto 12 con finestra ±30 min (vs ±15 baseline).

Riassembla cluster del 07 con HALF_MIN_WINDOW=30 (config 07 modificato in-place),
ricalcola delta_rate_1/2/3 con finestra ±30, esegue cell_pipeline.run_cell su
tutte le 10 celle (10 = 4 leg × 2 reg + 2 ECB extra).

Anche il proxy bond piece resta delta_rate_3 (originale del 12) — sostanziale:
solo la finestra cambia.
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

assert cfg07.HALF_MIN_WINDOW == 30, f"config 07 HALF_MIN_WINDOW deve essere 30, è {cfg07.HALF_MIN_WINDOW}"
print(f"  cfg07.HALF_MIN_WINDOW = {cfg07.HALF_MIN_WINDOW}  cfg07.MEDIAN_EDGE_MIN = {cfg07.MEDIAN_EDGE_MIN}")

OUT = ROOT / "09_risultati" / "window_30min"
OUT.mkdir(parents=True, exist_ok=True)

EVENTS_CSV = ROOT / "DATASET_TESI" / "01_eventi_hfi" / "events_with_regime_classifier.csv"
CONT_CSV = Path("/home/francesco/TESI/Dati/calendari/contaminants_build_2026-06-22/contaminants_v2_2026-06-22.csv")

D_BOND_FUTURE = 8.970865529245179
DP_BAR = -3.85
N_HORIZON = 100
BPS_TO_DEC = 1.0 / 1e4
TS = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
SEED = "decomp_12_window30_2026-06-24"


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def delta_window_event(prices_dict, sym, t_event, half_min=30, edge_min=5):
    """Δprice (post - pre) sulla finestra ±half_min minuti, in punti percentuali (bps)."""
    s = prices_dict[sym]
    pre = win07.extract_window(s, t_event, half_min=half_min, edge_min=edge_min)
    # extract_window restituisce log-return; per delta_rate_* (in bps) servirebbe
    # un Δprice diretto. Però per FFc/FEIc i prezzi sono yield-equivalent (100-yield),
    # quindi Δyield_bps = -(post-pre) * 100 (futures yield convention).
    return pre  # log-return — useremo questo come delta f anche se va riconvertito


def main():
    print(f"=== execute_12_window30.py — {TS} ===")
    events_full = data07.load_events(EVENTS_CSV)
    prices = run07.load_prices()
    regs = run07.compute_regimes(prices)
    cont = set()
    with open(CONT_CSV) as f:
        for r in csv.DictReader(f): cont.add(pd.Timestamp(r["center_utc"]))
    reject = run07.build_calendar_reject(set(pd.to_datetime(events_full["timestamp"], utc=True)), cont)
    per_type, _ = run07.assemble(events_full, prices, regs, reject)
    per_type, _ = win07.dedup_shared_controls(per_type)

    # Carico FFc1-3 e FEIc1-3 intraday per ricostruire delta_rate_* sulla nuova finestra
    INTRA = Path("/home/francesco/TESI/Dati/data_processed")
    def load_yield_intraday(name):
        df = pd.read_csv(INTRA/f"{name}_1min.csv", usecols=["Datetime_UTC","PX_LAST"])
        df["Datetime_UTC"] = pd.to_datetime(df["Datetime_UTC"], utc=True)
        s = df.set_index("Datetime_UTC")["PX_LAST"].astype(float).sort_index()
        return s[~s.index.duplicated(keep="first")].dropna()
    ff_series = {n: load_yield_intraday(n) for n in ("FFc1","FFc2","FFc3")}
    fei_series = {n: load_yield_intraday(n) for n in ("FEIc1","FEIc2","FEIc3")}

    def delta_yield_bps(s, t, half_min=30, edge_min=5):
        """Δyield in bps su finestra ±half_min. Per i futures yield-equivalent FFc/FEIc:
        prezzo P = 100 - yield(in pp). Δyield = -(P_post - P_pre) * 100 bps."""
        t0 = t - pd.Timedelta(minutes=half_min)
        t1 = t + pd.Timedelta(minutes=half_min)
        w = s.loc[t0:t1].dropna()
        if w.empty: return float("nan")
        pre_w = w.loc[t0: t0 + pd.Timedelta(minutes=edge_min)]
        post_w = w.loc[t1 - pd.Timedelta(minutes=edge_min): t1]
        if pre_w.empty or post_w.empty: return float("nan")
        pre = float(pre_w.median()); post = float(post_w.median())
        if np.isnan(pre) or np.isnan(post): return float("nan")
        return -(post - pre) * 100.0  # bps

    print("  ricostruzione delta_rate_* con finestra ±30 min ...")
    me_proxy = {}  # m_e per pre-check sostituito con PC1 ricalcolato? Usiamo old m_e dal CSV
    ev_csv = pd.read_csv(EVENTS_CSV, usecols=["timestamp","event_class","m_e"])
    ev_csv["timestamp"] = pd.to_datetime(ev_csv["timestamp"], utc=True)
    me_by_ts = dict(zip(ev_csv["timestamp"], ev_csv["m_e"]))

    rng = cfg12.make_rng(SEED)
    CELLS = [(leg, reg) for leg in cfg07.EVENT_TYPES for reg in ("pos", "neg")]
    results = {}
    for (leg, reg) in CELLS:
        clusters = per_type[leg][reg]
        rate_set = fei_series if leg == "ECB" else ff_series
        rate_names = ("FEIc1","FEIc2","FEIc3") if leg == "ECB" else ("FFc1","FFc2","FFc3")
        events_list = []
        n_skip = 0
        for cl in clusters:
            ts_event = pd.Timestamp(cl["event"]["center"])
            d1 = delta_yield_bps(rate_set[rate_names[0]], ts_event)
            d2 = delta_yield_bps(rate_set[rate_names[1]], ts_event)
            d3 = delta_yield_bps(rate_set[rate_names[2]], ts_event)
            if any(np.isnan([d1,d2,d3])):
                n_skip += 1; continue
            ctrls = cl.get("controls") or []
            if not ctrls: continue
            events_list.append({
                "r_e_event": float(cl["event"]["r_e"]),
                "r_e_control": float(np.mean([c["r_e"] for c in ctrls])),
                "r_b_event": float(cl["event"]["r_b"]),
                "r_b_control": float(np.mean([c["r_b"] for c in ctrls])),
                "delta_f_curve": np.array([d1,d2,d3], float) * BPS_TO_DEC,
                "D_bond": D_BOND_FUTURE,
                "delta_y_bond": float(d3) * BPS_TO_DEC,
            })
        n_ev = len(events_list)
        if n_ev < 5:
            results[f"{leg}/{reg}"] = {"n_events": n_ev, "verdict": "channel_not_identified",
                                        "n_skip_no_rate": n_skip}
            print(f"  {leg}/{reg}: n={n_ev} → SKIP")
            continue
        surprise = np.array([me_by_ts.get(pd.Timestamp(c["event"]["center"]), np.nan)
                              for c in clusters[:n_ev]], float)
        try:
            out = CP.run_cell(events_list, dp_bar=DP_BAR, N=N_HORIZON, rng=rng,
                                surprise_per_event=surprise if not np.isnan(surprise).any() else None)
            cb = out["construction_band"]; sb = out["sampling_band"]
            results[f"{leg}/{reg}"] = {
                "n_events": n_ev, "n_skip_no_rate": n_skip,
                "F_MOP": float(out["F_MOP"]),
                "shrink": float(out["shrink"]),
                "gate_a": str(out["gate_a"]),
                "beta_str_central": float(out["beta_str_central"]),
                "constr_band_min": float(cb["min"]), "constr_band_max": float(cb["max"]),
                "constr_band_width": float(cb["width"]),
                "sampling_band_low": float(sb["low"]), "sampling_band_high": float(sb["high"]),
                "precheck_status": str(out["precheck"]["status"]),
                "verdict": str(out["verdict"]),
            }
            print(f"  {leg:5s}/{reg:3s}: n={n_ev:4d}  F={out['F_MOP']:7.2f}  sh={out['shrink']:.4f}"
                  f"  β={out['beta_str_central']:+.4f}  band_w={cb['width']:.4f}  pre={out['precheck']['status']}  → {out['verdict']}")
        except Exception as e:
            results[f"{leg}/{reg}"] = {"n_events": n_ev, "error": str(e)}
            print(f"  {leg}/{reg}: FAIL {e}")

    n_robust = sum(1 for v in results.values() if v.get("verdict") == "identified_robust")
    n_fragile = sum(1 for v in results.values() if v.get("verdict") == "identified_fragile")
    n_notid = sum(1 for v in results.values() if v.get("verdict") == "channel_not_identified")
    print(f"\n  → robust={n_robust}, fragile={n_fragile}, not_id={n_notid}")
    robust_cells = [k for k,v in results.items() if v.get("verdict") == "identified_robust"]
    print(f"  robust cells: {robust_cells}")

    payload = {
        "task_timestamp": TS, "seed_name": SEED,
        "config_hash_12": cfg12.config_hash(),
        "config_07_HALF_MIN_WINDOW": cfg07.HALF_MIN_WINDOW,
        "config_07_MEDIAN_EDGE_MIN": cfg07.MEDIAN_EDGE_MIN,
        "window_change": "±30 min (vs ±15 baseline); EDGE = 5 min costante",
        "results": results,
        "sintesi": {"n_robust": n_robust, "n_fragile": n_fragile, "n_not_identified": n_notid,
                     "robust_cells": robust_cells},
    }
    (OUT / "results.json").write_bytes(
        json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8"))
    print(f"\nDONE → {OUT}/results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
