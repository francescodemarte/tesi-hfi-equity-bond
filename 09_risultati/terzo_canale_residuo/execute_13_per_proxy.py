"""execute_13_per_proxy.py — Esecutore del 13 con 4 varianti (un proxy alla volta + all).

Riusa la pipeline costruita in execute_13.py ma esegue 4 sotto-run, ognuno
con UN proxy attivo alla volta + uno "all_active". Output in sub-namespace
separati. Stesso fix tz e parse del precedente.

Varianti (BY family resta a 12 per costruzione del kernel; quando un proxy
e' "zeros" la sua comunalita' fallisce per costruzione - effettivo m attivo
e' minore):

  - single_L_TED:    L=ΔTED daily, V=zeros, C=zeros
  - single_V_VIX:    L=zeros, V=ΔVIX daily, C=zeros
  - single_C_corr:   L=zeros, V=zeros, C=corr intraday ES~TY giorno prec.
  - all_active:      L=ΔTED, V=ΔVIX, C=corr intraday
  - baseline:        L=zeros, V=ΔVIX, C=corr intraday (riproduce il run iniziale)

Nota: TED daily termina il 2022-01-21; eventi post-2022 avranno z_L=NaN -> mask
li filtra dalla cella corrispondente (riportato).
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

OUT_ROOT = ROOT / "09_risultati" / "terzo_canale_residuo"
OUT_ROOT.mkdir(parents=True, exist_ok=True)

EVENTS_CSV = ROOT / "DATASET_TESI" / "01_eventi_hfi" / "events_with_regime_classifier.csv"
CONTAMINANTS_CSV = Path("/home/francesco/TESI/Dati/calendari/contaminants_build_2026-06-22/"
                         "contaminants_v2_2026-06-22.csv")
PICKLE_AUTH_07 = ROOT / "09_risultati" / "v2_signflip" / "result_authoritative.pkl"
JK_FOMC_CSV = Path("/home/francesco/TESI/Dati/external_data/jk_surprises_fomc.csv")
VIXCLS_CSV = PKG07 / "external_data" / "snapshots" / "VIXCLS.csv"
TED_CSV = Path("/home/francesco/TESI/Dati/external_data/TEDRATE.csv")
ES_CSV = Path("/home/francesco/TESI/Dati/data_processed/ESc1_1min.csv")
TY_CSV = Path("/home/francesco/TESI/Dati/data_processed/TYc1_1min.csv")

D_BOND = 8.970865529245179
DP_BAR = -3.85
N_HORIZON = 100
BPS_TO_DECIMAL = 1.0 / 10000.0
RHO_CENTRAL = EPB.rho_from_dp_bar(DP_BAR)

SEED_NAME_BASE = "terzo_canale_per_proxy_2026-06-24"
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


def load_ted_daily() -> pd.Series:
    df = pd.read_csv(TED_CSV)
    df["observation_date"] = pd.to_datetime(df["observation_date"]).dt.normalize().dt.tz_localize("UTC")
    df["TEDRATE"] = pd.to_numeric(df["TEDRATE"], errors="coerce")
    return df.set_index("observation_date")["TEDRATE"].dropna().sort_index()


def load_intraday(csv_p: Path, price_col: str = "PX_LAST") -> pd.Series:
    df = pd.read_csv(csv_p, usecols=["Datetime_UTC", price_col])
    df["Datetime_UTC"] = pd.to_datetime(df["Datetime_UTC"], utc=True)
    s = df.set_index("Datetime_UTC")[price_col].astype(float)
    return s[~s.index.duplicated(keep="first")].sort_index().dropna()


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


def build_inputs(per_type, delta_curve_by_ts, me_by_ts, mp1_by_date,
                 vix, ted, es, ty):
    """Costruisce per cella: (re, rb, surprise, zL_TED, zV_VIX, zC_corr) arrays."""
    out = {}
    diag = {}
    for (leg, reg) in cfg13.ROBUST_CELLS:
        clusters = per_type[leg][reg]
        re_l, rb_l, s_l, zL, zV, zC, ts_l = [], [], [], [], [], [], []
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
                s = float(mp1_by_date.get(day_event, np.nan))
            else:
                s = float(me_by_ts.get(ts_event, np.nan))
            zL.append(delta_at_index(ted, day_event))
            zV.append(delta_at_index(vix, day_event))
            zC.append(realized_corr_intraday(es, ty, day_event))
            re_l.append(re_til); rb_l.append(rb_til); s_l.append(s); ts_l.append(day_event)
        diag[f"{leg}/{reg}"] = {"raw": len(clusters), "after_curve_filter": len(re_l)}
        out[(leg, reg)] = {
            "re": np.array(re_l, float), "rb": np.array(rb_l, float),
            "surprise": np.array(s_l, float),
            "zL_TED": np.array(zL, float), "zV_VIX": np.array(zV, float),
            "zC_corr": np.array(zC, float),
            "ts": ts_l,
        }
    return out, diag


def variant_run(label, inputs, beta_central_by_cell,
                use_L, use_V, use_C):
    """Esegue 1 variante: per ogni cella sostituisce gli zL/zV/zC con zeros se
    NON usato. Mask basata SOLO sui proxy attivi (i 'zeros' non hanno NaN).
    Ritorna dict {output_pipe, diagnostics_per_cell}."""
    cell_inputs = {}; candidate_proxies = {}; diagnostics = {}
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
        # I non-usati: zeros (proxy_unavailable_in_this_variant)
        zL = np.nan_to_num(zL, nan=0.0)
        zV = np.nan_to_num(zV, nan=0.0)
        zC = np.nan_to_num(zC, nan=0.0)
        beta = float(beta_central_by_cell[(leg, reg)])
        cell_inputs[(leg, reg)] = {
            "r_e_tilde": re_a, "r_b_tilde": rb_a,
            "beta_str": beta, "surprise": s_a,
        }
        candidate_proxies[(leg, reg)] = {
            "L": {"z": zL, "expected_sign": cfg13.EXPECTED_SIGN["L"],
                  "active": use_L},
            "V": {"z": zV, "expected_sign": cfg13.EXPECTED_SIGN["V"],
                  "active": use_V},
            "C": {"z": zC, "expected_sign": cfg13.EXPECTED_SIGN["C"],
                  "active": use_C},
        }
        diagnostics[f"{leg}/{reg}"] = {"n_before_mask": n0, "n_after_mask": n1}
    out = PIPE13.run_full_protocol(cell_inputs, candidate_proxies, q=cfg13.BY_Q)
    return out, diagnostics


def main() -> int:
    print(f"=== execute_13_per_proxy.py — {TASK_TIMESTAMP} ===")
    print(f"  D_bond={D_BOND}, dp_bar={DP_BAR}, ρ={RHO_CENTRAL:.6f}, N={N_HORIZON}")

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

    print("  loading proxies (TED, VIX, ES, TY) + surprises ...")
    mp1 = load_jk_mp1(); vix = load_vix_daily(); ted = load_ted_daily()
    es = load_intraday(ES_CSV); ty = load_intraday(TY_CSV)
    print(f"    TED span {ted.index.min().date()} → {ted.index.max().date()}  n={len(ted)}")
    print(f"    VIX span {vix.index.min().date()} → {vix.index.max().date()}  n={len(vix)}")

    print("  building per-cell inputs ...")
    inputs, diag_raw = build_inputs(per_type, delta_curve_by_ts, me_by_ts, mp1,
                                      vix, ted, es, ty)
    for k, v in diag_raw.items():
        print(f"    {k}: raw={v['raw']} after_curve={v['after_curve_filter']}")

    variants = [
        ("single_L_TED", True, False, False),
        ("single_V_VIX", False, True, False),
        ("single_C_corr", False, False, True),
        ("all_active", True, True, True),
        ("baseline_LzerosVdailyCintraday", False, True, True),
    ]

    summary = {"task_timestamp": TASK_TIMESTAMP,
                "seed_base": SEED_NAME_BASE,
                "config_hash": cfg13.config_hash(),
                "variants": {}}

    for label, useL, useV, useC in variants:
        print(f"\n  variant {label} (L={useL}, V={useV}, C={useC}) ...")
        try:
            out, diag = variant_run(label, inputs, beta_central_by_cell,
                                      useL, useV, useC)
        except Exception as e:
            print(f"    FAIL: {type(e).__name__}: {e}")
            summary["variants"][label] = {"error": f"{type(e).__name__}: {e}",
                                            "diagnostics": diag if "diag" in dir() else None}
            continue
        n_third = sum(1 for v in out["verdicts"].values() if v["third_channel"])
        print(f"    n verdetti third_channel=True: {n_third}/12")
        for k, v in diag.items():
            print(f"      {k}: n_after={v['n_after_mask']}/{v['n_before_mask']}")

        # Salva sub-namespace
        sub = OUT_ROOT / label
        sub.mkdir(exist_ok=True)
        # verdicts
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
        (sub / "verdicts.json").write_bytes(
            json.dumps({
                "variant": label,
                "active_proxies": {"L": useL, "V": useV, "C": useC},
                "verdicts": verdicts_clean,
                "by_crit": (out["by"].get("crit") if out["by"].get("crit") is not None else None),
                "n_third_channel_True": int(n_third),
                "diagnostics_per_cell": diag,
            }, indent=2, sort_keys=True, default=str).encode("utf-8"))

        summary["variants"][label] = {
            "active_proxies": {"L": useL, "V": useV, "C": useC},
            "n_third_channel_True": int(n_third),
            "diagnostics_per_cell": diag,
            "verdicts_per_cell_candidate": verdicts_clean,
        }

    # Manifest globale
    m = {
        "task": "terzo_canale_residuo_per_proxy",
        "task_timestamp": TASK_TIMESTAMP,
        "config_hash": cfg13.config_hash(),
        "config_version": cfg13.CONFIG_VERSION,
        "spec_revision_applied": (
            "Patologia §2/§3 risolta — variante 'antisymmetric' (vedi sessione precedente). "
            "Sign rule: L=antisymmetric_pos_eq, V=antisymmetric_neg_eq, C=ambiguous."
        ),
        "external_constants": {"D_bond": D_BOND, "dp_bar": DP_BAR,
                                 "rho_central": RHO_CENTRAL, "N_horizon": N_HORIZON},
        "proxy_provenance": {
            "L_TED": {
                "path": str(TED_CSV),
                "sha256": sha256_file(TED_CSV),
                "fred_series": "TEDRATE",
                "span": "1986-01-02 to 2022-01-21",
                "frequency": "daily, deltaT applicato",
                "note": "TED discontinued 2022-01-21; eventi post-2022 → z_L=NaN → mask scarta",
            },
            "V_VIX": {
                "path": str(VIXCLS_CSV),
                "sha256": sha256_file(VIXCLS_CSV),
                "fred_series": "VIXCLS",
                "frequency": "daily, deltaT applicato",
                "note": "intraday VIX non disponibile → fallback daily",
            },
            "C_corr": {
                "method": "realized 5-min corr ES~TY on PREVIOUS trading day",
                "intraday_inputs": [str(ES_CSV), str(TY_CSV)],
                "backstep_days": 7,
            },
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
    (OUT_ROOT / "per_proxy_manifest.json").write_bytes(
        json.dumps(m, indent=2, sort_keys=True, default=str).encode("utf-8"))
    print(f"\nDONE → {OUT_ROOT}")
    print("  5 sub-namespace + per_proxy_manifest.json")
    for v in variants:
        s = summary["variants"].get(v[0], {})
        if "error" in s:
            print(f"  {v[0]:36s} ERROR: {s['error']}")
        else:
            print(f"  {v[0]:36s} third_channel_True = {s['n_third_channel_True']}/12")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
