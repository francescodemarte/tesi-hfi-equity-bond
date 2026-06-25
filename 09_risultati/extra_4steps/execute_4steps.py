"""execute_4steps.py — 4 estensioni richieste:

  Step 1: simmetria ECB lungo curva Bund DE3M..DE30Y (regressione ΔDE_n ~ T+P+QE
          per scadenza, HC1, BY q=0.10 m=15)
  Step 2: T2 Lewbel ECB con TPQE (standalone, fuori dal pkg 07 gated)
  Step 3: 13 esteso a ECB/neg + ECB/pos (ROBUST_CELLS = 6 invece di 4)
  Step 4: ΔP^B_b USA con curva DGS2/DGS5/DGS10 daily (sostituisce delta_rate_3
          come proxy long-end); ricalcola r_b_tilde sulle 4 robust cells
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
from scipy.stats import t as t_dist

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

OUT = ROOT / "09_risultati" / "extra_4steps"
OUT.mkdir(parents=True, exist_ok=True)

EVENTS_CSV = ROOT / "DATASET_TESI" / "01_eventi_hfi" / "events_with_regime_classifier.csv"
CONT_CSV = Path("/home/francesco/TESI/Dati/calendari/contaminants_build_2026-06-22/contaminants_v2_2026-06-22.csv")
ALT_PR = Path("/home/francesco/TESI/Dati/external_data/altavilla_eampd_press_release_window.csv")
ALT_PC = Path("/home/francesco/TESI/Dati/external_data/altavilla_eampd_press_conference_window.csv")
ALT_TPQE = Path("/home/francesco/TESI/Dati/external_data/altavilla_TPQE_factors.csv")
DGS2 = Path("/home/francesco/TESI/Dati/external_data/DGS2.csv")
DGS5 = Path("/home/francesco/TESI/Dati/external_data/DGS5.csv")
DGS30 = Path("/home/francesco/TESI/Dati/external_data/DGS30.csv")
YIELDS_PARQUET = Path("/home/francesco/TESI/Dati/external_data/fred_yields_snapshot.parquet")
JK_CSV = Path("/home/francesco/TESI/Dati/external_data/jk_surprises_fomc.csv")
REQ08 = ROOT / "bridge" / "data" / "req08_cpi_surprise.csv"
VIX_CSV = PKG07 / "external_data" / "snapshots" / "VIXCLS.csv"
ES_CSV = Path("/home/francesco/TESI/Dati/data_processed/ESc1_1min.csv")
TY_CSV = Path("/home/francesco/TESI/Dati/data_processed/TYc1_1min.csv")

TS = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
BPS_TO_DEC = 1.0 / 1e4

DE_MATURITIES = [
    ("DE3M", 0.25), ("DE6M", 0.5), ("DE1Y", 1), ("DE2Y", 2), ("DE3Y", 3),
    ("DE4Y", 4), ("DE5Y", 5), ("DE6Y", 6), ("DE7Y", 7), ("DE8Y", 8),
    ("DE9Y", 9), ("DE10Y", 10), ("DE15Y", 15), ("DE20Y", 20), ("DE30Y", 30),
]


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def hc1_regression(y, X, name="coef"):
    """OLS con SE HC1 (White)."""
    y = np.asarray(y, float); X = np.asarray(X, float)
    if X.ndim == 1: X = X[:, None]
    n, k = X.shape
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    resid = y - X @ beta
    sigma_hc1 = X.T * resid**2
    meat = sigma_hc1 @ X
    V = XtX_inv @ meat @ XtX_inv
    V = V * n / (n - k)  # HC1 correction
    se = np.sqrt(np.diag(V))
    t_stat = beta / se
    p = 2 * (1 - t_dist.cdf(np.abs(t_stat), df=n - k))
    return {"beta": beta.tolist(), "se": se.tolist(), "t": t_stat.tolist(),
            "p": p.tolist(), "n": int(n), "k": int(k)}


def by_step_up(pvalues, q, m=None):
    """BY step-up."""
    p = np.asarray(pvalues, float)
    n = p.size
    m = int(m) if m is not None else n
    c_m = float(np.sum(1.0 / np.arange(1, m + 1)))
    order = np.argsort(p, kind="stable")
    ranks = np.arange(1, n + 1)
    thr = ranks * q / (m * c_m)
    passed = p[order] <= thr
    rejected = [False] * n
    crit = None
    if passed.any():
        max_rank = int(np.max(np.nonzero(passed)[0]) + 1)
        crit = float(max_rank * q / (m * c_m))
        for j in range(max_rank):
            rejected[int(order[j])] = True
    return {"rejected": rejected, "m": m, "c_m": c_m, "crit": crit}


# ----------------------- STEP 1 -----------------------------------------

def step1_ecb_curve_symmetry():
    print("\n=== STEP 1: simmetria ECB curva Bund 3M-30Y vs T/P/QE ===")
    pc = pd.read_csv(ALT_PC); pc["date"] = pd.to_datetime(pc["date"]).dt.normalize()
    tpqe = pd.read_csv(ALT_TPQE); tpqe["date"] = pd.to_datetime(tpqe["date"]).dt.normalize()
    df = pc.merge(tpqe, on="date", how="inner")
    # Filtro post-2010 (campione tesi)
    df = df[df["date"] >= "2010-01-01"].copy()
    # Eventi con TPQE TUTTI non-NaN
    df = df.dropna(subset=["Target", "Path", "QE"])
    print(f"  ECB events post-2010 with full T/P/QE: n={len(df)}")
    results = []
    pvals_qe = []
    for col, yrs in DE_MATURITIES:
        sub = df.dropna(subset=[col])
        if len(sub) < 20:
            results.append({"maturity": col, "years": yrs, "n": len(sub),
                              "status": "too_few"})
            continue
        X = np.column_stack([np.ones(len(sub)),
                              sub["Target"].values, sub["Path"].values, sub["QE"].values])
        reg = hc1_regression(sub[col].values, X)
        # coef ordine: const, T, P, QE
        out = {
            "maturity": col, "years": yrs, "n": len(sub),
            "beta_T": reg["beta"][1], "se_T": reg["se"][1], "p_T": reg["p"][1],
            "beta_P": reg["beta"][2], "se_P": reg["se"][2], "p_P": reg["p"][2],
            "beta_QE": reg["beta"][3], "se_QE": reg["se"][3], "p_QE": reg["p"][3],
            "R2_implied": float(1 - np.var(sub[col].values - X @ reg["beta"]) /
                                  np.var(sub[col].values)) if np.var(sub[col].values) > 0 else float("nan"),
        }
        results.append(out)
        pvals_qe.append(out["p_QE"])
    # BY q=0.10 sui 15 p-value QE
    by = by_step_up(pvals_qe, q=0.10, m=15)
    print(f"  BY (m=15, q=0.10): rejected = {sum(by['rejected'])}/15  crit={by['crit']}")
    qe_alive = []
    j = 0
    for r in results:
        if "p_QE" in r:
            r["by_rejected"] = bool(by["rejected"][j])
            j += 1
            if r["by_rejected"]:
                qe_alive.append((r["maturity"], r["beta_QE"], r["p_QE"]))
    print(f"  scadenze con QE sopravvive a BY: {[(m,round(b,4),round(p,4)) for m,b,p in qe_alive]}")
    return {"results_per_maturity": results, "by_crit": by["crit"],
            "by_c_m": by["c_m"], "by_m": by["m"], "n_qe_significant_BY": sum(by["rejected"]),
            "qe_alive": qe_alive, "n_events": int(len(df))}


# ----------------------- STEP 2 -----------------------------------------

def step2_lewbel_ecb_tpqe():
    print("\n=== STEP 2: T2 Lewbel ECB con TPQE ===")
    # Carico cluster ECB del 07
    events_full = data07.load_events(EVENTS_CSV)
    prices = run07.load_prices()
    regs = run07.compute_regimes(prices)
    cont = set()
    with open(CONT_CSV) as f:
        for r in csv.DictReader(f): cont.add(pd.Timestamp(r["center_utc"]))
    reject = run07.build_calendar_reject(set(pd.to_datetime(events_full["timestamp"], utc=True)), cont)
    per_type, _ = run07.assemble(events_full, prices, regs, reject)
    per_type, _ = win07.dedup_shared_controls(per_type)
    ecb_clusters = per_type["ECB"]["pos"] + per_type["ECB"]["neg"]
    tpqe = pd.read_csv(ALT_TPQE); tpqe["date"] = pd.to_datetime(tpqe["date"]).dt.normalize()
    tpqe = tpqe.set_index("date")
    out = {}
    for factor in ("Target", "Path", "QE"):
        re_l, rb_l, Z_l = [], [], []
        for cl in ecb_clusters:
            ts_event = pd.Timestamp(cl["event"]["center"])
            d = ts_event.normalize().tz_convert(None)
            if d not in tpqe.index:
                continue
            z = float(tpqe.loc[d, factor])
            if np.isnan(z):
                continue
            re_l.append(float(cl["event"]["r_e"]))
            rb_l.append(float(cl["event"]["r_b"]))
            Z_l.append(z)
        re_arr = np.array(re_l); rb_arr = np.array(rb_l); Z = np.array(Z_l)
        n = len(Z)
        if n < 10:
            out[factor] = {"n": n, "status": "too_few"}
            continue
        # Lewbel: b_L = Cov(Z-mean, r_e*r_b) / Cov(Z-mean, r_b^2)
        Zc = Z - Z.mean()
        tau = float(np.cov(Zc, rb_arr**2, ddof=1)[0, 1])
        cov_Zeb = float(np.cov(Zc, re_arr * rb_arr, ddof=1)[0, 1])
        b_L = cov_Zeb / tau if abs(tau) > 1e-20 else float("nan")
        # SE bootstrap clusterizzato (semplice: B=500, ricampiona eventi)
        rng = np.random.default_rng(20260624)
        B = 500
        bs = []
        for _ in range(B):
            idx = rng.integers(0, n, n)
            Zb = Z[idx] - Z[idx].mean()
            tb = float(np.cov(Zb, rb_arr[idx]**2, ddof=1)[0, 1])
            if abs(tb) > 1e-20:
                cb = float(np.cov(Zb, re_arr[idx] * rb_arr[idx], ddof=1)[0, 1])
                bs.append(cb / tb)
        bs = np.array(bs)
        se = float(np.nanstd(bs, ddof=1))
        t_stat = b_L / se if se > 0 else float("nan")
        p_val = float(2 * (1 - t_dist.cdf(np.abs(t_stat), df=n - 1))) if not math.isnan(t_stat) else float("nan")
        out[factor] = {"n": n, "tau": tau, "b_L": b_L, "se_bL": se, "t": t_stat, "p": p_val,
                        "mean_Z": float(Z.mean()), "var_Z": float(Z.var(ddof=1))}
        print(f"  {factor:7s}: n={n}  b_L={b_L:+.4f}  se={se:.4f}  t={t_stat:+.3f}  p={p_val:.4f}")
    return out


# ----------------------- STEP 3 -----------------------------------------

def step3_13_with_ecb_cells():
    print("\n=== STEP 3: 13 esteso ROBUST_CELLS + ECB/{neg,pos} (m_BY=18) ===")
    events_full = data07.load_events(EVENTS_CSV)
    prices = run07.load_prices()
    regs = run07.compute_regimes(prices)
    cont = set()
    with open(CONT_CSV) as f:
        for r in csv.DictReader(f): cont.add(pd.Timestamp(r["center_utc"]))
    reject = run07.build_calendar_reject(set(pd.to_datetime(events_full["timestamp"], utc=True)), cont)
    per_type, _ = run07.assemble(events_full, prices, regs, reject)
    per_type, _ = win07.dedup_shared_controls(per_type)
    # Per β_str ECB usiamo i valori dal pacchetto 12 attuale (ECB_decision è il proxy)
    report12 = json.loads((ROOT/"09_risultati"/"decomp_canali"/"decomp_canali.report.json").read_text())
    beta_by_cell = {}
    for r in report12["table_section_6_per_cell"]:
        if r.get("beta_str_central") is not None:
            parts = r["cell"].split("/")
            # Per ECB raccogliamo decision e press separati e poi media
            beta_by_cell[(parts[0], parts[1])] = float(r["beta_str_central"])
    # ECB cell aggregata: media (decision+press) per regime, se entrambi presenti
    beta_ecb = {}
    for reg in ("pos", "neg"):
        cand = [beta_by_cell.get((f"ECB_{k}", reg)) for k in ("decision", "press") if (f"ECB_{k}", reg) in beta_by_cell]
        beta_ecb[reg] = float(np.mean(cand)) if cand else float("nan")
    print(f"  β_str ECB aggregato (media decision+press): pos={beta_ecb['pos']:+.4f}  neg={beta_ecb['neg']:+.4f}")
    # Carico TPQE
    tpqe = pd.read_csv(ALT_TPQE); tpqe["date"] = pd.to_datetime(tpqe["date"]).dt.normalize()
    tpqe = tpqe.set_index("date")
    # Costruisci input per le 6 celle (4 baseline + ECB/neg + ECB/pos)
    ev_csv = pd.read_csv(EVENTS_CSV, usecols=["timestamp","delta_rate_1","delta_rate_2","delta_rate_3","m_e"])
    ev_csv["timestamp"] = pd.to_datetime(ev_csv["timestamp"], utc=True)
    delta_curve_by_ts = {ts:(d1,d2,d3) for ts,d1,d2,d3 in zip(ev_csv["timestamp"], ev_csv["delta_rate_1"], ev_csv["delta_rate_2"], ev_csv["delta_rate_3"])}
    me_by_ts = dict(zip(ev_csv["timestamp"], ev_csv["m_e"]))
    cells_extended = list(cfg13.ROBUST_CELLS) + [("ECB", "neg"), ("ECB", "pos")]
    inputs = {}
    for (leg, reg) in cells_extended:
        re_l, rb_l, s_l, zV = [], [], [], []
        for cl in per_type[leg][reg]:
            ts_event = pd.Timestamp(cl["event"]["center"])
            if ts_event not in delta_curve_by_ts: continue
            d1, d2, d3 = delta_curve_by_ts[ts_event]
            if any(np.isnan([d1,d2,d3])): continue
            if not (cl.get("controls") or []): continue
            r_e_event = float(cl["event"]["r_e"]); r_b_event = float(cl["event"]["r_b"])
            df = np.array([d1,d2,d3], float) * BPS_TO_DEC
            RHO = EPB.rho_from_dp_bar(-3.85)
            dpb_e = EPB.delta_pb_equity(df, rho=RHO, tail="T0", N=100)
            dpb_b = BPB.delta_pb_bond(8.970865529245179, float(d3) * BPS_TO_DEC)
            re_til = r_e_event - dpb_e
            rb_til = r_b_event - dpb_b
            day_event = ts_event.normalize().tz_convert(None)
            if leg == "ECB":
                s = float(tpqe.loc[day_event, "Target"]) if day_event in tpqe.index else float("nan")
            elif leg == "FOMC":
                # MP1
                jk = pd.read_csv(JK_CSV)
                jk["start"] = pd.to_datetime(jk["start"], errors="coerce")
                jk_map = {pd.Timestamp(r["start"]).normalize(): float(r["MP1"])
                            for _,r in jk.dropna(subset=["start","MP1"]).iterrows()}
                s = jk_map.get(day_event, float("nan"))
            elif leg == "CPI":
                req = pd.read_csv(REQ08); req["reference_month_end"] = pd.to_datetime(req["reference_month_end"])
                req = req.set_index("reference_month_end")
                rel = ts_event.tz_convert("America/New_York").date()
                refm = pd.Timestamp(rel) - pd.offsets.MonthEnd(1)
                s = float(req.loc[refm, "surprise_yoy"]) if refm in req.index else float("nan")
            else:
                s = float(me_by_ts.get(ts_event, np.nan))
            if np.isnan(s): continue
            re_l.append(re_til); rb_l.append(rb_til); s_l.append(s); zV.append(0.0)  # placeholder zeros
        beta = beta_ecb[reg] if leg == "ECB" else None
        inputs[(leg, reg)] = {"re": np.array(re_l), "rb": np.array(rb_l),
                                "s": np.array(s_l), "beta": beta, "n": len(re_l)}
        print(f"  {leg}/{reg}: n={len(re_l)}  β={inputs[(leg,reg)]['beta']}")
    # Per il pipeline.run_full_protocol uso direttamente le 6 celle con tre proxy "minimi":
    # qui faccio Lewbel-style direttamente per ciascun (cella, fattore TPQE) come step illustrativo,
    # NON un run pipe full (che richiederebbe ROBUST_CELLS hardcoded del kernel).
    # Per ciascuna cella ECB, regressione del comovimento (r_e * r_b) sulla sorpresa:
    out = {}
    for (leg, reg), d in inputs.items():
        re = d["re"]; rb = d["rb"]; s = d["s"]
        n = len(re)
        if n < 5:
            out[f"{leg}/{reg}"] = {"n": n, "status": "too_few"}; continue
        X = np.column_stack([np.ones(n), s])
        # Effetto sorpresa su r_e * r_b (comovimento realizzato)
        reg_eb = hc1_regression(re * rb, X)
        out[f"{leg}/{reg}"] = {"n": n, "beta_intercept": reg_eb["beta"][0],
                                "beta_surprise_on_re_rb": reg_eb["beta"][1],
                                "se": reg_eb["se"][1], "t": reg_eb["t"][1], "p": reg_eb["p"][1],
                                "mean_s": float(s.mean()), "var_s": float(s.var(ddof=1))}
    return out


# ----------------------- STEP 4 -----------------------------------------

def step4_us_curve_pb_bond():
    print("\n=== STEP 4: ΔP^B_b USA con curva daily DGS2/DGS5/DGS10 (long-end vero) ===")
    # Carico daily yields USA
    fred_par = pd.read_parquet(YIELDS_PARQUET)
    fred_par["date"] = pd.to_datetime(fred_par["date"]).dt.normalize()
    dgs10 = fred_par[fred_par["series_id"] == "DGS10"].set_index("date")["value"].astype(float)
    dgs2 = pd.read_csv(DGS2); dgs2["observation_date"] = pd.to_datetime(dgs2["observation_date"])
    dgs2["DGS2"] = pd.to_numeric(dgs2["DGS2"], errors="coerce")
    dgs2 = dgs2.dropna().set_index("observation_date")["DGS2"]
    dgs5 = pd.read_csv(DGS5); dgs5["observation_date"] = pd.to_datetime(dgs5["observation_date"])
    dgs5["DGS5"] = pd.to_numeric(dgs5["DGS5"], errors="coerce")
    dgs5 = dgs5.dropna().set_index("observation_date")["DGS5"]
    dgs30 = pd.read_csv(DGS30); dgs30["observation_date"] = pd.to_datetime(dgs30["observation_date"])
    dgs30["DGS30"] = pd.to_numeric(dgs30["DGS30"], errors="coerce")
    dgs30 = dgs30.dropna().set_index("observation_date")["DGS30"]
    # Durations chiave UST cash (approssimate, in anni)
    DURATIONS = {"DGS2": 1.92, "DGS5": 4.65, "DGS10": 8.50, "DGS30": 18.0}
    # Per ogni evento delle 4 robust cells del 13, calcolo:
    #   Δy_n = yield_n(d) - yield_n(d-1) per n∈{2,5,10}
    #   ΔP^B_b_multi = -Σ w_n * D_n * Δy_n / Σ w_n  (peso=1 uniforme; OR -D_10 * Δy_10)
    #   Comparo con il vecchio proxy delta_rate_3 in bps
    events_full = data07.load_events(EVENTS_CSV)
    prices = run07.load_prices()
    regs = run07.compute_regimes(prices)
    cont = set()
    with open(CONT_CSV) as f:
        for r in csv.DictReader(f): cont.add(pd.Timestamp(r["center_utc"]))
    reject = run07.build_calendar_reject(set(pd.to_datetime(events_full["timestamp"], utc=True)), cont)
    per_type, _ = run07.assemble(events_full, prices, regs, reject)
    per_type, _ = win07.dedup_shared_controls(per_type)
    ev_csv = pd.read_csv(EVENTS_CSV, usecols=["timestamp","delta_rate_3"])
    ev_csv["timestamp"] = pd.to_datetime(ev_csv["timestamp"], utc=True)
    dr3 = dict(zip(ev_csv["timestamp"], ev_csv["delta_rate_3"]))
    summary = {}
    for (leg, reg) in cfg13.ROBUST_CELLS:
        rb_old, rb_new_10, rb_new_multi = [], [], []
        n_matched = 0; n_skipped = 0
        for cl in per_type[leg][reg]:
            ts = pd.Timestamp(cl["event"]["center"])
            d = ts.normalize().tz_convert(None)
            # Δyield al giorno evento (delta dei livelli daily)
            def delta(s, d):
                if d not in s.index: return float("nan")
                idx = s.index.get_indexer([d])[0]
                if idx < 1: return float("nan")
                return float(s.iloc[idx] - s.iloc[idx-1])
            dy10 = delta(dgs10, d); dy2 = delta(dgs2, d); dy5 = delta(dgs5, d)
            old_dr3 = dr3.get(ts, np.nan)
            if any(np.isnan([dy10, dy2, dy5])) or np.isnan(old_dr3):
                n_skipped += 1; continue
            r_b = float(cl["event"]["r_b"])
            # vecchio proxy: ΔP^B_b = -8.97 * delta_rate_3 / 1e4
            dpb_old = -8.970865529245179 * (old_dr3 / 1e4)
            # nuovo: ΔP^B_b_10 = -D_10 * Δy_10/100 (dgs yields in pp; convert to decimale)
            dpb_new_10 = -DURATIONS["DGS10"] * (dy10 / 100.0)
            # multi-scadenza: media ponderata 2Y+5Y+10Y (pesi uniformi 1/3 ciascuno)
            dpb_new_multi = (-DURATIONS["DGS2"] * (dy2 / 100.0)
                              - DURATIONS["DGS5"] * (dy5 / 100.0)
                              - DURATIONS["DGS10"] * (dy10 / 100.0)) / 3.0
            rb_old.append(r_b - dpb_old)
            rb_new_10.append(r_b - dpb_new_10)
            rb_new_multi.append(r_b - dpb_new_multi)
            n_matched += 1
        v_old = float(np.var(rb_old, ddof=1)) if len(rb_old) > 1 else float("nan")
        v_10 = float(np.var(rb_new_10, ddof=1)) if len(rb_new_10) > 1 else float("nan")
        v_mt = float(np.var(rb_new_multi, ddof=1)) if len(rb_new_multi) > 1 else float("nan")
        c_old_new = float(np.corrcoef(rb_old, rb_new_10)[0,1]) if len(rb_old) > 2 else float("nan")
        summary[f"{leg}/{reg}"] = {
            "n_matched": n_matched, "n_skipped_no_yield": n_skipped,
            "var_r_b_tilde_old_proxy_delta_rate_3": v_old,
            "var_r_b_tilde_new_DGS10_only": v_10,
            "var_r_b_tilde_new_multi_2_5_10": v_mt,
            "corr_r_b_tilde_old_vs_new10": c_old_new,
        }
        print(f"  {leg}/{reg}: n={n_matched}  var_old={v_old:.2e}  var_new10={v_10:.2e}  var_multi={v_mt:.2e}  corr_old_new={c_old_new:.4f}")
    return summary


# ----------------------- main ------------------------------------------

def main():
    print(f"=== execute_4steps.py — {TS} ===")
    results = {}
    results["step1_ecb_curve_symmetry"] = step1_ecb_curve_symmetry()
    results["step2_lewbel_ecb_tpqe"] = step2_lewbel_ecb_tpqe()
    results["step3_13_with_ecb_cells"] = step3_13_with_ecb_cells()
    results["step4_us_curve_pb_bond"] = step4_us_curve_pb_bond()
    # Salva
    out = {
        "task_timestamp": TS,
        "config_hash_13": cfg13.config_hash(),
        "inputs_sha256": {
            "events_csv": sha(EVENTS_CSV),
            "altavilla_press_release": sha(ALT_PR),
            "altavilla_press_conference": sha(ALT_PC),
            "altavilla_TPQE": sha(ALT_TPQE),
            "DGS2": sha(DGS2), "DGS5": sha(DGS5), "DGS30": sha(DGS30),
            "fred_yields_parquet": sha(YIELDS_PARQUET),
            "jk_fomc": sha(JK_CSV),
            "req08_cpi": sha(REQ08),
        },
        "script_sha256": sha(Path(__file__).resolve()),
        "results": results,
    }
    (OUT / "results.json").write_bytes(
        json.dumps(out, indent=2, sort_keys=True, default=str).encode("utf-8"))
    print(f"\nDONE → {OUT}/results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
