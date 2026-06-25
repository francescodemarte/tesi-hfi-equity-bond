"""execute_13.py — Esecutore pacchetto 13 (terzo canale residuo).

Pre-requisiti soddisfatti (in sessione precedente, stesso ricercatore):
  - Patologia §2/§3 risolta con variante "antisymmetric" (config.EXPECTED_SIGN
    aggiornato a antisymmetric_pos_eq / antisymmetric_neg_eq / ambiguous).
  - Suite del 13: 40 passed, 0 xfailed (osservato).

Strategia di costruzione input (sui 4 robust cells):
  - r_e_tilde, r_b_tilde, β_str: ricostruiti dal punto centrale (T0, dp_bar=-3.85,
    ρ calibrato) del package 12, riusando cluster del 07 (coerenza inter-pacchetto).
  - surprise per cella:
      FOMC → MP1 da jk_surprises_fomc.csv (Jarociński-Karadi), allineato per data.
      NFP/CPI → m_e PC1 money-market dal CSV eventi (fallback dichiarato).
  - Proxy:
      L → proxy_unavailable. La pipeline richiede tutti e 3 i candidati, quindi
          passo `z = zeros` per L con label esplicita `proxy_unavailable` nel
          manifest. Comunalità tecnicamente fallisce per costruzione (λ=0,p=1).
      V → ΔVIXCLS daily (fallback daily dichiarato; intraday non disponibile).
      C → corr realizzata intraday ES~TY su giorno trading PRECEDENTE l'evento
          (5 min log-returns su 9:30-16:00 ET, finestra US trading hours).
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/francesco/TESI/tesi-hfi-equity-bond")
PKG07 = ROOT / "CODICI_TESI" / "07_protocollo_v2_signflip"
PKG12 = ROOT / "CODICI_TESI" / "12_decomposizione_canali"
PKG13 = ROOT / "CODICI_TESI" / "13_terzo_canale_residuo"

# --- Import sequenziale dei tre package con gestione collisione `config`. ---
# 07 per primo: i suoi run/windows/data binda il proprio config.
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
import netting as NET            # noqa: E402

for m in ("config", "manifest"):
    sys.modules.pop(m, None)
sys.path.remove(str(PKG12))
sys.path.insert(0, str(PKG13))
import config as cfg13           # noqa: E402
import manifest as MF13          # noqa: E402
import pipeline as PIPE13        # noqa: E402
import sensitivity as SENS13     # noqa: E402
import whitening as WHITE13      # noqa: E402

# Sanity: gli alias devono essere quelli giusti.
assert cfg07.MASTER_SEED == cfg12.MASTER_SEED == cfg13.MASTER_SEED == 20260621
assert tuple(cfg13.CANDIDATES) == ("L", "V", "C")
assert cfg13.EXPECTED_SIGN["L"] == "antisymmetric_pos_eq"

OUT_DIR = ROOT / "09_risultati" / "terzo_canale_residuo"
OUT_DIR.mkdir(parents=True, exist_ok=True)

EVENTS_CSV = ROOT / "DATASET_TESI" / "01_eventi_hfi" / "events_with_regime_classifier.csv"
CONTAMINANTS_CSV = Path("/home/francesco/TESI/Dati/calendari/contaminants_build_2026-06-22/"
                         "contaminants_v2_2026-06-22.csv")
PICKLE_AUTH_07 = ROOT / "09_risultati" / "v2_signflip" / "result_authoritative.pkl"
JK_FOMC_CSV = Path("/home/francesco/TESI/Dati/external_data/jk_surprises_fomc.csv")
VIXCLS_CSV = PKG07 / "external_data" / "snapshots" / "VIXCLS.csv"
TED_CSV = Path("/home/francesco/TESI/Dati/external_data/TEDRATE.csv")
ES_CSV = Path("/home/francesco/TESI/Dati/data_processed/ESc1_1min.csv")
TY_CSV = Path("/home/francesco/TESI/Dati/data_processed/TYc1_1min.csv")

# Costanti pre-registrate (allineate al run 12)
D_BOND = 8.970865529245179
DP_BAR = -3.85
N_HORIZON = 100
BPS_TO_DECIMAL = 1.0 / 10000.0
RHO_CENTRAL = EPB.rho_from_dp_bar(DP_BAR)

SEED_NAME = "terzo_canale_run_2026-06-23"
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
    """Carica MP1 (JK surprise) per ciascuna data FOMC. Key: pd.Timestamp UTC normalized."""
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
        # Chiavi tz-aware UTC (allineate al ts_event della pipeline 07)
        d = pd.Timestamp(r["start"]).normalize()
        d_utc = d.tz_localize("UTC") if d.tz is None else d.tz_convert("UTC")
        out[d_utc] = float(val)
    return out


def load_vix_daily() -> pd.Series:
    df = pd.read_csv(VIXCLS_CSV)
    date_col = next(c for c in df.columns if c.lower() in ("date", "observation_date"))
    val_col = next(c for c in df.columns if c != date_col)
    # tz-aware UTC normalizzato (allineato al day_event della pipeline)
    df[date_col] = pd.to_datetime(df[date_col]).dt.normalize().dt.tz_localize("UTC")
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    return df.set_index(date_col)[val_col].dropna().sort_index()


def load_intraday(csv: Path, price_col: str = "PX_LAST") -> pd.Series:
    df = pd.read_csv(csv, usecols=["Datetime_UTC", price_col])
    df["Datetime_UTC"] = pd.to_datetime(df["Datetime_UTC"], utc=True)
    s = df.set_index("Datetime_UTC")[price_col].astype(float)
    return s[~s.index.duplicated(keep="first")].sort_index().dropna()


def daily_log_returns_from_5min(prices: pd.Series, day: pd.Timestamp) -> np.ndarray:
    """Log-returns 5-min su un giorno (UTC). Approx finestra trading: 14:30-21:00 UTC."""
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
    # Aggregato 5-min con .resample
    r5 = np.log(w.resample("5min").last()).diff().dropna().to_numpy()
    return r5


def realized_corr_intraday(es: pd.Series, ty: pd.Series,
                            day_eve: pd.Timestamp) -> float:
    """Corr equity-bond intraday 5-min sul giorno trading PRECEDENTE day_eve."""
    prev = pd.Timestamp(day_eve) - pd.Timedelta(days=1)
    # back-step fino a trovare un giorno con dati
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


def delta_pb_equity_central(delta_f_decimal: np.ndarray) -> float:
    """ΔP^B equity al PUNTO CENTRALE T0, ρ calibrato (dp_bar=-3.85, N=100)."""
    return EPB.delta_pb_equity(delta_f_decimal, rho=RHO_CENTRAL,
                                tail="T0", N=N_HORIZON)


def main() -> int:
    print(f"=== execute_13.py — {TASK_TIMESTAMP} ===")
    print(f"  D_bond={D_BOND}, dp_bar={DP_BAR}, ρ={RHO_CENTRAL:.6f}, N={N_HORIZON}")

    # 1) CSV eventi (delta_rate_*, m_e) e mappa per timestamp
    ev_csv = pd.read_csv(EVENTS_CSV, usecols=["timestamp", "event_class", "date",
                                                "delta_rate_1", "delta_rate_2",
                                                "delta_rate_3", "m_e"])
    ev_csv["timestamp"] = pd.to_datetime(ev_csv["timestamp"], utc=True)
    ev_csv["date"] = pd.to_datetime(ev_csv["date"]).dt.normalize()
    delta_curve_by_ts = {ts: (d1, d2, d3) for ts, d1, d2, d3 in
                          zip(ev_csv["timestamp"], ev_csv["delta_rate_1"],
                              ev_csv["delta_rate_2"], ev_csv["delta_rate_3"])}
    me_by_ts = dict(zip(ev_csv["timestamp"], ev_csv["m_e"]))
    date_by_ts = dict(zip(ev_csv["timestamp"], ev_csv["date"]))

    # 2) Ricostruisco cluster del 07
    print("  reconstructing 07 clusters ...")
    events_full = data07.load_events(EVENTS_CSV)
    prices = run07.load_prices()
    regs = run07.compute_regimes(prices)
    cont = load_contaminant_centers(CONTAMINANTS_CSV)
    ev_centers = set(pd.to_datetime(events_full["timestamp"], utc=True))
    reject = run07.build_calendar_reject(ev_centers, cont)
    per_type, _accounting = run07.assemble(events_full, prices, regs, reject)
    per_type, dedup = win07.dedup_shared_controls(per_type)
    print(f"    dedup_shared: {dedup}")

    # 3) β_str centrali dal pacchetto 12 (estratti dal report)
    report12 = json.loads((ROOT / "09_risultati" / "decomp_canali"
                            / "decomp_canali.report.json").read_text())
    beta_central_by_cell = {}
    for r in report12["table_section_6_per_cell"]:
        if r.get("beta_str_central") is not None:
            parts = r["cell"].split("/")
            # Formato attuale: "leg/regime/regime" (3 token) — prendo (leg, regime)
            key = (parts[0], parts[1])
            beta_central_by_cell[key] = float(r["beta_str_central"])
    print(f"    β_str centrale (dal 12): { {f'{k[0]}/{k[1]}': round(v,4) for k,v in beta_central_by_cell.items()} }")

    # 4) Carico sorprese e proxy
    print("  loading surprises + proxy data ...")
    mp1_by_date = load_jk_mp1()
    vix = load_vix_daily()
    print(f"    VIX daily n={len(vix)}, span {vix.index.min().date()} → {vix.index.max().date()}")
    print("  loading intraday ES, TY (per C proxy) ...")
    es = load_intraday(ES_CSV); ty = load_intraday(TY_CSV)
    print(f"    ES: {len(es)} ticks  TY: {len(ty)} ticks")

    # 5) Per ciascuna ROBUST_CELL costruisco gli input + 3 proxy
    cell_inputs = {}
    candidate_proxies = {}
    diagnostics_per_cell = {}
    surprise_provenance = {}

    for (leg, reg) in cfg13.ROBUST_CELLS:
        clusters = per_type[leg][reg]
        if (leg, reg) not in beta_central_by_cell:
            raise SystemExit(f"β_str centrale mancante per {leg}/{reg}")
        beta_str = beta_central_by_cell[(leg, reg)]

        r_e_tilde_list, r_b_tilde_list = [], []
        z_L, z_V, z_C, surprise_list = [], [], [], []
        n_skipped = {"no_curve": 0, "no_dates": 0, "no_controls": 0,
                      "no_vix": 0, "no_corr": 0}
        for cl in clusters:
            ts_event = pd.Timestamp(cl["event"]["center"])
            if ts_event not in delta_curve_by_ts:
                n_skipped["no_curve"] += 1; continue
            d1, d2, d3 = delta_curve_by_ts[ts_event]
            if any(np.isnan([d1, d2, d3])):
                n_skipped["no_curve"] += 1; continue
            ctrls = cl.get("controls") or []
            if not ctrls:
                n_skipped["no_controls"] += 1; continue
            # r_e/r_b_event al punto centrale
            r_e_event = float(cl["event"]["r_e"])
            r_b_event = float(cl["event"]["r_b"])
            delta_f_dec = np.array([d1, d2, d3], dtype=float) * BPS_TO_DECIMAL
            dpb_e = delta_pb_equity_central(delta_f_dec)
            dpb_b = BPB.delta_pb_bond(D_BOND, float(d3) * BPS_TO_DECIMAL)
            r_e_til = r_e_event - dpb_e
            r_b_til = r_b_event - dpb_b
            r_e_tilde_list.append(r_e_til)
            r_b_tilde_list.append(r_b_til)
            # Sorpresa
            day_event = ts_event.normalize()
            if leg == "FOMC":
                surprise_list.append(float(mp1_by_date.get(day_event, np.nan)))
            else:
                surprise_list.append(float(me_by_ts.get(ts_event, np.nan)))
            # V proxy: ΔVIX daily
            if day_event in vix.index:
                # idx t / t-1
                idx_t = vix.index.get_indexer([day_event])[0]
                if idx_t > 0:
                    z_V.append(float(vix.iloc[idx_t] - vix.iloc[idx_t - 1]))
                else:
                    z_V.append(float("nan")); n_skipped["no_vix"] += 1
            else:
                z_V.append(float("nan")); n_skipped["no_vix"] += 1
            # C proxy: corr realizzata intraday giorno prec
            zc = realized_corr_intraday(es, ty, day_event)
            z_C.append(zc)
            if not math.isfinite(zc):
                n_skipped["no_corr"] += 1
            # L proxy: zeros (proxy_unavailable)
            z_L.append(0.0)

        # Pulizia: filtro righe con NaN nei vettori principali (per la pipeline)
        re_arr = np.array(r_e_tilde_list, dtype=float)
        rb_arr = np.array(r_b_tilde_list, dtype=float)
        s_arr = np.array(surprise_list, dtype=float)
        zL_arr = np.array(z_L, dtype=float)
        zV_arr = np.array(z_V, dtype=float)
        zC_arr = np.array(z_C, dtype=float)
        # Diagnostica delle 5 sotto-condizioni della mask
        cond = {
            "re_ok": ~np.isnan(re_arr), "rb_ok": ~np.isnan(rb_arr),
            "surprise_ok": ~np.isnan(s_arr), "zV_ok": ~np.isnan(zV_arr),
            "zC_ok": ~np.isnan(zC_arr),
        }
        n_before = len(re_arr)
        for k, m in cond.items():
            print(f"      {leg}/{reg} cond[{k}] OK={int(m.sum())}/{n_before}")
        mask = (cond["re_ok"] & cond["rb_ok"] & cond["surprise_ok"]
                & cond["zV_ok"] & cond["zC_ok"])
        n_after = int(mask.sum())
        re_arr = re_arr[mask]; rb_arr = rb_arr[mask]; s_arr = s_arr[mask]
        zL_arr = zL_arr[mask]; zV_arr = zV_arr[mask]; zC_arr = zC_arr[mask]

        diagnostics_per_cell[f"{leg}/{reg}"] = {
            "n_clusters_in_pickle": len(clusters),
            "n_skipped_raw": n_skipped,
            "n_before_mask": int(n_before),
            "n_after_mask": int(n_after),
            "n_final": int(n_after),
            "beta_str_central_from_12": float(beta_str),
        }
        surprise_provenance[f"{leg}/{reg}"] = (
            "MP1 Jarociński–Karadi (jk_surprises_fomc.csv)" if leg == "FOMC"
            else "m_e PC1 money-market dal CSV eventi v2 (fallback dichiarato)"
        )
        cell_inputs[(leg, reg)] = {
            "r_e_tilde": re_arr, "r_b_tilde": rb_arr,
            "beta_str": float(beta_str), "surprise": s_arr,
        }
        candidate_proxies[(leg, reg)] = {
            "L": {"z": zL_arr, "expected_sign": cfg13.EXPECTED_SIGN["L"],
                  "frequency": "proxy_unavailable",
                  "note": "no bid-ask intraday + no TED daily; passato zeros per soddisfare contract API; comunalità fallisce per costruzione."},
            "V": {"z": zV_arr, "expected_sign": cfg13.EXPECTED_SIGN["V"],
                  "frequency": "daily (ΔVIXCLS, fallback dichiarato; intraday non disponibile)"},
            "C": {"z": zC_arr, "expected_sign": cfg13.EXPECTED_SIGN["C"],
                  "frequency": "intraday (corr ES~TY 5-min realizzata sul giorno trading precedente)"},
        }
        print(f"    {leg}/{reg}: n={n_after} (was {n_before}); β_str={beta_str:.4f}")

    # 6) Esegui pipeline.run_full_protocol
    print("  pipeline.run_full_protocol ...")
    out = PIPE13.run_full_protocol(cell_inputs, candidate_proxies,
                                     q=cfg13.BY_Q)
    print(f"    BY family size = {out['by']['family_size']}, c_m = {out['by']['c_m']:.4f}")
    n_third = sum(1 for v in out["verdicts"].values() if v["third_channel"])
    print(f"    n verdetti third_channel=True: {n_third}/12")

    # 7) Diagnostiche: sensitivity, whiteness per cella
    sensitivity_per_cell = {}
    whiteness_per_cell = {}
    for (leg, reg) in cfg13.ROBUST_CELLS:
        # sensitivity richiede F_MOP della cella → la prendo dal report 12
        F_MOP = None
        for r in report12["table_section_6_per_cell"]:
            if tuple(r["cell"].split("/")) == (leg, reg) and r.get("F_MOP") is not None:
                F_MOP = float(r["F_MOP"]); break
        if F_MOP is None:
            sensitivity_per_cell[f"{leg}/{reg}"] = {"status": "F_MOP_missing_from_12_report"}
        else:
            sensitivity_per_cell[f"{leg}/{reg}"] = SENS13.gate_a_sensitivity(F_MOP)
        # whiteness: residui u_e, u_b dalla pipeline + regimes finta single-regime
        # (i regimi multipli a livello cell non esistono qui — è una cella già single-regime;
        # serve la diagnostica autocorr/cross-corr).
        # Riprendo u_e, u_b di L (per esempio) — i tre candidati hanno LO STESSO u_e/u_b.
        pair = out["per_pair"][((leg, reg), "L")]
        u_e = pair["u_e"]; u_b = pair["u_b"]
        autoc_e = WHITE13.autocorrelation(u_e)
        autoc_b = WHITE13.autocorrelation(u_b)
        # regime_dependence: la cella è già single-regime → "un solo regime" risultato
        regimes_array = np.array(["x"] * len(u_e))
        regdep_e = WHITE13.regime_dependence(u_e, regimes_array)
        # cross-corr: rispetto ai 3 z_perp
        cross_p = {}
        for cand in ("L", "V", "C"):
            zp = out["per_pair"][((leg, reg), cand)]["z_perp"]
            if len(zp) == len(u_e) and np.std(zp) > 0 and np.std(u_e) > 0:
                cross_p[cand] = float(2 * (1 - abs(np.corrcoef(u_e, zp)[0, 1])
                                              * np.sqrt(len(u_e)) > 1.96)) * 0.5  # approx
                # più rigoroso: il p-value della correlazione campionaria
                rho = float(np.corrcoef(u_e, zp)[0, 1])
                n = len(u_e)
                # Fisher: t = rho * sqrt((n-2)/(1-rho^2))
                if abs(rho) < 1 and n > 2:
                    t = rho * math.sqrt((n - 2) / max(1e-20, 1 - rho ** 2))
                    from scipy.stats import t as t_dist
                    cross_p[cand] = float(2 * (1 - t_dist.cdf(abs(t), df=n - 2)))
                else:
                    cross_p[cand] = float("nan")
            else:
                cross_p[cand] = float("nan")
        whiteness_per_cell[f"{leg}/{reg}"] = {
            "autocorr_u_e": autoc_e, "autocorr_u_b": autoc_b,
            "regime_dependence_u_e": regdep_e,
            "cross_corr_p_with_z_perp": cross_p,
            "summary": WHITE13.whiteness_summary(
                autocorr_p=autoc_e["p_value"],
                regime_dep_p=regdep_e["p_value"],
                cross_corr_p=cross_p,
                alpha=0.05),
        }

    # 8) Scrivi outputs: 6 file
    def jsonify(x):
        if isinstance(x, dict):
            return {(f"{k[0]}|{k[1]}" if isinstance(k, tuple) else str(k)): jsonify(v)
                    for k, v in x.items()}
        if isinstance(x, np.ndarray):
            return [jsonify(v) for v in x.tolist()]
        if isinstance(x, (list, tuple)):
            return [jsonify(v) for v in x]
        if isinstance(x, (np.floating, np.integer)):
            return x.item()
        if isinstance(x, float) and not math.isfinite(x):
            return None
        return x

    # verdicts.json
    verdicts_clean = {f"{cell[0]}/{cell[1]}|{cand}": jsonify(v)
                       for (cell, cand), v in out["verdicts"].items()}
    (OUT_DIR / "verdicts.json").write_bytes(
        json.dumps({
            "verdicts": verdicts_clean,
            "by": jsonify(out["by"]),
            "config_hash": cfg13.config_hash(),
            "n_third_channel_True": int(n_third),
            "diagnostics_per_cell": diagnostics_per_cell,
            "surprise_provenance": surprise_provenance,
        }, indent=2, sort_keys=True).encode("utf-8"))

    # per_pair.json (senza u_e/u_b serializzati, solo statistiche)
    per_pair_clean = {}
    for (cell, cand), p in out["per_pair"].items():
        per_pair_clean[f"{cell[0]}/{cell[1]}|{cand}"] = {
            "lambda_e": jsonify(p["lambda_e"]),
            "lambda_b": jsonify(p["lambda_b"]),
            "p_e": jsonify(p["p_e"]), "p_b": jsonify(p["p_b"]),
            "p_commonality": jsonify(p["p_commonality"]),
            "commonality": bool(p["commonality"]),
            "sign_ok": (None if p["sign_ok"] is None else bool(p["sign_ok"])),
            "expected_sign": p["expected_sign"],
            "u_e_var": float(np.var(p["u_e"], ddof=1)) if len(p["u_e"]) > 1 else None,
            "u_b_var": float(np.var(p["u_b"], ddof=1)) if len(p["u_b"]) > 1 else None,
            "z_perp_var": float(np.var(p["z_perp"], ddof=1)) if len(p["z_perp"]) > 1 else None,
        }
    (OUT_DIR / "per_pair.json").write_bytes(
        json.dumps(per_pair_clean, indent=2, sort_keys=True).encode("utf-8"))

    # sensitivity.json
    (OUT_DIR / "sensitivity.json").write_bytes(
        json.dumps(jsonify(sensitivity_per_cell), indent=2, sort_keys=True).encode("utf-8"))

    # whiteness.json
    (OUT_DIR / "whiteness.json").write_bytes(
        json.dumps(jsonify(whiteness_per_cell), indent=2, sort_keys=True).encode("utf-8"))

    # manifest.json
    pkl_sha = sha256_file(PICKLE_AUTH_07)
    input_paths = [EVENTS_CSV, CONTAMINANTS_CSV, PICKLE_AUTH_07, JK_FOMC_CSV,
                    VIXCLS_CSV, ES_CSV, TY_CSV,
                    ROOT / "09_risultati" / "decomp_canali" / "decomp_canali.report.json"]
    code_paths = [PKG13 / f for f in ("config.py", "residual.py", "tests_channel.py",
                                        "proxies.py", "pipeline.py", "multiplicity.py",
                                        "sensitivity.py", "whitening.py", "manifest.py",
                                        "synthetic.py")]
    m = MF13.build_manifest(
        run_output=out, input_paths=input_paths, code_paths=code_paths,
        seed_name=SEED_NAME, timestamp=TASK_TIMESTAMP,
    )
    m["executor"] = {
        "script_path": str(Path(__file__).resolve()),
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "package_path": str(PKG13),
        "namespace_output_dir": str(OUT_DIR),
        "tests_observed_before_run": "40 passed, 0 xfailed (osservato in tool result)",
        "spec_revision_applied": (
            "Patologia §2/§3 risolta — sign rule rivista 'antisymmetric_pos_eq' (L) / "
            "'antisymmetric_neg_eq' (V) / 'ambiguous' (C). Lettura: dichiarazione 'L' "
            "non garantisce contributo bond indipendente (vedi xfail rimosso e "
            "test_dgp_case3_*_documents_structural_false_positive_for_L)."
        ),
    }
    m["external_constants"] = {
        "D_bond": D_BOND, "dp_bar": DP_BAR, "rho_central": RHO_CENTRAL,
        "N_horizon": N_HORIZON,
        "delta_y_bond_proxy": "delta_rate_3 (front-3 FF/FEI) BPS÷10000",
        "delta_f_curve_units": "decimale (BPS÷10000)",
    }
    m["surprise_provenance"] = surprise_provenance
    m["proxy_provenance"] = {
        "L": "proxy_unavailable — no bid-ask intraday TY/SPY in data_processed, no TED daily nei FRED snapshots; passato z=zeros per soddisfare contract API. Comunalità tecnicamente fallisce per costruzione (λ=0).",
        "V": "ΔVIXCLS daily (fallback dichiarato; intraday non disponibile).",
        "C": "corr realizzata intraday ES~TY 5-min sul giorno trading PRECEDENTE l'evento.",
    }
    m["diagnostics_per_cell"] = diagnostics_per_cell
    m["replicability_assumption_note"] = (
        "Vedi spec_revision_applied: la patologia §2/§3 (coef_b=−coef_e/β per "
        "costruzione) è stata accettata come constraint strutturale; la sign rule "
        "rivista è coerente con quel pattern. Una dichiarazione 'L' sotto questa "
        "spec significa attività residua significativa con λ_e>0; la spec NON "
        "consente di distinguere terzo canale genuino da fattore solo-equity. "
        "Esito anticipato del DGP §9.3 documentato come falso positivo strutturale "
        "(vedi test rinominato)."
    )
    MF13.write_manifest(OUT_DIR / "manifest.json", m)

    # report.md
    rows = []
    for cell in cfg13.ROBUST_CELLS:
        cell_t = tuple(cell)
        for cand in cfg13.CANDIDATES:
            v = out["verdicts"][(cell_t, cand)]
            rows.append({"cell": f"{cell_t[0]}/{cell_t[1]}", "candidate": cand,
                          "third_channel": bool(v["third_channel"]),
                          "passed_by": bool(v["passed_by"]),
                          "commonality": bool(v["commonality"]),
                          "sign_ok": (None if v["sign_ok"] is None else bool(v["sign_ok"])),
                          "lambda_e": float(v["lambda_e"]),
                          "lambda_b": float(v["lambda_b"]),
                          "p_commonality": float(v["p_commonality"])})

    lines = [
        "# Pacchetto 13 — terzo canale residuo — report esecutore",
        "",
        f"- timestamp: `{TASK_TIMESTAMP}`",
        f"- seed: `{SEED_NAME}` (master {cfg13.MASTER_SEED})",
        f"- config_hash: `{cfg13.config_hash()}`",
        f"- pickle_07_sha256: `{pkl_sha[:16]}…`",
        f"- ρ centrale (T0, dp_bar={DP_BAR}): {RHO_CENTRAL:.6f}",
        f"- D_bond = {D_BOND}",
        f"- BY q={cfg13.BY_Q}, family size={cfg13.BY_FAMILY_SIZE}, crit={out['by'].get('crit')}",
        "",
        "**Nota — spec §3 RIVISTA (risoluzione patologia §2/§3)**: la sign rule per "
        "L è `antisymmetric_pos_eq` (λ_e>0, λ_b<0), per V `antisymmetric_neg_eq` (λ_e<0, "
        "λ_b>0), per C `ambiguous`. Una dichiarazione `L=True` NON garantisce contributo "
        "indipendente del bond — la spec §2 produce coef_b≈−coef_e/β per costruzione. "
        "Vedi `manifest.json → executor.spec_revision_applied`.",
        "",
        "## Tabella §8 — terzo canale (12 voci)",
        "",
        "| cell | candidate | third_channel | passed_BY | commonality | sign_ok | λ_e | λ_b | p_comm |",
        "|---|---|:---:|:---:|:---:|:---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(f"| {r['cell']} | {r['candidate']} | "
                     f"{'**True**' if r['third_channel'] else 'False'} | "
                     f"{r['passed_by']} | {r['commonality']} | {r['sign_ok']} | "
                     f"{r['lambda_e']:+.4f} | {r['lambda_b']:+.4f} | {r['p_commonality']:.4f} |")

    lines += [
        "", "## Bianchezza dei residui (per cella, prima della cella L; gli ũ sono comuni)",
        "",
        "| cella | autocorr_u_e (p) | autocorr_u_b (p) | regime_dep (p) | is_white |",
        "|---|---:|---:|---:|:---:|",
    ]
    for cell in cfg13.ROBUST_CELLS:
        key = f"{cell[0]}/{cell[1]}"
        w = whiteness_per_cell[key]
        a_e_p = w["autocorr_u_e"]["p_value"]; a_b_p = w["autocorr_u_b"]["p_value"]
        rd_p = w["regime_dependence_u_e"]["p_value"]
        is_w = w["summary"]["is_white"]
        lines.append(f"| {key} | {a_e_p:.4f} | {a_b_p:.4f} | "
                     f"{('n/a' if not math.isfinite(rd_p) else f'{rd_p:.4f}')} | {is_w} |")

    lines += [
        "", "## Sensibilità del gate_a a soglie multiple (F_MOP del 12)",
        "",
        "| cella | F_MOP | bias_10pct (23.11) | bias_15pct (17.87) | bias_20pct (15.06) | F10 | robustezza |",
        "|---|---:|:---:|:---:|:---:|:---:|---|",
    ]
    for cell in cfg13.ROBUST_CELLS:
        key = f"{cell[0]}/{cell[1]}"
        s = sensitivity_per_cell[key]
        if s.get("status"):
            lines.append(f"| {key} | - | - | - | - | - | {s['status']} |")
        else:
            p = s["passes"]
            lines.append(f"| {key} | {s['F_MOP']:.4f} | {p['bias_10pct']} | "
                         f"{p['bias_15pct']} | {p['bias_20pct']} | "
                         f"{p['practical_F10']} | {s['robustness']} |")

    lines += [
        "",
        "## Sezione interpretativa (vincolata dalla patologia §2/§3 — risolta via opzione 2a)",
        "",
        "- **L e V** sotto la spec rivista sono identificabili in SENSO (segno di λ_e) ma "
        "non in MAGNITUDINE INDIPENDENTE del bond (la patologia §2 forza coef_b=−coef_e/β).",
        "- **C** (ambiguous) si appoggia solo alla comunalità; il sign_ok è True per costruzione.",
        "- Il caso DGP §9.3 (`equity_only`) sotto la sign rule rivista produce L=True come "
        "falso positivo strutturale documentato. **Una dichiarazione 'L' in una cella reale "
        "NON garantisce che il bond contribuisca indipendentemente al canale.**",
        "- L (proxy_unavailable) ha `z=zeros` per costruzione → comunalità sempre fallisce. "
        "I numeri di L sono tecnicamente coerenti col contract API ma NON SONO EVIDENZA.",
        "- Lettura della tabella §8: il risultato del ricercatore.",
    ]

    (OUT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nDONE → {OUT_DIR}")
    print(f"  6 file: verdicts.json, per_pair.json, sensitivity.json, whiteness.json, manifest.json, report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
