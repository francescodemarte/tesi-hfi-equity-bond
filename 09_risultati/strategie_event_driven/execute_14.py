"""execute_14.py — Esecutore del pacchetto 14 (strategie event-driven).

Costruisce events_by_strategy = {CPI, NFP, FOMC} con:
  - date: data evento (normalize)
  - regime: pos/neg dal pickle accounting 07 (autoritativo)
  - surprise: CPI=req08 surprise_yoy; FOMC=MP1 JK; NFP=m_e (fallback dichiarato)
  - r_e_event, r_b_event: dai cluster del 07 (finestra ±15 min HFI)
  - r_e_eod, r_b_eod: log-return chiusura giornaliera ES/TY (UTC date close)

Chiama run_all (default scheme=equal) e scrive trittico (report+manifest+log).
"""
from __future__ import annotations

import csv
import hashlib
import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/francesco/TESI/tesi-hfi-equity-bond")
PKG07 = ROOT / "CODICI_TESI" / "07_protocollo_v2_signflip"
PKG14 = ROOT / "CODICI_TESI" / "14_strategie_event_driven"

sys.path.insert(0, str(PKG07))
import config as cfg07           # noqa: E402
import data as data07            # noqa: E402
import run as run07              # noqa: E402
import windows as win07          # noqa: E402

for m in ("config", "manifest"):
    sys.modules.pop(m, None)
sys.path.remove(str(PKG07))
sys.path.insert(0, str(PKG14))
import config as cfg14           # noqa: E402
import manifest as MF14          # noqa: E402
import run_strategies as RS14    # noqa: E402

OUT = ROOT / "09_risultati" / "strategie_event_driven"
OUT.mkdir(parents=True, exist_ok=True)

EVENTS_CSV = ROOT / "DATASET_TESI" / "01_eventi_hfi" / "events_with_regime_classifier.csv"
CONT_CSV = Path("/home/francesco/TESI/Dati/calendari/contaminants_build_2026-06-22/contaminants_v2_2026-06-22.csv")
PICKLE_AUTH_07 = ROOT / "09_risultati" / "v2_signflip" / "result_authoritative.pkl"
JK_CSV = Path("/home/francesco/TESI/Dati/external_data/jk_surprises_fomc.csv")
REQ08 = ROOT / "bridge" / "data" / "req08_cpi_surprise.csv"
ES_CSV = Path("/home/francesco/TESI/Dati/data_processed/ESc1_1min.csv")
TY_CSV = Path("/home/francesco/TESI/Dati/data_processed/TYc1_1min.csv")

TS = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
SEED_NAME = "strategie_event_driven_2026-06-24"


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def load_daily_close(csv_p: Path) -> pd.Series:
    df = pd.read_csv(csv_p, usecols=["Datetime_UTC", "PX_LAST"])
    df["Datetime_UTC"] = pd.to_datetime(df["Datetime_UTC"], utc=True)
    df["date"] = df["Datetime_UTC"].dt.date
    return (df.groupby("date", as_index=True)["PX_LAST"]
              .last().astype(float).sort_index().dropna())


def main():
    print(f"=== execute_14.py — {TS} ===")
    print(f"  config_hash 14 = {cfg14.config_hash()}")

    # 1) Cluster 07 autoritativi
    events_full = data07.load_events(EVENTS_CSV)
    prices = run07.load_prices()
    regs = run07.compute_regimes(prices)
    cont = set()
    with open(CONT_CSV) as f:
        for r in csv.DictReader(f): cont.add(pd.Timestamp(r["center_utc"]))
    reject = run07.build_calendar_reject(set(pd.to_datetime(events_full["timestamp"], utc=True)), cont)
    per_type, _ = run07.assemble(events_full, prices, regs, reject)
    per_type, _ = win07.dedup_shared_controls(per_type)

    # 2) Loader sorprese
    # JK MP1
    jk_df = pd.read_csv(JK_CSV)
    jk_df["start"] = pd.to_datetime(jk_df["start"], errors="coerce")
    jk_map = {pd.Timestamp(r["start"]).normalize().tz_localize("UTC"): float(r["MP1"])
               for _, r in jk_df.dropna(subset=["start", "MP1"]).iterrows()
               if not pd.isna(r["MP1"])}
    # req08 CPI
    req = pd.read_csv(REQ08)
    req["reference_month_end"] = pd.to_datetime(req["reference_month_end"])
    req_map = req.set_index("reference_month_end")["surprise_yoy"]
    # m_e fallback per NFP
    me_df = pd.read_csv(EVENTS_CSV, usecols=["timestamp", "m_e"])
    me_df["timestamp"] = pd.to_datetime(me_df["timestamp"], utc=True)
    me_map = dict(zip(me_df["timestamp"], me_df["m_e"]))

    # 3) Daily close ES, TY per r_*_eod
    es_close = load_daily_close(ES_CSV)
    ty_close = load_daily_close(TY_CSV)
    es_logret = np.log(es_close).diff().dropna()
    ty_logret = np.log(ty_close).diff().dropna()
    print(f"  ES daily close: {len(es_close)}  TY daily close: {len(ty_close)}")

    # 4) Costruisce events_by_strategy
    events_by_strategy = {}
    diagnostics = {}
    for strategy in cfg14.STRATEGIES:
        rows = []
        n_no_surprise = 0; n_no_eod = 0
        for reg in ("pos", "neg"):
            clusters = per_type[strategy][reg]
            for cl in clusters:
                ts_event = pd.Timestamp(cl["event"]["center"])
                day_event = ts_event.normalize()
                # Sorpresa specifica
                if strategy == "CPI":
                    rel = ts_event.tz_convert("America/New_York").date()
                    refm = pd.Timestamp(rel) - pd.offsets.MonthEnd(1)
                    s = float(req_map.loc[refm]) if refm in req_map.index else float("nan")
                elif strategy == "FOMC":
                    s = jk_map.get(day_event, float("nan"))
                else:  # NFP
                    s = float(me_map.get(ts_event, float("nan")))
                if np.isnan(s):
                    n_no_surprise += 1; continue
                # r_e_eod / r_b_eod
                d_naive = day_event.tz_convert(None).date()
                if d_naive in es_logret.index and d_naive in ty_logret.index:
                    r_e_eod = float(es_logret.loc[d_naive])
                    r_b_eod = float(ty_logret.loc[d_naive])
                else:
                    n_no_eod += 1; continue
                rows.append({
                    "date": day_event.tz_convert(None),
                    "regime": reg,
                    "surprise": s,
                    "r_e_event": float(cl["event"]["r_e"]),
                    "r_b_event": float(cl["event"]["r_b"]),
                    "r_e_eod": r_e_eod, "r_b_eod": r_b_eod,
                })
        df = pd.DataFrame(rows)
        events_by_strategy[strategy] = df
        diagnostics[strategy] = {
            "total_clusters": sum(len(per_type[strategy][r]) for r in ("pos","neg")),
            "dropped_no_surprise": n_no_surprise,
            "dropped_no_eod": n_no_eod,
            "events_emitted": len(df),
            "active_regime": cfg14.ACTIVE_REGIME[strategy],
            "n_in_active_regime": int((df["regime"] == cfg14.ACTIVE_REGIME[strategy]).sum()),
        }
        print(f"  {strategy}: emitted={len(df)}  (drop_no_surprise={n_no_surprise}, drop_no_eod={n_no_eod})")
        print(f"    n in active regime ({cfg14.ACTIVE_REGIME[strategy]}): {diagnostics[strategy]['n_in_active_regime']}")

    # 5) run_all
    print("\n  run_strategies.run_all (scheme=equal) ...")
    out = RS14.run_all(events_by_strategy, scheme="equal")
    for s in cfg14.STRATEGIES:
        ps = out["per_strategy"][s]
        m = ps["metrics"]
        print(f"  {s:5s}  n_active={ps['n_active']:3d}  period={ps['period']}")
        for h in cfg14.HORIZONS:
            mh = m[h]
            print(f"    {h:14s}: mean={mh['mean']:+.4e}  vol={mh['vol']:.4e}  sharpe={mh['sharpe']:+.4f}  n={mh['n']}")
    print(f"\n  PORTAFOLIO (scheme=equal, pesi={out['portfolio']['weights']})")
    pm = out["portfolio"]["metrics"]
    for h in cfg14.HORIZONS:
        mh = pm[h]
        print(f"    {h:14s}: mean={mh['mean']:+.4e}  vol={mh['vol']:.4e}  sharpe={mh['sharpe']:+.4f}  n={mh['n']}")

    # 6) Manifest + report + log
    input_paths = [EVENTS_CSV, CONT_CSV, PICKLE_AUTH_07, JK_CSV, REQ08, ES_CSV, TY_CSV]
    code_paths = [PKG14/f for f in ("config.py","strategy_rule.py","payoff.py",
                                      "portfolio.py","metrics.py","run_strategies.py","manifest.py")]
    m = MF14.build_manifest(run_output=out, input_paths=input_paths,
                              code_paths=code_paths, seed_name=SEED_NAME, timestamp=TS)
    m["executor"] = {
        "script_path": str(Path(__file__).resolve()),
        "script_sha256": sha(Path(__file__).resolve()),
        "namespace_output_dir": str(OUT),
        "tests_observed_before_run": "37 passed (osservato in tool result)",
    }
    m["diagnostics"] = diagnostics
    m["surprise_sources_per_leg"] = {
        "CPI": "surprise_yoy = cpi_yoy_actual - cpi_yoy_consensus (bridge req08_cpi_surprise.csv)",
        "FOMC": "MP1 Jarociński-Karadi — limitato al sotto-campione fino a 2024-01-31",
        "NFP": "m_e PC1 money-market dal CSV eventi v2 (fallback dichiarato: consensus NFP non disponibile)",
    }
    (OUT/"manifest.json").write_bytes(
        json.dumps(m, indent=2, sort_keys=True, default=str).encode("utf-8"))

    # Report.json
    report = {
        "task_timestamp": TS, "seed_name": SEED_NAME,
        "config_hash_14": cfg14.config_hash(),
        "config_version_14": cfg14.CONFIG_VERSION,
        "diagnostics_per_strategy": diagnostics,
        "per_strategy": {s: {"n_active": out["per_strategy"][s]["n_active"],
                               "period": out["per_strategy"][s]["period"],
                               "metrics": out["per_strategy"][s]["metrics"]}
                          for s in cfg14.STRATEGIES},
        "portfolio": {"scheme": out["portfolio"]["scheme"],
                       "weights": out["portfolio"]["weights"],
                       "period": out["portfolio"]["period"],
                       "metrics": out["portfolio"]["metrics"]},
        "fomc_subsample_end": out["fomc_subsample_end"],
        "label": "GROSS Sharpe — no transaction costs (CONDIZIONALE alla conferma β_str del 07).",
        "beta_str_provenance": cfg14.BETA_STR_PROVENANCE,
    }
    (OUT/"report.json").write_bytes(
        json.dumps(report, indent=2, sort_keys=True, default=str).encode("utf-8"))

    # log.txt
    lines = [
        "=== Log di custodia — pacchetto 14 (strategie event-driven) ===",
        f"task_timestamp: {TS}",
        f"seed_name: {SEED_NAME}  seed_value: {cfg14.seed_for(SEED_NAME)}",
        f"config_version: {cfg14.CONFIG_VERSION}  config_hash: {cfg14.config_hash()}",
        f"β_str usato (PRE-REGISTRATO): {cfg14.BETA_STR}",
        f"regime attivo per strategia: {cfg14.ACTIVE_REGIME}",
        f"FOMC subsample end: {cfg14.FOMC_SUBSAMPLE_END.date()}",
        "",
        "Sorprese per leg:",
        f"  CPI:  surprise_yoy (req08_cpi_surprise.csv) sha256={sha(REQ08)}",
        f"  FOMC: MP1 (jk_surprises_fomc.csv) sha256={sha(JK_CSV)} — sottocampione ≤ 2024-01-31",
        f"  NFP:  m_e PC1 money-market (fallback dichiarato) — events CSV sha256={sha(EVENTS_CSV)}",
        "",
        "Conteggi:",
    ]
    for s in cfg14.STRATEGIES:
        d = diagnostics[s]
        lines.append(f"  {s}: clusters={d['total_clusters']}  emitted={d['events_emitted']}  "
                     f"in_active_regime({d['active_regime']})={d['n_in_active_regime']}  "
                     f"dropped_no_surprise={d['dropped_no_surprise']}  dropped_no_eod={d['dropped_no_eod']}")
    lines += ["", "Sharpe per strategia (LORDO):"]
    for s in cfg14.STRATEGIES:
        ps = out["per_strategy"][s]
        for h in cfg14.HORIZONS:
            mh = ps["metrics"][h]
            lines.append(f"  {s:5s} {h:14s}: n={mh['n']:3d}  Sharpe={mh['sharpe']:+.4f}  mean={mh['mean']:+.4e}  vol={mh['vol']:.4e}")
    lines += ["", f"Portafoglio (scheme={out['portfolio']['scheme']}, pesi={out['portfolio']['weights']}):"]
    for h in cfg14.HORIZONS:
        mh = out["portfolio"]["metrics"][h]
        lines.append(f"  {h:14s}: n={mh['n']:3d}  Sharpe={mh['sharpe']:+.4f}  mean={mh['mean']:+.4e}  vol={mh['vol']:.4e}")
    lines += ["", "Caveat:",
                "  - Sharpe LORDO (no costi, no slippage, no leva). NON Sharpe eseguibile.",
                "  - β_str usato è ILLUSTRATIVO/CONDIZIONALE (vedi beta_str_provenance).",
                "  - Nessuna selezione orizzonte: entrambi (±15 min e end-of-day) riportati.",
                "  - FOMC limitato al sotto-campione ≤ 2024-01-31 (limite serie JK)."]
    (OUT/"log.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nDONE → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
