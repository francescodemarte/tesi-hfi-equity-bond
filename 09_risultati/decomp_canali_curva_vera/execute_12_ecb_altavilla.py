"""execute_12_ecb_altavilla.py — Pacchetto 12 con curva Bund Altavilla per ECB.

Δy_bond per cella:
  - US (FOMC, CPI, NFP): delta_rate_3 (baseline C)
  - ECB: ΔDE10Y dalla Monetary Event Window di Altavilla EA-MPD 2019
         (event-window-based, in pp → decimale ÷100)

Variante aggiuntiva: ECB_multi = media duration-pesata ΔDE2Y/ΔDE5Y/ΔDE10Y
                    ECB_30Y = ΔDE30Y (test coda lunga)
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
ALT_MEW = Path("/home/francesco/TESI/Dati/external_data/altavilla_eampd_monetary_event_window.csv")

D_BOND_FUTURE = 8.970865529245179   # duration FGBL (10Y future) — costante
DP_BAR = -3.85
N_HORIZON = 100
BPS_TO_DEC = 1.0 / 1e4
PP_TO_DEC = 1.0 / 100.0
DURATIONS_DE = {"DE2Y": 1.95, "DE5Y": 4.70, "DE10Y": 8.80, "DE30Y": 22.0}
TS = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
SEED = "decomp_12_ecb_altavilla_2026-06-24"

CELLS_US = [("FOMC", "pos"), ("FOMC", "neg"), ("CPI", "pos"), ("CPI", "neg"),
             ("NFP", "pos"), ("NFP", "neg")]
CELLS_ECB = [("ECB", "pos"), ("ECB", "neg")]


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def load_altavilla_mew():
    df = pd.read_csv(ALT_MEW)
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df.set_index("date")


def delta_y_ecb(variant: str, ts_event, alt_df):
    """Variant ECB: DE10Y / multi (2/5/10) / DE30Y."""
    day = ts_event.normalize().tz_convert(None)
    if day not in alt_df.index:
        return float("nan")
    row = alt_df.loc[day]
    if variant == "ECB_DE10Y":
        v = row.get("DE10Y", np.nan)
        return float(v) * PP_TO_DEC if not pd.isna(v) else float("nan")
    if variant == "ECB_multi_2_5_10":
        d2 = row.get("DE2Y", np.nan); d5 = row.get("DE5Y", np.nan); d10 = row.get("DE10Y", np.nan)
        if any(pd.isna([d2, d5, d10])): return float("nan")
        num = (DURATIONS_DE["DE2Y"] * d2 + DURATIONS_DE["DE5Y"] * d5
               + DURATIONS_DE["DE10Y"] * d10)
        return (num / D_BOND_FUTURE) * PP_TO_DEC
    if variant == "ECB_DE30Y":
        v = row.get("DE30Y", np.nan)
        # Δprice ≈ -D_30 · Δy_30; dato che D_bond_future=8.97 (è FGBL=10Y),
        # scalo come (D_30/D_bond_future) · Δy_30 per mantenere coerenza dimensionale
        if pd.isna(v): return float("nan")
        return (DURATIONS_DE["DE30Y"] / D_BOND_FUTURE) * float(v) * PP_TO_DEC
    raise ValueError(variant)


def main():
    print(f"=== execute_12_ecb_altavilla.py — {TS} ===")
    events_full = data07.load_events(EVENTS_CSV)
    prices = run07.load_prices()
    regs = run07.compute_regimes(prices)
    cont = set()
    with open(CONT_CSV) as f:
        for r in csv.DictReader(f): cont.add(pd.Timestamp(r["center_utc"]))
    reject = run07.build_calendar_reject(set(pd.to_datetime(events_full["timestamp"], utc=True)), cont)
    per_type, _ = run07.assemble(events_full, prices, regs, reject)
    per_type, _ = win07.dedup_shared_controls(per_type)
    ev_csv = pd.read_csv(EVENTS_CSV, usecols=["timestamp","delta_rate_1","delta_rate_2","delta_rate_3","m_e"])
    ev_csv["timestamp"] = pd.to_datetime(ev_csv["timestamp"], utc=True)
    by_ts = {ts:(d1,d2,d3,me) for ts,d1,d2,d3,me in zip(ev_csv["timestamp"],
        ev_csv["delta_rate_1"], ev_csv["delta_rate_2"], ev_csv["delta_rate_3"], ev_csv["m_e"])}
    me_by_ts = dict(zip(ev_csv["timestamp"], ev_csv["m_e"]))
    alt = load_altavilla_mew()
    print(f"  Altavilla MEW: {len(alt)} eventi, span {alt.index.min().date()} → {alt.index.max().date()}")

    rng = cfg12.make_rng(SEED)
    results = {}
    for ecb_variant in ("ECB_DE10Y", "ECB_multi_2_5_10", "ECB_DE30Y"):
        print(f"\n--- ECB variant: {ecb_variant} (US resta baseline C delta_rate_3) ---")
        per_variant = {}
        # US celle: baseline C
        for (leg, reg) in CELLS_US:
            clusters = per_type[leg][reg]
            events_list = []
            for cl in clusters:
                ts_event = pd.Timestamp(cl["event"]["center"])
                if ts_event not in by_ts: continue
                d1, d2, d3, _ = by_ts[ts_event]
                if any(np.isnan([d1,d2,d3])): continue
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
                per_variant[f"{leg}/{reg}"] = {"n_events": n_ev, "verdict": "channel_not_identified"}
                continue
            surprise = np.array([me_by_ts.get(pd.Timestamp(c["event"]["center"]), np.nan)
                                  for c in clusters[:n_ev]], float)
            try:
                out = CP.run_cell(events_list, dp_bar=DP_BAR, N=N_HORIZON, rng=rng,
                                    surprise_per_event=surprise if not np.isnan(surprise).any() else None)
                per_variant[f"{leg}/{reg}"] = {
                    "n_events": n_ev, "F_MOP": float(out["F_MOP"]),
                    "shrink": float(out["shrink"]), "gate_a": str(out["gate_a"]),
                    "beta_str_central": float(out["beta_str_central"]),
                    "construction_band_width": float(out["construction_band"]["width"]),
                    "verdict": str(out["verdict"]),
                }
            except Exception as e:
                per_variant[f"{leg}/{reg}"] = {"n_events": n_ev, "error": str(e)}
        # ECB celle: variante Altavilla
        for (leg, reg) in CELLS_ECB:
            clusters = per_type[leg][reg]
            events_list = []
            n_no_match = 0
            for cl in clusters:
                ts_event = pd.Timestamp(cl["event"]["center"])
                if ts_event not in by_ts: continue
                d1, d2, d3, _ = by_ts[ts_event]
                if any(np.isnan([d1,d2,d3])): continue
                ctrls = cl.get("controls") or []
                if not ctrls: continue
                delta_y = delta_y_ecb(ecb_variant, ts_event, alt)
                if np.isnan(delta_y): n_no_match += 1; continue
                events_list.append({
                    "r_e_event": float(cl["event"]["r_e"]),
                    "r_e_control": float(np.mean([c["r_e"] for c in ctrls])),
                    "r_b_event": float(cl["event"]["r_b"]),
                    "r_b_control": float(np.mean([c["r_b"] for c in ctrls])),
                    "delta_f_curve": np.array([d1,d2,d3], float) * BPS_TO_DEC,
                    "D_bond": D_BOND_FUTURE,
                    "delta_y_bond": float(delta_y),
                })
            n_ev = len(events_list)
            if n_ev < 5:
                per_variant[f"{leg}/{reg}"] = {"n_events": n_ev, "n_no_altavilla_match": n_no_match,
                                                "verdict": "channel_not_identified",
                                                "reason": "n<5 dopo match Altavilla"}
                print(f"  {leg}/{reg}: n={n_ev}  no_match={n_no_match} → SKIP")
                continue
            surprise = np.array([me_by_ts.get(pd.Timestamp(c["event"]["center"]), np.nan)
                                  for c in clusters[:n_ev]], float)
            try:
                out = CP.run_cell(events_list, dp_bar=DP_BAR, N=N_HORIZON, rng=rng,
                                    surprise_per_event=surprise if not np.isnan(surprise).any() else None)
                per_variant[f"{leg}/{reg}"] = {
                    "n_events": n_ev, "n_no_altavilla_match": n_no_match,
                    "F_MOP": float(out["F_MOP"]),
                    "shrink": float(out["shrink"]), "gate_a": str(out["gate_a"]),
                    "beta_str_central": float(out["beta_str_central"]),
                    "construction_band_width": float(out["construction_band"]["width"]),
                    "verdict": str(out["verdict"]),
                }
                print(f"  {leg}/{reg}: n={n_ev:3d}  no_match={n_no_match:3d}  F={out['F_MOP']:7.2f}  sh={out['shrink']:.3f}  "
                      f"gate_a={out['gate_a']}  band={out['construction_band']['width']:.3f}  → {out['verdict']}")
            except Exception as e:
                per_variant[f"{leg}/{reg}"] = {"n_events": n_ev, "error": str(e)}
                print(f"  {leg}/{reg}: FAIL {e}")
        # Sintesi per variante
        n_robust = sum(1 for v in per_variant.values() if v.get("verdict") == "identified_robust")
        n_fragile = sum(1 for v in per_variant.values() if v.get("verdict") == "identified_fragile")
        n_notid = sum(1 for v in per_variant.values() if v.get("verdict") == "channel_not_identified")
        robust_cells = [k for k,v in per_variant.items() if v.get("verdict") == "identified_robust"]
        results[ecb_variant] = per_variant
        print(f"  → robust={n_robust}, fragile={n_fragile}, not_id={n_notid}  robust_cells={robust_cells}")

    payload = {
        "task_timestamp": TS, "seed_name": SEED,
        "config_hash_12": cfg12.config_hash(),
        "design": ("US (FOMC, CPI, NFP) usa baseline C delta_rate_3; "
                    "ECB usa Altavilla EA-MPD Monetary Event Window con 3 sub-varianti "
                    "(DE10Y, multi 2/5/10 duration-weighted, DE30Y come stress coda lunga)."),
        "inputs_sha256": {"events_csv": sha(EVENTS_CSV), "altavilla_MEW": sha(ALT_MEW)},
        "results_per_variant": results,
    }
    (OUT / "results_ecb_altavilla.json").write_bytes(
        json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8"))
    print(f"\nDONE → {OUT}/results_ecb_altavilla.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
