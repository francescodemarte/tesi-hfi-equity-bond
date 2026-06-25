"""extract_full_moments.py — Esecutore: deposita le matrici di covarianza 2×2
(bond, equity) per evento e controllo nelle 4 celle robuste.

Compito: completare beta_H_robust_cells_w15.json, che riporta solo var(b) e
cov(b,e), aggiungendo la varianza dell'equity per ciascun regime. La matrice
di covarianza 2×2 completa serve per:
  - disegnare le ellissi di covarianza al 95% (figura "identificazione" del
    capitolo Risultati);
  - verificare che le pendenze OLS evento/controllo siano coerenti con il
    file pre-esistente;
  - documentare la firma di Rigobon-Sack r_hat = var_b_e / var_b_c per
    ciascuna cella.

Vincoli (mandato esecutore):
- Sola lettura sul pickle autoritativo, sui CSV intraday, sul calendario
  contaminanti e sui file di codice congelati del pacchetto `protocol_v2`.
- Stesso seed dichiarato dal run autoritativo: `execute_v2_signflip_2026-06-22`
  (master 20260621). Non esegue bootstrap qui — i momenti deterministici non
  richiedono RNG, ma il seed e' registrato nel manifest per coerenza.
- Validazione: ogni campo gia' presente in beta_H_robust_cells_w15.json
  (b_OLS, var_e, var_c, cov_e, cov_c, r_hat) viene RICALCOLATO e CONFRONTATO
  con il file di riferimento entro tolleranza 1e-9. Se non combacia, lo
  script solleva e non scrive numeri.
- Output: nfp_neg_moments_2x2.json + all_robust_cells_moments_2x2.json +
  manifest.json. Niente interpretazione, solo numeri.

Riproducibilita': eseguendo questo script con i dati Refinitiv intraday
nella stessa locazione (data/intraday/) deve produrre output con sha256
identico a quello del manifest registrato.
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

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results" / "01_protocol_v2" / "full_moments_2x2"
OUT.mkdir(parents=True, exist_ok=True)

# Pacchetto protocol_v2 (riuso del codice congelato)
sys.path.insert(0, str(ROOT / "src/hfi/protocol_v2"))
import config as cfg07
import data as data07
import run as run07
import windows as win07

# Dati Refinitiv intraday (proprietary, fuori dalla repo pubblica)
INTRADAY = Path("/home/francesco/TESI/Dati/data_processed")
EVENTS_CSV = ROOT / "data/events/events_with_regime_classifier.csv"
CONT_CSV = Path("/home/francesco/TESI/Dati/calendari/contaminants_build_2026-06-22/"
                "contaminants_v2_2026-06-22.csv")
BETAH_FILE = ROOT / "results/01_protocol_v2/beta_H_robust_cells_w15.json"

ROBUST_CELLS = [("NFP", "neg"), ("CPI", "neg"), ("FOMC", "neg"), ("CPI", "pos")]
SEED_NAME = "execute_v2_signflip_2026-06-22"
TASK_TIMESTAMP = (
    datetime.now(timezone.utc).replace(microsecond=0)
        .isoformat().replace("+00:00", "Z")
)
TOL = 1e-9


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def cov2x2(b: np.ndarray, e: np.ndarray) -> dict:
    """Matrice 2x2 (b, e), eigendecomposizione, semi-assi al 95% (chi^2_2=5.991)."""
    mat = np.cov(np.vstack([b, e]), ddof=1)
    var_b = float(mat[0, 0]); var_e = float(mat[1, 1]); cov_be = float(mat[0, 1])
    w, v = np.linalg.eigh(mat)
    idx = w.argsort()[::-1]
    w, v = w[idx], v[:, idx]
    angle_deg = float(np.degrees(np.arctan2(v[1, 0], v[0, 0])))
    chi2_95 = 5.991  # chi2 quantile a 2 df, p=0.95
    semi_major = float(np.sqrt(chi2_95 * w[0]))
    semi_minor = float(np.sqrt(chi2_95 * w[1]))
    return {
        "var_b": var_b, "var_e": var_e, "cov_be": cov_be,
        "eigenvalues_desc": [float(w[0]), float(w[1])],
        "eigenvector_pc1": [float(v[0, 0]), float(v[1, 0])],
        "angle_deg_pc1": angle_deg,
        "ellipse_95": {
            "chi2_2_quantile": chi2_95,
            "semi_axis_major": semi_major,
            "semi_axis_minor": semi_minor,
            "angle_deg": angle_deg,
        },
        "ols_slope_equity_on_bond": cov_be / var_b if var_b > 0 else float("nan"),
    }


def main():
    print(f"=== extract_full_moments.py — {TASK_TIMESTAMP} ===")
    print(f"  Seed name: {SEED_NAME}")
    print(f"  Master seed: {cfg07.MASTER_SEED}")
    print(f"  Cells: {ROBUST_CELLS}")

    # 1. Carica reference per validazione
    print("\n  [1/4] Caricamento reference beta_H_robust_cells_w15.json ...")
    ref = json.loads(BETAH_FILE.read_text())
    ref_by_cell = {r["cell"]: r for r in ref["robust_cells"]}
    print(f"      reference: {list(ref_by_cell.keys())}")

    # 2. Riassembla cluster (stesso protocollo del pacchetto 07)
    print("\n  [2/4] Riassemblaggio cluster con pacchetto protocol_v2 ...")
    cfg07.INTRADAY_DIR = INTRADAY
    events = data07.load_events(EVENTS_CSV)
    prices = run07.load_prices()
    regs = run07.compute_regimes(prices)
    cont = set()
    with open(CONT_CSV) as f:
        for r in csv.DictReader(f):
            cont.add(pd.Timestamp(r["center_utc"]))
    ev_centers = set(pd.to_datetime(events["timestamp"], utc=True))
    reject = run07.build_calendar_reject(ev_centers, cont)
    per_type, _ = run07.assemble(events, prices, regs, reject)
    per_type, _ = win07.dedup_shared_controls(per_type)

    # 3. Calcola momenti per ciascuna cella + valida
    print("\n  [3/4] Calcolo matrici 2x2 + validazione vs reference ...")
    results = {}
    for leg, reg in ROBUST_CELLS:
        clusters = per_type[leg][reg]
        re_e, rb_e, re_c, rb_c = [], [], [], []
        for cl in clusters:
            ev = cl["event"]
            if ev.get("r_e") is None or ev.get("r_b") is None:
                continue
            re_e.append(float(ev["r_e"]))
            rb_e.append(float(ev["r_b"]))
            for ct in cl.get("controls", []):
                if ct.get("r_e") is not None and ct.get("r_b") is not None:
                    re_c.append(float(ct["r_e"]))
                    rb_c.append(float(ct["r_b"]))
        re_e = np.array(re_e); rb_e = np.array(rb_e)
        re_c = np.array(re_c); rb_c = np.array(rb_c)
        n_e, n_c = len(re_e), len(re_c)

        cell_label = f"{leg}/{reg}"
        ev_moments = cov2x2(rb_e, re_e)
        ct_moments = cov2x2(rb_c, re_c)

        # Validazione vs reference (b_OLS, var_e, var_c, cov_e, cov_c, r_hat)
        ref_cell = ref_by_cell[cell_label]
        checks = {
            "b_OLS": (ev_moments["ols_slope_equity_on_bond"], ref_cell["b_OLS"]),
            "var_b_event": (ev_moments["var_b"], ref_cell["var_e"]),
            "var_b_control": (ct_moments["var_b"], ref_cell["var_c"]),
            "cov_be_event": (ev_moments["cov_be"], ref_cell["cov_e"]),
            "cov_be_control": (ct_moments["cov_be"], ref_cell["cov_c"]),
            "r_hat": (ev_moments["var_b"] / ct_moments["var_b"], ref_cell["r_hat"]),
        }
        validations = {}
        for k, (computed, reference) in checks.items():
            diff = abs(computed - reference)
            ok = diff < TOL * max(1.0, abs(reference))
            validations[k] = {"computed": computed, "reference": reference,
                               "abs_diff": diff, "ok": ok}
            if not ok:
                raise SystemExit(
                    f"[STOP] Validazione fallita per {cell_label}.{k}:\n"
                    f"  computed = {computed:.10g}\n"
                    f"  reference = {reference:.10g}\n"
                    f"  abs_diff = {diff:.3e} > tol = {TOL}\n"
                    f"  Lo script non scrive numeri non riprodotti."
                )

        # Bootstrap: r_hat sui rendimenti grezzi (= var_e_bond/var_c_bond)
        # già calcolato in beta_H_robust_cells_w15.json — qui solo coerenza
        results[cell_label] = {
            "n_e": int(n_e), "n_c": int(n_c),
            "event_moments_raw_returns": ev_moments,
            "control_moments_raw_returns": ct_moments,
            "r_hat_signature": ev_moments["var_b"] / ct_moments["var_b"],
            "validation_vs_beta_H_file": validations,
        }
        print(f"      {cell_label:10s}  n_e={n_e:3d}  n_c={n_c:4d}  "
              f"var_b_e={ev_moments['var_b']:.4e}  var_b_c={ct_moments['var_b']:.4e}  "
              f"r_hat={ev_moments['var_b']/ct_moments['var_b']:.4f}  [valido]")

    # 4. Scrivi output
    print("\n  [4/4] Scrittura output ...")
    # nfp_neg dedicato (usato dalla Figura 3)
    nfp_only = {
        "cell": "NFP/neg",
        "n_e": results["NFP/neg"]["n_e"],
        "n_c": results["NFP/neg"]["n_c"],
        "event_moments_raw_returns": results["NFP/neg"]["event_moments_raw_returns"],
        "control_moments_raw_returns": results["NFP/neg"]["control_moments_raw_returns"],
        "r_hat_signature": results["NFP/neg"]["r_hat_signature"],
        "validation_vs_beta_H_file": results["NFP/neg"]["validation_vs_beta_H_file"],
        "_note": (
            "Matrice 2x2 (bond, equity) per la cella NFP/neg, fonte autoritativa "
            "delle ellissi di covarianza 95% disegnate nella Figura 3 del capitolo "
            "Risultati. Rendimenti in scala rendimento (log-return); per le bps "
            "moltiplicare per 1e4 prima delle ellissi (la pipeline figure lo fa)."
        ),
    }
    (OUT / "nfp_neg_moments_2x2.json").write_bytes(
        json.dumps(nfp_only, indent=2, sort_keys=True, default=str).encode("utf-8"))

    # Tutte e 4 le celle robuste
    all_cells = {
        "robust_cells": results,
        "format_note": (
            "Per ciascuna delle 4 celle robuste del run autoritativo del 12, "
            "matrice di covarianza 2x2 in base (bond=x, equity=y) per evento "
            "e controllo, in scala rendimento. Eigendecomposizione e semi-assi "
            "al 95% (chi^2_2(0.95)=5.991) inclusi. La validazione confronta "
            "var_b, cov_b_e e b_OLS coi valori gia' presenti in "
            "results/01_protocol_v2/beta_H_robust_cells_w15.json: l'esecutore "
            "ha sollevato se non combaciavano entro tol=1e-9."
        ),
    }
    (OUT / "all_robust_cells_moments_2x2.json").write_bytes(
        json.dumps(all_cells, indent=2, sort_keys=True, default=str).encode("utf-8"))

    # Manifest
    script_path = Path(__file__).resolve()
    manifest = {
        "task": "deposit_full_2x2_moments_for_robust_cells",
        "task_timestamp": TASK_TIMESTAMP,
        "seed_name": SEED_NAME,
        "master_seed": int(cfg07.MASTER_SEED),
        "seed_int_for_consistency": int(cfg07.seed_for(SEED_NAME)),
        "executor": {
            "script_path": str(script_path),
            "script_sha256": sha256_file(script_path),
        },
        "code_modules_used": {
            p.name: sha256_file(p) for p in
            (ROOT/"src/hfi/protocol_v2/config.py",
             ROOT/"src/hfi/protocol_v2/data.py",
             ROOT/"src/hfi/protocol_v2/run.py",
             ROOT/"src/hfi/protocol_v2/windows.py")
        },
        "inputs": {
            "events_csv": {"path": str(EVENTS_CSV), "sha256": sha256_file(EVENTS_CSV)},
            "contaminants_csv": {"path": str(CONT_CSV), "sha256": sha256_file(CONT_CSV)},
            "beta_H_reference": {"path": str(BETAH_FILE), "sha256": sha256_file(BETAH_FILE)},
            "intraday_dir": str(INTRADAY),
            "intraday_files_status": "PROPRIETARY (Refinitiv), not redistributed",
        },
        "outputs": {
            "nfp_neg_moments_2x2.json": {
                "path": str(OUT/"nfp_neg_moments_2x2.json"),
                "sha256": sha256_file(OUT/"nfp_neg_moments_2x2.json"),
            },
            "all_robust_cells_moments_2x2.json": {
                "path": str(OUT/"all_robust_cells_moments_2x2.json"),
                "sha256": sha256_file(OUT/"all_robust_cells_moments_2x2.json"),
            },
        },
        "validation": (
            "Ogni campo del file beta_H_robust_cells_w15.json (b_OLS, var_e, "
            "var_c, cov_e, cov_c, r_hat) e' stato ricalcolato dai cluster "
            "riassemblati e confrontato con il valore di riferimento entro "
            "tol=1e-9. Tutti i 24 confronti (4 celle x 6 campi) sono passati."
        ),
        "use_case": (
            "I dati di output sono la fonte autoritativa delle matrici di "
            "covarianza 2x2 per le ellissi disegnate nella Figura 3 del "
            "capitolo Risultati. Sostituiscono il calcolo on-the-fly fatto "
            "originalmente in sessione (figure/scripts/genera_fig_"
            "identificazione.py)."
        ),
    }
    (OUT / "manifest.json").write_bytes(
        json.dumps(manifest, indent=2, sort_keys=True, default=str).encode("utf-8"))

    print(f"\n  DONE → {OUT}")
    print(f"    nfp_neg_moments_2x2.json")
    print(f"    all_robust_cells_moments_2x2.json")
    print(f"    manifest.json")
    print(f"\n  Validazione: 4 celle x 6 campi = 24/24 confronti passati con tol={TOL}.")


if __name__ == "__main__":
    main()
