"""execute_ts_gate.py — Cancello canale tasso dalla struttura a termine (Fed).

Estensione finale del kernel 10/diagnostica_canale_tassi/. Pre-registrazione:
  - Eventi: FOMC, CPI, NFP (US). ECB fuori (richiederebbe FEI in euro a più
    scadenze: lo è, ma il briefing chiede questo tentativo SOLO sui Fed events).
  - Struttura a termine: FEIc1, FEIc2, FEIc3, FEIc4 (Eurodollar 3M front 1-4).
  - Fattori: PC1 / PC2 standard via SVD, segno fissato (loading c1 ≥ 0 / c4 ≥ 0).
  - Finestra ±15 min (edge mediana 5 min), seed dichiarato.
  - Soglie del PRIMO cancello (congelate in config):
      (i)  var_explained(PC2) ≥ TS_PC2_VAR_EXPLAINED_MIN
      (ii) frac(|Δc3|>0) ≥ TS_LONG_CONTRACT_MOVEMENT_MIN_FRAC e idem c4
      (iii) la mediana di |PC2| non collassa
  - Soglia del SECONDO cancello: |cos| < 0.95 (kernel) in ENTRAMBI i regimi.

Disciplina:
  - Riporta ENTRAMBI i fattori (PC1 e PC2), in ENTRAMBI i regimi, sempre.
  - Esito (pre-registrato):
      SUCCESS = almeno uno dei due fattori ha |cos| < 0.95 in entrambi i regimi
                (con celle popolate in entrambi i regimi).
      FAIL    = entrambi i fattori sono collineari col regime (|cos| ≥ 0.95)
                in almeno un regime, oppure le celle non si popolano in entrambi.
      PARTIAL = fattore distinto in un solo regime → osservazione, NON success.
  - Niente scelta ex-post del fattore.
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
PKG = ROOT / "CODICI_TESI" / "10_diagnostica_canale_tassi"
sys.path.insert(0, str(PKG))

import config              # noqa: E402
import diagnostics as D    # noqa: E402
import manifest as mf      # noqa: E402
import rate_shock          # noqa: E402
import term_structure as TS  # noqa: E402

OUT_DIR = ROOT / "09_risultati" / "term_structure_channel_gate"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PICKLE_AUTH = ROOT / "09_risultati" / "v2_signflip" / "result_authoritative.pkl"
INTRADAY_DIR = Path("/home/francesco/TESI/Dati/data_processed")
FEI_FILES = {c: INTRADAY_DIR / f"{c}_1min.csv" for c in config.TS_CONTRACTS}
ES_CSV = INTRADAY_DIR / "ESc1_1min.csv"
TY_CSV = INTRADAY_DIR / "TYc1_1min.csv"

SEED_NAME = "ts_gate_run_2026-06-23"
TASK_TIMESTAMP = (
    datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
)
FED_LEGS = ("FOMC", "CPI", "NFP")
COSINE_THR = config.COSINE_HIGH_THRESHOLD_DEFAULT


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_intraday(path: Path, price_col: str = "PX_LAST") -> pd.Series:
    df = pd.read_csv(path, usecols=["Datetime_UTC", price_col])
    df["Datetime_UTC"] = pd.to_datetime(df["Datetime_UTC"], utc=True)
    s = df.set_index("Datetime_UTC")[price_col].astype(float)
    return s[~s.index.duplicated(keep="first")].sort_index().dropna()


def load_events_from_pickle(pkl_path: Path) -> tuple[pd.DataFrame, str, dict]:
    sha = sha256_file(pkl_path)
    with open(pkl_path, "rb") as f:
        obj = pickle.load(f)
    rows = []
    for a in obj["accounting"]:
        s = a["event"]; leg, rest = s.split("@", 1); ts, regime = rest.rsplit("|", 1)
        rows.append({"timestamp": pd.Timestamp(ts), "leg": leg, "regime": regime})
    return pd.DataFrame(rows), sha, {"label": obj["label"], "timestamp": obj["timestamp"]}


def log_return_window(prices: pd.Series, t: pd.Timestamp) -> float:
    w = rate_shock.extract_event_window(prices, t)
    pre, post = w["pre"], w["post"]
    if np.isnan(pre) or np.isnan(post) or pre <= 0 or post <= 0:
        return float("nan")
    return float(np.log(post / pre))


def cells_moments(df: pd.DataFrame, regime_col: str, intensity_col: str) -> dict:
    out = {}
    sub_valid = df.dropna(subset=["r_e", "r_b"])
    for (r, i), s in sub_valid.groupby([regime_col, intensity_col]):
        re = s["r_e"].to_numpy(); rb = s["r_b"].to_numpy()
        if len(re) < 2:
            out[(str(r), str(i))] = {"var_e": float("nan"), "var_b": float("nan"),
                                       "cov_eb": float("nan"), "n": int(len(re))}
            continue
        out[(str(r), str(i))] = {
            "var_e": float(np.var(re, ddof=1)),
            "var_b": float(np.var(rb, ddof=1)),
            "cov_eb": float(np.cov(re, rb, ddof=1)[0, 1]),
            "n": int(len(re)),
        }
    return out


def criterion_d(event_moments: dict) -> dict:
    needed = [("positivo", "high"), ("positivo", "low"),
              ("negativo", "high"), ("negativo", "low")]
    missing = [k for k in needed if k not in event_moments
               or any(np.isnan(event_moments[k].get(f, np.nan))
                       for f in ("var_e", "var_b", "cov_eb"))]
    if missing:
        return {"status": "missing_cells", "missing": missing}
    drate_pos = D.change_vector(
        {"h": event_moments[("positivo", "high")],
         "l": event_moments[("positivo", "low")]}, "h", "l")
    drate_neg = D.change_vector(
        {"h": event_moments[("negativo", "high")],
         "l": event_moments[("negativo", "low")]}, "h", "l")
    dreg_hi  = D.change_vector(
        {"p": event_moments[("positivo", "high")],
         "n": event_moments[("negativo", "high")]}, "p", "n")
    dreg_lo  = D.change_vector(
        {"p": event_moments[("positivo", "low")],
         "n": event_moments[("negativo", "low")]}, "p", "n")
    dist_pos = D.change_vectors_distinctness(drate_pos, dreg_hi)
    dist_neg = D.change_vectors_distinctness(drate_neg, dreg_lo)
    return {
        "status": "ok",
        "delta_rate_pos": drate_pos.tolist(),
        "delta_rate_neg": drate_neg.tolist(),
        "delta_regime_hi": dreg_hi.tolist(),
        "delta_regime_lo": dreg_lo.tolist(),
        "distinctness_at_regime_pos": dist_pos,
        "distinctness_at_regime_neg": dist_neg,
        "non_collinear_pos": bool(abs(dist_pos["cosine"]) < COSINE_THR),
        "non_collinear_neg": bool(abs(dist_neg["cosine"]) < COSINE_THR),
        "passes_d_in_both_regimes": bool(
            abs(dist_pos["cosine"]) < COSINE_THR and abs(dist_neg["cosine"]) < COSINE_THR),
    }


def main() -> int:
    print(f"=== execute_ts_gate.py — {TASK_TIMESTAMP} ===")

    # 1. Events: filtra Fed legs
    events_full, pkl_sha, pkl_meta = load_events_from_pickle(PICKLE_AUTH)
    events = events_full[events_full["leg"].isin(FED_LEGS)].reset_index(drop=True).copy()
    print(f"  events (Fed legs): {len(events)} / {len(events_full)} totali")

    # 2. Prezzi FEIc1..c4 e equity/bond
    print("  loading FEIc1..c4 + ES/TY ...")
    rate_prices = {c: load_intraday(p) for c, p in FEI_FILES.items()}
    eq = load_intraday(ES_CSV)
    bo = load_intraday(TY_CSV)

    # 3. Term-structure deltas per evento
    print("  build_term_structure_table ...")
    ts_table = TS.build_term_structure_table(events, rate_prices)
    delta_cols = [f"delta_{c}" for c in config.TS_CONTRACTS]
    ts_table_clean = ts_table.dropna(subset=delta_cols).reset_index(drop=True)
    print(f"  con tutti i Δ validi: {len(ts_table_clean)} / {len(ts_table)}")

    # 4. Rendimenti r_e, r_b sulla finestra evento
    ts_table_clean["r_e"] = [log_return_window(eq, t) for t in ts_table_clean["timestamp"]]
    ts_table_clean["r_b"] = [log_return_window(bo, t) for t in ts_table_clean["timestamp"]]

    # 5. PCA su tutti gli eventi Fed validi (pooled, come da pre-registrazione)
    deltas_mat = ts_table_clean[delta_cols].to_numpy()
    pca = TS.extract_pc_factors(deltas_mat, contracts=list(config.TS_CONTRACTS))
    ts_table_clean["pc1_score"] = pca["scores"][:, 0]
    ts_table_clean["pc2_score"] = pca["scores"][:, 1]
    print(f"  var_explained: {[round(float(x), 4) for x in pca['var_explained']]}")
    print(f"  PC1 loadings: {dict(zip(config.TS_CONTRACTS, [round(float(x), 4) for x in pca['loadings'][0]]))}")
    print(f"  PC2 loadings: {dict(zip(config.TS_CONTRACTS, [round(float(x), 4) for x in pca['loadings'][1]]))}")

    # 6. PRIMO CANCELLO
    gate1 = TS.first_gate_non_degeneracy(ts_table_clean, pca)
    print(f"  gate-1 passed: {gate1['passed']}")
    for k, v in gate1.items():
        if isinstance(v, dict) and "passed" in v:
            print(f"     {k}: {v}")

    # 7. SECONDO CANCELLO — applica (d) a PC1 e a PC2 (riporta entrambi)
    factor_results = {}
    fraction_near_zero = {}
    for fname, score_col in (("PC1", "pc1_score"), ("PC2", "pc2_score")):
        scores = ts_table_clean[score_col].to_numpy()
        intensity = np.abs(scores)
        # Trasparenza: frazione di score "vicini a zero" (≤ percentile 5% di |·|)
        if len(intensity) > 0:
            small_thr = float(np.quantile(intensity, 0.05))
            frac_near_zero = float((intensity <= small_thr).mean())
        else:
            small_thr = float("nan"); frac_near_zero = float("nan")
        fraction_near_zero[fname] = {"threshold_q05": small_thr,
                                       "fraction_below_or_eq": frac_near_zero}

        labels = D.dichotomize(intensity, mode="median")
        df = ts_table_clean.copy()
        df["intensity_label"] = labels
        # event_moments per (regime, intensity_label)
        em = cells_moments(df, regime_col="regime", intensity_col="intensity_label")
        # counts per cella
        counts = {}
        for (r, i), grp in df.dropna(subset=["r_e", "r_b"]).groupby(["regime", "intensity_label"]):
            counts[(str(r), str(i))] = int(len(grp))
        below = [k for k, v in counts.items() if v < config.MIN_CELL_EVENTS]

        d_res = criterion_d(em)
        factor_results[fname] = {
            "intensity_partition": {
                "mode": "median",
                "median_abs_score": float(np.median(intensity)) if len(intensity) else float("nan"),
                "n_high": int((labels == "high").sum()),
                "n_low": int((labels == "low").sum()),
                "fraction_near_zero": fraction_near_zero[fname],
            },
            "cell_counts": counts,
            "cells_below_min": below,
            "criterion_d": d_res,
        }

    # 8. ESITO complessivo pre-registrato
    def factor_succeeds(fr: dict) -> bool:
        if fr["cells_below_min"]:
            return False
        d = fr["criterion_d"]
        return d.get("status") == "ok" and d.get("passes_d_in_both_regimes", False)

    def factor_partial(fr: dict) -> bool:
        d = fr["criterion_d"]
        if d.get("status") != "ok": return False
        return (d.get("non_collinear_pos", False)
                != d.get("non_collinear_neg", False)) and not fr["cells_below_min"]

    pc1_succ = factor_succeeds(factor_results["PC1"])
    pc2_succ = factor_succeeds(factor_results["PC2"])
    pc1_par  = factor_partial(factor_results["PC1"])
    pc2_par  = factor_partial(factor_results["PC2"])

    if not gate1["passed"]:
        outcome = "FAIL_GATE_1"
    elif pc1_succ or pc2_succ:
        outcome = "SUCCESS"
    elif pc1_par or pc2_par:
        outcome = "PARTIAL"
    else:
        outcome = "FAIL_GATE_2"

    print(f"\n  OUTCOME: {outcome}")
    print(f"  PC1 success: {pc1_succ}  PC2 success: {pc2_succ}")
    print(f"  PC1 partial: {pc1_par}   PC2 partial: {pc2_par}")

    # ------------------------------- Output -------------------------------
    def jsonify(x):
        if isinstance(x, dict):
            return {(f"{k[0]}|{k[1]}" if isinstance(k, tuple) else str(k)): jsonify(v)
                    for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [jsonify(v) for v in x]
        if isinstance(x, (np.ndarray,)):
            return [jsonify(v) for v in x.tolist()]
        if isinstance(x, (np.floating, np.integer)):
            return x.item()
        return x

    verdicts = {
        "outcome": outcome,
        "gate_1_passed": bool(gate1["passed"]),
        "gate_1_subchecks": {
            "i_pc2_var_explained":
                bool(gate1["check_i_pc2_var_explained"]["passed"]),
            "ii_long_contract_movement":
                bool(gate1["check_ii_long_contract_movement"]["passed"]),
            "iii_pc2_partition_non_degenerate":
                bool(gate1["check_iii_pc2_partition_non_degenerate"]["passed"]),
        },
        "factor_PC1_success": bool(pc1_succ),
        "factor_PC2_success": bool(pc2_succ),
        "factor_PC1_partial": bool(pc1_par),
        "factor_PC2_partial": bool(pc2_par),
        "n_events_fed_total": int(len(events)),
        "n_events_with_all_deltas_valid": int(len(ts_table_clean)),
    }
    (OUT_DIR / "verdicts.json").write_bytes(
        json.dumps(verdicts, indent=2, sort_keys=True).encode("utf-8"))

    numbers = {
        "pca": {
            "contracts": list(config.TS_CONTRACTS),
            "var_explained": [float(x) for x in pca["var_explained"]],
            "loadings_pc1": {c: float(v) for c, v in zip(config.TS_CONTRACTS, pca["loadings"][0])},
            "loadings_pc2": {c: float(v) for c, v in zip(config.TS_CONTRACTS, pca["loadings"][1])},
            "n_events_used": int(pca["n_events"]),
            "mean_deltas": {c: float(v) for c, v in zip(config.TS_CONTRACTS, pca["mean_deltas"])},
        },
        "gate_1": jsonify(gate1),
        "factor_PC1": jsonify(factor_results["PC1"]),
        "factor_PC2": jsonify(factor_results["PC2"]),
        "thresholds": {
            "pc2_var_explained_min": config.TS_PC2_VAR_EXPLAINED_MIN,
            "long_contract_movement_min_frac": config.TS_LONG_CONTRACT_MOVEMENT_MIN_FRAC,
            "min_cell_events": config.MIN_CELL_EVENTS,
            "cosine_high_threshold": COSINE_THR,
        },
    }
    (OUT_DIR / "numbers.json").write_bytes(
        json.dumps(numbers, indent=2, sort_keys=True, default=str).encode("utf-8"))

    # Manifest
    input_paths = [PICKLE_AUTH] + list(FEI_FILES.values()) + [ES_CSV, TY_CSV]
    m = mf.build_gate_manifest(
        rate_contract="|".join(config.TS_CONTRACTS),
        window_half_min=config.HALF_MIN_WINDOW,
        partition_mode="median (on |PC1| and |PC2|)",
        min_cell=config.MIN_CELL_EVENTS,
        seed_name=SEED_NAME,
        timestamp=TASK_TIMESTAMP,
        input_paths=input_paths,
        thresholds={
            "pc2_var_explained_min": config.TS_PC2_VAR_EXPLAINED_MIN,
            "long_contract_movement_min_frac": config.TS_LONG_CONTRACT_MOVEMENT_MIN_FRAC,
            "min_cell_events": config.MIN_CELL_EVENTS,
            "cosine_high_threshold": COSINE_THR,
        },
    )
    m["pickle_auth"] = {"path": str(PICKLE_AUTH), "sha256": pkl_sha,
                         "run_label": pkl_meta["label"], "run_timestamp": pkl_meta["timestamp"]}
    m["executor"] = {
        "script_path": str(Path(__file__).resolve()),
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "package_path": str(PKG),
        "package_module_sha256": {p.name: sha256_file(p) for p in sorted(PKG.glob("*.py"))},
        "tests_dir": str(PKG / "tests"),
        "tests_module_sha256": {p.name: sha256_file(p) for p in sorted((PKG / "tests").glob("*.py"))},
        "namespace_output_dir": str(OUT_DIR),
    }
    m["legs_in_scope"] = list(FED_LEGS)
    m["n_events"] = {
        "fed_total": int(len(events)),
        "with_all_4_deltas_valid": int(len(ts_table_clean)),
        "by_leg_regime": {f"{l}|{r}": int(c) for (l, r), c
                          in events.groupby(["leg", "regime"]).size().items()},
        "with_returns_valid": int(ts_table_clean[["r_e", "r_b"]].notna().all(axis=1).sum()),
    }
    m["pre_registration"] = (
        "Term-structure (Eurodollar FEIc1..c4) PCA, PC1+PC2 segno fissato. "
        "Eventi Fed (FOMC, CPI, NFP) — ECB fuori (vedi briefing). "
        "ESITO: SUCCESS sse almeno uno fra PC1 e PC2 ha |cos|<0.95 in entrambi i regimi, "
        "con celle popolate in entrambi; PARTIAL se un fattore distinto in un solo regime; "
        "FAIL altrimenti. Soglie congelate prima del run."
    )
    mf.write_manifest(OUT_DIR / "manifest.json", m)

    # Report
    th_text = (f"var_PC2 ≥ {config.TS_PC2_VAR_EXPLAINED_MIN}; "
               f"|Δc3|>0 e |Δc4|>0 in ≥ {config.TS_LONG_CONTRACT_MOVEMENT_MIN_FRAC}; "
               f"min_cell = {config.MIN_CELL_EVENTS}; |cos| < {COSINE_THR}.")
    lines = [
        "# Cancello canale tasso dalla struttura a termine — report esecutore",
        "",
        f"- timestamp: `{TASK_TIMESTAMP}`",
        f"- eventi in ambito: {list(FED_LEGS)} ({len(events)} totali; ECB FUORI per pre-registrazione)",
        f"- contratti: {list(config.TS_CONTRACTS)}",
        f"- finestra: ±{config.HALF_MIN_WINDOW} min (edge mediana {config.MEDIAN_EDGE_MIN} min)",
        f"- seed: `{SEED_NAME}` (master {config.MASTER_SEED})",
        f"- soglie a priori (congelate): {th_text}",
        f"- config_hash: `{config.config_hash()}`",
        f"- pickle_auth sha256: `{pkl_sha}`",
        "",
        f"## ESITO: **{outcome}**",
        "",
        f"- gate-1 passed: **{gate1['passed']}**",
        f"  - (i) var_explained(PC2) = {gate1['check_i_pc2_var_explained']['value']:.4g} "
        f"(soglia {gate1['check_i_pc2_var_explained']['threshold']}) → "
        f"{'PASS' if gate1['check_i_pc2_var_explained']['passed'] else 'FAIL'}",
        f"  - (ii) frazioni di movimento c3/c4: "
        f"{ {k: round(v, 4) for k, v in gate1['check_ii_long_contract_movement']['fractions'].items()} } "
        f"(soglia {gate1['check_ii_long_contract_movement']['threshold']}) → "
        f"{'PASS' if gate1['check_ii_long_contract_movement']['passed'] else 'FAIL'}",
        f"  - (iii) partition |PC2| (n_high={gate1['check_iii_pc2_partition_non_degenerate']['n_high']}, "
        f"n_low={gate1['check_iii_pc2_partition_non_degenerate']['n_low']}) → "
        f"{'PASS' if gate1['check_iii_pc2_partition_non_degenerate']['passed'] else 'FAIL'}",
        f"- factor_PC1: success={pc1_succ}, partial={pc1_par}",
        f"- factor_PC2: success={pc2_succ}, partial={pc2_par}",
        "",
        "## PCA — struttura a termine (pooled Fed events)",
        "",
        f"- n_events_used = {pca['n_events']}",
        f"- var_explained = {[round(float(x), 4) for x in pca['var_explained']]}",
        f"- PC1 loadings (livello attesa: tutti concordi):",
    ]
    for c, v in zip(config.TS_CONTRACTS, pca["loadings"][0]):
        lines.append(f"  - {c}: {float(v):.4f}")
    lines.append("- PC2 loadings (pendenza attesa: segno opposto tra c1 e c4):")
    for c, v in zip(config.TS_CONTRACTS, pca["loadings"][1]):
        lines.append(f"  - {c}: {float(v):.4f}")

    for fname in ("PC1", "PC2"):
        fr = factor_results[fname]
        lines += [
            "",
            f"## Fattore {fname} — criterio (d)",
            "",
            f"- partition median |{fname}| = {fr['intensity_partition']['median_abs_score']:.4g}, "
            f"n_high = {fr['intensity_partition']['n_high']}, n_low = {fr['intensity_partition']['n_low']}",
            f"- fraction near zero (≤ q05 di |score|) = "
            f"{fr['intensity_partition']['fraction_near_zero']['fraction_below_or_eq']:.4g} "
            f"(threshold q05 = {fr['intensity_partition']['fraction_near_zero']['threshold_q05']:.6g})",
            "- cell counts (regime × intensity):",
        ]
        for k, v in sorted(fr["cell_counts"].items()):
            lines.append(f"  - {k}: {v}")
        if fr["cells_below_min"]:
            lines.append(f"  - **celle sotto soglia** ({config.MIN_CELL_EVENTS}): "
                         f"{fr['cells_below_min']}")
        d = fr["criterion_d"]
        if d.get("status") == "missing_cells":
            lines.append(f"- (d) status: `missing_cells` — missing {d['missing']}")
        else:
            lines += [
                f"- Δ_rate (positivo) = {[f'{x:.4g}' for x in d['delta_rate_pos']]}",
                f"- Δ_rate (negativo) = {[f'{x:.4g}' for x in d['delta_rate_neg']]}",
                f"- Δ_regime (high)   = {[f'{x:.4g}' for x in d['delta_regime_hi']]}",
                f"- Δ_regime (low)    = {[f'{x:.4g}' for x in d['delta_regime_lo']]}",
                f"- distinctness @ positivo: cos = {d['distinctness_at_regime_pos']['cosine']:.6g}, "
                f"angle = {d['distinctness_at_regime_pos']['angle_deg']:.3f}°, "
                f"rank = {d['distinctness_at_regime_pos']['rank_numerical']} → "
                f"non collineare: {d['non_collinear_pos']}",
                f"- distinctness @ negativo: cos = {d['distinctness_at_regime_neg']['cosine']:.6g}, "
                f"angle = {d['distinctness_at_regime_neg']['angle_deg']:.3f}°, "
                f"rank = {d['distinctness_at_regime_neg']['rank_numerical']} → "
                f"non collineare: {d['non_collinear_neg']}",
                f"- passa (d) in ENTRAMBI i regimi: **{d['passes_d_in_both_regimes']}**",
            ]
    lines += [
        "",
        "## Note dell'esecutore",
        "",
        "- ECB fuori scope (briefing). `events_df` letto dal pickle autoritativo del v2.",
        "- PCA pooled sui Fed events con Δ valido su tutti e 4 i contratti (filtro NaN dichiarato).",
        "- Convenzione di segno PC1/PC2 fissata e validata su test sintetico (45/45 verdi).",
        "- Riportati entrambi i fattori, in entrambi i regimi. Nessuna scelta ex-post. "
        "L'identificabilità (lettura dell'esito) è del ricercatore.",
    ]
    (OUT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nDONE → {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
