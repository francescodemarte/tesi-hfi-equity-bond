"""execute_gate.py — Esecutore del cancello descrittivo per il canale tassi.

Mandato: eseguire il cancello (CODICI_TESI/10_diagnostica_canale_tassi/) sui dati
reali, contratto FFc2, finestra ±15 min, partizione mediana, seed dichiarato.
Output: verdicts.json, numbers.json, manifest.json, report.md (namespace
09_risultati/rate_channel_gate/).

Disciplina (presidio anti-fabbricazione):
- Sola lettura su tutti gli input. Nessuna scrittura fuori dal namespace.
- Nessuna modifica dei kernel (diagnostics.py, gate.py, rate_shock.py, manifest.py).
- Soglie congelate dal config: η²≤0.20 (a), |κ|≤0.20 (b), min_cell=30 (c), |cos|<0.95 (d).
- Eventi non alimentabili → intensity_raw=NaN; run_gate li filtra a valle.
- Eventi con regime indefinito non rientrano (events_df è costruito dall'
  accounting del run autoritativo del protocollo v2 — input datato, sola lettura).
- Niente conclusione di identificabilità complessiva: solo verdetti per criterio.
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
PKG = ROOT / "CODICI_TESI" / "10_diagnostica_canale_tassi"
sys.path.insert(0, str(PKG))

# Import del package del cancello (10) — solo questo, niente altro codice repo.
import config        # noqa: E402
import diagnostics as D  # noqa: E402
import gate          # noqa: E402
import manifest as mf    # noqa: E402
import rate_shock    # noqa: E402

OUT_DIR = ROOT / "09_risultati" / "rate_channel_gate_FEIc1"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Input datati (sola lettura).
PICKLE_AUTH = ROOT / "09_risultati" / "v2_signflip" / "result_authoritative.pkl"
INTRADAY_DIR = Path("/home/francesco/TESI/Dati/data_processed")
RATE_CSV = INTRADAY_DIR / "FEIc1_1min.csv"
ES_CSV = INTRADAY_DIR / "ESc1_1min.csv"
TY_CSV = INTRADAY_DIR / "TYc1_1min.csv"
STXE_CSV = INTRADAY_DIR / "STXE_continuous_1min.csv"
FGBL_CSV = INTRADAY_DIR / "FGBLc1_1min.csv"

CONTRACT = "FEIc1"
SEED_NAME = "gate_run_2026-06-22"
# Timestamp ISO passato dall'esterno (no clock interno del kernel): qui lo
# stampiamo a tempo di esecuzione dell'esecutore.
TASK_TIMESTAMP = (
    datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# --------------------------------------------------------------------------
# Loaders intraday (formato data_processed: Datetime_UTC + colonna prezzo)
# --------------------------------------------------------------------------

def load_intraday(path: Path, price_col: str) -> pd.Series:
    df = pd.read_csv(path, usecols=["Datetime_UTC", price_col])
    df["Datetime_UTC"] = pd.to_datetime(df["Datetime_UTC"], utc=True)
    s = df.set_index("Datetime_UTC")[price_col].astype(float)
    s = s[~s.index.duplicated(keep="first")].sort_index()
    return s.dropna()


# --------------------------------------------------------------------------
# Costruzione events_df dall'accounting del pickle autoritativo (input datato)
# --------------------------------------------------------------------------

def load_events_from_pickle(pkl_path: Path) -> tuple[pd.DataFrame, str]:
    import pickle
    sha = sha256_file(pkl_path)
    with open(pkl_path, "rb") as f:
        obj = pickle.load(f)
    rows = []
    for a in obj["accounting"]:
        s = a["event"]
        leg, rest = s.split("@", 1)
        ts, regime = rest.rsplit("|", 1)
        rows.append({"timestamp": pd.Timestamp(ts), "leg": leg, "regime": regime})
    return pd.DataFrame(rows), sha


# --------------------------------------------------------------------------
# Rendimenti equity/bond sulla finestra evento ±15 min (edge mediana 5 min)
# Replica della disciplina del protocollo v2: r = log(post/pre), pre/post
# mediana dei prezzi nei primi/ultimi 5 minuti. NON modifica i kernel.
# --------------------------------------------------------------------------

def log_return_window(prices: pd.Series, t: pd.Timestamp,
                       half_min: int = config.HALF_MIN_WINDOW,
                       edge_min: int = config.MEDIAN_EDGE_MIN) -> float:
    w = rate_shock.extract_event_window(prices, t, half_min=half_min, edge_min=edge_min)
    pre, post = w["pre"], w["post"]
    if np.isnan(pre) or np.isnan(post) or pre <= 0 or post <= 0:
        return float("nan")
    return float(np.log(post / pre))


# --------------------------------------------------------------------------
# Mappa leg → (equity_series, bond_series): NFP/CPI/FOMC su ES/TY, ECB su
# STXE/FGBL (stessa scelta INSTRUMENT_MAP del protocollo v2).
# --------------------------------------------------------------------------

def event_returns(events_df: pd.DataFrame,
                  eq_by_area: dict, bo_by_area: dict) -> pd.DataFrame:
    out_re, out_rb = [], []
    for _, ev in events_df.iterrows():
        leg = ev["leg"]
        if leg == "ECB":
            eq, bo = eq_by_area["EU"], bo_by_area["EU"]
        else:
            eq, bo = eq_by_area["US"], bo_by_area["US"]
        out_re.append(log_return_window(eq, ev["timestamp"]))
        out_rb.append(log_return_window(bo, ev["timestamp"]))
    out = events_df.copy()
    out["r_e"] = out_re
    out["r_b"] = out_rb
    return out


# --------------------------------------------------------------------------
# Momenti di cella regime × intensity_label dai rendimenti delle finestre evento.
# var_e=Var(r_e), var_b=Var(r_b), cov_eb=Cov(r_e, r_b), ddof=1.
# --------------------------------------------------------------------------

def compute_cell_moments(events_with_returns_and_label: pd.DataFrame,
                          regime_col: str = "regime",
                          intensity_col: str = "intensity_label") -> dict:
    out = {}
    valid = events_with_returns_and_label.dropna(subset=["r_e", "r_b"]).copy()
    for (r, i), sub in valid.groupby([regime_col, intensity_col]):
        re = sub["r_e"].to_numpy(dtype=float)
        rb = sub["r_b"].to_numpy(dtype=float)
        if len(re) < 2:
            # Vuoto/insufficiente: registriamo NaN nei momenti (saranno propagati
            # in change_vector se la cella manca). Non si fabbricano valori.
            out[(str(r), str(i))] = {
                "var_e": float("nan"), "var_b": float("nan"),
                "cov_eb": float("nan"), "n": int(len(re)),
            }
            continue
        out[(str(r), str(i))] = {
            "var_e": float(np.var(re, ddof=1)),
            "var_b": float(np.var(rb, ddof=1)),
            "cov_eb": float(np.cov(re, rb, ddof=1)[0, 1]),
            "n": int(len(re)),
        }
    return out


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    print(f"=== execute_gate.py — {TASK_TIMESTAMP} — contract={CONTRACT} ===")

    # 1. events_df da pickle autoritativo (input datato in sola lettura)
    print("[1/7] events_df from authoritative pickle accounting ...")
    events_df, pkl_sha = load_events_from_pickle(PICKLE_AUTH)
    print(f"  events: {len(events_df)} (pickle sha256={pkl_sha[:16]}...)")
    print(f"  by (leg, regime): {events_df.groupby(['leg','regime']).size().to_dict()}")

    # 2. Carico contratto tassi + equity/bond (ES/TY per US, STXE/FGBL per EU)
    print("[2/7] loading intraday prices ...")
    rate_prices = load_intraday(RATE_CSV, "PX_LAST")
    eq_us = load_intraday(ES_CSV, "PX_LAST")
    bo_us = load_intraday(TY_CSV, "PX_LAST")
    eq_eu = load_intraday(STXE_CSV, "Mid_raw") if "STXE" in str(STXE_CSV) else load_intraday(STXE_CSV, "PX_LAST")
    bo_eu = load_intraday(FGBL_CSV, "PX_LAST")
    print(f"  {CONTRACT}: {len(rate_prices)} ticks, span {rate_prices.index.min()} → {rate_prices.index.max()}")

    # 3. Tabella intensità tasso
    print("[3/7] build_event_intensity_table ...")
    ev_intensity = rate_shock.build_event_intensity_table(events_df, rate_prices,
                                                          contract_label=CONTRACT)
    n_with = int(ev_intensity["intensity_raw"].notna().sum())
    print(f"  con intensità valida: {n_with}/{len(ev_intensity)}")

    # 4. Rendimenti equity/bond su finestra annuncio
    print("[4/7] compute equity/bond returns on event window ...")
    ev_returns = event_returns(events_df, {"US": eq_us, "EU": eq_eu},
                                          {"US": bo_us, "EU": bo_eu})

    # 5. Unione: merge per (timestamp, leg, regime) — gli indici sono allineati
    print("[5/7] merge intensity + returns ...")
    if not (ev_intensity[["timestamp", "leg", "regime"]].reset_index(drop=True)
            .equals(ev_returns[["timestamp", "leg", "regime"]].reset_index(drop=True))):
        raise SystemExit("[STOP] disallineamento ordine tra ev_intensity e ev_returns.")
    merged = ev_intensity.copy()
    merged["r_e"] = ev_returns["r_e"].values
    merged["r_b"] = ev_returns["r_b"].values

    # 6. Dicotomizza intensity_raw sulla mediana within-sample (degli eventi
    # con intensità valida), poi calcola momenti di cella.
    print("[6/7] dichotomize + cell moments ...")
    valid_mask = merged["intensity_raw"].notna()
    valid = merged[valid_mask].copy()
    intensity_label = D.dichotomize(valid["intensity_raw"].to_numpy(), mode="median")
    valid["intensity_label"] = intensity_label
    # Re-iniettiamo la label sul merged completo per il run_gate (run_gate
    # filtra autonomamente sui NaN dell'intensità).
    merged["intensity_label"] = pd.Series(
        index=valid.index, data=intensity_label).reindex(merged.index)

    event_moments = compute_cell_moments(valid)
    print("  event_moments cells: ", {k: v["n"] for k, v in event_moments.items()})

    # 7. Esecuzione gate (le soglie sono i default congelati del config)
    print("[7/7] run_gate ...")
    out_gate = gate.run_gate(merged, event_moments=event_moments)

    verdicts = {
        **out_gate["verdicts"],
        "n_events_total": out_gate["n_events_total"],
        "n_events_with_intensity": out_gate["n_events_with_intensity"],
    }

    # --- File di output ----------------------------------------------------
    verdicts_path = OUT_DIR / "verdicts.json"
    verdicts_blob = json.dumps(verdicts, indent=2, sort_keys=True).encode("utf-8")
    verdicts_path.write_bytes(verdicts_blob)

    # numbers.json contiene TUTTO out_gate (incluso η², κ, conteggi, vettori).
    # Conversione delle chiavi tuple in stringhe "regime|intensity" per JSON.
    def jsonify(x):
        if isinstance(x, dict):
            return {(f"{k[0]}|{k[1]}" if isinstance(k, tuple) else str(k)): jsonify(v)
                    for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [jsonify(v) for v in x]
        if isinstance(x, (np.floating, np.integer)):
            return x.item()
        return x

    numbers = jsonify(out_gate)
    numbers["event_moments_raw"] = jsonify(event_moments)
    numbers_path = OUT_DIR / "numbers.json"
    numbers_blob = json.dumps(numbers, indent=2, sort_keys=True, default=str).encode("utf-8")
    numbers_path.write_bytes(numbers_blob)

    # Manifest via il kernel del cancello (manifest.build_gate_manifest)
    input_paths = [PICKLE_AUTH, RATE_CSV, ES_CSV, TY_CSV, STXE_CSV, FGBL_CSV]
    m = mf.build_gate_manifest(
        rate_contract=CONTRACT,
        window_half_min=config.HALF_MIN_WINDOW,
        partition_mode="median",
        min_cell=config.MIN_CELL_EVENTS,
        seed_name=SEED_NAME,
        timestamp=TASK_TIMESTAMP,
        input_paths=input_paths,
        thresholds=out_gate["thresholds_used"],
    )
    # Aggiunte di provenance esecutore (oltre allo standard build_gate_manifest)
    m["executor"] = {
        "script_path": str(Path(__file__).resolve()),
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "package_path": str(PKG),
        "package_module_sha256": {p.name: sha256_file(p) for p in sorted(PKG.glob("*.py"))},
        "namespace_output_dir": str(OUT_DIR),
    }
    m["n_events"] = {
        "total_in_events_df": int(len(events_df)),
        "with_intensity_valid": int(verdicts["n_events_with_intensity"]),
        "by_leg_regime": {f"{l}|{r}": int(c) for (l, r), c in
                          events_df.groupby(["leg", "regime"]).size().items()},
        "with_returns_valid": int(merged[["r_e", "r_b"]].notna().all(axis=1).sum()),
    }
    m["partition"] = {
        "mode": "median",
        "median_intensity": float(np.median(valid["intensity_raw"].to_numpy())),
    }
    m["dropped_events_disclosure"] = {
        "policy": "Nessun evento scartato dall'esecutore. Eventi con intensity_raw=NaN "
                  "sono filtrati dentro gate.run_gate (criteri a/b/c) e dentro "
                  "compute_cell_moments (criterio d) — disclosure conforme al contratto.",
        "events_with_intensity_nan": int(len(events_df) - verdicts["n_events_with_intensity"]),
        "events_with_returns_nan": int((~merged[["r_e", "r_b"]].notna().all(axis=1)).sum()),
    }
    mf.write_manifest(OUT_DIR / "manifest.json", m)

    # Report markdown (solo facts + verdetti per criterio; nessun giudizio
    # complessivo — vincolo dell'esecutore)
    report_path = OUT_DIR / "report.md"
    report_path.write_text(_render_report(out_gate, verdicts, m, event_moments),
                            encoding="utf-8")

    print(f"\nDONE → {OUT_DIR}")
    print(f"  verdicts.json  sha256={sha256_bytes(verdicts_blob)}")
    print(f"  numbers.json   sha256={sha256_bytes(numbers_blob)}")
    print(f"  manifest.json  written")
    print(f"  report.md      written")
    print(f"\nVerdetti: {out_gate['verdicts']}")
    return 0


def _render_report(out_gate: dict, verdicts: dict, manifest_d: dict,
                    event_moments: dict) -> str:
    th = out_gate["thresholds_used"]
    a = out_gate["criterion_a"]
    b = out_gate["criterion_b"]
    c = out_gate["criterion_c"]
    d = out_gate["criterion_d"]
    lines = [
        "# Cancello canale tassi — report esecutore",
        "",
        f"- timestamp (esterno): `{manifest_d['timestamp']}`",
        f"- contratto tassi: `{manifest_d['rate_contract']}`",
        f"- finestra: ±{manifest_d['window_half_min']} min (edge mediana 5 min)",
        f"- modalità partizione: `{manifest_d['partition_mode']}` (mediana = "
        f"{manifest_d['partition']['median_intensity']:.6g})",
        f"- seed dichiarato: `{manifest_d['seed']['name']}` (master "
        f"{config.MASTER_SEED}, schema in `config.make_rng`)",
        f"- soglie a priori: η² ≤ {th['eta2_low']} (a) — |κ_aligned| ≤ "
        f"{th['kappa_low']} (b) — min_cell = {th['min_cell']} (c) — |cos| < "
        f"{th['cosine_high']} (d). NON modificate ex-post.",
        f"- config_hash: `{manifest_d['config_hash']}`",
        f"- eventi totali (events_df): {verdicts['n_events_total']}",
        f"- eventi con intensità valida: {verdicts['n_events_with_intensity']}",
        "",
        "## Verdetti per criterio",
        "",
        f"- **(a) within-regime ampia** (η² ≤ {th['eta2_low']} overall E per ogni leg): "
        f"`{verdicts['a']}`",
        f"- **(b) dimensioni distinte** (|κ_aligned| ≤ {th['kappa_low']} overall): "
        f"`{verdicts['b']}`",
        f"- **(c) celle popolate** (n ≥ {th['min_cell']} per ogni cella regime×intensità): "
        f"`{verdicts['c']}`",
        f"- **(d) vettori di cambiamento non collineari** (|cos| < {th['cosine_high']} "
        f"in entrambe le fette): `{verdicts['d']}`",
        "",
        "## (a) Variance decomposition dell'intensità sul regime",
        "",
        f"- overall: η² = {a['overall']['eta_squared']:.6g}, n = {a['overall']['n']}",
    ]
    for leg, v in a["by_leg"].items():
        eta = v.get("eta_squared", float("nan"))
        lines.append(f"- by_leg {leg}: η² = {eta:.6g}, n = {v.get('n','-')}")
    lines += [
        "",
        "## (b) Allineamento partizioni (kappa con label-alignment)",
        "",
        f"- κ_aligned overall = {b['overall_kappa']:.6g}",
    ]
    for leg, k in b["by_leg_kappa"].items():
        lines.append(f"- κ_aligned by_leg {leg} = {k}")
    lines += [
        "",
        f"## (c) Popolamento celle regime × intensity (soglia {th['min_cell']})",
        "",
        "- counts overall (regime, intensità) → n:",
    ]
    for (r, i), n in sorted(c["counts_overall"].items()):
        lines.append(f"  - ({r}, {i}): {n}")
    if c["below_overall"]:
        lines.append(f"- **CELLE SOTTO SOGLIA (overall):** {c['below_overall']}")
    lines += [
        "",
        "## (d) Vettori di cambiamento dei momenti (var_e, var_b, cov_eb)",
        "",
    ]
    if isinstance(d, dict) and "status" in d and d["status"] == "missing_cells":
        lines.append(f"- status: `{d['status']}` (celle mancanti: {d['missing']})")
    else:
        lines += [
            f"- Δ_rate (positivo) = {d['delta_rate_pos']}",
            f"- Δ_rate (negativo) = {d['delta_rate_neg']}",
            f"- Δ_regime (high)   = {d['delta_regime_hi']}",
            f"- Δ_regime (low)    = {d['delta_regime_lo']}",
            f"- distinctness @ positivo: cos = {d['distinctness_at_regime_pos']['cosine']:.6g}, "
            f"angle = {d['distinctness_at_regime_pos']['angle_deg']:.3f}°, "
            f"rank = {d['distinctness_at_regime_pos']['rank_numerical']}",
            f"- distinctness @ negativo: cos = {d['distinctness_at_regime_neg']['cosine']:.6g}, "
            f"angle = {d['distinctness_at_regime_neg']['angle_deg']:.3f}°, "
            f"rank = {d['distinctness_at_regime_neg']['rank_numerical']}",
        ]
    lines += [
        "",
        "## Note dell'esecutore",
        "",
        "- events_df costruito dall'`accounting` del run autoritativo del protocollo v2 "
        "(`09_risultati/v2_signflip/result_authoritative.pkl`), input datato in sola lettura. "
        "Non è stato eseguito altro codice del repo all'interno di questo run.",
        "- Rendimenti r_e/r_b calcolati sulla stessa finestra ±15 min con edge mediana 5 min "
        "(`rate_shock.extract_event_window`), log-return = log(post/pre). NFP/CPI/FOMC su ES/TY, "
        "ECB su STXE/FGBL (stesso INSTRUMENT_MAP del protocollo v2).",
        "- Nessun evento scartato dall'esecutore: eventi senza intensità o senza rendimenti "
        "validi vengono filtrati nei criteri rispettivi (run_gate / compute_cell_moments). "
        "Conteggi nel manifest (`dropped_events_disclosure`).",
        "- L'identificabilità complessiva del canale tassi NON è oggetto di questo report "
        "(vincolo dell'esecutore). I verdetti a/b/c/d sopra sono i soli output deliberativi.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
