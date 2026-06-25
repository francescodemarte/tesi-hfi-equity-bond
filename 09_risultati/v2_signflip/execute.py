"""execute.py — Driver dell'ESECUTORE per il run reale del protocollo v2 sign-flip.

Non modifica il codice congelato in CODICI_TESI/07_protocollo_v2_signflip/.
Costruisce gli input attesi da `run.run_protocol_full(...)` e ne consuma
l'output, scrivendo i risultati in `OUT_DIR/results.pkl` + manifest.

Disciplina (mandato esecutore):
- Una sola passata.
- Niente clock interno per il manifest: timestamp passato esplicitamente.
- I gate dichiarati (NFP non alimentato, ECB LEVEL gated, decomp daily gated)
  restano espliciti nel manifest. Niente inventare.
"""
from __future__ import annotations

import csv
import hashlib
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/francesco/TESI/tesi-hfi-equity-bond")
PKG = ROOT / "CODICI_TESI" / "07_protocollo_v2_signflip"
sys.path.insert(0, str(PKG))

import config           # noqa: E402
import data             # noqa: E402
import loaders          # noqa: E402
import provenance       # noqa: E402
import run              # noqa: E402
import surprises        # noqa: E402
import windows          # noqa: E402

EVENTS_CSV = ROOT / "DATASET_TESI" / "01_eventi_hfi" / "events_with_regime_classifier.csv"
CONTAMINANTS_CSV = Path("/home/francesco/TESI/Dati/calendari/contaminants_build_2026-06-22/contaminants_v2_2026-06-22.csv")
SNAPSHOTS_DIR = PKG / "external_data" / "snapshots"
CPI_SURPRISE_CSV = ROOT / "bridge" / "data" / "req08_cpi_surprise.csv"
OUT_DIR = ROOT / "09_risultati" / "v2_signflip"
OUT_DIR.mkdir(parents=True, exist_ok=True)

RUN_TIMESTAMP = "2026-06-22T15:00:00Z"   # PASSATO ESPLICITAMENTE (no clock interno)
RUN_LABEL = "v2_signflip_run_authoritative_2026-06-22_post_bug2"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Loaders specifici per il driver
# ---------------------------------------------------------------------------

def load_contaminant_centers(path: Path) -> set:
    """Legge il CSV aggregato e ritorna un set di pd.Timestamp UTC."""
    centers = set()
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            centers.add(pd.Timestamp(r["center_utc"]))
    return centers


def load_fred_snapshot(name: str) -> pd.Series:
    """Snapshot FRED: CSV con colonne date + value (formato fredgraph.csv)."""
    p = SNAPSHOTS_DIR / f"{name}.csv"
    df = pd.read_csv(p)
    date_col = next(c for c in df.columns if c.lower() in ("date", "observation_date", "datetime"))
    val_col = next(c for c in df.columns if c != date_col)
    df[date_col] = pd.to_datetime(df[date_col])
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    return df.set_index(date_col)[val_col].dropna().rename(name)


def load_cpi_surprises() -> pd.DataFrame:
    """req08: reference_month_end → surprise_yoy."""
    df = pd.read_csv(CPI_SURPRISE_CSV)
    df["reference_month_end"] = pd.to_datetime(df["reference_month_end"])
    return df.set_index("reference_month_end")[["surprise_mom", "surprise_yoy"]]


# ---------------------------------------------------------------------------
# Sorprese per tipo (per T2 e T9)
# ---------------------------------------------------------------------------

def _cluster_rows(cluster_list):
    """Estrai (centers, r_e, r_b) come array allineati da una lista di cluster."""
    centers = [pd.Timestamp(c["event"]["center"]) for c in cluster_list]
    r_e = np.array([c["event"]["r_e"] for c in cluster_list], dtype=float)
    r_b = np.array([c["event"]["r_b"] for c in cluster_list], dtype=float)
    return centers, r_e, r_b


def build_cpi_payload(per_type_clusters: dict, cpi_surprises: pd.DataFrame) -> dict | None:
    """Mapping evento CPI → surprise_yoy via reference_month_end = end-of(M-1).

    Ogni evento CPI rilasciato nel mese M si riferisce al dato CPI del mese M-1.
    req08 e' indicizzato per `reference_month_end` (ultimo giorno di M-1).
    """
    cells = per_type_clusters.get("CPI", {})
    pos, neg = cells.get("pos") or [], cells.get("neg") or []
    if not pos and not neg:
        return None

    def z_for_event(center: pd.Timestamp) -> float:
        # mese di rilascio dell'evento (UTC date → reference_month_end del mese precedente)
        rel_date = center.tz_convert("America/New_York").date()
        ref_month = pd.Timestamp(rel_date) - pd.offsets.MonthEnd(1)
        if ref_month in cpi_surprises.index:
            return float(cpi_surprises.loc[ref_month, "surprise_yoy"])
        return np.nan

    centers_pos, re_pos, rb_pos = _cluster_rows(pos)
    centers_neg, re_neg, rb_neg = _cluster_rows(neg)
    s_pos = np.array([z_for_event(c) for c in centers_pos])
    s_neg = np.array([z_for_event(c) for c in centers_neg])

    # pooled (per T2): r_e/r_b di TUTTI gli eventi CPI (pos+neg), allineati con Z
    r_e = np.concatenate([re_pos, re_neg])
    r_b = np.concatenate([rb_pos, rb_neg])
    Z = np.concatenate([s_pos, s_neg])

    # filter NaN-in-Z (eventi senza match nel req08)
    mask = ~np.isnan(Z)
    return {
        "r_e": r_e[mask], "r_b": r_b[mask], "Z": Z[mask],
        "r_e_pos": re_pos[~np.isnan(s_pos)], "r_b_pos": rb_pos[~np.isnan(s_pos)],
        "s_pos": s_pos[~np.isnan(s_pos)],
        "r_e_neg": re_neg[~np.isnan(s_neg)], "r_b_neg": rb_neg[~np.isnan(s_neg)],
        "s_neg": s_neg[~np.isnan(s_neg)],
        "n_pooled_matched": int(mask.sum()),
        "n_pos_matched": int((~np.isnan(s_pos)).sum()),
        "n_neg_matched": int((~np.isnan(s_neg)).sum()),
    }


def build_fomc_payload(per_type_clusters: dict, prices: dict) -> dict | None:
    """FOMC m_e = PC1 PCA su (FFc1, FFc2, FFc3, SRc1, SRc2) — deltas su finestra HFI ±15 min.

    Versione PRE-REGISTRATA (SPEC §8): set FISSO di 5 serie money-market <1y, PCA pooled.
    Carica i futures tassi NON gia in `prices` (config.INTRADAY_FILES non li ha).
    """
    cells = per_type_clusters.get("FOMC", {})
    pos, neg = cells.get("pos") or [], cells.get("neg") or []
    if not pos and not neg:
        return None

    rate_files = {
        "FFc1": "FFc1_1min.csv", "FFc2": "FFc2_1min.csv", "FFc3": "FFc3_1min.csv",
        "SRc1": "SRc1_1min.csv", "SRc2": "SRc2_1min.csv",
    }
    rate_series = {}
    for sym, fname in rate_files.items():
        p = config.INTRADAY_DIR / fname
        if not p.exists():
            print(f"[FOMC payload] WARN: missing {p}, skip {sym}")
            continue
        rate_series[sym] = data.load_minute(p, price_col="PX_LAST")
    if len(rate_series) < 2:
        print("[FOMC payload] insufficient rate futures for PCA — gated")
        return None

    def delta_vec(center: pd.Timestamp):
        out = []
        for sym, s in rate_series.items():
            d = windows.extract_window(s, center)
            if d is None:
                return None
            out.append(d)
        return np.array(out)

    centers_pos, re_pos, rb_pos = _cluster_rows(pos)
    centers_neg, re_neg, rb_neg = _cluster_rows(neg)
    deltas_pos = [delta_vec(c) for c in centers_pos]
    deltas_neg = [delta_vec(c) for c in centers_neg]

    mask_pos = [d is not None for d in deltas_pos]
    mask_neg = [d is not None for d in deltas_neg]
    deltas_pos_arr = np.array([d for d in deltas_pos if d is not None]) if any(mask_pos) else np.zeros((0, len(rate_series)))
    deltas_neg_arr = np.array([d for d in deltas_neg if d is not None]) if any(mask_neg) else np.zeros((0, len(rate_series)))

    if deltas_pos_arr.size == 0 and deltas_neg_arr.size == 0:
        return None

    deltas_all = np.vstack([deltas_pos_arr, deltas_neg_arr])
    me_all = loaders.m_e_pca(deltas_all)
    n_p = deltas_pos_arr.shape[0]
    me_pos = me_all[:n_p]
    me_neg = me_all[n_p:]

    re_pos_f = re_pos[mask_pos]; rb_pos_f = rb_pos[mask_pos]
    re_neg_f = re_neg[mask_neg]; rb_neg_f = rb_neg[mask_neg]

    return {
        "r_e": np.concatenate([re_pos_f, re_neg_f]),
        "r_b": np.concatenate([rb_pos_f, rb_neg_f]),
        "Z": me_all,
        "r_e_pos": re_pos_f, "r_b_pos": rb_pos_f, "s_pos": me_pos,
        "r_e_neg": re_neg_f, "r_b_neg": rb_neg_f, "s_neg": me_neg,
        "n_pooled_matched": int(len(me_all)),
        "n_pos_matched": int(n_p),
        "n_neg_matched": int(len(me_all) - n_p),
        "rate_futures_used": list(rate_series.keys()),
        "approach": "set fisso 5 serie (SPEC §8 pre-registrato)",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"=== execute.py — {RUN_LABEL} (timestamp={RUN_TIMESTAMP}) ===")

    # 1. Eventi
    print("[1/8] events ...")
    events = data.load_events(EVENTS_CSV)
    print(f"  events: {len(events)}")

    # 2. Prezzi intraday
    print("[2/8] prices (ES/TY/STXE/FGBL) ...")
    prices = run.load_prices()
    for sym, s in prices.items():
        print(f"  {sym}: {len(s)} ticks, {s.index.min()} -> {s.index.max()}")

    # 3. Regimi (corr 63gg, ricalcolati dal raw)
    print("[3/8] regimes from raw (window=63gg) ...")
    regime_by_area = run.compute_regimes(prices)
    for area, ser in regime_by_area.items():
        n = ser.notna().sum()
        print(f"  {area}: {n} giorni etichettati")

    # 4. Calendario contaminanti
    print("[4/8] contaminant centers ...")
    contaminant_centers = load_contaminant_centers(CONTAMINANTS_CSV)
    print(f"  contaminanti: {len(contaminant_centers)}")
    event_centers = set(pd.to_datetime(events["timestamp"], utc=True))
    reject = run.build_calendar_reject(event_centers, contaminant_centers)

    # 5. Assemble celle tipo × regime
    print("[5/8] assemble cells ...")
    per_type_clusters, accounting = run.assemble(events, prices, regime_by_area, reject)
    for t in config.EVENT_TYPES:
        n_pos = len(per_type_clusters[t]["pos"])
        n_neg = len(per_type_clusters[t]["neg"])
        print(f"  {t}: pos={n_pos}, neg={n_neg}")

    # 6. Input secondari
    print("[6/8] exogenous + cpi_yoy + surprises ...")
    exogenous_series = {nm: load_fred_snapshot(nm) for nm in config.T7_EXOGENOUS_REQUIRED}
    cpi_yoy = load_fred_snapshot("CPI_YoY")
    cpi_surprises = load_cpi_surprises()

    surprises_by_type = {}
    cpi_payload = build_cpi_payload(per_type_clusters, cpi_surprises)
    if cpi_payload:
        surprises_by_type["CPI"] = cpi_payload
        print(f"  CPI payload: pooled={cpi_payload['n_pooled_matched']}, pos={cpi_payload['n_pos_matched']}, neg={cpi_payload['n_neg_matched']}")
    fomc_payload = build_fomc_payload(per_type_clusters, prices)
    if fomc_payload:
        surprises_by_type["FOMC"] = fomc_payload
        print(f"  FOMC payload: pooled={fomc_payload['n_pooled_matched']}, pos={fomc_payload['n_pos_matched']}, neg={fomc_payload['n_neg_matched']}, approach={fomc_payload['approach']}")
        print(f"    rates={fomc_payload['rate_futures_used']}")
    # NFP/ECB: non alimentati (consensus non disponibile / Altavilla LEVEL gated)
    print(f"  NFP: NOT FED (consensus non reperibile — SPEC §8)")
    print(f"  ECB: NOT FED (Altavilla LEVEL parser gated — loaders.load_ecb_level)")

    # 7. Run
    print("[7/8] run.run_protocol_full ...")
    rng = config.make_rng("execute_v2_signflip_2026-06-22")
    manifest_inputs = [
        provenance.make_entry(
            figure="execute.py", script=Path(__file__),
            inputs=[EVENTS_CSV, CONTAMINANTS_CSV, CPI_SURPRISE_CSV,
                    SNAPSHOTS_DIR / "T10Y2Y.csv", SNAPSHOTS_DIR / "VIXCLS.csv",
                    SNAPSHOTS_DIR / "CPI_YoY.csv"],
            seed_name="execute_v2_signflip_2026-06-22",
            timestamp=RUN_TIMESTAMP,
        )
    ]
    result = run.run_protocol_full(
        per_type_clusters, rng,
        events=events,
        prices=prices,
        reject=reject,
        exogenous_series=exogenous_series,
        cpi_yoy=cpi_yoy,
        surprises_by_type=surprises_by_type,
        decomp_inputs=None,  # GATED: loader eventi→duration equity non implementato
        manifest_path=OUT_DIR / "manifest_authoritative.json",
        manifest_timestamp=RUN_TIMESTAMP,
        manifest_inputs=manifest_inputs,
    )

    # 8. Persistenza
    print("[8/8] writing results ...")
    result_path = OUT_DIR / "result_authoritative.pkl"
    with open(result_path, "wb") as f:
        pickle.dump({
            "result": result,
            "accounting": accounting,
            "label": RUN_LABEL,
            "timestamp": RUN_TIMESTAMP,
            "n_per_type_pos_neg": {t: {"pos": len(per_type_clusters[t]["pos"]),
                                       "neg": len(per_type_clusters[t]["neg"])} for t in config.EVENT_TYPES},
            "n_contaminants": len(contaminant_centers),
            "surprises_fed": list(surprises_by_type.keys()),
            "gated": {
                "NFP_T2_T9": "consensus NFP non disponibile (SPEC §8)",
                "ECB_T2_T9": "Altavilla LEVEL parser gated (loaders.load_ecb_level)",
                "decomposition_daily": "loader eventi→duration equity non implementato",
            },
        }, f)
    print(f"  result: {result_path}  (sha256={sha256_file(result_path)})")
    print(f"  manifest: {OUT_DIR / 'manifest.json'}")
    print("\nDONE. Output grezzi consegnati. Niente interpretazione.")


if __name__ == "__main__":
    main()
