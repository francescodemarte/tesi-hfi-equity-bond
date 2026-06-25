"""execute_13_intraday_L.py — Rifa il test del 13 con proxy L INTRADAY VERA.

Pre-registrato q=0.10. Proxy L NON e' piu' TED daily (discontinued + look-back
limitato): e' Δ(bid-ask spread) intraday post−pre sulla finestra evento, media
fra ES e TY. La proxy:
  - copre TUTTO il periodo 2010-2025 senza buchi post-2022 (TED problem);
  - e' specificamente "shock di liquidita' all'evento", non rumore daily;
  - sfrutta direttamente le colonne Bid/Ask delle 1-min CSV.

Calcolo per evento:
  pre  window  = [t-15min, t-10min]  (5 min)
  post window  = [t+10min, t+15min]  (5 min)
  spread_pre   = mean((Ask-Bid)/PX_LAST) sulla finestra pre   [bps quando ×10000]
  spread_post  = mean((Ask-Bid)/PX_LAST) sulla finestra post
  z_L_asset    = spread_post - spread_pre                        [bps]
  z_L          = (z_L_ES + z_L_TY) / 2

Esegue 2 varianti (q=0.10 pre-registrato fisso):
  - single_L_intraday:  L=z_L, V=0, C=0
  - all_with_intraday_L: L=z_L, V=ΔVIX daily, C=corr intraday giorno prec
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

OUT_DIR = ROOT / "09_risultati" / "terzo_canale_residuo" / "intraday_L"
OUT_DIR.mkdir(parents=True, exist_ok=True)

EVENTS_CSV = ROOT / "DATASET_TESI" / "01_eventi_hfi" / "events_with_regime_classifier.csv"
CONTAMINANTS_CSV = Path("/home/francesco/TESI/Dati/calendari/contaminants_build_2026-06-22/"
                         "contaminants_v2_2026-06-22.csv")
PICKLE_AUTH_07 = ROOT / "09_risultati" / "v2_signflip" / "result_authoritative.pkl"
JK_FOMC_CSV = Path("/home/francesco/TESI/Dati/external_data/jk_surprises_fomc.csv")
VIXCLS_CSV = PKG07 / "external_data" / "snapshots" / "VIXCLS.csv"
ES_CSV = Path("/home/francesco/TESI/Dati/data_processed/ESc1_1min.csv")
TY_CSV = Path("/home/francesco/TESI/Dati/data_processed/TYc1_1min.csv")

D_BOND = 8.970865529245179
DP_BAR = -3.85
N_HORIZON = 100
BPS_TO_DECIMAL = 1.0 / 10000.0
RHO_CENTRAL = EPB.rho_from_dp_bar(DP_BAR)

SEED_NAME = "terzo_canale_intraday_L_2026-06-24"
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
    out = {}
    df = pd.read_csv(JK_FOMC_CSV)
    df["start"] = pd.to_datetime(df["start"], errors="coerce")
    for _, r in df.iterrows():
        if pd.isna(r["start"]):
            continue
        val = r.get("MP1")
        if pd.isna(val):
            val = r.get("FF1")
        if pd.isna(val):
            continue
        d = pd.Timestamp(r["start"]).normalize()
        d_utc = d.tz_localize("UTC") if d.tz is None else d.tz_convert("UTC")
        out[d_utc] = float(val)
    return out


def load_vix_daily() -> pd.Series:
    df = pd.read_csv(VIXCLS_CSV)
    date_col = next(c for c in df.columns if c.lower() in ("date", "observation_date"))
    val_col = next(c for c in df.columns if c != date_col)
    df[date_col] = pd.to_datetime(df[date_col]).dt.normalize().dt.tz_localize("UTC")
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    return df.set_index(date_col)[val_col].dropna().sort_index()


def load_intraday_with_ba(csv_p: Path) -> pd.DataFrame:
    """Carica intraday con Bid/Ask/PX_LAST → DataFrame indicizzato su Datetime_UTC."""
    df = pd.read_csv(csv_p, usecols=["Datetime_UTC", "Bid", "Ask", "PX_LAST"])
    df["Datetime_UTC"] = pd.to_datetime(df["Datetime_UTC"], utc=True)
    df = df.set_index("Datetime_UTC").sort_index()
    df["spread_bps"] = (df["Ask"] - df["Bid"]) / df["PX_LAST"] * 1e4
    return df


def delta_spread_event(df: pd.DataFrame, t_event: pd.Timestamp) -> float:
    """Δ(spread bps) post−pre sulla finestra ±15 min, 5 min mediana ai bordi."""
    t = pd.Timestamp(t_event)
    pre_a = t - pd.Timedelta(minutes=15)
    pre_b = t - pd.Timedelta(minutes=10)
    post_a = t + pd.Timedelta(minutes=10)
    post_b = t + pd.Timedelta(minutes=15)
    pre = df.loc[pre_a:pre_b, "spread_bps"].dropna()
    post = df.loc[post_a:post_b, "spread_bps"].dropna()
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
    r5 = np.log(w.resample("5min").last()).diff().dropna().to_numpy()
    return r5


def realized_corr_intraday(es: pd.Series, ty: pd.Series, day_eve) -> float:
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
    print(f"=== execute_13_intraday_L.py — {TASK_TIMESTAMP} ===")
    print("  Proxy L = Δ(bid-ask spread bps) post−pre, media ES+TY")
    print("  q = 0.10 PRE-REGISTRATO; ROBUST_CELLS invariate.")
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

    print("  loading intraday ES, TY (with bid/ask) ...")
    es_full = load_intraday_with_ba(ES_CSV)
    ty_full = load_intraday_with_ba(TY_CSV)
    es_px = es_full["PX_LAST"]
    ty_px = ty_full["PX_LAST"]
    mp1 = load_jk_mp1(); vix = load_vix_daily()
    print(f"    ES: {len(es_full)} ticks, span {es_full.index.min()} → {es_full.index.max()}")
    print(f"    TY: {len(ty_full)} ticks, span {ty_full.index.min()} → {ty_full.index.max()}")

    print("  building per-cell inputs with intraday L ...")
    inputs = {}
    for (leg, reg) in cfg13.ROBUST_CELLS:
        clusters = per_type[leg][reg]
        re_l, rb_l, s_l, zL, zV, zC = [], [], [], [], [], []
        for cl in clusters:
            ts_event = pd.Timestamp(cl["event"]["center"])
            if ts_event not in delta_curve_by_ts:
                continue
            d1, d2, d3 = delta_curve_by_ts[ts_event]
            if any(np.isnan([d1, d2, d3])):
                continue
            ctrls = cl.get("controls") or []
            if not ctrls:
                continue
            r_e_event = float(cl["event"]["r_e"]); r_b_event = float(cl["event"]["r_b"])
            df = np.array([d1, d2, d3], dtype=float) * BPS_TO_DECIMAL
            dpb_e = EPB.delta_pb_equity(df, rho=RHO_CENTRAL, tail="T0", N=N_HORIZON)
            dpb_b = BPB.delta_pb_bond(D_BOND, float(d3) * BPS_TO_DECIMAL)
            re_til = r_e_event - dpb_e
            rb_til = r_b_event - dpb_b
            day_event = ts_event.normalize()
            if leg == "FOMC":
                s = float(mp1.get(day_event, np.nan))
            else:
                s = float(me_by_ts.get(ts_event, np.nan))
            # L intraday: media Δspread ES+TY in bps
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
            "zL_intraday": np.array(zL, float),
            "zV_VIX": np.array(zV, float),
            "zC_corr": np.array(zC, float),
        }

    variants = [
        ("single_L_intraday", True, False, False),
        ("all_with_intraday_L", True, True, True),
    ]
    summary = {"task_timestamp": TASK_TIMESTAMP, "q": 0.10,
                "config_hash": cfg13.config_hash(),
                "spec": "L intraday Δspread ES+TY; q pre-registrato",
                "variants": {}}

    for label, useL, useV, useC in variants:
        cell_inputs = {}; candidate_proxies = {}; diag = {}
        for (leg, reg) in cfg13.ROBUST_CELLS:
            d = inputs[(leg, reg)]
            n0 = len(d["re"])
            conds = [~np.isnan(d["re"]), ~np.isnan(d["rb"]), ~np.isnan(d["surprise"])]
            if useL: conds.append(~np.isnan(d["zL_intraday"]))
            if useV: conds.append(~np.isnan(d["zV_VIX"]))
            if useC: conds.append(~np.isnan(d["zC_corr"]))
            mask = np.ones(n0, dtype=bool)
            for c in conds: mask &= c
            n1 = int(mask.sum())
            re_a = d["re"][mask]; rb_a = d["rb"][mask]; s_a = d["surprise"][mask]
            zL = d["zL_intraday"][mask] if useL else np.zeros(n1)
            zV = d["zV_VIX"][mask] if useV else np.zeros(n1)
            zC = d["zC_corr"][mask] if useC else np.zeros(n1)
            zL = np.nan_to_num(zL, nan=0.0)
            zV = np.nan_to_num(zV, nan=0.0)
            zC = np.nan_to_num(zC, nan=0.0)
            beta = float(beta_central_by_cell[(leg, reg)])
            cell_inputs[(leg, reg)] = {"r_e_tilde": re_a, "r_b_tilde": rb_a,
                                         "beta_str": beta, "surprise": s_a}
            candidate_proxies[(leg, reg)] = {
                "L": {"z": zL, "expected_sign": cfg13.EXPECTED_SIGN["L"]},
                "V": {"z": zV, "expected_sign": cfg13.EXPECTED_SIGN["V"]},
                "C": {"z": zC, "expected_sign": cfg13.EXPECTED_SIGN["C"]},
            }
            diag[f"{leg}/{reg}"] = {"n_before": n0, "n_after": n1}
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
        sub = OUT_DIR / label
        sub.mkdir(exist_ok=True)
        (sub / "verdicts.json").write_bytes(
            json.dumps({
                "variant": label, "q": 0.10,
                "active_proxies": {"L": useL, "V": useV, "C": useC},
                "verdicts": verdicts_clean,
                "by_crit": (out["by"].get("crit") if out["by"].get("crit") is not None else None),
                "by_c_m": out["by"]["c_m"],
                "by_family_size": out["by"]["family_size"],
                "n_third_channel_True": int(n_third),
                "passing_pairs": passing,
                "diagnostics_per_cell": diag,
            }, indent=2, sort_keys=True, default=str).encode("utf-8"))
        summary["variants"][label] = {
            "active_proxies": {"L": useL, "V": useV, "C": useC},
            "n_third_channel_True": int(n_third),
            "passing_pairs": passing,
            "by_crit": (out["by"].get("crit") if out["by"].get("crit") is not None else None),
            "diagnostics_per_cell": diag,
            "verdicts_per_pair": verdicts_clean,
        }
        print(f"\n  {label}: third_channel_True={n_third}/12  passing={passing}")
        for k, v in diag.items():
            print(f"    {k}: n_after={v['n_after']}/{v['n_before']}")

    # Manifest
    m = {
        "task": "terzo_canale_residuo_intraday_L_q010_pre_registered",
        "task_timestamp": TASK_TIMESTAMP,
        "seed_name": SEED_NAME,
        "config_hash": cfg13.config_hash(),
        "config_version": cfg13.CONFIG_VERSION,
        "q": 0.10,
        "note": (
            "Proxy L INTRADAY (Δspread bid-ask post-pre ES+TY medio bps). "
            "Sostituisce TED daily (discontinued 2022). Soglia q pre-registrata."
        ),
        "external_constants": {"D_bond": D_BOND, "dp_bar": DP_BAR,
                                 "rho_central": RHO_CENTRAL, "N_horizon": N_HORIZON},
        "proxy_provenance": {
            "L_intraday": {
                "method": "Δ(bid-ask spread bps) = mean(post 5min) − mean(pre 5min); media ES+TY.",
                "intraday_inputs": [
                    {"path": str(ES_CSV), "sha256": sha256_file(ES_CSV)},
                    {"path": str(TY_CSV), "sha256": sha256_file(TY_CSV)},
                ],
                "note": "Pre-window [t-15,t-10], post-window [t+10,t+15]; spread = (Ask-Bid)/PX_LAST × 10000.",
            },
            "V_VIX": {"path": str(VIXCLS_CSV), "sha256": sha256_file(VIXCLS_CSV),
                       "frequency": "daily"},
            "C_corr": {"method": "realized 5-min corr ES~TY on PREVIOUS trading day"},
        },
        "surprise_provenance": {
            "FOMC": f"MP1 (JK) — {sha256_file(JK_FOMC_CSV)}",
            "NFP_CPI": "m_e PC1 money-market dal CSV eventi v2 (fallback dichiarato)",
        },
        "variants_run": [v[0] for v in variants],
        "summary": summary,
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "pickle_07_sha256": sha256_file(PICKLE_AUTH_07),
    }
    (OUT_DIR / "intraday_L_manifest.json").write_bytes(
        json.dumps(m, indent=2, sort_keys=True, default=str).encode("utf-8"))
    print(f"\nDONE → {OUT_DIR}")
    for v in variants:
        s = summary["variants"][v[0]]
        print(f"  {v[0]:24s} third={s['n_third_channel_True']}/12  passing={s['passing_pairs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
