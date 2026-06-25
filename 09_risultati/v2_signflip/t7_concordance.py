"""t7_concordance.py — Estrae la concordance E3.1 fra regime baseline (corr3m, lag t-1)
e regime esogeno (T10Y2Y, VIXCLS) per ogni tipo evento.

NON ri-esegue la pipeline. Riusa esattamente la stessa logica di:
  - run.compute_regimes (regime baseline ricalcolato dal raw, window=63gg, lag t-1)
  - regimes.build_exogenous_regime (regime esogeno, mediana causale 252gg, lag t-1)
  - regimes.assign_regime (as-of evento)

Output:
  - stampa su stdout: per ogni (tipo, criterio) tabella 2x2 + concordance + n
  - JSON: 09_risultati/v2_signflip/t7_concordance.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/francesco/TESI/tesi-hfi-equity-bond")
PKG = ROOT / "CODICI_TESI" / "07_protocollo_v2_signflip"
sys.path.insert(0, str(PKG))

import config           # noqa: E402
import data             # noqa: E402
import regimes          # noqa: E402
import run              # noqa: E402

EVENTS_CSV = ROOT / "DATASET_TESI" / "01_eventi_hfi" / "events_with_regime_classifier.csv"
SNAPSHOTS_DIR = PKG / "external_data" / "snapshots"
OUT_JSON = ROOT / "09_risultati" / "v2_signflip" / "t7_concordance.json"


def load_fred_snapshot(name: str) -> pd.Series:
    df = pd.read_csv(SNAPSHOTS_DIR / f"{name}.csv")
    date_col = next(c for c in df.columns if c.lower() in ("date", "observation_date"))
    val_col = next(c for c in df.columns if c != date_col)
    df[date_col] = pd.to_datetime(df[date_col])
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    return df.set_index(date_col)[val_col].dropna().rename(name)


def main():
    events = data.load_events(EVENTS_CSV)

    # Baseline regime: ricalcolato dal raw (corr 63gg, lag t-1)
    prices = run.load_prices()
    regime_by_area = run.compute_regimes(prices)

    # Esogeni: T10Y2Y, VIXCLS (build_exogenous_regime, 252gg mediana causale, lag t-1)
    area_of = lambda t: "EU" if t == "ECB" else "US"
    exo_series = {nm: load_fred_snapshot(nm) for nm in config.T7_EXOGENOUS_REQUIRED}
    exo_regimes = {
        nm: regimes.build_exogenous_regime(
            s, window=config.T7_ROLLING_DAYS, lag=config.T7_LAG_BDAYS)["regime"]
        for nm, s in exo_series.items()
    }

    out = {"by_type_criterion": {}, "config": {
        "baseline_window_days": config.REGIME_WINDOW_DAYS,
        "baseline_lag_bdays": config.REGIME_LAG_BDAYS,
        "exogenous_window_days": config.T7_ROLLING_DAYS,
        "exogenous_lag_bdays": config.T7_LAG_BDAYS,
        "exogenous_criteria": list(config.T7_EXOGENOUS_REQUIRED),
    }}

    # assegnazioni baseline per area
    base_assign = {area: regimes.assign_regime(events[events["event_class"].map(area_of) == area]["date"],
                                               regime_by_area[area])
                   for area in ("US", "EU")}

    for t in config.EVENT_TYPES:
        sub = events[events["event_class"] == t].reset_index(drop=True)
        area = area_of(t)
        bas_labels = regimes.assign_regime(sub["date"], regime_by_area[area])
        out["by_type_criterion"][t] = {}
        for crit, exo_reg in exo_regimes.items():
            exo_labels = regimes.assign_regime(sub["date"], exo_reg)
            # tabella 2x2: baseline ∈ {pos, neg, None}, esogeno ∈ {alto, basso, None}
            n_total = len(sub)
            valid = [(b, e) for b, e in zip(bas_labels, exo_labels)
                     if b in ("positivo", "negativo") and e in ("alto", "basso")]
            n_valid = len(valid)
            # tabella 2x2
            counts = {("positivo", "alto"): 0, ("positivo", "basso"): 0,
                      ("negativo", "alto"): 0, ("negativo", "basso"): 0}
            for b, e in valid:
                counts[(b, e)] += 1
            # concordance under best matching: max(d, ad) / n_valid
            d = counts[("positivo", "alto")] + counts[("negativo", "basso")]
            ad = counts[("positivo", "basso")] + counts[("negativo", "alto")]
            best = max(d, ad)
            conc_best = best / n_valid if n_valid else None
            # raw concordance under fixed mapping pos↔alto
            conc_fixed = d / n_valid if n_valid else None
            out["by_type_criterion"][t][crit] = {
                "n_events": n_total,
                "n_valid_pairs": n_valid,
                "counts_2x2": {f"{b}_{e}": v for (b, e), v in counts.items()},
                "concordance_best_matching": conc_best,
                "concordance_pos_to_alto_fixed": conc_fixed,
                "best_mapping": "pos↔alto" if d >= ad else "pos↔basso",
            }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, indent=2, sort_keys=True)

    # Stampa tabella leggibile
    print("=" * 80)
    print("T7 CONCORDANCE — Baseline (corr3m, lag t-1) vs Esogeno (mediana causale 252gg, lag t-1)")
    print("=" * 80)
    for t in config.EVENT_TYPES:
        print(f"\n{t}:")
        for crit, m in out["by_type_criterion"][t].items():
            c = m["counts_2x2"]
            print(f"  vs {crit}: n_valid={m['n_valid_pairs']}/{m['n_events']}")
            print(f"    pos|alto={c['positivo_alto']:3d}  pos|basso={c['positivo_basso']:3d}")
            print(f"    neg|alto={c['negativo_alto']:3d}  neg|basso={c['negativo_basso']:3d}")
            print(f"    concordance best-matching ({m['best_mapping']}): {m['concordance_best_matching']:.4f}")
            print(f"    concordance pos↔alto fixed:                    {m['concordance_pos_to_alto_fixed']:.4f}")
    print(f"\nSaved: {OUT_JSON}")


if __name__ == "__main__":
    main()
