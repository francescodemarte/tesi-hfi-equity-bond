"""term_structure.py — Estrazione fattori PC1/PC2 dalla struttura a termine.

Estensione del kernel del cancello canale tassi (modulo 10): si aggiunge
l'estrazione di due fattori ortogonali dai movimenti congiunti dei contratti
Eurodollar FEIc1..c4 nelle finestre ±15 min attorno agli annunci Fed.

Convenzioni FISSATE (non discrezionali):
  - PCA standard sui Δ centrati (4-D), via SVD; PC1 e PC2 sono le prime due
    componenti per varianza spiegata.
  - Segno: PC1 ha loading non negativo sul contratto FEIc1 (TS_PC1_SIGN_REF);
    PC2 ha loading non negativo sul contratto FEIc4 (TS_PC2_SIGN_REF).
    Toglie l'ambiguità di segno della PCA (autovettori definiti a meno del segno).
  - Nessuna rotazione (varimax, etc.). Solo PCA.

Anti-fabbricazione: niente fallback su valori costanti; finestre con Δ mancante
producono NaN nella riga corrispondente e l'evento viene escluso a monte
dall'estrazione PCA (in modo dichiarato). Nessuno stub.
"""
from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

import config
import rate_shock


def event_term_structure_deltas(rate_prices: Mapping[str, pd.Series],
                                 t_center: pd.Timestamp,
                                 contracts=config.TS_CONTRACTS,
                                 half_min: int = config.HALF_MIN_WINDOW,
                                 edge_min: int = config.MEDIAN_EDGE_MIN
                                 ) -> np.ndarray:
    """Vettore 4-D dei Δ (post - pre) sui contratti `contracts`, finestra ±half_min.

    `rate_prices` è dict {contract_name: pd.Series} con DatetimeIndex.
    NaN nel risultato se uno qualunque dei contratti manca i suoi edge nella
    finestra (anti-fabbricazione: non si imputa zero al posto di un dato assente).
    Δ = post - pre, NON in valore assoluto (PCA opera sui Δ con segno).
    """
    out = np.full(len(contracts), np.nan, dtype=float)
    for i, name in enumerate(contracts):
        if name not in rate_prices:
            return np.full(len(contracts), np.nan, dtype=float)
        w = rate_shock.extract_event_window(rate_prices[name], t_center,
                                              half_min=half_min, edge_min=edge_min)
        if np.isnan(w["pre"]) or np.isnan(w["post"]):
            return np.full(len(contracts), np.nan, dtype=float)
        out[i] = float(w["post"] - w["pre"])
    return out


def build_term_structure_table(events: pd.DataFrame,
                                rate_prices: Mapping[str, pd.Series],
                                contracts=config.TS_CONTRACTS,
                                half_min: int = config.HALF_MIN_WINDOW,
                                edge_min: int = config.MEDIAN_EDGE_MIN
                                ) -> pd.DataFrame:
    """DataFrame con colonne timestamp/leg/regime + un Δ per contratto.

    Le righe con qualunque Δ mancante sono mantenute (con NaN); è chi consuma
    questa tabella a dichiarare la regola di esclusione (segnale verde di
    trasparenza per il manifest).
    """
    required = {"timestamp", "leg", "regime"}
    if not required.issubset(events.columns):
        raise ValueError(f"events deve avere colonne {required}")
    rows = []
    for _, ev in events.iterrows():
        ts = pd.Timestamp(ev["timestamp"])
        deltas = event_term_structure_deltas(rate_prices, ts, contracts=contracts,
                                              half_min=half_min, edge_min=edge_min)
        d = {"timestamp": ts, "leg": str(ev["leg"]), "regime": str(ev["regime"])}
        for i, name in enumerate(contracts):
            d[f"delta_{name}"] = float(deltas[i])
        rows.append(d)
    return pd.DataFrame(rows)


def extract_pc_factors(deltas: np.ndarray,
                        contracts=config.TS_CONTRACTS,
                        sign_ref_pc1: str = config.TS_PC1_SIGN_REF,
                        sign_ref_pc2: str = config.TS_PC2_SIGN_REF) -> dict:
    """PCA sui Δ centrati. Restituisce loading, varianza spiegata, scores per evento.

    `deltas` ha shape (n_events, n_contracts). Centra le colonne (mean=0) e
    decompone via SVD; le componenti principali sono gli autovettori della
    matrice di covarianza ordinati per varianza decrescente. I segni di PC1 e
    PC2 sono fissati richiedendo loading non negativo su `sign_ref_pc1` /
    `sign_ref_pc2`.

    Ritorna:
      - loadings: (n_components, n_contracts) — autovettori (righe), ordinati
        PC1, PC2, ...
      - var_explained: array di frazioni di varianza spiegata
      - scores: (n_events, n_components) — proiezione dei Δ centrati
      - mean_deltas: media riga-per-riga sottratta
      - n_events: int
      - contracts: list[str]
    Solleva ValueError se shape inconsistente o n_events < 2.
    """
    X = np.asarray(deltas, dtype=float)
    if X.ndim != 2 or X.shape[1] != len(contracts):
        raise ValueError(f"deltas deve avere shape (n_events, {len(contracts)}); "
                         f"ha {X.shape}")
    if X.shape[0] < 2:
        raise ValueError(f"PCA richiede ≥ 2 eventi; ricevuti {X.shape[0]}")
    if np.isnan(X).any():
        raise ValueError("deltas contiene NaN: pulire a monte (filtrare eventi "
                         "con Δ mancante) prima di chiamare extract_pc_factors")

    mean = X.mean(axis=0)
    Xc = X - mean
    # SVD: Xc = U S V^T; le componenti principali sono le righe di V^T.
    U, s, Vt = np.linalg.svd(Xc, full_matrices=False)
    # Varianza spiegata da ciascuna componente: (s^2) / sum(s^2) [degrees of
    # freedom cancellano nella normalizzazione].
    var = s ** 2
    var_explained = var / var.sum() if var.sum() > 0 else np.zeros_like(var)

    loadings = Vt.copy()
    # Fissa il segno di PC1 e PC2 secondo la convenzione dichiarata.
    idx_pc1 = contracts.index(sign_ref_pc1)
    if loadings.shape[0] >= 1 and loadings[0, idx_pc1] < 0:
        loadings[0] = -loadings[0]
    idx_pc2 = contracts.index(sign_ref_pc2)
    if loadings.shape[0] >= 2 and loadings[1, idx_pc2] < 0:
        loadings[1] = -loadings[1]

    # Scores coerenti col segno fissato
    scores = Xc @ loadings.T

    return {
        "loadings": loadings,
        "var_explained": var_explained,
        "scores": scores,
        "mean_deltas": mean,
        "n_events": int(X.shape[0]),
        "contracts": list(contracts),
    }


def first_gate_non_degeneracy(ts_table: pd.DataFrame,
                                pca: dict,
                                pc2_var_min: float = config.TS_PC2_VAR_EXPLAINED_MIN,
                                long_move_min_frac: float = config.TS_LONG_CONTRACT_MOVEMENT_MIN_FRAC,
                                contracts=config.TS_CONTRACTS) -> dict:
    """Primo cancello — non degenerazione della pendenza.

    Tre check, tutti devono passare per procedere a (d):
      (i)  var_explained(PC2) ≥ pc2_var_min  → la pendenza è un fattore vivo;
      (ii) frazione di eventi con Δ_c3 ≠ 0 ≥ long_move_min_frac AND
           frazione con Δ_c4 ≠ 0 ≥ long_move_min_frac → i contratti lunghi
           non sono fermi (esclude la degenerazione strutturale di FFc2);
      (iii) la partizione mediana di |PC2| produce entrambe le celle high/low
            non vuote (= non degenera come faceva FFc2 mediana).

    `ts_table` è la tabella riga-per-evento con `delta_<contract>` (le righe
    devono essere già state filtrate sui NaN — l'estrazione PCA fa lo stesso
    filtro). I conteggi di (ii) sono calcolati su `ts_table` non-NaN.
    `pca` è il dict di `extract_pc_factors`.
    """
    # (i) varianza PC2
    var_pc2 = float(pca["var_explained"][1]) if len(pca["var_explained"]) >= 2 else float("nan")
    check_i = (not np.isnan(var_pc2)) and (var_pc2 >= pc2_var_min)

    # (ii) movimento contratti lunghi
    valid = ts_table.dropna(subset=[f"delta_{c}" for c in contracts])
    n_valid = int(len(valid))
    long_fractions = {}
    for c in contracts[-2:]:
        col = valid[f"delta_{c}"].to_numpy()
        frac = float((col != 0).sum() / n_valid) if n_valid > 0 else float("nan")
        long_fractions[c] = frac
    check_ii = (n_valid > 0
                and all(f >= long_move_min_frac for f in long_fractions.values()))

    # (iii) mediana |PC2|: entrambe le celle high/low devono essere non vuote
    pc2_scores = pca["scores"][:, 1] if pca["scores"].shape[1] >= 2 else np.array([])
    abs_pc2 = np.abs(pc2_scores)
    if abs_pc2.size > 0:
        med = float(np.median(abs_pc2))
        n_high = int((abs_pc2 >= med).sum())
        n_low = int((abs_pc2 < med).sum())
        check_iii = (n_high > 0 and n_low > 0)
    else:
        med = float("nan"); n_high = 0; n_low = 0; check_iii = False

    passed = bool(check_i and check_ii and check_iii)
    return {
        "passed": passed,
        "check_i_pc2_var_explained": {
            "value": var_pc2, "threshold": pc2_var_min, "passed": bool(check_i),
        },
        "check_ii_long_contract_movement": {
            "fractions": long_fractions, "threshold": long_move_min_frac,
            "n_valid_events": n_valid, "passed": bool(check_ii),
        },
        "check_iii_pc2_partition_non_degenerate": {
            "median_abs_pc2": med, "n_high": n_high, "n_low": n_low,
            "passed": bool(check_iii),
        },
    }
