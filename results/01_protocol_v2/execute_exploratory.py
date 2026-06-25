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

RUN_TIMESTAMP = "2026-06-22T13:00:00Z"   # PASSATO ESPLICITAMENTE (no clock interno)
RUN_LABEL = "v2_signflip_run2_2026-06-22_fomc_variable_k"


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
    """FOMC m_e via PCA SU SET SERIE VARIABILE PER EVENTO (decisione esecutore 2026-06-22).

    Approccio cascata-per-gruppi: per ogni evento si rileva l'insieme delle serie
    money-market <1y con tick in finestra ±15 min; gli eventi sono raggruppati per
    tupla-disponibilita e si esegue PCA pooled DENTRO ogni gruppo (n_eventi >= 2
    nel gruppo). Loadings cambiano fra gruppi (eterogeneita esplicita), m_e di
    ogni evento e' la PC1 calcolata sul gruppo a cui appartiene.

    Motivazione: SRc1/SRc2 (SOFR futures) hanno tick sparsi negli orari FOMC,
    eventi con tutte e 5 le serie disponibili erano solo 2/189. Il fallback a
    cascata mantiene la disciplina del SPEC §8 ('PC1 money-market <1y, se
    fattibile') con set serie best-effort per evento.
    """
    from collections import defaultdict

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

    centers_pos, re_pos, rb_pos = _cluster_rows(pos)
    centers_neg, re_neg, rb_neg = _cluster_rows(neg)
    all_centers = list(centers_pos) + list(centers_neg)
    all_re = np.concatenate([re_pos, re_neg])
    all_rb = np.concatenate([rb_pos, rb_neg])
    all_regs = ["pos"] * len(centers_pos) + ["neg"] * len(centers_neg)

    # Per ogni evento: dict {sym: delta_or_None} su tutte le rate_series
    event_deltas = [
        {sym: windows.extract_window(s, c) for sym, s in rate_series.items()}
        for c in all_centers
    ]
    # Set serie disponibili (delta != None) per ogni evento
    event_sets = [
        frozenset(sym for sym, d in ed.items() if d is not None) for ed in event_deltas
    ]

    # Raggruppa eventi per (set-disponibilita) con almeno 2 serie nel set
    groups: dict = defaultdict(list)
    for i, s in enumerate(event_sets):
        if len(s) >= 2:
            groups[s].append(i)
    # Tieni solo gruppi con n_eventi >= 2 (PCA degenere su 1 evento)
    groups = {s: idxs for s, idxs in groups.items() if len(idxs) >= 2}

    # PCA pooled DENTRO ogni gruppo
    me_per_event = np.full(len(all_centers), np.nan)
    loadings_by_group: dict = {}
    for s, idxs in groups.items():
        syms = sorted(s)
        M = np.array([[event_deltas[i][sym] for sym in syms] for i in idxs])
        me_vec = loaders.m_e_pca(M)
        for k, i in enumerate(idxs):
            me_per_event[i] = me_vec[k]
        loadings_by_group["+".join(syms)] = {"n_events": int(len(idxs)),
                                              "series": syms}

    valid_mask = ~np.isnan(me_per_event)
    if not valid_mask.any():
        return None

    me_valid = me_per_event[valid_mask]
    re_valid = all_re[valid_mask]
    rb_valid = all_rb[valid_mask]
    regs_valid = np.array([all_regs[i] for i in range(len(all_centers)) if valid_mask[i]])
    is_pos = regs_valid == "pos"
    is_neg = regs_valid == "neg"

    return {
        "r_e": re_valid, "r_b": rb_valid, "Z": me_valid,
        "r_e_pos": re_valid[is_pos], "r_b_pos": rb_valid[is_pos], "s_pos": me_valid[is_pos],
        "r_e_neg": re_valid[is_neg], "r_b_neg": rb_valid[is_neg], "s_neg": me_valid[is_neg],
        "n_pooled_matched": int(valid_mask.sum()),
        "n_pos_matched": int(is_pos.sum()),
        "n_neg_matched": int(is_neg.sum()),
        "groups_summary": {k: v["n_events"] for k, v in loadings_by_group.items()},
        "loadings_by_group": loadings_by_group,
        "approach": "cascata-per-gruppi (set serie variabile per evento)",
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
        print(f"    groups: {fomc_payload['groups_summary']}")
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
        manifest_path=OUT_DIR / "manifest_v2_fomc_variable_k.json",
        manifest_timestamp=RUN_TIMESTAMP,
        manifest_inputs=manifest_inputs,
    )

    # 8. Persistenza
    print("[8/8] writing results ...")
    result_path = OUT_DIR / "result_v2_fomc_variable_k.pkl"
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
