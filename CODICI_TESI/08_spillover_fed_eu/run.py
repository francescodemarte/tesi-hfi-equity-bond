"""run.py — Orchestratore della pipeline di spillover Fed→area euro.

⚠️ `main()` è BLOCCATO: l'esecuzione sui dati reali è dell'ESECUTORE (anello
successivo della catena). Questo modulo fornisce `run_protocol_full(...)` che
gira **solo su input passati dall'esterno** (DataFrames/array, MAI fetch).
"""
from __future__ import annotations

import numpy as np

import config
import regression as reg
import report
import surprises as su
import tests_h as th


def run_protocol_full(*, m, s, responses: dict, controls=None,
                      controls_names=(), manifest_path=None,
                      manifest_timestamp: str | None = None,
                      seed_name: str = "run",
                      basket_labels: tuple | None = None,
                      surprise_label: str | None = None,
                      require_all_assets: bool = True) -> dict:
    """Stadio 0 (separazione JK) + Stadio 1 (responses) + Stadio 2 (test).

    Args:
        m, s: array delle sorprese grezze (PC1 paniere tassi, log-return SP500).
        responses: dict {asset_label: array Δa_j}. Atteso "BUND_10Y" (H1
            primaria, obbligatorio). Se `require_all_assets=True` (default),
            anche "ESTOXX50" e "BTP_BUND_SPREAD" devono essere presenti — un
            placeholder p=1.0 in BY con m=3 fisso falsificherebbe la struttura
            del test (review #7).
        controls, controls_names: controlli minimali pre-dichiarati (opzionali).
        manifest_path / manifest_timestamp: scrittura manifest (timestamp esterno).
        seed_name: chiave del seed dichiarato nel manifest.
        basket_labels: etichette delle serie del paniere tassi US (review #4 wiring).
            Se passate, ognuna viene validata contro `FORBIDDEN_SOURCES`.
        surprise_label: etichetta della sorpresa `s` (es. "ES" per E-mini); validata.
    """
    # --- Validate source labels sul PERCORSO runtime (review #4) ----------
    if basket_labels is not None:
        for lbl in basket_labels:
            su.validate_source(lbl)
    if surprise_label is not None:
        su.validate_source(surprise_label)

    m = np.asarray(m, float); s = np.asarray(s, float)
    # `return_diagnostics=True`: la feasibility entra nel manifest (review #1/#8);
    # ma se NON identificabile la routine solleva comunque (no Z fabbricato).
    sep = su.separate_jk(m, s, return_diagnostics=True)
    if not sep.get("feasible", True):
        raise su.JKNotIdentifiedError(
            "Struttura JK non identificata sui dati forniti (0 ∈ CI95 di Cov(m,s)). "
            f"Diagnostica: {sep['feasibility']}"
        )
    Z_mp = sep["Z_mp"]; Z_cbi = sep["Z_cbi"]

    if controls is not None:
        X = np.column_stack([Z_mp, Z_cbi, np.asarray(controls, float)])
        names = ("Z_mp", "Z_cbi") + tuple(controls_names or
                                          tuple(f"x{i}" for i in range(np.asarray(controls).shape[1])))
    else:
        X = np.column_stack([Z_mp, Z_cbi])
        names = ("Z_mp", "Z_cbi")

    fits = {a: reg.ols_hc(y, X, names=names) for a, y in responses.items()}

    # Test per le 4 ipotesi (i nomi degli asset attesi seguono la spec)
    fit_bund = fits.get("BUND_10Y"); fit_estoxx = fits.get("ESTOXX50")
    fit_btpbund = fits.get("BTP_BUND_SPREAD")
    if fit_bund is None:
        raise KeyError("Manca 'BUND_10Y' nelle responses: H1 (primaria) richiesto.")
    if require_all_assets and (fit_estoxx is None or fit_btpbund is None):
        raise KeyError(
            "Mancano asset secondari ('ESTOXX50' e/o 'BTP_BUND_SPREAD'). "
            "BY con m=3 fisso assume i 3 test ESEGUITI (review #7); usare "
            "`require_all_assets=False` solo se documentato esplicitamente."
        )

    h1 = th.T_H1(fit_bund, coef="Z_mp")
    h2 = th.T_H2(fit_estoxx, coef="Z_mp") if fit_estoxx is not None else {"p_one_sided": 1.0}
    h3 = th.T_H3(fit_btpbund, coef="Z_mp") if fit_btpbund is not None else {"p_one_sided": 1.0}
    h4 = th.T_H4(fit_bund, coef_mp="Z_mp", coef_cbi="Z_cbi")
    hier = th.hierarchy(h1=h1, h2=h2, h3=h3, h4=h4)

    by = hier["secondary"]
    asset_rows = [
        report.build_asset_row("BUND_10Y", fit_bund, h1, by_decision=hier["h1_reject"]),
    ]
    if fit_estoxx is not None:
        asset_rows.append(report.build_asset_row("ESTOXX50", fit_estoxx, h2, by_decision=by["H2"]))
    if fit_btpbund is not None:
        asset_rows.append(report.build_asset_row("BTP_BUND_SPREAD", fit_btpbund, h3, by_decision=by["H3"]))

    concordance = su.sign_concordance(sep, su.poor_mans(m, s))
    manifest = None
    if manifest_path is not None:
        if manifest_timestamp is None:
            raise ValueError("manifest_timestamp obbligatorio se manifest_path è dato.")
        manifest = report.build_manifest(
            included_events=int(len(m)), excluded_events=0,
            seed_name=seed_name, timestamp=manifest_timestamp)
        # Review #8: concordance E3.1 NON è orfana — entra nel manifest scritto.
        manifest["concordance_poor_mans"] = concordance
        # Diagnostica feasibility JK (review #1) — anche questa nel manifest.
        manifest["jk_feasibility"] = sep.get("feasibility")
        report.write_report(manifest_path, asset_rows=asset_rows,
                            manifest=manifest, timestamp=manifest_timestamp)

    return {"h1": h1, "h2": h2, "h3": h3, "h4": h4, "hierarchy": hier,
            "asset_rows": asset_rows, "manifest": manifest,
            "concordance": concordance,
            "jk_feasibility": sep.get("feasibility")}


def main():  # pragma: no cover
    raise SystemExit(
        "run.py: l'esecuzione sui dati reali è dell'ESECUTORE (anello successivo). "
        "Vedi run_protocol_full(...) per il contratto, e tests/test_report.py per "
        "lo smoke su input sintetici."
    )


if __name__ == "__main__":
    main()
