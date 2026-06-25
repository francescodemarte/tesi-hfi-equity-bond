"""tests_and_strategy_spec.py — Test statistici e di robustezza della strategia.

Output: results_tests.json con:
  - bootstrap Sharpe (B=10 000) per stimare SE e CI 95%
  - p-value contro H0: Sharpe=0 (test t one-sided su mean per-evento)
  - sensibilità soglie: p70 / p75 / p80
  - Sharpe annualizzato (per-evento × √n_per_year)
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
from scipy.stats import t as t_dist

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

EVENTS_CSV = ROOT/"DATASET_TESI/01_eventi_hfi/events_with_regime_classifier.csv"
CONT_CSV = Path("/home/francesco/TESI/Dati/calendari/contaminants_build_2026-06-22/contaminants_v2_2026-06-22.csv")
VIX_CSV = PKG07/"external_data/snapshots/VIXCLS.csv"
TPQE_CSV = Path("/home/francesco/TESI/Dati/external_data/altavilla_TPQE_factors.csv")
ALT_MEW = Path("/home/francesco/TESI/Dati/external_data/altavilla_eampd_monetary_event_window.csv")

TRAIN_START, TRAIN_END = pd.Timestamp("2010-01-01"), pd.Timestamp("2018-12-31")
TEST_START, TEST_END = pd.Timestamp("2019-01-01"), pd.Timestamp("2025-12-31")
TRAIN_YEARS = (TRAIN_END - TRAIN_START).days / 365.25
TEST_YEARS = (TEST_END - TEST_START).days / 365.25

TS = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
SEED = 20260624
B_BOOT = 10_000


def sharpe(a):
    a = np.asarray(a, float)
    if a.size < 2: return float("nan")
    s = float(a.std(ddof=1))
    return float(a.mean()/s) if s > 1e-12 else float("nan")


def bootstrap_sharpe(payoffs, B=B_BOOT, seed=SEED):
    """Bootstrap del Sharpe: B ricampionamenti con reinserimento, return CI 95% percentile + SE."""
    p = np.asarray(payoffs, float)
    n = p.size
    if n < 5: return {"n": n, "sharpe": sharpe(p), "se_boot": float("nan"),
                      "ci_low": float("nan"), "ci_high": float("nan"), "p_value_2sided": float("nan")}
    rng = np.random.default_rng(seed)
    samples = np.empty(B)
    for b in range(B):
        idx = rng.integers(0, n, n)
        samples[b] = sharpe(p[idx])
    samples = samples[~np.isnan(samples)]
    se = float(np.std(samples, ddof=1))
    ci_low = float(np.percentile(samples, 2.5))
    ci_high = float(np.percentile(samples, 97.5))
    # p-value bilaterale H0: Sharpe=0 (via t-stat su mean/std)
    t_stat = p.mean()/(p.std(ddof=1)/np.sqrt(n)) if p.std(ddof=1) > 0 else float("nan")
    p_val = float(2*(1 - t_dist.cdf(abs(t_stat), df=n-1))) if not np.isnan(t_stat) else float("nan")
    return {"n": n, "sharpe": sharpe(p), "se_boot": se,
              "ci_low": ci_low, "ci_high": ci_high, "p_value_2sided": p_val,
              "t_stat_mean": float(t_stat)}


def main():
    print(f"=== tests_and_strategy_spec.py — {TS} ===")

    # Setup
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

    vix = pd.read_csv(VIX_CSV)
    dc = next(c for c in vix.columns if c.lower() in ("date","observation_date"))
    vc = next(c for c in vix.columns if c != dc)
    vix[dc] = pd.to_datetime(vix[dc]).dt.normalize()
    vix[vc] = pd.to_numeric(vix[vc], errors="coerce")
    vix = vix.set_index(dc)[vc].dropna().sort_index()

    # NFP/neg payoffs
    rows = []
    for cl in per_type["NFP"]["neg"]:
        ts_event = pd.Timestamp(cl["event"]["center"])
        m_e = me_map.get(ts_event, np.nan)
        if np.isnan(m_e): continue
        d = ts_event.normalize().tz_convert(None)
        v = float(vix.loc[d]) if d in vix.index else np.nan
        if np.isnan(v): continue
        pos = SR14.position("NFP", float(m_e))
        pay = pos["size"]*(pos["sign_equity"]*float(cl["event"]["r_e"])
                            + pos["sign_bond"]*float(cl["event"]["r_b"]))
        rows.append({"date": d, "m_e": float(m_e), "vix": v, "payoff": float(pay)})
    df_nfp = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)

    # ECB QE → short DE30Y
    tpqe = pd.read_csv(TPQE_CSV); tpqe["date"] = pd.to_datetime(tpqe["date"]).dt.normalize()
    alt = pd.read_csv(ALT_MEW); alt["date"] = pd.to_datetime(alt["date"]).dt.normalize()
    ecb = tpqe.merge(alt[["date","DE30Y"]], on="date", how="left")
    ecb = ecb.dropna(subset=["QE","DE30Y"]).copy()
    # SEGNO PRE-REGISTRATO: dalla regressione β_QE=+1.07 → SHORT bond quando QE>0
    ecb["payoff"] = np.sign(ecb["QE"])*(ecb["DE30Y"]/100.0)

    df_nfp_tr = df_nfp[(df_nfp["date"]>=TRAIN_START)&(df_nfp["date"]<=TRAIN_END)]
    df_nfp_te = df_nfp[(df_nfp["date"]>=TEST_START)&(df_nfp["date"]<=TEST_END)]
    ecb_tr = ecb[(ecb["date"]>=TRAIN_START)&(ecb["date"]<=TRAIN_END)]
    ecb_te = ecb[(ecb["date"]>=TEST_START)&(ecb["date"]<=TEST_END)]

    # 1) Test sensibilità soglie p70 / p75 / p80
    print("\n--- Test 1: sensibilità soglie (training only) ---")
    sens = {}
    for q in (0.70, 0.75, 0.80):
        p_me = float(df_nfp_tr["m_e"].abs().quantile(q))
        p_vix = float(df_nfp_tr["vix"].quantile(q))
        p_qe = float(ecb_tr["QE"].abs().quantile(q))
        nfp_tr_f = df_nfp_tr[(df_nfp_tr["m_e"].abs()>=p_me)&(df_nfp_tr["vix"]<=p_vix)]
        nfp_te_f = df_nfp_te[(df_nfp_te["m_e"].abs()>=p_me)&(df_nfp_te["vix"]<=p_vix)]
        ecb_tr_f = ecb_tr[ecb_tr["QE"].abs()>=p_qe]
        ecb_te_f = ecb_te[ecb_te["QE"].abs()>=p_qe]
        # Pesi inverse-vol on training
        v_nfp = float(nfp_tr_f["payoff"].std(ddof=1))
        v_ecb = float(ecb_tr_f["payoff"].std(ddof=1))
        w_nfp = 1/v_nfp; w_ecb = 1/v_ecb; Z = w_nfp+w_ecb
        w_nfp/=Z; w_ecb/=Z
        def combine(nfp_df, ecb_df):
            a = pd.DataFrame({"date":nfp_df["date"],"p":w_nfp*nfp_df["payoff"]})
            b = pd.DataFrame({"date":ecb_df["date"],"p":w_ecb*ecb_df["payoff"]})
            return pd.concat([a,b]).sort_values("date")["p"].values
        sens[f"q{int(q*100)}"] = {
            "thresholds": {"p_abs_me": p_me, "p_vix": p_vix, "p_abs_qe": p_qe},
            "weights": {"NFP": w_nfp, "ECB": w_ecb},
            "NFP_filt_n": {"train": len(nfp_tr_f), "oos": len(nfp_te_f)},
            "ECB_filt_n": {"train": len(ecb_tr_f), "oos": len(ecb_te_f)},
            "NFP_sharpe": {"train": sharpe(nfp_tr_f["payoff"].values),
                            "oos": sharpe(nfp_te_f["payoff"].values)},
            "ECB_sharpe": {"train": sharpe(ecb_tr_f["payoff"].values),
                            "oos": sharpe(ecb_te_f["payoff"].values)},
            "portfolio_sharpe": {"train": sharpe(combine(nfp_tr_f, ecb_tr_f)),
                                  "oos": sharpe(combine(nfp_te_f, ecb_te_f))},
        }
        print(f"  q={int(q*100)}: nfp[tr/oos]={len(nfp_tr_f)}/{len(nfp_te_f)}  "
              f"ecb[tr/oos]={len(ecb_tr_f)}/{len(ecb_te_f)}  "
              f"portfolio_oos_sharpe={sens[f'q{int(q*100)}']['portfolio_sharpe']['oos']:+.4f}")

    # 2) Bootstrap Sharpe sul setup pre-registrato (q=0.75)
    print("\n--- Test 2: bootstrap Sharpe (B=10 000) sul setup baseline q=0.75 ---")
    p_me = float(df_nfp_tr["m_e"].abs().quantile(0.75))
    p_vix = float(df_nfp_tr["vix"].quantile(0.75))
    p_qe = float(ecb_tr["QE"].abs().quantile(0.75))
    nfp_tr_f = df_nfp_tr[(df_nfp_tr["m_e"].abs()>=p_me)&(df_nfp_tr["vix"]<=p_vix)]
    nfp_te_f = df_nfp_te[(df_nfp_te["m_e"].abs()>=p_me)&(df_nfp_te["vix"]<=p_vix)]
    ecb_tr_f = ecb_tr[ecb_tr["QE"].abs()>=p_qe]
    ecb_te_f = ecb_te[ecb_te["QE"].abs()>=p_qe]
    v_nfp = float(nfp_tr_f["payoff"].std(ddof=1))
    v_ecb = float(ecb_tr_f["payoff"].std(ddof=1))
    w_nfp = 1/v_nfp; w_ecb = 1/v_ecb; Z = w_nfp+w_ecb
    w_nfp/=Z; w_ecb/=Z
    a_tr = pd.DataFrame({"date":nfp_tr_f["date"],"p":w_nfp*nfp_tr_f["payoff"]})
    b_tr = pd.DataFrame({"date":ecb_tr_f["date"],"p":w_ecb*ecb_tr_f["payoff"]})
    port_tr = pd.concat([a_tr,b_tr]).sort_values("date")["p"].values
    a_te = pd.DataFrame({"date":nfp_te_f["date"],"p":w_nfp*nfp_te_f["payoff"]})
    b_te = pd.DataFrame({"date":ecb_te_f["date"],"p":w_ecb*ecb_te_f["payoff"]})
    port_te = pd.concat([a_te,b_te]).sort_values("date")["p"].values
    boot = {
        "NFP_filtered": {"train": bootstrap_sharpe(nfp_tr_f["payoff"].values),
                          "oos": bootstrap_sharpe(nfp_te_f["payoff"].values)},
        "ECB_filtered": {"train": bootstrap_sharpe(ecb_tr_f["payoff"].values),
                          "oos": bootstrap_sharpe(ecb_te_f["payoff"].values)},
        "Portfolio": {"train": bootstrap_sharpe(port_tr),
                       "oos": bootstrap_sharpe(port_te)},
    }
    for k, v in boot.items():
        print(f"  {k}:")
        for period in ("train","oos"):
            d = v[period]
            print(f"    {period}: Sharpe={d['sharpe']:+.4f}  SE_boot={d['se_boot']:.4f}  CI95=[{d['ci_low']:+.4f},{d['ci_high']:+.4f}]  p={d['p_value_2sided']:.4f}  n={d['n']}")

    # 3) Sharpe annualizzato
    print("\n--- Test 3: Sharpe annualizzato ---")
    ann = {}
    for k in ("NFP_filtered","ECB_filtered","Portfolio"):
        n_oos = boot[k]["oos"]["n"]
        n_per_year_oos = n_oos / TEST_YEARS
        sh_oos = boot[k]["oos"]["sharpe"]
        sh_ann = sh_oos * np.sqrt(n_per_year_oos) if not np.isnan(sh_oos) else float("nan")
        ann[k] = {"n_per_year_oos": float(n_per_year_oos),
                   "sharpe_oos_per_event": sh_oos,
                   "sharpe_oos_annualized": float(sh_ann)}
        print(f"  {k}: n/year_oos={n_per_year_oos:.2f}  Sharpe_oos_event={sh_oos:+.4f}  → annualized ≈ {sh_ann:+.4f}")

    payload = {
        "task_timestamp": TS, "seed": SEED, "B_bootstrap": B_BOOT,
        "training_years": float(TRAIN_YEARS), "oos_years": float(TEST_YEARS),
        "sensitivity_thresholds": sens,
        "bootstrap_baseline_q75": boot,
        "annualized_oos": ann,
        "strategy_specification": {
            "trade_1_NFP_neg_event_window": {
                "trigger": "Annuncio NFP, regime negativo (corr equity-bond < 0 su 63gg lag t-1)",
                "filters_pre_registered": ["|m_e| ≥ p75(training m_e abs)",
                                            "VIX_event ≤ p75(training VIX)"],
                "entry": "all'orario rilascio NFP (12:30 UTC primo venerdì del mese)",
                "exit": "T+15 min (event_window)",
                "position": "size = |β_str(NFP)|, sign_equity e sign_bond da strategy_rule.position(NFP, m_e)",
                "instruments": "ES (S&P 500 future) long/short, TY (UST 10Y future) long/short",
                "surprise": "m_e PC1 money-market dal CSV eventi (fallback)",
            },
            "trade_2_ECB_QE_short_DE30Y": {
                "trigger": "Annuncio ECB (decision o press), tutti i regimi (no filtro regime)",
                "filters_pre_registered": ["|QE| ≥ p75(training |QE|)"],
                "entry": "monetary event window Altavilla (combined PR+PC)",
                "exit": "close of event window (Altavilla MEW close)",
                "position": "sign(QE) × short Bund 30Y future (payoff = +sign(QE)·ΔDE30Y/100)",
                "instruments": "Bund 30Y future (Buxl FGBXc1) — proxy via ΔDE30Y daily",
                "surprise": "QE factor Altavilla (PC-rotation of ΔOIS_10Y press conference orth Target+Path)",
            },
            "portfolio": {
                "weights": "inverse-volatility on TRAINING (anti-look-ahead)",
                "rebalance": "static (pesi calibrati su training, applicati identicamente OOS)",
                "split": f"training {TRAIN_START.date()}..{TRAIN_END.date()}; OOS {TEST_START.date()}..{TEST_END.date()}",
            },
        },
        "data_sources": {
            "NFP cluster": "pickle autoritativo 07 (per_type[NFP][neg])",
            "m_e": "CSV eventi v2 (colonna m_e PC1 money-market)",
            "VIX": "FRED VIXCLS daily (snapshot 07)",
            "ECB QE": "altavilla_TPQE_factors.csv (estratto in questa sessione)",
            "ΔDE30Y": "altavilla_eampd_monetary_event_window.csv",
        },
        "caveats": [
            "Sharpe LORDO (no costi, slippage, leva, vincoli custodia).",
            "Sample piccolo (n=10-14 OOS per strategia, n=24 portafoglio OOS).",
            "Sharpe annualizzato = per-event × √(n/anno) — valido sotto i.i.d.",
            "Strategia richiede esecuzione su 2 mercati distinti (US futures + Bund futures).",
            "Soglia p75 è scelta a priori dalla letteratura (no ottimizzazione).",
        ],
    }
    (OUT/"results_tests.json").write_bytes(
        json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8"))
    print(f"\nDONE → {OUT}/results_tests.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
