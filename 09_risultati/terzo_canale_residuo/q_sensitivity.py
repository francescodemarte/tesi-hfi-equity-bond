"""q_sensitivity.py — Sensitivita BY q (FDR) per le varianti del 13.

ESPLORATIVO (NON pre-registrato): allarga la soglia BY q sopra il default 0.10
per vedere a quale tolleranza FDR il segnale borderline (CPI/pos|L_TED p=0.0037)
sopravvive. La pre-registrazione resta q=0.10; questo run e' diagnostica.

Riusa la pipeline costruita in execute_13_per_proxy.py, chiamando run_full_protocol
con q ∈ {0.10, 0.15, 0.20, 0.25, 0.30}.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/francesco/TESI/tesi-hfi-equity-bond")
PKG07 = ROOT / "CODICI_TESI" / "07_protocollo_v2_signflip"
PKG12 = ROOT / "CODICI_TESI" / "12_decomposizione_canali"
PKG13 = ROOT / "CODICI_TESI" / "13_terzo_canale_residuo"

sys.path.insert(0, str(PKG07))
import config as cfg07           # noqa: E402
import data as data07            # noqa: E402
import run as run07              # noqa: E402
import windows as win07          # noqa: E402

for m in ("config",):
    sys.modules.pop(m, None)
sys.path.remove(str(PKG07))
sys.path.insert(0, str(PKG12))
import config as cfg12           # noqa: E402
import bond_pb as BPB            # noqa: E402
import equity_pb as EPB          # noqa: E402

for m in ("config", "manifest"):
    sys.modules.pop(m, None)
sys.path.remove(str(PKG12))
sys.path.insert(0, str(PKG13))
import config as cfg13           # noqa: E402
import pipeline as PIPE13        # noqa: E402

OUT_DIR = ROOT / "09_risultati" / "terzo_canale_residuo" / "q_sensitivity"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Importo le stesse funzioni helper dall'execute_13_per_proxy
sys.path.insert(0, str(ROOT / "09_risultati" / "terzo_canale_residuo"))
from execute_13_per_proxy import (  # noqa: E402
    load_jk_mp1, load_vix_daily, load_ted_daily, load_intraday,
    load_contaminant_centers, build_inputs,
    EVENTS_CSV, CONTAMINANTS_CSV, ES_CSV, TY_CSV, BPS_TO_DECIMAL,
    D_BOND, DP_BAR, N_HORIZON, RHO_CENTRAL,
)

TASK_TIMESTAMP = (
    datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
)

Q_GRID = [0.10, 0.15, 0.20, 0.25, 0.30]
VARIANTS = [
    ("single_L_TED", True, False, False),
    ("all_active", True, True, True),
]


def variant_inputs(inputs, beta_central_by_cell, use_L, use_V, use_C):
    cell_inputs = {}; candidate_proxies = {}
    for (leg, reg) in cfg13.ROBUST_CELLS:
        d = inputs[(leg, reg)]
        n0 = len(d["re"])
        active_cond = [~np.isnan(d["re"]), ~np.isnan(d["rb"]),
                       ~np.isnan(d["surprise"])]
        if use_L: active_cond.append(~np.isnan(d["zL_TED"]))
        if use_V: active_cond.append(~np.isnan(d["zV_VIX"]))
        if use_C: active_cond.append(~np.isnan(d["zC_corr"]))
        mask = np.ones(n0, dtype=bool)
        for c in active_cond: mask &= c
        n1 = int(mask.sum())
        re_a = d["re"][mask]; rb_a = d["rb"][mask]; s_a = d["surprise"][mask]
        zL = d["zL_TED"][mask] if use_L else np.zeros(n1)
        zV = d["zV_VIX"][mask] if use_V else np.zeros(n1)
        zC = d["zC_corr"][mask] if use_C else np.zeros(n1)
        zL = np.nan_to_num(zL, nan=0.0); zV = np.nan_to_num(zV, nan=0.0); zC = np.nan_to_num(zC, nan=0.0)
        beta = float(beta_central_by_cell[(leg, reg)])
        cell_inputs[(leg, reg)] = {"r_e_tilde": re_a, "r_b_tilde": rb_a,
                                     "beta_str": beta, "surprise": s_a}
        candidate_proxies[(leg, reg)] = {
            "L": {"z": zL, "expected_sign": cfg13.EXPECTED_SIGN["L"]},
            "V": {"z": zV, "expected_sign": cfg13.EXPECTED_SIGN["V"]},
            "C": {"z": zC, "expected_sign": cfg13.EXPECTED_SIGN["C"]},
        }
    return cell_inputs, candidate_proxies


def main() -> int:
    print(f"=== q_sensitivity.py — {TASK_TIMESTAMP} ===")
    print("  ESPLORATIVO — q variabile ex-post; pre-registrazione resta q=0.10")

    # Carico stesso input pipeline di execute_13_per_proxy
    print("  loading inputs ...")
    ev_csv = pd.read_csv(EVENTS_CSV, usecols=["timestamp", "event_class", "date",
                                                "delta_rate_1", "delta_rate_2",
                                                "delta_rate_3", "m_e"])
    ev_csv["timestamp"] = pd.to_datetime(ev_csv["timestamp"], utc=True)
    delta_curve_by_ts = {ts: (d1, d2, d3) for ts, d1, d2, d3 in
                          zip(ev_csv["timestamp"], ev_csv["delta_rate_1"],
                              ev_csv["delta_rate_2"], ev_csv["delta_rate_3"])}
    me_by_ts = dict(zip(ev_csv["timestamp"], ev_csv["m_e"]))

    events_full = data07.load_events(EVENTS_CSV)
    prices = run07.load_prices()
    regs = run07.compute_regimes(prices)
    cont = load_contaminant_centers(CONTAMINANTS_CSV)
    ev_centers = set(pd.to_datetime(events_full["timestamp"], utc=True))
    reject = run07.build_calendar_reject(ev_centers, cont)
    per_type, _ = run07.assemble(events_full, prices, regs, reject)
    per_type, _ = win07.dedup_shared_controls(per_type)

    report12 = json.loads((ROOT / "09_risultati" / "decomp_canali"
                            / "decomp_canali.report.json").read_text())
    beta_central_by_cell = {}
    for r in report12["table_section_6_per_cell"]:
        if r.get("beta_str_central") is not None:
            parts = r["cell"].split("/")
            beta_central_by_cell[(parts[0], parts[1])] = float(r["beta_str_central"])

    mp1 = load_jk_mp1(); vix = load_vix_daily(); ted = load_ted_daily()
    es = load_intraday(ES_CSV); ty = load_intraday(TY_CSV)

    inputs, _ = build_inputs(per_type, delta_curve_by_ts, me_by_ts, mp1,
                              vix, ted, es, ty)

    results = []
    for var_name, useL, useV, useC in VARIANTS:
        cell_in, cand_prox = variant_inputs(inputs, beta_central_by_cell, useL, useV, useC)
        for q in Q_GRID:
            out = PIPE13.run_full_protocol(cell_in, cand_prox, q=q)
            third_true = []
            for (cell, cand), v in out["verdicts"].items():
                if v["third_channel"]:
                    third_true.append(f"{cell[0]}/{cell[1]}|{cand}")
            n_t = len(third_true)
            results.append({
                "variant": var_name, "q": q,
                "n_third_channel_True": n_t,
                "pairs_passed": third_true,
                "by_crit": (out["by"]["crit"] if out["by"]["crit"] is not None else None),
                "by_c_m": out["by"]["c_m"], "by_m": out["by"]["family_size"],
            })
            print(f"  {var_name:18s} q={q:.2f}  third={n_t}/12  crit={out['by']['crit']}  pairs={third_true}")

    payload = {
        "task_timestamp": TASK_TIMESTAMP,
        "note": "ESPLORATIVO — sensitivita q (BY FDR) sopra il pre-registrato 0.10. "
                "Riportato per trasparenza, NON sostituisce il verdetto pre-registrato.",
        "q_grid": Q_GRID,
        "variants": [v[0] for v in VARIANTS],
        "config_hash": cfg13.config_hash(),
        "results": results,
    }
    (OUT_DIR / "q_sensitivity.json").write_bytes(
        json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8"))
    print(f"\nDONE → {OUT_DIR}/q_sensitivity.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
