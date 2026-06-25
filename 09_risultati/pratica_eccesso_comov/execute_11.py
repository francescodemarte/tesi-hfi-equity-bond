"""execute_11.py — Esecutore pacchetto 11 (pratica eccesso di comovimento).

Anello finale per il pacchetto 11. Costruisce events_df esterno con
(date, leg, regime, epsilon) usando le tre finestre disgiunte richieste dal
package, poi chiama run.run_strategy passando event_calendar per ATTIVARE il
presidio intra-evento strutturale.

Dati (sola lettura, input datati):
  - intraday ESc1, TYc1 in /home/francesco/TESI/Dati/data_processed/ →
    chiusura giornaliera + log-returns daily.
  - calendario eventi NFP+CPI da events_with_regime_classifier.csv.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/francesco/TESI/tesi-hfi-equity-bond")
PKG = ROOT / "CODICI_TESI" / "11_pratica_eccesso_comovimento"
sys.path.insert(0, str(PKG))

import config        # noqa: E402
import excess as EX  # noqa: E402
import manifest as MF  # noqa: E402
import run as RUN    # noqa: E402
import windows as W  # noqa: E402

OUT_DIR = ROOT / "09_risultati" / "pratica_eccesso_comov"
OUT_DIR.mkdir(parents=True, exist_ok=True)

INTRADAY_DIR = Path("/home/francesco/TESI/Dati/data_processed")
ES_CSV = INTRADAY_DIR / "ESc1_1min.csv"
TY_CSV = INTRADAY_DIR / "TYc1_1min.csv"
EVENTS_CSV = ROOT / "DATASET_TESI" / "01_eventi_hfi" / "events_with_regime_classifier.csv"

SEED_NAME = "pratica_baseline_2026-06-23"
TASK_TIMESTAMP = (
    datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_daily_close(csv: Path, price_col: str = "PX_LAST") -> pd.Series:
    df = pd.read_csv(csv, usecols=["Datetime_UTC", price_col])
    df["Datetime_UTC"] = pd.to_datetime(df["Datetime_UTC"], utc=True)
    df["date"] = df["Datetime_UTC"].dt.date
    return (df.groupby("date", as_index=True)[price_col]
              .last().astype(float).sort_index().dropna())


def main() -> int:
    print(f"=== execute_11.py — {TASK_TIMESTAMP} (seed_name={SEED_NAME}) ===")

    # 1) Daily closes ES, TY → log-returns; calendario = intersezione di date.
    print("  loading daily closes ES, TY ...")
    es = load_daily_close(ES_CSV)
    ty = load_daily_close(TY_CSV)
    common = sorted(set(es.index) & set(ty.index))
    daily = pd.DataFrame({"date": common,
                           "es_close": [es[d] for d in common],
                           "ty_close": [ty[d] for d in common]}).set_index("date")
    daily["r_eq"] = np.log(daily["es_close"]).diff()
    daily["r_bo"] = np.log(daily["ty_close"]).diff()
    daily = daily.dropna(subset=["r_eq", "r_bo"]).reset_index()
    daily["date"] = pd.to_datetime(daily["date"])
    calendar = daily["date"].tolist()
    date_to_idx = {pd.Timestamp(d).normalize(): i for i, d in enumerate(calendar)}
    print(f"    calendar n = {len(calendar)}  span {calendar[0].date()} → {calendar[-1].date()}")

    # 2) Eventi NFP + CPI dal CSV; allineamento alla data di mercato.
    print("  loading events NFP+CPI ...")
    ev_raw = pd.read_csv(EVENTS_CSV, usecols=["date", "event_class", "timestamp"])
    ev_raw["date"] = pd.to_datetime(ev_raw["date"]).dt.normalize()
    ev = ev_raw[ev_raw["event_class"].isin(("NFP", "CPI"))].copy()
    ev["leg"] = ev["event_class"]
    ev = ev[["date", "leg"]].drop_duplicates().reset_index(drop=True)
    # Filtra eventi le cui date non sono nel calendario di mercato
    n_drop_off_cal = int((~ev["date"].isin(date_to_idx)).sum())
    ev = ev[ev["date"].isin(date_to_idx)].copy()
    print(f"    NFP+CPI events: {len(ev)} (scartati {n_drop_off_cal} fuori calendario)")

    # 3) Costruisci events_df: per ogni evento applica three_windows + ε.
    rows = []
    skipped_warmup = 0; skipped_zerovar = 0
    for _, row in ev.iterrows():
        d = row["date"]; idx = date_to_idx[d]
        try:
            r_idx, p_idx, ev_idx = W.three_windows(calendar, idx)
        except ValueError:
            skipped_warmup += 1
            continue
        W.assert_no_lookahead(r_idx + p_idx, event_idx=ev_idx)  # check ridondante
        r_eq_regime = daily["r_eq"].iloc[r_idx].to_numpy()
        r_bo_regime = daily["r_bo"].iloc[r_idx].to_numpy()
        try:
            regime = W.regime_sign(r_eq_regime, r_bo_regime)
        except ValueError:
            skipped_zerovar += 1
            continue
        r_eq_proxy = daily["r_eq"].iloc[p_idx].to_numpy()
        r_bo_proxy = daily["r_bo"].iloc[p_idx].to_numpy()
        r_eq_event = float(daily["r_eq"].iloc[ev_idx])
        r_bo_event = float(daily["r_bo"].iloc[ev_idx])
        c = EX.realized_comovement(r_eq_event, r_bo_event)
        a = EX.expected_comovement(r_eq_proxy, r_bo_proxy)
        s2 = EX.pre_variance(r_eq_proxy, r_bo_proxy)
        eps = EX.epsilon(c, a, s2)
        if np.isnan(eps):
            skipped_zerovar += 1
            continue
        rows.append({"date": d, "leg": row["leg"], "regime": regime,
                      "epsilon": eps})
    events_df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    print(f"    events_df: {len(events_df)} (warmup skip={skipped_warmup}, "
          f"zero-var skip={skipped_zerovar})")

    # Persistenza events_df + sidecar provenance
    ev_csv = OUT_DIR / "events_df.csv"
    events_df.to_csv(ev_csv, index=False)
    ev_prov = OUT_DIR / "events_df.csv.provenance.json"
    ev_prov.write_text(json.dumps({
        "build_timestamp": TASK_TIMESTAMP,
        "inputs": {
            "events_csv": {"path": str(EVENTS_CSV), "sha256": sha256_file(EVENTS_CSV)},
            "es_intraday": {"path": str(ES_CSV), "sha256": sha256_file(ES_CSV)},
            "ty_intraday": {"path": str(TY_CSV), "sha256": sha256_file(TY_CSV)},
        },
        "calendar_n": int(len(calendar)),
        "calendar_span": [str(calendar[0].date()), str(calendar[-1].date())],
        "events_input": int(len(ev)),
        "events_off_calendar_dropped": n_drop_off_cal,
        "events_warmup_skipped": skipped_warmup,
        "events_zero_variance_skipped": skipped_zerovar,
        "events_emitted": int(len(events_df)),
        "definitions": {
            "regime": "sign(corr(r_eq, r_bo)) on 63 sessions ending at t-4",
            "epsilon": "(c - a) / sigma2_pre with three_windows disjoint",
        },
    }, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(f"    wrote events_df.csv (sha256={sha256_file(ev_csv)[:16]}…)")

    # 4) event_calendar per attivare presidio intra-evento strutturale.
    ev2idx = {pd.Timestamp(d).normalize(): int(date_to_idx[pd.Timestamp(d).normalize()])
              for d in events_df["date"]}
    event_calendar = {"calendar": calendar, "event_to_idx": ev2idx}

    # 5) Run strategy
    print("  run.run_strategy ...")
    out = RUN.run_strategy(events_df, event_calendar=event_calendar)
    assert out["intra_event_lookahead_check"] == "validated", \
        "presidio intra-evento NON attivato"
    print(f"    intra_event_lookahead_check = {out['intra_event_lookahead_check']}")
    print(f"    n_train={out['n_train']}  n_test={out['n_test']}")
    print(f"    e_gk: { {f'{k[0]}/{k[1]}': round(float(v),4) for k,v in out['calibration']['e_gk'].items()} }")

    # 6) Manifest via il kernel del package
    m = MF.build_manifest(
        run_output=out,
        input_paths=[ev_csv, ev_prov, EVENTS_CSV, ES_CSV, TY_CSV],
        code_paths=[PKG / f for f in ("run.py", "calibration.py", "weighting.py",
                                       "windows.py", "excess.py", "payoff.py",
                                       "metrics.py", "manifest.py", "config.py")],
        seed_name=SEED_NAME,
        timestamp=TASK_TIMESTAMP,
    )
    m["executor"] = {
        "script_path": str(Path(__file__).resolve()),
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "package_path": str(PKG),
        "namespace_output_dir": str(OUT_DIR),
        "intra_event_lookahead_check": out["intra_event_lookahead_check"],
    }
    m["n_events_emission_diagnostics"] = {
        "events_input": int(len(ev)),
        "off_calendar_dropped": n_drop_off_cal,
        "warmup_skipped": skipped_warmup,
        "zero_variance_skipped": skipped_zerovar,
        "events_emitted": int(len(events_df)),
    }
    MF.write_manifest(OUT_DIR / "pratica_baseline.manifest.json", m)
    print("  wrote pratica_baseline.manifest.json")

    # 7) Report (3 file: report + manifest + log; manifest gia scritto)
    cells = {}
    for period_key in ("training_metrics", "test_metrics"):
        period = out[period_key]
        per = {"period": period["_period"]}
        for key, val in period.items():
            if isinstance(key, tuple) and len(key) == 2:
                n = int(val["n"])
                strat = val["strategy"]; bench = val["benchmark"]
                verdict = "inconclusive" if n < config.MIN_CELL_N_FOR_VERDICT else "concluded"
                per[f"{key[0]}/{key[1]}"] = {
                    "n": n,
                    "strategy_mean": float(strat.get("mean", float("nan"))),
                    "strategy_sharpe": float(strat.get("sharpe", float("nan"))),
                    "strategy_hit_rate": float(strat.get("hit_rate", float("nan"))),
                    "benchmark_mean": float(bench.get("mean", float("nan"))),
                    "diff_mean": float(val["diff"].get("mean_diff", float("nan"))),
                    "verdict": verdict,
                }
        cells[period_key] = per

    report = {
        "task_timestamp": TASK_TIMESTAMP,
        "package": "11_pratica_eccesso_comovimento",
        "seed_name": SEED_NAME,
        "config_hash": config.config_hash(),
        "config_version": config.CONFIG_VERSION,
        "n_train": out["n_train"], "n_test": out["n_test"], "n_total": out["n_total"],
        "split_date": out["split_date"],
        "intra_event_lookahead_check": out["intra_event_lookahead_check"],
        "calibration_e_gk": {f"{k[0]}/{k[1]}": float(v)
                              for k, v in out["calibration"]["e_gk"].items()},
        "cells": cells,
        "labeling": ("payoff teorico LORDO (covariance-swap-like), no costi, "
                      "NON Sharpe eseguibile. Verdetto 'inconclusive' per "
                      f"n < {config.MIN_CELL_N_FOR_VERDICT}."),
        "preregistration_note": (
            "Il regime POSITIVO è atteso povero nel test (regime quasi solo nel "
            "test, training lo ha visto poco) → celle pos del test possono essere "
            "'inconclusive' per pre-registrazione, NON è un fallimento della strategia."
        ),
    }
    (OUT_DIR / "pratica_baseline.report.json").write_bytes(
        json.dumps(report, indent=2, sort_keys=True, default=str).encode("utf-8"))
    print("  wrote pratica_baseline.report.json")

    # 8) Log di custodia in chiaro
    lines = [
        "=== Log di custodia — pacchetto 11 (pratica eccesso di comovimento) ===",
        f"task_timestamp:       {TASK_TIMESTAMP}",
        f"seed_name:            {SEED_NAME}",
        f"seed_value:           {config.seed_for(SEED_NAME)}",
        f"config_version:       {config.CONFIG_VERSION}",
        f"config_hash:          {config.config_hash()}",
        f"split_date:           {out['split_date']}",
        f"n_total:              {out['n_total']}",
        f"n_train:              {out['n_train']}",
        f"n_test:               {out['n_test']}",
        f"intra_event_check:    {out['intra_event_lookahead_check']}",
        "",
        "Calibrazione (train-only):",
    ]
    n_train_field = out["calibration"]["n_train"]
    n_train_repr = (n_train_field if isinstance(n_train_field, int)
                    else dict(n_train_field) if hasattr(n_train_field, "items") else n_train_field)
    for k, v in out["calibration"]["e_gk"].items():
        cell_n = (n_train_repr.get(k, "NA")
                  if isinstance(n_train_repr, dict) else "NA")
        lines.append(f"  e_gk[{k[0]}/{k[1]}] = {float(v):+.6e}  (n_train_cell = {cell_n})")
    lines.append(f"  n_train_total = {n_train_field}")
    lines += [
        "",
        "Inputs (sha256):",
        f"  events_df.csv                 sha256={sha256_file(ev_csv)}",
        f"  events_df.csv.provenance.json sha256={sha256_file(ev_prov)}",
        f"  events_with_regime_classifier sha256={sha256_file(EVENTS_CSV)}",
        f"  ESc1_1min.csv                 sha256={sha256_file(ES_CSV)}",
        f"  TYc1_1min.csv                 sha256={sha256_file(TY_CSV)}",
        "",
        "Code modules (sha256):",
    ]
    for fname in ("run.py", "calibration.py", "weighting.py", "windows.py",
                   "excess.py", "payoff.py", "metrics.py", "manifest.py", "config.py"):
        p = PKG / fname
        lines.append(f"  {fname:30s} sha256={sha256_file(p)}")
    lines += [
        "",
        "Cell counts × period (n):",
    ]
    for period in ("training_metrics", "test_metrics"):
        for key, val in out[period].items():
            if isinstance(key, tuple) and len(key) == 2:
                n = int(val["n"])
                tag = "<MIN_CELL_N=20 → inconclusive" if n < config.MIN_CELL_N_FOR_VERDICT else ""
                lines.append(f"  {period[:5]:5s} {key[0]:9s} {key[1]:3s} n={n:4d}  {tag}")
    lines += [
        "",
        "Etichetta finale: payoff teorico LORDO (covariance-swap-like), NO costi, NON Sharpe eseguibile.",
        "Pre-registrazione: regime 'pos' atteso povero nel test ⇒ celle pos del test possono essere inconclusive.",
        "",
        "Files emessi nella directory di output:",
        "  pratica_baseline.report.json",
        "  pratica_baseline.manifest.json",
        "  pratica_baseline.log.txt   (questo file)",
        "  events_df.csv  + events_df.csv.provenance.json",
        "  execute_11.py",
    ]
    (OUT_DIR / "pratica_baseline.log.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("  wrote pratica_baseline.log.txt")

    print(f"\nDONE → {OUT_DIR}")
    print("  trittico: report + manifest + log + events_df + executor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
