"""calibration.py — Calibrazione SOLO sul training (presidio strutturale).

`calibrate(events_df, training_end)` solleva se trova eventi con date ≥
training_end: la funzione di calibrazione NON PUÒ vedere il test, per
costruzione. È il presidio richiesto dalla spec ("il codice deve rendere
strutturalmente impossibile la ricalibrazione sul test").
"""
from __future__ import annotations

import pandas as pd

import config


def calibrate(events_df: pd.DataFrame, training_end: pd.Timestamp) -> dict:
    """e_{g,k} = media di ε sui SOLI eventi di training, per cella (gamba, regime).

    `events_df` deve contenere: 'date' (Timestamp), 'leg' (NFP/CPI),
    'regime' (pos/neg), 'epsilon' (float). Se anche un solo evento ha
    `date >= training_end` la funzione SOLLEVA (no leakage).
    """
    needed = {"date", "leg", "regime", "epsilon"}
    if not needed.issubset(events_df.columns):
        raise ValueError(f"events_df serve colonne {needed}, ha {set(events_df.columns)}")
    leaks = events_df[events_df["date"] >= training_end]
    if len(leaks) > 0:
        raise ValueError(
            f"leakage: {len(leaks)} eventi con date ≥ training_end={training_end.date()}. "
            "La funzione di calibrazione DEVE ricevere SOLO il training (presidio strutturale)."
        )
    e_gk = (events_df.groupby(["leg", "regime"])["epsilon"]
            .mean()
            .to_dict())
    # rendiamo le chiavi tuple esplicite
    e_gk = {tuple(k): float(v) for k, v in e_gk.items()}
    return {"e_gk": e_gk,
            "n_train": int(len(events_df)),
            "training_end": pd.Timestamp(training_end)}


def position_for(leg: str, regime: str, e_gk: dict,
                 min_abs: float = config.MIN_ABS_E_FOR_POSITION) -> int:
    """Versione base: w = sign(e_{g,k}); 0 sotto soglia |min_abs|.

    Spec: "Versione base: il segno (robusta, minimo data-mining).
    La size proporzionale ... si riporta solo come robustezza".

    REVIEW #5 (nit): col default `MIN_ABS_E_FOR_POSITION=0`, il branch
    `if abs(e) < min_abs: return 0` è DORMIENTE (abs(e) < 0 è sempre False);
    la spec lo prevede esplicitamente come "default: nessuna soglia". Il
    parametro è esposto per consentire all'esecutore di filtrare e_{g,k}
    spurio (es. e ≈ 0 ± rumore) in robustezza dichiarata, non ex-post.
    """
    key = (leg, regime)
    if key not in e_gk:
        raise KeyError(f"cella {key} non calibrata; eventi training in questa cella nulli")
    e = float(e_gk[key])
    if abs(e) < min_abs:
        return 0
    if e > 0:
        return +1
    if e < 0:
        return -1
    return 0   # e esattamente 0 → posizione 0
