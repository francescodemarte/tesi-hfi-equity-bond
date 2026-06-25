"""execute_15_concentrated.py — Strategia concentrata pre-registrata.

Disegno (a priori, prima di vedere risultati):
  - **Trade 1 — NFP/neg event_window**: posizione `strategy_rule.position("NFP", m_e)`,
    finestra ±15 min. Filtri: |m_e| ≥ p75(training), VIX_event ≤ p75(training VIX).
  - **Trade 2 — ECB QE → DE30Y**: posizione `sign(QE) * (-ΔDE30Y)` (β_QE=+1.07
    significa QE>0 → yield 30Y sale → prezzo scende, quindi SHORT 30Y). Filtri:
    |QE| ≥ p75(training).
  - **Pesi portafoglio**: inverse-vol su training-only.
  - **Split temporale (anti-look-ahead)**: training 2010-01-01..2018-12-31,
    OOS test 2019-01-01..2025-12-31.

Output: Sharpe IN-SAMPLE (training) e OOS (test) separati, per ciascuna
strategia e portafoglio. NIENTE selezione del migliore.
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
PKG07 = ROOT/"CODICI_TESI/07_protocollo_v2_signflip"
PKG14 = ROOT/"CODICI_TESI/14_strategie_event_driven"
sys.path.insert(0, str(PKG07))
import config as cfg07, data as data07, run as run07, windows as win07
for m in ("config","manifest"): sys.modules.pop(m, None)
sys.path.remove(str(PKG07))
sys.path.insert(0, str(PKG14))
import config as cfg14, strategy_rule as SR14

OUT = ROOT/"09_risultati/strategie_event_driven/concentrated"
OUT.mkdir(parents=True, exist_ok=True)

EVENTS_CSV = ROOT/"DATASET_TESI/01_eventi_hfi/events_with_regime_classifier.csv"
CONT_CSV = Path("/home/francesco/TESI/Dati/calendari/contaminants_build_2026-06-22/contaminants_v2_2026-06-22.csv")
VIX_CSV = PKG07/"external_data/snapshots/VIXCLS.csv"
TPQE_CSV = Path("/home/francesco/TESI/Dati/external_data/altavilla_TPQE_factors.csv")
ALT_MEW = Path("/home/francesco/TESI/Dati/external_data/altavilla_eampd_monetary_event_window.csv")

TRAIN_START = pd.Timestamp("2010-01-01")
TRAIN_END = pd.Timestamp("2018-12-31")
TEST_START = pd.Timestamp("2019-01-01")
TEST_END = pd.Timestamp("2025-12-31")

TS = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
SEED = "concentrated_strategy_2026-06-24"


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def sharpe(arr):
    a = np.asarray(arr, float)
    if a.size < 2: return float("nan")
    s = float(a.std(ddof=1))
    if s <= 1e-12: return float("nan")
    return float(a.mean()/s)


def main():
    print(f"=== execute_15_concentrated.py — {TS} ===")
    print(f"  Training: {TRAIN_START.date()}..{TRAIN_END.date()}")
    print(f"  OOS:      {TEST_START.date()}..{TEST_END.date()}")

    # 1) NFP/neg events dal pickle 07
    events_full = data07.load_events(EVENTS_CSV)
    prices = run07.load_prices()
    regs = run07.compute_regimes(prices)
    cont = set()
    with open(CONT_CSV) as f:
        for r in csv.DictReader(f): cont.add(pd.Timestamp(r["center_utc"]))
    reject = run07.build_calendar_reject(set(pd.to_datetime(events_full["timestamp"],utc=True)), cont)
    per_type, _ = run07.assemble(events_full, prices, regs, reject)
    per_type, _ = win07.dedup_shared_controls(per_type)

    me_df = pd.read_csv(EVENTS_CSV, usecols=["timestamp","m_e"])
    me_df["timestamp"] = pd.to_datetime(me_df["timestamp"], utc=True)
    me_map = dict(zip(me_df["timestamp"], me_df["m_e"]))

    # VIX daily
    vix = pd.read_csv(VIX_CSV)
    dc = next(c for c in vix.columns if c.lower() in ("date","observation_date"))
    vc = next(c for c in vix.columns if c != dc)
    vix[dc] = pd.to_datetime(vix[dc]).dt.normalize()
    vix[vc] = pd.to_numeric(vix[vc], errors="coerce")
    vix = vix.set_index(dc)[vc].dropna().sort_index()

    # NFP rows
    rows_nfp = []
    for cl in per_type["NFP"]["neg"]:
        ts_event = pd.Timestamp(cl["event"]["center"])
        m_e = me_map.get(ts_event, np.nan)
        if np.isnan(m_e): continue
        d = ts_event.normalize().tz_convert(None)
        v = float(vix.loc[d]) if d in vix.index else np.nan
        if np.isnan(v): continue
        # Payoff event_window: usa la regola pre-registrata del 14 (sign+sizing)
        pos = SR14.position("NFP", float(m_e))
        pay = pos["size"] * (pos["sign_equity"]*float(cl["event"]["r_e"]) +
                              pos["sign_bond"]*float(cl["event"]["r_b"]))
        rows_nfp.append({"date": d, "m_e": float(m_e), "vix": v, "payoff": float(pay)})
    df_nfp = pd.DataFrame(rows_nfp).sort_values("date").reset_index(drop=True)
    print(f"  NFP/neg eventi pre-filtro: {len(df_nfp)}")

    # Split
    df_nfp_tr = df_nfp[(df_nfp["date"]>=TRAIN_START)&(df_nfp["date"]<=TRAIN_END)].copy()
    df_nfp_te = df_nfp[(df_nfp["date"]>=TEST_START)&(df_nfp["date"]<=TEST_END)].copy()
    # Soglie pre-registrate sui dati TRAINING ONLY
    p75_abs_me = float(df_nfp_tr["m_e"].abs().quantile(0.75))
    p75_vix = float(df_nfp_tr["vix"].quantile(0.75))
    print(f"  NFP soglie training: |m_e|≥{p75_abs_me:.4f}  VIX≤{p75_vix:.2f}")

    def apply_nfp_filter(df):
        return df[(df["m_e"].abs() >= p75_abs_me) & (df["vix"] <= p75_vix)].copy()

    nfp_tr_filt = apply_nfp_filter(df_nfp_tr)
    nfp_te_filt = apply_nfp_filter(df_nfp_te)
    nfp_tr_unf = df_nfp_tr
    nfp_te_unf = df_nfp_te
    print(f"  NFP/neg: training n={len(nfp_tr_filt)}/{len(nfp_tr_unf)} | OOS n={len(nfp_te_filt)}/{len(nfp_te_unf)}")

    # 2) ECB QE → DE30Y
    tpqe = pd.read_csv(TPQE_CSV); tpqe["date"] = pd.to_datetime(tpqe["date"]).dt.normalize()
    alt = pd.read_csv(ALT_MEW); alt["date"] = pd.to_datetime(alt["date"]).dt.normalize()
    ecb = tpqe.merge(alt[["date","DE30Y"]], on="date", how="left")
    ecb = ecb.dropna(subset=["QE","DE30Y"]).copy()
    # Payoff: short DE30Y proporzionale a sign(QE), valore = -sign(QE) * ΔDE30Y in pp/100
    # (yield 30Y in pp; ΔDE30Y già in pp/100 per evento)
    # Regola pre-registrata dalla regressione β_QE=+1.07 a DE30Y (step 1):
    # QE>0 → yield 30Y sale → bond price scende → SHORT bond profitable
    # payoff(short bond) = +sign(QE) * (Δyield in pp/100) ≈ sign(QE) * ΔDE30Y
    ecb["payoff"] = np.sign(ecb["QE"]) * (ecb["DE30Y"] / 100.0)
    ecb_tr = ecb[(ecb["date"]>=TRAIN_START)&(ecb["date"]<=TRAIN_END)].copy()
    ecb_te = ecb[(ecb["date"]>=TEST_START)&(ecb["date"]<=TEST_END)].copy()
    p75_abs_qe = float(ecb_tr["QE"].abs().quantile(0.75))
    print(f"  ECB QE soglie training: |QE|≥{p75_abs_qe:.4f}")
    def apply_ecb_filter(df):
        return df[df["QE"].abs() >= p75_abs_qe].copy()
    ecb_tr_filt = apply_ecb_filter(ecb_tr)
    ecb_te_filt = apply_ecb_filter(ecb_te)
    print(f"  ECB QE: training n={len(ecb_tr_filt)}/{len(ecb_tr)} | OOS n={len(ecb_te_filt)}/{len(ecb_te)}")

    # 3) Sharpe per strategia e periodo
    metrics = {}
    for label, ev_tr, ev_te in (("NFP_event_window_filtered", nfp_tr_filt["payoff"].values, nfp_te_filt["payoff"].values),
                                  ("NFP_event_window_unfiltered", nfp_tr_unf["payoff"].values, nfp_te_unf["payoff"].values),
                                  ("ECB_QE_short_DE30Y_filtered", ecb_tr_filt["payoff"].values, ecb_te_filt["payoff"].values),
                                  ("ECB_QE_short_DE30Y_unfiltered", ecb_tr["payoff"].values, ecb_te["payoff"].values)):
        metrics[label] = {
            "training": {"n": int(len(ev_tr)), "mean": float(np.mean(ev_tr)) if len(ev_tr) else float("nan"),
                          "vol": float(np.std(ev_tr, ddof=1)) if len(ev_tr)>1 else float("nan"),
                          "sharpe": sharpe(ev_tr)},
            "oos": {"n": int(len(ev_te)), "mean": float(np.mean(ev_te)) if len(ev_te) else float("nan"),
                     "vol": float(np.std(ev_te, ddof=1)) if len(ev_te)>1 else float("nan"),
                     "sharpe": sharpe(ev_te)},
        }
    for label, m in metrics.items():
        print(f"\n  {label}:")
        for period in ("training","oos"):
            d = m[period]
            print(f"    {period:9s}: n={d['n']:3d}  Sharpe={d['sharpe']:+.4f}  mean={d['mean']:+.4e}  vol={d['vol']:.4e}")

    # 4) Portafoglio inverse-vol on training (filtered)
    nfp_tr_pay = nfp_tr_filt["payoff"].values
    ecb_tr_pay = ecb_tr_filt["payoff"].values
    vol_nfp = float(np.std(nfp_tr_pay, ddof=1)) if len(nfp_tr_pay)>1 else float("nan")
    vol_ecb = float(np.std(ecb_tr_pay, ddof=1)) if len(ecb_tr_pay)>1 else float("nan")
    w_nfp = (1/vol_nfp); w_ecb = (1/vol_ecb)
    Z = w_nfp + w_ecb
    w_nfp /= Z; w_ecb /= Z
    print(f"\n  Portafoglio inverse-vol training: w_NFP={w_nfp:.4f}, w_ECB={w_ecb:.4f}")

    # I due trade hanno date diverse → costruisco una time-series unica (concatenata sorted)
    def combine_series(nfp_df, ecb_df):
        a = pd.DataFrame({"date": nfp_df["date"], "p": w_nfp * nfp_df["payoff"]})
        b = pd.DataFrame({"date": ecb_df["date"], "p": w_ecb * ecb_df["payoff"]})
        c = pd.concat([a, b]).sort_values("date").reset_index(drop=True)
        return c["p"].values
    p_tr = combine_series(nfp_tr_filt, ecb_tr_filt)
    p_te = combine_series(nfp_te_filt, ecb_te_filt)
    portfolio = {
        "weights": {"NFP_filtered": w_nfp, "ECB_QE_DE30Y_filtered": w_ecb},
        "training": {"n": int(len(p_tr)), "mean": float(np.mean(p_tr)) if len(p_tr) else float("nan"),
                      "vol": float(np.std(p_tr, ddof=1)) if len(p_tr)>1 else float("nan"),
                      "sharpe": sharpe(p_tr)},
        "oos": {"n": int(len(p_te)), "mean": float(np.mean(p_te)) if len(p_te) else float("nan"),
                 "vol": float(np.std(p_te, ddof=1)) if len(p_te)>1 else float("nan"),
                 "sharpe": sharpe(p_te)},
    }
    print(f"\n  Portafoglio (filtered + inverse-vol training):")
    for period in ("training","oos"):
        d = portfolio[period]
        print(f"    {period:9s}: n={d['n']:3d}  Sharpe={d['sharpe']:+.4f}  mean={d['mean']:+.4e}  vol={d['vol']:.4e}")

    payload = {
        "task_timestamp": TS, "seed_name": SEED,
        "design": "Strategia concentrata pre-registrata: NFP/neg event_window filtered + ECB QE short DE30Y filtered, inverse-vol weighting on training.",
        "training_period": f"{TRAIN_START.date()}..{TRAIN_END.date()}",
        "oos_period": f"{TEST_START.date()}..{TEST_END.date()}",
        "thresholds_pre_registered_from_training": {
            "NFP_p75_abs_m_e": p75_abs_me,
            "NFP_p75_VIX": p75_vix,
            "ECB_p75_abs_QE": p75_abs_qe,
        },
        "per_strategy_metrics": metrics,
        "portfolio_inverse_vol": portfolio,
        "caveats": [
            "Sharpe LORDO (no costi, no slippage, no leva). NON Sharpe eseguibile.",
            "Soglie p75 calibrate SOLO sui dati training 2010-2018 (anti-look-ahead).",
            "Filtri applicati identicamente a training e OOS.",
            "ECB QE: 129/315 eventi totali hanno QE non-NaN (OIS_10Y_pc disponibile post-2007).",
            "Portafoglio combina serie di date diverse (NFP mensili + ECB ~8/anno).",
        ],
    }
    (OUT/"results.json").write_bytes(
        json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8"))
    print(f"\nDONE → {OUT}/results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
