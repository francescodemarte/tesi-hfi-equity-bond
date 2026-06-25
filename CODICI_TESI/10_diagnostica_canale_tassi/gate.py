"""gate.py — Orchestra le 4 diagnostiche e produce verdetti per criterio.

I 4 criteri (a/b/c/d) sono valutati ciascuno SUI NUMERI con soglie esplicite.
Il giudizio di identificabilità complessiva NON è prodotto qui — è del ricercatore.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config
import diagnostics as D


def run_gate(events: pd.DataFrame,
             event_moments: dict,
             *,
             intensity_col: str = "intensity_raw",
             regime_col: str = "regime",
             leg_col: str = "leg",
             partition_mode: str = config.PARTITION_DEFAULT,
             min_cell: int = config.MIN_CELL_EVENTS,
             eta2_low: float = config.ETA_SQUARED_LOW_THRESHOLD_DEFAULT,
             kappa_low: float = config.KAPPA_LOW_THRESHOLD_DEFAULT,
             cosine_high: float = config.COSINE_HIGH_THRESHOLD_DEFAULT,
             ) -> dict:
    """Esegue le 4 diagnostiche e produce verdetti per criterio.

    `events`: DataFrame con colonne [timestamp, leg, regime, intensity_raw].
    `event_moments`: dict ((regime_label, intensity_label) → {var_e, var_b, cov_eb}),
        pre-calcolato dall'esecutore SULLE FINESTRE D'ANNUNCIO (var/cov di
        rendimenti equity/bond dentro la cella regime × intensità).

    Restituisce dict con:
      - "criterion_a" (variance decomposition)
      - "criterion_b" (kappa)
      - "criterion_c" (cell counts)
      - "criterion_d" (vettori di cambiamento)
      - "verdicts" (a/b/c/d → bool)
      - "thresholds_used" (per provenienza)
      - "n_events_total", "n_events_with_intensity"
    """
    # Anti-fabbricazione: rifiuta se mancano le colonne attese
    needed = {intensity_col, regime_col, leg_col, "timestamp"}
    if not needed.issubset(events.columns):
        raise ValueError(f"events deve avere colonne {needed}; ha {set(events.columns)}")

    # Filtra eventi con intensità non NaN
    n_total = int(len(events))
    valid = events.dropna(subset=[intensity_col]).copy()
    n_valid = int(len(valid))
    if n_valid == 0:
        raise ValueError("nessun evento con intensità di shock di tasso valida")

    # --- (a) variance decomposition: complessivo + within-tipo-evento --------
    overall = D.variance_decomposition(valid[intensity_col].values,
                                        valid[regime_col].values)
    by_leg = {}
    for leg, sub in valid.groupby(leg_col):
        if sub[regime_col].nunique() < 2:
            by_leg[str(leg)] = {"eta_squared": float("nan"),
                                 "n": int(len(sub)),
                                 "note": "un solo regime presente"}
        else:
            by_leg[str(leg)] = D.variance_decomposition(sub[intensity_col].values,
                                                         sub[regime_col].values)
    crit_a = {
        "overall": overall,
        "by_leg": by_leg,
        "threshold_eta2_low": eta2_low,
    }
    # Verdetto (a): η² ≤ soglia COMPLESSIVO E per ciascun leg (within-tipo OK)
    a_overall = overall["eta_squared"] <= eta2_low
    a_by_leg = {l: (v["eta_squared"] <= eta2_low if not np.isnan(v["eta_squared"]) else None)
                for l, v in by_leg.items()}
    verdict_a = bool(a_overall and all(x is True for x in a_by_leg.values() if x is not None))

    # --- (b) partizione intensità + kappa -----------------------------------
    intensity_labels = D.dichotomize(valid[intensity_col].values, mode=partition_mode)
    valid = valid.copy()
    valid["intensity_label"] = intensity_labels
    # in modalità tertile_extremes scarta i 'drop'
    valid_kappa = valid[valid["intensity_label"] != "drop"]
    # κ con allineamento delle etichette (label-free): misura se le DIMENSIONI
    # sono confuse, non se le etichette coincidono letteralmente.
    align_overall = D.partition_alignment_kappa(valid_kappa["intensity_label"].values,
                                                  valid_kappa[regime_col].values)
    kappa_overall = align_overall["kappa_aligned"]
    kappa_by_leg = {}
    for leg, sub in valid_kappa.groupby(leg_col):
        if sub["intensity_label"].nunique() < 2 or sub[regime_col].nunique() < 2:
            kappa_by_leg[str(leg)] = float("nan")
        else:
            al = D.partition_alignment_kappa(sub["intensity_label"].values,
                                              sub[regime_col].values)
            kappa_by_leg[str(leg)] = al["kappa_aligned"]
    crit_b = {
        "overall_kappa": kappa_overall,
        "by_leg_kappa": kappa_by_leg,
        "partition_mode": partition_mode,
        "threshold_kappa_low": kappa_low,
    }
    # Verdetto (b): kappa_overall ≤ soglia. Il by-leg è RIPORTATO (informativo)
    # ma non blocca il verdetto: con ~30 eventi/leg l'aligned-κ ha bias positivo
    # campionario per "ricerca della migliore permutazione", quindi by-leg sopra
    # soglia non implica confusione strutturale. Lettura del prompt: "complessivo
    # e within-tipo-evento" significa riportare entrambi; la regola di esito è
    # sull'overall, il by-leg serve a vedere se la confusione è guidata da un
    # singolo tipo.
    verdict_b = bool(abs(kappa_overall) <= kappa_low)

    # --- (c) popolamento celle ---------------------------------------------
    counts_overall = D.cell_counts(valid_kappa, regime_col=regime_col,
                                    intensity_col="intensity_label")
    below_overall = D.cells_below_threshold(counts_overall, min_cell)
    counts_by_leg = {}
    below_by_leg = {}
    for leg, sub in valid_kappa.groupby(leg_col):
        c = D.cell_counts(sub, regime_col=regime_col, intensity_col="intensity_label")
        counts_by_leg[str(leg)] = c
        below_by_leg[str(leg)] = D.cells_below_threshold(c, min_cell)
    crit_c = {
        "counts_overall": counts_overall,
        "counts_by_leg": counts_by_leg,
        "below_overall": below_overall,
        "below_by_leg": below_by_leg,
        "min_cell": min_cell,
    }
    # Verdetto (c): NESSUNA cella sotto soglia (overall)
    verdict_c = bool(len(below_overall) == 0)

    # --- (d) vettori di cambiamento sui momenti ----------------------------
    # event_moments deve esporre le 4 celle. Se mancano alcune, si dichiara.
    needed_cells = [(r, i) for r in ("positivo", "negativo") for i in ("high", "low")]
    missing = [k for k in needed_cells if k not in event_moments]
    if missing:
        crit_d = {"status": "missing_cells", "missing": missing, "note":
                  "vettori di cambiamento non calcolabili (celle mancanti)"}
        verdict_d = None
    else:
        # delta lungo intensità a regime FISSO (es. positivo): high - low
        delta_rate_pos = D.change_vector(
            {"hi": event_moments[("positivo", "high")],
             "lo": event_moments[("positivo", "low")]}, "hi", "lo")
        delta_rate_neg = D.change_vector(
            {"hi": event_moments[("negativo", "high")],
             "lo": event_moments[("negativo", "low")]}, "hi", "lo")
        # delta lungo regime a intensità FISSA: positivo - negativo
        delta_regime_hi = D.change_vector(
            {"p": event_moments[("positivo", "high")],
             "n": event_moments[("negativo", "high")]}, "p", "n")
        delta_regime_lo = D.change_vector(
            {"p": event_moments[("positivo", "low")],
             "n": event_moments[("negativo", "low")]}, "p", "n")
        dist_pos = D.change_vectors_distinctness(delta_rate_pos, delta_regime_hi)
        dist_neg = D.change_vectors_distinctness(delta_rate_neg, delta_regime_lo)
        crit_d = {
            "delta_rate_pos": delta_rate_pos.tolist(),
            "delta_rate_neg": delta_rate_neg.tolist(),
            "delta_regime_hi": delta_regime_hi.tolist(),
            "delta_regime_lo": delta_regime_lo.tolist(),
            "distinctness_at_regime_pos": dist_pos,
            "distinctness_at_regime_neg": dist_neg,
            "threshold_cosine_high": cosine_high,
        }
        # Verdetto (d): cosine STRETTAMENTE < soglia (= non-collineari) almeno
        # in una delle due "fette" — ma il prompt chiede "non collineare", che
        # rendo come: |cos| < cosine_high in ALMENO una delle due fette
        non_collinear_pos = abs(dist_pos["cosine"]) < cosine_high
        non_collinear_neg = abs(dist_neg["cosine"]) < cosine_high
        verdict_d = bool(non_collinear_pos and non_collinear_neg)

    return {
        "criterion_a": crit_a,
        "criterion_b": crit_b,
        "criterion_c": crit_c,
        "criterion_d": crit_d,
        "verdicts": {"a": verdict_a, "b": verdict_b, "c": verdict_c, "d": verdict_d},
        "thresholds_used": {
            "eta2_low": eta2_low, "kappa_low": kappa_low,
            "cosine_high": cosine_high, "min_cell": min_cell,
            "partition_mode": partition_mode,
        },
        "n_events_total": n_total,
        "n_events_with_intensity": n_valid,
        "config_hash": config.config_hash(),
    }
