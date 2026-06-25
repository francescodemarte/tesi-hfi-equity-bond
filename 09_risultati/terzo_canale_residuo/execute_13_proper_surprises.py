"""execute_13_proper_surprises.py — Rifa il 13 con SORPRESE SPECIFICHE per cella.

Specifiche di sorpresa (corregge l'uso di m_e generico):
  - CPI: surprise_yoy = cpi_yoy_actual - cpi_yoy_consensus dal bridge req08
    (`bridge/data/req08_cpi_surprise.csv`). Mapping per reference_month_end =
    end-of(M-1). Identica logica del T2 Lewbel del 07.
  - FOMC: MP1 (Jarociński-Karadi) — copertura 114/189 (post-2010, JK fino a 2024-01).
    Per i 75 eventi FOMC fuori dataset JK → SCARTATI dalla mask (dichiarato).
  - NFP: m_e PC1 money-market (FALLBACK DICHIARATO — actual-vs-consensus NFP
    non presente nel filesystem; documentato come limite di copertura).

Proxy:
  L: Δ(bid-ask spread bps) intraday post-pre, media ES+TY.
  V: ΔVIX daily.
  C: corr 5-min ES~TY giorno trading precedente.

q = 0.10 PRE-REGISTRATO.
"""
from __future__ import annotations

import csv
import hashlib
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
import manifest as MF13          # noqa: E402
import pipeline as PIPE13        # noqa: E402

OUT_DIR = ROOT / "09_risultati" / "terzo_canale_residuo" / "proper_surprises"
OUT_DIR.mkdir(parents=True, exist_ok=True)

EVENTS_CSV = ROOT / "DATASET_TESI" / "01_eventi_hfi" / "events_with_regime_classifier.csv"
CONTAMINANTS_CSV = Path("/home/francesco/TESI/Dati/calendari/contaminants_build_2026-06-22/"
                         "contaminants_v2_2026-06-22.csv")
PICKLE_AUTH_07 = ROOT / "09_risultati" / "v2_signflip" / "result_authoritative.pkl"
JK_FOMC_CSV = Path("/home/francesco/TESI/Dati/external_data/jk_surprises_fomc.csv")
VIXCLS_CSV = PKG07 / "external_data" / "snapshots" / "VIXCLS.csv"
ES_CSV = Path("/home/francesco/TESI/Dati/data_processed/ESc1_1min.csv")
TY_CSV = Path("/home/francesco/TESI/Dati/data_processed/TYc1_1min.csv")
REQ08_CSV = ROOT / "bridge" / "data" / "req08_cpi_surprise.csv"

D_BOND = 8.970865529245179
DP_BAR = -3.85
N_HORIZON = 100
BPS_TO_DECIMAL = 1.0 / 10000.0
RHO_CENTRAL = EPB.rho_from_dp_bar(DP_BAR)

SEED_NAME = "terzo_canale_proper_surprises_2026-06-24"
TASK_TIMESTAMP = (
    datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_contaminant_centers(path: Path) -> set:
    out = set()
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.add(pd.Timestamp(r["center_utc"]))
    return out


def load_jk_mp1() -> dict:
    """MP1 JK per evento FOMC. Chiavi tz-aware UTC normalized."""
    out = {}
    df = pd.read_csv(JK_FOMC_CSV)
    df["start"] = pd.to_datetime(df["start"], errors="coerce")
    for _, r in df.iterrows():
        if pd.isna(r["start"]):
            continue
        val = r.get("MP1")
        if pd.isna(val):
            continue  # niente fallback su FF1: rigore per FOMC
        d = pd.Timestamp(r["start"]).normalize()
        d_utc = d.tz_localize("UTC") if d.tz is None else d.tz_convert("UTC")
        out[d_utc] = float(val)
    return out


def load_req08_cpi_surprise() -> pd.DataFrame:
    """req08: reference_month_end → surprise_yoy (cpi_yoy_actual − cpi_yoy_consensus)."""
    df = pd.read_csv(REQ08_CSV)
    df["reference_month_end"] = pd.to_datetime(df["reference_month_end"])
    return df.set_index("reference_month_end")[["surprise_mom", "surprise_yoy"]]


def cpi_surprise_for_event(t_event: pd.Timestamp, req08: pd.DataFrame) -> float:
    """Mappa evento CPI → surprise_yoy via reference_month_end = end-of(M-1)."""
    rel_date = pd.Timestamp(t_event).tz_convert("America/New_York").date()
    ref_month = pd.Timestamp(rel_date) - pd.offsets.MonthEnd(1)
    if ref_month in req08.index:
        return float(req08.loc[ref_month, "surprise_yoy"])
    return float("nan")


def load_vix_daily() -> pd.Series:
    df = pd.read_csv(VIXCLS_CSV)
    date_col = next(c for c in df.columns if c.lower() in ("date", "observation_date"))
    val_col = next(c for c in df.columns if c != date_col)
    df[date_col] = pd.to_datetime(df[date_col]).dt.normalize().dt.tz_localize("UTC")
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    return df.set_index(date_col)[val_col].dropna().sort_index()


def load_intraday_with_ba(csv_p: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_p, usecols=["Datetime_UTC", "Bid", "Ask", "PX_LAST"])
    df["Datetime_UTC"] = pd.to_datetime(df["Datetime_UTC"], utc=True)
    df = df.set_index("Datetime_UTC").sort_index()
    df["spread_bps"] = (df["Ask"] - df["Bid"]) / df["PX_LAST"] * 1e4
    return df


def delta_spread_event(df: pd.DataFrame, t_event: pd.Timestamp) -> float:
    t = pd.Timestamp(t_event)
    pre = df.loc[t - pd.Timedelta(minutes=15): t - pd.Timedelta(minutes=10), "spread_bps"].dropna()
    post = df.loc[t + pd.Timedelta(minutes=10): t + pd.Timedelta(minutes=15), "spread_bps"].dropna()
    if len(pre) < 2 or len(post) < 2:
        return float("nan")
    return float(post.mean() - pre.mean())


def daily_log_returns_from_5min(prices: pd.Series, day) -> np.ndarray:
    day_ts = pd.Timestamp(day)
    if day_ts.tz is None:
        day_ts = day_ts.tz_localize("UTC")
    else:
        day_ts = day_ts.tz_convert("UTC")
    day_ts = day_ts.normalize()
    start = day_ts + pd.Timedelta(hours=14, minutes=30)
    end = day_ts + pd.Timedelta(hours=21)
    w = prices.loc[start:end]
    if len(w) < 12:
        return np.array([])
    return np.log(w.resample("5min").last()).diff().dropna().to_numpy()


def realized_corr_intraday(es, ty, day_eve):
    prev = pd.Timestamp(day_eve) - pd.Timedelta(days=1)
    for _ in range(7):
        re5 = daily_log_returns_from_5min(es, prev)
        rb5 = daily_log_returns_from_5min(ty, prev)
        if len(re5) >= 10 and len(rb5) >= 10:
            n = min(len(re5), len(rb5))
            if np.std(re5[:n]) == 0 or np.std(rb5[:n]) == 0:
                return float("nan")
            return float(np.corrcoef(re5[:n], rb5[:n])[0, 1])
        prev = prev - pd.Timedelta(days=1)
    return float("nan")


def delta_at_index(series: pd.Series, day) -> float:
    if day in series.index:
        idx = series.index.get_indexer([day])[0]
        if idx > 0:
            return float(series.iloc[idx] - series.iloc[idx - 1])
    return float("nan")


def main() -> int:
    print(f"=== execute_13_proper_surprises.py — {TASK_TIMESTAMP} ===")
    print("  Sorprese specifiche: CPI=req08 surprise_yoy, FOMC=MP1 JK, NFP=m_e (fallback)")
    print("  Proxy: L=Δbid-ask intraday, V=ΔVIX daily, C=corr 5-min ES~TY prev day")
    print(f"  q = 0.10 PRE-REGISTRATO; ROBUST_CELLS invariate.")

    ev_csv = pd.read_csv(EVENTS_CSV, usecols=["timestamp", "event_class", "date",
                                                "delta_rate_1", "delta_rate_2",
                                                "delta_rate_3", "m_e"])
    ev_csv["timestamp"] = pd.to_datetime(ev_csv["timestamp"], utc=True)
    delta_curve_by_ts = {ts: (d1, d2, d3) for ts, d1, d2, d3 in
                          zip(ev_csv["timestamp"], ev_csv["delta_rate_1"],
                              ev_csv["delta_rate_2"], ev_csv["delta_rate_3"])}
    me_by_ts = dict(zip(ev_csv["timestamp"], ev_csv["m_e"]))

    print("  reconstructing 07 clusters ...")
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

    print("  loading proxies + sorprese ...")
    mp1 = load_jk_mp1()
    req08 = load_req08_cpi_surprise()
    vix = load_vix_daily()
    es_full = load_intraday_with_ba(ES_CSV)
    ty_full = load_intraday_with_ba(TY_CSV)
    es_px = es_full["PX_LAST"]; ty_px = ty_full["PX_LAST"]
    print(f"    MP1 JK n={len(mp1)} dates")
    print(f"    req08 CPI surprises n={len(req08)} months")
    print(f"    VIX daily n={len(vix)}")

    print("  building per-cell inputs with PROPER surprises ...")
    inputs = {}
    diag = {}
    for (leg, reg) in cfg13.ROBUST_CELLS:
        clusters = per_type[leg][reg]
        re_l, rb_l, s_l, zL, zV, zC = [], [], [], [], [], []
        n_skip_no_surprise = 0
        for cl in clusters:
            ts_event = pd.Timestamp(cl["event"]["center"])
            if ts_event not in delta_curve_by_ts: continue
            d1, d2, d3 = delta_curve_by_ts[ts_event]
            if any(np.isnan([d1, d2, d3])): continue
            ctrls = cl.get("controls") or []
            if not ctrls: continue
            r_e_event = float(cl["event"]["r_e"]); r_b_event = float(cl["event"]["r_b"])
            df_curve = np.array([d1, d2, d3], dtype=float) * BPS_TO_DECIMAL
            dpb_e = EPB.delta_pb_equity(df_curve, rho=RHO_CENTRAL, tail="T0", N=N_HORIZON)
            dpb_b = BPB.delta_pb_bond(D_BOND, float(d3) * BPS_TO_DECIMAL)
            re_til = r_e_event - dpb_e
            rb_til = r_b_event - dpb_b
            day_event = ts_event.normalize()
            # SORPRESA SPECIFICA per cella
            if leg == "FOMC":
                s = float(mp1.get(day_event, np.nan))
            elif leg == "CPI":
                s = cpi_surprise_for_event(ts_event, req08)
            elif leg == "NFP":
                s = float(me_by_ts.get(ts_event, np.nan))
            else:
                s = float("nan")
            if np.isnan(s):
                n_skip_no_surprise += 1
                continue
            # Proxy
            dsp_es = delta_spread_event(es_full, ts_event)
            dsp_ty = delta_spread_event(ty_full, ts_event)
            if np.isnan(dsp_es) or np.isnan(dsp_ty):
                zL.append(float("nan"))
            else:
                zL.append(0.5 * (dsp_es + dsp_ty))
            zV.append(delta_at_index(vix, day_event))
            zC.append(realized_corr_intraday(es_px, ty_px, day_event))
            re_l.append(re_til); rb_l.append(rb_til); s_l.append(s)
        inputs[(leg, reg)] = {
            "re": np.array(re_l, float), "rb": np.array(rb_l, float),
            "surprise": np.array(s_l, float),
            "zL": np.array(zL, float), "zV": np.array(zV, float), "zC": np.array(zC, float),
        }
        diag[f"{leg}/{reg}"] = {"n_clusters": len(clusters), "n_skip_no_surprise": n_skip_no_surprise,
                                  "n_with_surprise": len(re_l)}
        print(f"    {leg}/{reg}: clusters={len(clusters)}, dropped_no_surprise={n_skip_no_surprise}, with_surprise={len(re_l)}")

    print("  pipeline.run_full_protocol q=0.10 ...")
    cell_inputs = {}; candidate_proxies = {}
    for (leg, reg) in cfg13.ROBUST_CELLS:
        d = inputs[(leg, reg)]
        n0 = len(d["re"])
        # mask: solo proxy NaN (la surprise è già stata filtrata)
        mask = (~np.isnan(d["zL"])) & (~np.isnan(d["zV"])) & (~np.isnan(d["zC"]))
        n1 = int(mask.sum())
        re_a = d["re"][mask]; rb_a = d["rb"][mask]; s_a = d["surprise"][mask]
        zL = d["zL"][mask]; zV = d["zV"][mask]; zC = d["zC"][mask]
        beta = float(beta_central_by_cell[(leg, reg)])
        cell_inputs[(leg, reg)] = {"r_e_tilde": re_a, "r_b_tilde": rb_a,
                                     "beta_str": beta, "surprise": s_a}
        candidate_proxies[(leg, reg)] = {
            "L": {"z": zL, "expected_sign": cfg13.EXPECTED_SIGN["L"]},
            "V": {"z": zV, "expected_sign": cfg13.EXPECTED_SIGN["V"]},
            "C": {"z": zC, "expected_sign": cfg13.EXPECTED_SIGN["C"]},
        }
        diag[f"{leg}/{reg}"]["n_after_proxy_mask"] = n1
        print(f"    {leg}/{reg}: n_after_proxy_mask={n1}/{n0}")
    out = PIPE13.run_full_protocol(cell_inputs, candidate_proxies, q=0.10)

    verdicts_clean = {}
    for (cell, cand), v in out["verdicts"].items():
        verdicts_clean[f"{cell[0]}/{cell[1]}|{cand}"] = {
            "third_channel": bool(v["third_channel"]),
            "passed_by": bool(v["passed_by"]),
            "commonality": bool(v["commonality"]),
            "sign_ok": (None if v["sign_ok"] is None else bool(v["sign_ok"])),
            "lambda_e": (float(v["lambda_e"]) if isinstance(v["lambda_e"], (int, float))
                          and math.isfinite(v["lambda_e"]) else None),
            "lambda_b": (float(v["lambda_b"]) if isinstance(v["lambda_b"], (int, float))
                          and math.isfinite(v["lambda_b"]) else None),
            "p_commonality": (float(v["p_commonality"]) if isinstance(v["p_commonality"], (int, float))
                                and math.isfinite(v["p_commonality"]) else None),
        }
    n_third = sum(1 for v in out["verdicts"].values() if v["third_channel"])
    passing = [k for k, v in verdicts_clean.items() if v["third_channel"]]
    print(f"\n  third_channel_True: {n_third}/12  passing={passing}")

    (OUT_DIR / "verdicts.json").write_bytes(
        json.dumps({
            "q": 0.10, "config_hash": cfg13.config_hash(),
            "verdicts": verdicts_clean,
            "by_crit": (out["by"].get("crit") if out["by"].get("crit") is not None else None),
            "by_c_m": out["by"]["c_m"], "by_family_size": out["by"]["family_size"],
            "n_third_channel_True": int(n_third),
            "passing_pairs": passing,
            "diagnostics_per_cell": diag,
            "surprise_sources_per_leg": {
                "FOMC": "MP1 Jarociński-Karadi (jk_surprises_fomc.csv)",
                "CPI": "surprise_yoy = cpi_yoy_actual - cpi_yoy_consensus (bridge req08_cpi_surprise.csv)",
                "NFP": "m_e PC1 money-market (fallback DICHIARATO — consensus NFP non disponibile)",
            },
        }, indent=2, sort_keys=True, default=str).encode("utf-8"))

    # Manifest
    m = {
        "task": "terzo_canale_residuo_proper_surprises_q010_pre_registered",
        "task_timestamp": TASK_TIMESTAMP,
        "seed_name": SEED_NAME,
        "config_hash": cfg13.config_hash(),
        "q": 0.10,
        "note": (
            "Run con SORPRESE SPECIFICHE per cella: CPI usa surprise_yoy actual-vs-consensus "
            "(coerente col T2 Lewbel del run autoritativo 07); FOMC usa MP1 JK (114/189 eventi "
            "post-2010 disponibili). NFP usa m_e come fallback DICHIARATO (consensus NFP non "
            "presente nel filesystem)."
        ),
        "input_sha256": {
            "events_csv": sha256_file(EVENTS_CSV),
            "contaminants_csv": sha256_file(CONTAMINANTS_CSV),
            "pickle_07_authoritative": sha256_file(PICKLE_AUTH_07),
            "req08_cpi_surprise": sha256_file(REQ08_CSV),
            "jk_fomc": sha256_file(JK_FOMC_CSV),
            "vix_daily_snapshot": sha256_file(VIXCLS_CSV),
            "es_intraday": sha256_file(ES_CSV),
            "ty_intraday": sha256_file(TY_CSV),
        },
        "external_constants": {"D_bond": D_BOND, "dp_bar": DP_BAR,
                                 "rho_central": RHO_CENTRAL, "N_horizon": N_HORIZON},
        "surprise_provenance_per_leg": {
            "FOMC": "MP1 Jarociński-Karadi — span 1988-02 to 2024-01; 114/189 eventi post-2010 hanno match. Eventi FOMC 2024-09→2025-12 scartati (fuori arco JK).",
            "CPI": "surprise_yoy = cpi_yoy_actual - cpi_yoy_consensus, da bridge/data/req08_cpi_surprise.csv. Stesso source del T2 Lewbel autoritativo (07).",
            "NFP": "m_e PC1 money-market dal CSV eventi v2 (fallback DICHIARATO — actual-vs-consensus NFP NON disponibile).",
        },
        "proxy_provenance": {
            "L": "Δ(bid-ask spread bps) post-pre, media ES+TY intraday",
            "V": "ΔVIXCLS daily (intraday non disponibile)",
            "C": "corr ES~TY 5-min realizzata sul giorno trading precedente l'evento",
        },
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "results_summary": {
            "n_third_channel_True": int(n_third),
            "passing_pairs": passing,
            "diagnostics_per_cell": diag,
            "verdicts": verdicts_clean,
        },
    }
    MF13.write_manifest(OUT_DIR / "manifest.json", m)
    print(f"\nDONE → {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
