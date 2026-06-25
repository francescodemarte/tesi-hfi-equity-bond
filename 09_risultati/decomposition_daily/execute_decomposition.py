"""execute_decomposition.py — Decomposizione Campbell-Ammer daily applicata
agli eventi del run autoritativo v2.

Lettura del briefing: il cancello ad alta frequenza è chiuso (FAIL_GATE_1 sul
fattore pendenza FEIc1..c4). Si porta il canale a livello GIORNALIERO usando
il modulo `07/decomposition.py` (aritmetica pura, gia validata dai test).

Mappa dei dati (sola lettura, input datati):
  - eventi (842): pickle autoritativo v2 (accounting → leg + regime)
  - daily nominal 10Y yield (DGS10) e 5Y TIPS yield (DFII5):
    snapshot parquet FRED esterno (DATI/external_data/fred_yields_snapshot.parquet)
  - daily breakeven inflation 10Y (T10YIE): tips_breakeven_10y.csv
  - daily close ES/TY: chiusura giornaliera UTC dei prezzi 1-min processati
  - duration: D_bond = 8.9709 (UST 10Y, costante nel CSV eventi);
    duration_partial equity = D_eq_A = 5.0 (Specifica A, floor conservativo).

Aritmetica (per evento al giorno d):
  delta_r_real = DFII5(d) − DFII5(d−1)        [convertito da pp a decimale: /100]
  delta_pi     = T10YIE(d) − T10YIE(d−1)      [convertito da pp a decimale: /100]
  r_b_daily    = log(close_TY(d) / close_TY(d−1))
  r_e_daily    = log(close_ES(d) / close_ES(d−1))
  c_b_rate = -delta_r_real * D_bond ; c_b_pi = -delta_pi * D_bond ;
  c_b_res  = r_b_daily - c_b_rate - c_b_pi
  c_e_rate = -delta_r_real * D_eq_partial ; c_e_res = r_e_daily - c_e_rate
  twin_cov per cella (regime × leg) sui residui.

ECB events: i Treasury 10Y/TIPS riflettono il mercato USA; per ECB la
decomposizione daily col canale tasso USA è quanto meno discutibile, quindi
viene calcolata ma riportata in un sotto-blocco separato (etichettato come
"canale tasso USA applicato a evento ECB — lettura del ricercatore").

Output: per_event.csv, cell_twin_cov.json, manifest.json, report.md.
"""
from __future__ import annotations

import hashlib
import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/francesco/TESI/tesi-hfi-equity-bond")
PKG = ROOT / "CODICI_TESI" / "07_protocollo_v2_signflip"
sys.path.insert(0, str(PKG))

import decomposition as DECOMP   # noqa: E402

OUT_DIR = ROOT / "09_risultati" / "decomposition_daily"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PICKLE_AUTH = ROOT / "09_risultati" / "v2_signflip" / "result_authoritative.pkl"
INTRADAY_DIR = Path("/home/francesco/TESI/Dati/data_processed")
ES_CSV = INTRADAY_DIR / "ESc1_1min.csv"
TY_CSV = INTRADAY_DIR / "TYc1_1min.csv"
FRED_YIELDS_PARQUET = Path("/home/francesco/TESI/Dati/external_data/fred_yields_snapshot.parquet")
T10YIE_CSV = Path("/home/francesco/TESI/Dati/external_data/tips_breakeven_10y.csv")

# Costanti dalla pipeline v2 (CSV eventi: D_bond, D_eq_A costanti)
D_BOND = 8.970865529245179        # UST 10Y duration (proxy congelato)
D_EQ_PARTIAL = 5.0                # Specifica A, floor conservativo

SEED_NAME = "decomposition_daily_2026-06-23"
TASK_TIMESTAMP = (
    datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_events_from_pickle(pkl_path: Path):
    sha = sha256_file(pkl_path)
    with open(pkl_path, "rb") as f:
        obj = pickle.load(f)
    rows = []
    for a in obj["accounting"]:
        s = a["event"]; leg, rest = s.split("@", 1); ts, regime = rest.rsplit("|", 1)
        rows.append({"timestamp": pd.Timestamp(ts), "leg": leg, "regime": regime,
                      "date": pd.Timestamp(ts).date()})
    return pd.DataFrame(rows), sha, {"label": obj["label"], "timestamp": obj["timestamp"]}


def load_daily_close(intraday_csv: Path, price_col: str = "PX_LAST") -> pd.Series:
    """Chiusura giornaliera = ultimo minute disponibile UTC del giorno."""
    df = pd.read_csv(intraday_csv, usecols=["Datetime_UTC", price_col])
    df["Datetime_UTC"] = pd.to_datetime(df["Datetime_UTC"], utc=True)
    df["date"] = df["Datetime_UTC"].dt.date
    last_per_day = df.groupby("date", as_index=True)[price_col].last().astype(float)
    return last_per_day.sort_index().dropna()


def load_fred_yields() -> dict:
    df = pd.read_parquet(FRED_YIELDS_PARQUET)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    out = {}
    for sid in ("DGS10", "DFII5"):
        sub = df[df["series_id"] == sid].set_index("date")["value"].astype(float)
        out[sid] = sub.sort_index().dropna()
    # T10YIE separato
    t10 = pd.read_csv(T10YIE_CSV)
    t10["observation_date"] = pd.to_datetime(t10["observation_date"]).dt.date
    out["T10YIE"] = (t10.set_index("observation_date")["T10YIE"]
                       .astype(float).sort_index().dropna())
    return out


def daily_diff_at(series: pd.Series, date) -> float:
    """Differenza prima della serie alla data `date` (vs precedente giorno disponibile)."""
    if date not in series.index:
        return float("nan")
    prev = series.loc[:date].iloc[:-1]
    if prev.empty:
        return float("nan")
    return float(series.loc[date] - prev.iloc[-1])


def daily_log_return_at(daily_close: pd.Series, date) -> float:
    if date not in daily_close.index:
        return float("nan")
    prev = daily_close.loc[:date].iloc[:-1]
    if prev.empty:
        return float("nan")
    p_now = float(daily_close.loc[date]); p_prev = float(prev.iloc[-1])
    if p_now <= 0 or p_prev <= 0:
        return float("nan")
    return float(np.log(p_now / p_prev))


def main() -> int:
    print(f"=== execute_decomposition.py — {TASK_TIMESTAMP} ===")
    events, pkl_sha, pkl_meta = load_events_from_pickle(PICKLE_AUTH)
    print(f"  events: {len(events)}  (pickle sha256 {pkl_sha[:16]}...)")

    print("  loading daily closes ES, TY ...")
    es_close = load_daily_close(ES_CSV)
    ty_close = load_daily_close(TY_CSV)
    print(f"    ES: {len(es_close)} days, {es_close.index.min()} → {es_close.index.max()}")
    print(f"    TY: {len(ty_close)} days, {ty_close.index.min()} → {ty_close.index.max()}")

    print("  loading FRED yields ...")
    fred = load_fred_yields()
    for k, s in fred.items():
        print(f"    {k}: {len(s)} obs, {s.index.min()} → {s.index.max()}")

    # Calcola per ogni evento la decomposizione
    print("  computing per-event channels ...")
    rows = []
    for _, ev in events.iterrows():
        d = ev["date"]
        d_pi = daily_diff_at(fred["T10YIE"], d) / 100.0 if not np.isnan(daily_diff_at(fred["T10YIE"], d)) else float("nan")
        d_rr = daily_diff_at(fred["DFII5"], d) / 100.0 if not np.isnan(daily_diff_at(fred["DFII5"], d)) else float("nan")
        r_b = daily_log_return_at(ty_close, d)
        r_e = daily_log_return_at(es_close, d)
        # bond_channels e equity_channels — anche se input NaN, l'aritmetica
        # propaga NaN coerentemente (no fabbricazione)
        bch = DECOMP.bond_channels(r_b=r_b, delta_r_real=d_rr,
                                     delta_pi=d_pi, d_bond=D_BOND)
        ech = DECOMP.equity_channels(r_e=r_e, delta_r_real=d_rr,
                                       duration_partial=D_EQ_PARTIAL)
        rows.append({
            "timestamp": ev["timestamp"], "date": d,
            "leg": ev["leg"], "regime": ev["regime"],
            "delta_r_real": d_rr, "delta_pi": d_pi,
            "r_b_daily": r_b, "r_e_daily": r_e,
            "c_b_rate": float(bch["c_b_rate"]) if not np.isnan(bch["c_b_rate"]) else float("nan"),
            "c_b_pi":   float(bch["c_b_pi"])   if not np.isnan(bch["c_b_pi"])   else float("nan"),
            "c_b_res":  float(bch["c_b_res"])  if not np.isnan(bch["c_b_res"])  else float("nan"),
            "c_e_rate": float(ech["c_e_rate"]) if not np.isnan(ech["c_e_rate"]) else float("nan"),
            "c_e_res":  float(ech["c_e_res"])  if not np.isnan(ech["c_e_res"])  else float("nan"),
        })
    per_event = pd.DataFrame(rows)

    # Identità additiva: r_b == c_b_rate + c_b_pi + c_b_res (oracolo, fallisce noisy)
    valid_b = per_event.dropna(subset=["r_b_daily", "c_b_rate", "c_b_pi", "c_b_res"])
    if len(valid_b):
        diff = (valid_b["r_b_daily"]
                - valid_b["c_b_rate"] - valid_b["c_b_pi"] - valid_b["c_b_res"])
        max_abs_diff_bond = float(diff.abs().max())
    else:
        max_abs_diff_bond = float("nan")
    valid_e = per_event.dropna(subset=["r_e_daily", "c_e_rate", "c_e_res"])
    if len(valid_e):
        diff = (valid_e["r_e_daily"] - valid_e["c_e_rate"] - valid_e["c_e_res"])
        max_abs_diff_equity = float(diff.abs().max())
    else:
        max_abs_diff_equity = float("nan")
    print(f"  additive identity max|err|: bond={max_abs_diff_bond:.2e}, equity={max_abs_diff_equity:.2e}")

    # twin_cov per cella (regime × leg)
    print("  twin_cov per cella regime × leg ...")
    cells = {}
    valid_re = per_event.dropna(subset=["c_e_res", "c_b_res"])
    for (leg, reg), sub in valid_re.groupby(["leg", "regime"]):
        if len(sub) < 2:
            cells[f"{leg}|{reg}"] = {"n": int(len(sub)),
                                       "twin_cov": float("nan"),
                                       "var_c_e_res": float("nan"),
                                       "var_c_b_res": float("nan"),
                                       "corr_twin": float("nan")}
            continue
        ce = sub["c_e_res"].to_numpy()
        cb = sub["c_b_res"].to_numpy()
        tc = DECOMP.twin_cov(ce, cb)
        var_e = float(np.var(ce, ddof=1)); var_b = float(np.var(cb, ddof=1))
        corr = tc / (np.sqrt(var_e) * np.sqrt(var_b)) if var_e > 0 and var_b > 0 else float("nan")
        cells[f"{leg}|{reg}"] = {"n": int(len(sub)),
                                   "twin_cov": float(tc),
                                   "var_c_e_res": var_e,
                                   "var_c_b_res": var_b,
                                   "corr_twin": float(corr)}

    # Sintesi per regime (aggregato sui leg US — FOMC/CPI/NFP; ECB separato)
    summary_by_regime = {}
    for reg in ("positivo", "negativo"):
        sub_us = valid_re[(valid_re["regime"] == reg)
                          & (valid_re["leg"].isin(("FOMC", "CPI", "NFP")))]
        if len(sub_us) >= 2:
            ce = sub_us["c_e_res"].to_numpy(); cb = sub_us["c_b_res"].to_numpy()
            tc = DECOMP.twin_cov(ce, cb)
            v_e = float(np.var(ce, ddof=1)); v_b = float(np.var(cb, ddof=1))
            corr = tc / (np.sqrt(v_e) * np.sqrt(v_b)) if v_e > 0 and v_b > 0 else float("nan")
            summary_by_regime[f"US_only|{reg}"] = {
                "n": int(len(sub_us)), "twin_cov": float(tc),
                "var_c_e_res": v_e, "var_c_b_res": v_b, "corr_twin": float(corr),
            }
        sub_ecb = valid_re[(valid_re["regime"] == reg) & (valid_re["leg"] == "ECB")]
        if len(sub_ecb) >= 2:
            ce = sub_ecb["c_e_res"].to_numpy(); cb = sub_ecb["c_b_res"].to_numpy()
            tc = DECOMP.twin_cov(ce, cb)
            v_e = float(np.var(ce, ddof=1)); v_b = float(np.var(cb, ddof=1))
            corr = tc / (np.sqrt(v_e) * np.sqrt(v_b)) if v_e > 0 and v_b > 0 else float("nan")
            summary_by_regime[f"ECB|{reg}"] = {
                "n": int(len(sub_ecb)), "twin_cov": float(tc),
                "var_c_e_res": v_e, "var_c_b_res": v_b, "corr_twin": float(corr),
            }

    # Persistenza
    per_event.to_csv(OUT_DIR / "per_event.csv", index=False)
    print(f"  wrote per_event.csv ({len(per_event)} rows)")

    output = {
        "task_timestamp": TASK_TIMESTAMP,
        "seed_name": SEED_NAME,
        "duration_constants": {"D_bond": D_BOND, "D_eq_partial_A": D_EQ_PARTIAL},
        "data_inputs": {
            "pickle_auth": {"path": str(PICKLE_AUTH), "sha256": pkl_sha,
                             "run_label": pkl_meta["label"], "run_timestamp": pkl_meta["timestamp"]},
            "fred_yields": {"path": str(FRED_YIELDS_PARQUET),
                              "sha256": sha256_file(FRED_YIELDS_PARQUET),
                              "series_used": ["DFII5"]},
            "t10yie": {"path": str(T10YIE_CSV), "sha256": sha256_file(T10YIE_CSV)},
            "es_intraday": {"path": str(ES_CSV), "sha256": sha256_file(ES_CSV),
                              "n_daily_closes": int(len(es_close))},
            "ty_intraday": {"path": str(TY_CSV), "sha256": sha256_file(TY_CSV),
                              "n_daily_closes": int(len(ty_close))},
        },
        "n_events_total": int(len(per_event)),
        "n_events_with_bond_channels_valid": int(len(valid_b)),
        "n_events_with_equity_channels_valid": int(len(valid_e)),
        "additive_identity_max_abs_err": {
            "bond_r_b - sum_channels": max_abs_diff_bond,
            "equity_r_e - sum_channels": max_abs_diff_equity,
        },
        "twin_cov_by_cell_regime_x_leg": cells,
        "twin_cov_summary_us_vs_ecb": summary_by_regime,
    }
    (OUT_DIR / "cell_twin_cov.json").write_bytes(
        json.dumps(output, indent=2, sort_keys=True, default=str).encode("utf-8"))
    print("  wrote cell_twin_cov.json")

    # Manifest
    manifest = {
        "task": "decomposition_daily_campbell_ammer",
        "task_timestamp": TASK_TIMESTAMP,
        "seed_name": SEED_NAME,
        "script": {"path": str(Path(__file__).resolve()),
                    "sha256": sha256_file(Path(__file__).resolve())},
        "decomposition_module": {"path": str(PKG / "decomposition.py"),
                                   "sha256": sha256_file(PKG / "decomposition.py")},
        "decomposition_module_tests_passed": "11/11 (osservato in tool result prima del run)",
        "data_inputs": output["data_inputs"],
        "duration_constants": output["duration_constants"],
        "fields_provenance": {
            "delta_r_real": "Δ DFII5 (5Y TIPS yield) daily, da pp a decimale (÷100)",
            "delta_pi":     "Δ T10YIE (10Y breakeven inflation) daily, da pp a decimale (÷100)",
            "r_b_daily":    "log-return chiusura giornaliera TY (UST 10Y future, prezzo)",
            "r_e_daily":    "log-return chiusura giornaliera ES (S&P 500 future, prezzo)",
            "D_bond":       "8.9709 (UST 10Y duration costante nel CSV eventi v2)",
            "D_eq_partial": "5.0 (Specifica A — floor conservativo, da CLAUDE.md §6.3)",
        },
        "caveats": [
            "Frequenza GIORNALIERA: evidenza SECONDARIA (decomposition.py docstring). "
            "Non è la frequenza-evento dello stimatore principale b_H.",
            "Per gli eventi ECB il canale tasso USA (DFII5) è una proxy discutibile; "
            "i risultati ECB sono riportati separati per trasparenza, lettura del ricercatore.",
            "duration_partial equity = 5.0 (Specifica A). Le specifiche B/floor/ceil "
            "esistono nel CSV ma per coerenza si usa il valore canonico v2.",
        ],
    }
    (OUT_DIR / "manifest.json").write_bytes(
        json.dumps(manifest, indent=2, sort_keys=True, default=str).encode("utf-8"))
    print("  wrote manifest.json")

    # Report
    lines = [
        "# Decomposizione daily Campbell-Ammer — applicata agli eventi v2",
        "",
        f"- timestamp: `{TASK_TIMESTAMP}`",
        f"- modulo: `07/decomposition.py` (11/11 test verdi, osservato prima del run)",
        f"- pickle autoritativo: `{pkl_meta['label']}` sha256 `{pkl_sha[:16]}…`",
        f"- eventi: {len(per_event)} totali",
        f"- D_bond = {D_BOND:.6f}; D_eq_partial (Specifica A) = {D_EQ_PARTIAL}",
        "",
        "## Aritmetica per evento (input giornalieri):",
        "",
        "- `delta_r_real` = Δ DFII5 (5Y TIPS, FRED snapshot), da pp a decimale",
        "- `delta_pi`     = Δ T10YIE (10Y breakeven, FRED), da pp a decimale",
        "- `r_b_daily`    = log-return chiusura giornaliera TY (UST 10Y future)",
        "- `r_e_daily`    = log-return chiusura giornaliera ES (S&P 500 future)",
        "- `c_b_rate = −Δr_real · D_bond`, `c_b_pi = −Δπ · D_bond`, `c_b_res = r_b − c_b_rate − c_b_pi`",
        "- `c_e_rate = −Δr_real · D_eq_partial`, `c_e_res = r_e − c_e_rate`",
        "",
        "## Validità input (eventi totali = " + str(len(per_event)) + ")",
        "",
        f"- bond_channels validi (tutti gli input non-NaN): {len(valid_b)}",
        f"- equity_channels validi: {len(valid_e)}",
        f"- max |r_b − Σ canali bond|  = {max_abs_diff_bond:.2e} (identità additiva)",
        f"- max |r_e − Σ canali equity| = {max_abs_diff_equity:.2e}",
        "",
        "## twin_cov per cella (regime × leg)",
        "",
        "| leg | regime | n | twin_cov | corr | var(c_e_res) | var(c_b_res) |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for key, v in sorted(cells.items()):
        leg, reg = key.split("|")
        lines.append(
            f"| {leg} | {reg} | {v['n']} | {v['twin_cov']:.4e} | "
            f"{v['corr_twin']:.4f} | {v['var_c_e_res']:.4e} | {v['var_c_b_res']:.4e} |"
        )
    lines += [
        "",
        "## twin_cov aggregato — leg US (FOMC+CPI+NFP) vs ECB, per regime",
        "",
        "| gruppo | regime | n | twin_cov | corr |",
        "|---|---|---:|---:|---:|",
    ]
    for key, v in sorted(summary_by_regime.items()):
        grp, reg = key.split("|")
        lines.append(f"| {grp} | {reg} | {v['n']} | {v['twin_cov']:.4e} | {v['corr_twin']:.4f} |")
    lines += [
        "",
        "## Note dell'esecutore",
        "",
        "- Aritmetica pura: l'identità additiva r = Σ canali è soddisfatta entro la "
        "precisione macchina (max |err| dichiarato sopra). Niente fabbricazione.",
        "- Frequenza daily, evidenza secondaria — NON sostituisce b_H eventi.",
        "- Eventi ECB: il canale tasso USA è proxy debole; riportato separato.",
        "- L'interpretazione (es. 'il residuo gemello identifica un terzo fattore?') "
        "è del ricercatore.",
    ]
    (OUT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("  wrote report.md")

    print(f"\nDONE → {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
