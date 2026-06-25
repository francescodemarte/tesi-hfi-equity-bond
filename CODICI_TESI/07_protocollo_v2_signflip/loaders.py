"""loaders.py — Loader per le sorprese e gli input secondari.

- `m_e_pca` (FOMC): prima componente principale delle variazioni money-market
  <1y nella finestra HFI. Tipicamente alimentata dalle Δ dei front-month
  futures sui Fed Funds (FFc1..c3) e SOFR/Euribor short (SR/FEI). Il calcolo
  PCA è qui; l'estrazione delle Δ-finestra è a monte (windows.extract_window
  applicato ai prezzi dei futures tassi).
- `equity_duration_partial`: ∑ w·h / ∑ w (nan-safe) — duration parziale equity
  dai pesi dei dividend strip e dagli orizzonti corrispondenti.
- `load_ecb_level`: dichiarato GATED. La componente LEVEL di Altavilla et al.
  (2019) sta in un foglio Excel non-tabulare con struttura interna opaca; un
  parser fedele richiede autorizzazione separata + congelamento del file.

Convenzioni: solo numpy/pandas; nessun side-effect su disco.
"""
from __future__ import annotations

import numpy as np


def m_e_pca(deltas: np.ndarray) -> np.ndarray:
    """PC1 di una matrice (n_events × k_serie) di variazioni money-market.

    - Standardizza ciascuna colonna a media nulla.
    - Estrae il primo autovettore della covarianza (n piccolo, k piccolo).
    - Convenzione di segno: somma dei loading non negativa → la PC1 ha lo
      stesso senso del «fattore comune dei tassi» (utile per coerenza
      cross-evento e per l'interpretazione hawkish).
    - Se la varianza totale è ~0 (input costante), ritorna zeri (no segno).
    """
    M = np.asarray(deltas, dtype=float)
    if M.ndim != 2:
        raise ValueError("deltas deve essere 2D (n_events × k_serie)")
    Mc = M - M.mean(axis=0, keepdims=True)
    if not np.isfinite(Mc).all():
        raise ValueError("input non finiti")
    cov = np.cov(Mc, rowvar=False, ddof=1) if Mc.shape[1] > 1 else np.var(Mc, ddof=1)
    if np.atleast_2d(cov).trace() <= 0:
        return np.zeros(M.shape[0])
    cov2 = np.atleast_2d(cov)
    vals, vecs = np.linalg.eigh(cov2)
    v = vecs[:, -1]                      # autovettore associato all'autovalore massimo
    if v.sum() < 0:                      # fissa il segno per loading non-negativi
        v = -v
    return Mc @ v


def equity_duration_partial(weights, horizons) -> float:
    """Duration parziale equity = ∑ w·h / ∑ w, nan-safe sui pesi.

    Restituisce np.nan se la somma dei pesi (al netto dei NaN) è ≤ 0.
    """
    w = np.asarray(weights, dtype=float)
    h = np.asarray(horizons, dtype=float)
    mask = ~np.isnan(w)
    wt = w[mask]
    if wt.sum() <= 0:
        return float("nan")
    return float(np.nansum(w * h) / np.nansum(w))


def load_ecb_level(path):
    """ECB LEVEL (Altavilla et al. 2019) — DICHIARATO GATED.

    Il file Excel ha foglio interno non-tabulare con struttura specifica al paper;
    un parser fedele richiede AUTORIZZAZIONE SEPARATA (non FRED), il file
    CONGELATO con provenienza (URL+hash+data) e mappatura colonne→date validata
    contro le release ECB. L'esecutore lo cabla quando l'input è autorizzato.
    """
    raise NotImplementedError(
        "load_ecb_level: GATED. Foglio Excel non-tabulare (Altavilla 2019); richiede "
        "autorizzazione separata (non FRED) + congelamento del file con provenienza "
        "e mappatura colonne→date validata. L'esecutore lo cabla al run reale."
    )
