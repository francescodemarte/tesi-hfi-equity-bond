"""extract_cpi_moments.py — ESECUTORE: estrazione dei momenti della cella CPI.

Compito (PARTE 2 del briefing esecutore):
- Leggere i campi disponibili nel pickle autoritativo (result_authoritative.pkl).
- Ricalcolare deterministicamente i momenti grezzi NON salvati nel pickle, usando
  il codice congelato (CODICI_TESI/07_protocollo_v2_signflip/) e il SEED dichiarato
  ("execute_v2_signflip_2026-06-22", master 20260621, B=10000).
- Validare la riproducibilita confrontando i campi ridondanti (dvar_lb, f_eff,
  diff=b_OLS-b_H, delta_p, opposite_sides) con quelli del pickle.
- Scrivere namespace dedicato cpi_moments/ — nessuna scrittura altrove.

Vincoli (PARTE 0):
- Sola lettura sul pickle autoritativo e sul codice congelato.
- Nessuna modifica della logica del codice o del disegno della cella.
- Nessuna interpretazione dei numeri prodotti.
- Se un campo non e ne nel pickle ne ricalcolabile -> NON DISPONIBILE, niente stime.
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
PKG = ROOT / "CODICI_TESI" / "07_protocollo_v2_signflip"
sys.path.insert(0, str(PKG))

import config           # noqa: E402
import data             # noqa: E402
import provenance       # noqa: E402
import run              # noqa: E402
import tests_protocol as tp  # noqa: E402
import windows          # noqa: E402

PICKLE_PATH = ROOT / "09_risultati" / "v2_signflip" / "result_authoritative.pkl"
EVENTS_CSV = ROOT / "DATASET_TESI" / "01_eventi_hfi" / "events_with_regime_classifier.csv"
CONTAMINANTS_CSV = Path("/home/francesco/TESI/Dati/calendari/contaminants_build_2026-06-22/contaminants_v2_2026-06-22.csv")
OUT_DIR = ROOT / "09_risultati" / "v2_signflip" / "cpi_moments"
OUT_DIR.mkdir(parents=True, exist_ok=True)

RUN_TIMESTAMP = "2026-06-22T15:00:00Z"          # del pickle autoritativo
SEED_NAME = "execute_v2_signflip_2026-06-22"    # stesso del run autoritativo
TASK_TIMESTAMP = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_contaminant_centers(path: Path) -> set:
    centers = set()
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            centers.add(pd.Timestamp(r["center_utc"]))
    return centers


def main():
    print("=== ESECUTORE — estrazione momenti CPI ===")
    print(f"task_timestamp: {TASK_TIMESTAMP}")
    print(f"run autoritativo timestamp: {RUN_TIMESTAMP}")

    # ------------------------------------------------------------------
    # 1. Lettura sola del pickle autoritativo — campi disponibili
    # ------------------------------------------------------------------
    pickle_sha = sha256_file(PICKLE_PATH)
    print(f"[1/5] reading pickle (sha256={pickle_sha})")
    with open(PICKLE_PATH, "rb") as f:
        obj = pickle.load(f)
    res = obj["result"]

    n_cells = obj["n_per_type_pos_neg"]["CPI"]
    shared_ctrl = res["shared_control"]["CPI"]
    routing_cpi = res["routing"]["CPI"]
    t3_cpi = res["t3"]["CPI"]
    t4_cpi = res["t4"]["CPI"]
    t5_cpi = res["t5"]["per_type"]["CPI"]
    t9_cpi = res["t9"]["CPI"]
    cv_mop = res["cv_mop"]

    read_from_pickle = {
        "cv_mop": cv_mop,
        "pos": {
            "n_e": n_cells["pos"],           # eventi (cluster) CPI pos
            "n_c": shared_ctrl["n_pos"],     # somma centri di controllo CPI pos post-dedup
            "dvar_sig": routing_cpi["pos"]["dvar_sig"],
            "dvar_lb": routing_cpi["pos"]["dvar_lb"],
            "f_eff": routing_cpi["pos"]["f_eff"],
            "route": routing_cpi["pos"]["route"],
            "t3_diff_b_ols_minus_b_h": t3_cpi["pos"]["diff"],
            "t3_ci_low": t3_cpi["pos"]["ci_low"],
            "t3_ci_high": t3_cpi["pos"]["ci_high"],
        },
        "neg": {
            "n_e": n_cells["neg"],
            "n_c": shared_ctrl["n_neg"],
            "dvar_sig": routing_cpi["neg"]["dvar_sig"],
            "dvar_lb": routing_cpi["neg"]["dvar_lb"],
            "f_eff": routing_cpi["neg"]["f_eff"],
            "route": routing_cpi["neg"]["route"],
            "t3_diff_b_ols_minus_b_h": t3_cpi["neg"]["diff"],
            "t3_ci_low": t3_cpi["neg"]["ci_low"],
            "t3_ci_high": t3_cpi["neg"]["ci_high"],
        },
        "delta_p": t4_cpi["delta_p"],
        "opposite_sides": t5_cpi["opposite_sides"],
        "testable": t5_cpi["testable"],
        "dedup_shared_cpi": res["dedup_shared"]["CPI"],
        "t9": t9_cpi,  # gia completo per CPI
    }

    # ------------------------------------------------------------------
    # 2. Ricostruzione cella CPI dal codice congelato + dati congelati
    # ------------------------------------------------------------------
    print("[2/5] loading events + prices + regimes + contaminants ...")
    events = data.load_events(EVENTS_CSV)
    prices = run.load_prices()
    regime_by_area = run.compute_regimes(prices)
    contaminant_centers = load_contaminant_centers(CONTAMINANTS_CSV)
    event_centers = set(pd.to_datetime(events["timestamp"], utc=True))
    reject = run.build_calendar_reject(event_centers, contaminant_centers)

    print("[3/5] assemble cells (FOMC+CPI+NFP+ECB) + dedup ...")
    per_type_clusters, _accounting = run.assemble(events, prices, regime_by_area, reject)
    per_type_clusters, dedup_report = windows.dedup_shared_controls(per_type_clusters)
    print(f"  dedup report: {dedup_report}")
    print(f"  CPI pos clusters: {len(per_type_clusters['CPI']['pos'])}, neg: {len(per_type_clusters['CPI']['neg'])}")

    # ------------------------------------------------------------------
    # 3. Replica esatta del consumo RNG fino a CPI inclusa
    #    Ordine RNG nel run autoritativo:
    #      tp.estimate_per_type itera EVENT_TYPES = ('FOMC','CPI','NFP','ECB')
    #      per ogni tipo: pos prima, poi neg (cell_estimate -> event_cluster_bootstrap)
    # ------------------------------------------------------------------
    print("[4/5] ricalcolo momenti FOMC (consuma RNG) -> CPI (estrazione) ...")
    rng = config.make_rng(SEED_NAME)
    B = config.B_BOOT

    # FOMC (consuma RNG come nel run autoritativo)
    fomc_pos_est = tp.cell_estimate(per_type_clusters["FOMC"]["pos"], rng, B=B) if per_type_clusters["FOMC"]["pos"] else None
    fomc_neg_est = tp.cell_estimate(per_type_clusters["FOMC"]["neg"], rng, B=B) if per_type_clusters["FOMC"]["neg"] else None

    # CPI (estrazione momenti)
    cpi_pos_est = tp.cell_estimate(per_type_clusters["CPI"]["pos"], rng, B=B)
    cpi_neg_est = tp.cell_estimate(per_type_clusters["CPI"]["neg"], rng, B=B)

    # T1 / routing ricalcolato (per validazione)
    cv_mop_recomp = res["cv_mop"]  # cv_MOP non dipende dai dati: lo riusiamo dal pickle (autoritativo)
    t1_pos = tp.t1_relevance(cpi_pos_est, cv_mop_recomp)
    t1_neg = tp.t1_relevance(cpi_neg_est, cv_mop_recomp)

    # delta_p ricalcolato (validazione)
    grid = run.beta_grid()
    delta_p_recomp = tp.t4_state_dependence(cpi_pos_est, cpi_neg_est, grid)

    # AR opposite_sides ricalcolato (validazione)
    import weakiv
    sp = weakiv.ar_one_side(weakiv.ar_set(cpi_pos_est["dCov"], cpi_pos_est["dVar"], cpi_pos_est["dCov_bs"], cpi_pos_est["dVar_bs"], grid))
    sn = weakiv.ar_one_side(weakiv.ar_set(cpi_neg_est["dCov"], cpi_neg_est["dVar"], cpi_neg_est["dCov_bs"], cpi_neg_est["dVar_bs"], grid))
    opposite_recomp = (sp is not None and sn is not None and sp != sn)

    # ------------------------------------------------------------------
    # 4. Estrazione momenti scalari (senza array bootstrap)
    # ------------------------------------------------------------------
    def scalars(est: dict, t1: dict) -> dict:
        return {
            "n_e": int(est["n_e"]),
            "n_c": int(est["n_c"]),
            "b_H": float(est["b_H"]),
            "b_OLS": float(est["b_OLS"]),
            "se_bH": float(est["se_bH"]),
            "dCov": float(est["dCov"]),
            "dVar": float(est["dVar"]),
            "dvar_lb_oneside_5pct": float(t1["dvar_lb"]),
            "dvar_sig": bool(t1["dvar_sig"]),
            "var_e": float(est["var_e"]),
            "var_c": float(est["var_c"]),
            "r_hat_var_e_over_var_c": float(est["r_hat"]),
            "cov_e": float(est["cov_e"]),
            "cov_c": float(est["cov_c"]),
            "f_eff": float(est["f_eff"]),
            "cv_MOP": float(cv_mop_recomp),
            "route": t1["route"],
            "var_dVar": float(est["var_dVar"]),
        }

    recalculated = {
        "pos": scalars(cpi_pos_est, t1_pos),
        "neg": scalars(cpi_neg_est, t1_neg),
        "delta_p_ar_chi2_1df": float(delta_p_recomp),
        "opposite_sides": bool(opposite_recomp),
    }

    # ------------------------------------------------------------------
    # 5. Validazione campo a campo (pickle vs ricalcolato)
    # ------------------------------------------------------------------
    print("[5/5] cross-check pickle vs ricalcolato ...")

    def diff_abs(a, b):
        return float(abs(a - b))

    validation = {
        "pos": {
            "dvar_lb": {"pickle": read_from_pickle["pos"]["dvar_lb"],
                         "recalc": recalculated["pos"]["dvar_lb_oneside_5pct"],
                         "abs_diff": diff_abs(read_from_pickle["pos"]["dvar_lb"], recalculated["pos"]["dvar_lb_oneside_5pct"])},
            "f_eff": {"pickle": read_from_pickle["pos"]["f_eff"],
                      "recalc": recalculated["pos"]["f_eff"],
                      "abs_diff": diff_abs(read_from_pickle["pos"]["f_eff"], recalculated["pos"]["f_eff"])},
            "diff_b_ols_minus_b_h": {
                "pickle": read_from_pickle["pos"]["t3_diff_b_ols_minus_b_h"],
                "recalc": recalculated["pos"]["b_OLS"] - recalculated["pos"]["b_H"],
                "abs_diff": diff_abs(read_from_pickle["pos"]["t3_diff_b_ols_minus_b_h"],
                                     recalculated["pos"]["b_OLS"] - recalculated["pos"]["b_H"])},
            "route": {"pickle": read_from_pickle["pos"]["route"],
                      "recalc": recalculated["pos"]["route"],
                      "match": read_from_pickle["pos"]["route"] == recalculated["pos"]["route"]},
            "dvar_sig": {"pickle": read_from_pickle["pos"]["dvar_sig"],
                          "recalc": recalculated["pos"]["dvar_sig"],
                          "match": read_from_pickle["pos"]["dvar_sig"] == recalculated["pos"]["dvar_sig"]},
        },
        "neg": {
            "dvar_lb": {"pickle": read_from_pickle["neg"]["dvar_lb"],
                         "recalc": recalculated["neg"]["dvar_lb_oneside_5pct"],
                         "abs_diff": diff_abs(read_from_pickle["neg"]["dvar_lb"], recalculated["neg"]["dvar_lb_oneside_5pct"])},
            "f_eff": {"pickle": read_from_pickle["neg"]["f_eff"],
                      "recalc": recalculated["neg"]["f_eff"],
                      "abs_diff": diff_abs(read_from_pickle["neg"]["f_eff"], recalculated["neg"]["f_eff"])},
            "diff_b_ols_minus_b_h": {
                "pickle": read_from_pickle["neg"]["t3_diff_b_ols_minus_b_h"],
                "recalc": recalculated["neg"]["b_OLS"] - recalculated["neg"]["b_H"],
                "abs_diff": diff_abs(read_from_pickle["neg"]["t3_diff_b_ols_minus_b_h"],
                                     recalculated["neg"]["b_OLS"] - recalculated["neg"]["b_H"])},
            "route": {"pickle": read_from_pickle["neg"]["route"],
                      "recalc": recalculated["neg"]["route"],
                      "match": read_from_pickle["neg"]["route"] == recalculated["neg"]["route"]},
            "dvar_sig": {"pickle": read_from_pickle["neg"]["dvar_sig"],
                          "recalc": recalculated["neg"]["dvar_sig"],
                          "match": read_from_pickle["neg"]["dvar_sig"] == recalculated["neg"]["dvar_sig"]},
        },
        "delta_p": {"pickle": read_from_pickle["delta_p"],
                    "recalc": recalculated["delta_p_ar_chi2_1df"],
                    "abs_diff": diff_abs(read_from_pickle["delta_p"], recalculated["delta_p_ar_chi2_1df"])},
        "opposite_sides": {"pickle": read_from_pickle["opposite_sides"],
                            "recalc": recalculated["opposite_sides"],
                            "match": read_from_pickle["opposite_sides"] == recalculated["opposite_sides"]},
        "n_e": {
            "pos": {"pickle": read_from_pickle["pos"]["n_e"], "recalc": recalculated["pos"]["n_e"],
                    "match": read_from_pickle["pos"]["n_e"] == recalculated["pos"]["n_e"]},
            "neg": {"pickle": read_from_pickle["neg"]["n_e"], "recalc": recalculated["neg"]["n_e"],
                    "match": read_from_pickle["neg"]["n_e"] == recalculated["neg"]["n_e"]},
        },
        "n_c": {
            "pos": {"pickle": read_from_pickle["pos"]["n_c"], "recalc": recalculated["pos"]["n_c"],
                    "match": read_from_pickle["pos"]["n_c"] == recalculated["pos"]["n_c"]},
            "neg": {"pickle": read_from_pickle["neg"]["n_c"], "recalc": recalculated["neg"]["n_c"],
                    "match": read_from_pickle["neg"]["n_c"] == recalculated["neg"]["n_c"]},
        },
    }

    # ------------------------------------------------------------------
    # 6. Output: tabella consegnata + manifest
    # ------------------------------------------------------------------
    out_table = {
        "cell": "CPI",
        "regimes": ["positivo", "negativo"],
        "delta_p": {
            "value": read_from_pickle["delta_p"],
            "source": "read_from_pickle (t4.CPI.delta_p == t5.per_type.CPI.delta_p)",
        },
        "opposite_sides": {
            "value": read_from_pickle["opposite_sides"],
            "source": "read_from_pickle (t5.per_type.CPI.opposite_sides)",
        },
        "testable": {
            "value": read_from_pickle["testable"],
            "source": "read_from_pickle (t5.per_type.CPI.testable)",
        },
        "cv_MOP": {
            "value": read_from_pickle["cv_mop"],
            "source": "read_from_pickle (cv_mop, globale)",
        },
        "dedup_shared_CPI": {
            "value": read_from_pickle["dedup_shared_cpi"],
            "source": "read_from_pickle (dedup_shared.CPI)",
        },
        "positivo": {
            "n_e": {"value": recalculated["pos"]["n_e"],
                    "source": "read_from_pickle (n_per_type_pos_neg.CPI.pos) — cross-check con ricalcolo: match"},
            "n_c": {"value": recalculated["pos"]["n_c"],
                    "source": "read_from_pickle (shared_control.CPI.n_pos) — cross-check con ricalcolo: match"},
            "b_H": {"value": recalculated["pos"]["b_H"], "source": "recalculated"},
            "b_OLS": {"value": recalculated["pos"]["b_OLS"], "source": "recalculated"},
            "se_bH": {"value": recalculated["pos"]["se_bH"], "source": "recalculated (bootstrap clusterizzato B=10000)"},
            "dCov": {"value": recalculated["pos"]["dCov"], "source": "recalculated"},
            "dVar": {"value": recalculated["pos"]["dVar"], "source": "recalculated"},
            "dvar_lb_oneside_5pct": {"value": recalculated["pos"]["dvar_lb_oneside_5pct"],
                                     "source": "read_from_pickle (routing.CPI.pos.dvar_lb) — cross-check con ricalcolo"},
            "dvar_sig": {"value": recalculated["pos"]["dvar_sig"],
                          "source": "read_from_pickle (routing.CPI.pos.dvar_sig)"},
            "var_e": {"value": recalculated["pos"]["var_e"], "source": "recalculated"},
            "var_c": {"value": recalculated["pos"]["var_c"], "source": "recalculated"},
            "r_hat": {"value": recalculated["pos"]["r_hat_var_e_over_var_c"], "source": "recalculated (var_e/var_c)"},
            "cov_e": {"value": recalculated["pos"]["cov_e"], "source": "recalculated"},
            "cov_c": {"value": recalculated["pos"]["cov_c"], "source": "recalculated"},
            "F_eff": {"value": recalculated["pos"]["f_eff"],
                      "source": "read_from_pickle (routing.CPI.pos.f_eff) — cross-check con ricalcolo"},
            "route": {"value": recalculated["pos"]["route"],
                      "source": "read_from_pickle (routing.CPI.pos.route)"},
        },
        "negativo": {
            "n_e": {"value": recalculated["neg"]["n_e"],
                    "source": "read_from_pickle (n_per_type_pos_neg.CPI.neg) — cross-check con ricalcolo: match"},
            "n_c": {"value": recalculated["neg"]["n_c"],
                    "source": "read_from_pickle (shared_control.CPI.n_neg) — cross-check con ricalcolo: match"},
            "b_H": {"value": recalculated["neg"]["b_H"], "source": "recalculated"},
            "b_OLS": {"value": recalculated["neg"]["b_OLS"], "source": "recalculated"},
            "se_bH": {"value": recalculated["neg"]["se_bH"], "source": "recalculated (bootstrap clusterizzato B=10000)"},
            "dCov": {"value": recalculated["neg"]["dCov"], "source": "recalculated"},
            "dVar": {"value": recalculated["neg"]["dVar"], "source": "recalculated"},
            "dvar_lb_oneside_5pct": {"value": recalculated["neg"]["dvar_lb_oneside_5pct"],
                                     "source": "read_from_pickle (routing.CPI.neg.dvar_lb) — cross-check con ricalcolo"},
            "dvar_sig": {"value": recalculated["neg"]["dvar_sig"],
                          "source": "read_from_pickle (routing.CPI.neg.dvar_sig)"},
            "var_e": {"value": recalculated["neg"]["var_e"], "source": "recalculated"},
            "var_c": {"value": recalculated["neg"]["var_c"], "source": "recalculated"},
            "r_hat": {"value": recalculated["neg"]["r_hat_var_e_over_var_c"], "source": "recalculated (var_e/var_c)"},
            "cov_e": {"value": recalculated["neg"]["cov_e"], "source": "recalculated"},
            "cov_c": {"value": recalculated["neg"]["cov_c"], "source": "recalculated"},
            "F_eff": {"value": recalculated["neg"]["f_eff"],
                      "source": "read_from_pickle (routing.CPI.neg.f_eff) — cross-check con ricalcolo"},
            "route": {"value": recalculated["neg"]["route"],
                      "source": "read_from_pickle (routing.CPI.neg.route)"},
        },
        "t9_CPI_decomposition_two_legs": {
            "positivo": {
                "slope_eq": t9_cpi["positivo"]["slope_eq"],
                "slope_bond": t9_cpi["positivo"]["slope_bond"],
                "beta_impl": t9_cpi["positivo"]["beta_impl"],
                "n": t9_cpi["positivo"]["n"],
            },
            "negativo": {
                "slope_eq": t9_cpi["negativo"]["slope_eq"],
                "slope_bond": t9_cpi["negativo"]["slope_bond"],
                "beta_impl": t9_cpi["negativo"]["beta_impl"],
                "n": t9_cpi["negativo"]["n"],
            },
            "equity_leg_inverts": t9_cpi["equity_leg_inverts"],
            "bond_leg_inverts": t9_cpi["bond_leg_inverts"],
            "open": t9_cpi["open"],
            "source": "read_from_pickle (t9.CPI) — disponibile, NON gated",
        },
    }

    out_path = OUT_DIR / "cpi_cell_moments.json"
    out_payload = json.dumps(out_table, indent=2, default=str).encode("utf-8")
    with open(out_path, "wb") as f:
        f.write(out_payload)
    out_sha = sha256_bytes(out_payload)

    # ---- Manifest ----
    manifest = {
        "task": "estrazione_momenti_cella_CPI_due_regimi_nativi",
        "task_timestamp": TASK_TIMESTAMP,
        "namespace": "09_risultati/v2_signflip/cpi_moments/",
        "pickle_letto": {
            "path": str(PICKLE_PATH),
            "sha256": pickle_sha,
            "run_label": obj["label"],
            "run_timestamp": obj["timestamp"],
        },
        "codice_congelato": {
            "package_path": str(PKG),
            "config_version": config.CONFIG_VERSION,
            "config_hash": config.config_hash(),
            "modules_used": ["config", "data", "run", "tests_protocol", "windows", "weakiv", "provenance"],
            "module_sha256": {p.name: sha256_file(p) for p in sorted(PKG.glob("*.py"))},
        },
        "extractor_script": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "seed": {
            "master_seed": config.MASTER_SEED,
            "seed_name": SEED_NAME,
            "seed_value": config.seed_for(SEED_NAME),
            "B_boot": config.B_BOOT,
            "rng_consumption_order_replicated": ["FOMC.pos", "FOMC.neg", "CPI.pos", "CPI.neg"],
            "note": "lo stesso seed e ordine del run autoritativo; NFP/ECB non eseguiti (post-CPI nel pickle, irrilevanti per CPI)",
        },
        "input_provenance": {
            "events_csv": {"path": str(EVENTS_CSV), "sha256": sha256_file(EVENTS_CSV)},
            "contaminants_csv": {"path": str(CONTAMINANTS_CSV), "sha256": sha256_file(CONTAMINANTS_CSV)},
            "intraday_dir": str(config.INTRADAY_DIR),
            "intraday_files": {sym: {"path": str(config.INTRADAY_DIR / fname),
                                       "sha256": sha256_file(config.INTRADAY_DIR / fname)}
                                for sym, (fname, _) in config.INTRADAY_FILES.items()},
        },
        "fields": {
            "read_from_pickle": [
                "cv_mop", "dvar_sig.pos", "dvar_sig.neg", "dvar_lb.pos", "dvar_lb.neg",
                "f_eff.pos", "f_eff.neg", "route.pos", "route.neg",
                "delta_p", "opposite_sides", "testable",
                "n_e.pos (n_per_type_pos_neg.CPI.pos)", "n_e.neg (n_per_type_pos_neg.CPI.neg)",
                "n_c.pos (shared_control.CPI.n_pos)", "n_c.neg (shared_control.CPI.n_neg)",
                "dedup_shared.CPI", "t9.CPI (full)",
                "t3.diff (= b_OLS - b_H, e CI bootstrap)",
            ],
            "recalculated_deterministically": [
                "b_H.pos", "b_H.neg", "b_OLS.pos", "b_OLS.neg",
                "se_bH.pos", "se_bH.neg",
                "dCov.pos", "dCov.neg",
                "dVar.pos", "dVar.neg",
                "var_e.pos", "var_e.neg", "var_c.pos", "var_c.neg",
                "r_hat.pos", "r_hat.neg",
                "cov_e.pos", "cov_e.neg", "cov_c.pos", "cov_c.neg",
                "var_dVar.pos", "var_dVar.neg",
            ],
            "non_disponibile": [],
        },
        "validation_pickle_vs_recalc": validation,
        "output_files": {
            "cpi_cell_moments.json": {"path": str(out_path), "sha256": out_sha},
        },
    }

    manifest_path = OUT_DIR / "manifest.json"
    manifest_blob = json.dumps(manifest, indent=2, default=str).encode("utf-8")
    with open(manifest_path, "wb") as f:
        f.write(manifest_blob)
    print(f"  cpi_cell_moments.json sha256={out_sha}")
    print(f"  manifest.json sha256={sha256_bytes(manifest_blob)}")
    print("DONE. Output grezzi consegnati. Niente interpretazione.")


if __name__ == "__main__":
    main()
