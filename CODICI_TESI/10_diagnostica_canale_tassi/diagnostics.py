"""diagnostics.py — I 4 calcoli descrittivi del cancello per il canale tassi.

Solo statistica descrittiva sui dati. Nessuna stima di β̂_H del canale tassi,
nessuna risoluzione di sistemi strutturali. I numeri escono direttamente dai
dati passati come input.

I 4 calcoli:
  1. Variance decomposition within/between regime dell'intensità-tasso (η² ANOVA).
  2. Cohen's kappa fra partizione intensità-tasso e partizione regime.
  3. Cell counts regime × intensità (popolamento).
  4. Vettori di cambiamento dei momenti (var_e, var_b, cov_eb) lungo le due
     dimensioni → distinguibilità (angolo / cosine / rango numerico).

Anti-fabbricazione: ogni funzione produce numeri direttamente o solleva
(no fallback su valori costanti). Helper `cells_below_threshold` ritorna
liste vuote quando tutte le celle sono sopra soglia — non è un default
fabbricato, è il valore corretto del dato.
"""
from __future__ import annotations

from collections.abc import Iterable
from collections import Counter

import numpy as np


# ----- 1. Variance decomposition (η² ANOVA) ---------------------------------

def variance_decomposition(values, groups) -> dict:
    """Scomposizione classica ANOVA-style della varianza totale di `values`
    in within-group + between-group, rispetto al fattore `groups`.

    SS_total = Σ_i (x_i − x̄)²
    SS_between = Σ_g n_g (x̄_g − x̄)²
    SS_within  = SS_total − SS_between
    η² = SS_between / SS_total ∈ [0, 1]

    Restituisce `within_var`, `between_var` (varianze pop., NON normalizzate),
    `eta_squared`, `n`, `group_n`.
    """
    x = np.asarray(values, dtype=float)
    g = np.asarray(groups)
    if x.shape != g.shape:
        raise ValueError("values e groups devono avere stessa lunghezza")
    if x.size == 0:
        raise ValueError("input vuoto")

    mean_total = x.mean()
    ss_total = float(((x - mean_total) ** 2).sum())
    ss_between = 0.0
    group_n = {}
    for label in np.unique(g):
        sub = x[g == label]
        group_n[str(label)] = int(sub.size)
        ss_between += sub.size * (sub.mean() - mean_total) ** 2
    ss_within = ss_total - ss_between
    eta2 = float(ss_between / ss_total) if ss_total > 0 else 0.0
    return {
        "within_var": float(ss_within / x.size),
        "between_var": float(ss_between / x.size),
        "total_var": float(ss_total / x.size),
        "eta_squared": eta2,
        "n": int(x.size),
        "group_n": group_n,
    }


# ----- 2. Cohen's kappa fra due partizioni ----------------------------------

def cohens_kappa(part_a, part_b) -> float:
    """Cohen's κ per due partizioni di pari lunghezza.

    κ = (p_obs − p_exp) / (1 − p_exp)
    Dove p_obs = accordo osservato, p_exp = accordo atteso sotto indipendenza
    (prodotto delle marginali per ciascuna categoria comune). Caso 2×2 perfetto
    disaccordo → κ = −1; perfetto accordo → +1; indipendenza → ≈ 0.
    """
    a = np.asarray(part_a); b = np.asarray(part_b)
    if a.shape != b.shape:
        raise ValueError("le partizioni devono avere stessa lunghezza")
    if a.size == 0:
        raise ValueError("input vuoto")
    n = a.size
    cats = sorted(set(a) | set(b), key=str)
    p_obs = float(np.mean(a == b))
    p_exp = 0.0
    for c in cats:
        p_a = float(np.mean(a == c))
        p_b = float(np.mean(b == c))
        p_exp += p_a * p_b
    if p_exp == 1.0:
        return 1.0 if p_obs == 1.0 else float("nan")
    return float((p_obs - p_exp) / (1.0 - p_exp))


def partition_alignment_kappa(part_a, part_b) -> dict:
    """κ con allineamento delle etichette via permutazione che massimizza |κ|.

    Cohen's κ confronta etichette letteralmente: due partizioni con label set
    disgiunti (es. {high,low} vs {positivo,negativo}) producono κ≈0 anche con
    accordo strutturale perfetto. Per misurare se due DIMENSIONI sono confuse
    (senso del prompt) si rimappa una delle due partizioni tramite la permu-
    tazione delle sue etichette che massimizza |κ|, e si riporta quel valore.

    Caso 2×2: due possibili rimappature, si sceglie la migliore.
    Caso k×k generale: si enumerano tutte le permutazioni delle k etichette
    della seconda partizione (k! candidates) — usato per piccoli k.

    Restituisce {"kappa_aligned": float, "kappa_signed_max": float,
                  "best_mapping": dict, "raw_kappa": float}.
    """
    from itertools import permutations
    a = np.asarray(part_a); b = np.asarray(part_b)
    if a.shape != b.shape:
        raise ValueError("le partizioni devono avere stessa lunghezza")
    cats_b = sorted(set(b), key=str)
    cats_a = sorted(set(a), key=str)
    # cohen "raw" su etichette così come sono (per provenance)
    raw = cohens_kappa(a, b)
    best_abs = -np.inf; best_signed = 0.0; best_map = None
    # enumeriamo permutazioni di cats_b mappate su cats_a (richiede stessa cardinalità)
    if len(cats_b) != len(cats_a):
        # cardinalità diverse: cohen "raw" è già il meglio definibile senza ambiguità
        return {"kappa_aligned": abs(raw), "kappa_signed_max": raw,
                "best_mapping": {c: c for c in cats_b}, "raw_kappa": raw}
    for perm in permutations(cats_a):
        mapping = dict(zip(cats_b, perm))
        b_remap = np.array([mapping[x] for x in b])
        k = cohens_kappa(a, b_remap)
        if abs(k) > best_abs:
            best_abs = abs(k); best_signed = k; best_map = dict(mapping)
    return {"kappa_aligned": float(best_abs), "kappa_signed_max": float(best_signed),
            "best_mapping": best_map, "raw_kappa": float(raw)}


# ----- 3. Dicotomizzazione + popolamento celle ------------------------------

def dichotomize(values, mode: str = "median") -> np.ndarray:
    """Etichetta valori in 'high'/'low' (o 'drop' nel modo tertile_extremes).

    - "median": split sulla mediana within-sample (x ≥ mediana → 'high').
    - "tertile_extremes": top tertile → 'high', bottom tertile → 'low',
      middle tertile → 'drop' (da escludere a valle).
    - "movement": binario sì/no movimento (x > 0 → 'high', x == 0 → 'low').
      Modalità coerente con misure ad escursione assoluta (|Δprice|) che hanno
      massa puntuale in 0: lo split su mediana = 0 degenera (tutti in 'high');
      'movement' è una partizione strutturalmente valida sulla stessa metrica
      ed è pre-registrabile a priori sulla base della natura del segnale.
    """
    x = np.asarray(values, dtype=float)
    if mode == "median":
        med = float(np.median(x))
        return np.where(x >= med, "high", "low")
    if mode == "tertile_extremes":
        q1 = float(np.quantile(x, 1.0 / 3.0))
        q2 = float(np.quantile(x, 2.0 / 3.0))
        out = np.full(x.shape, "drop", dtype=object)
        out[x <= q1] = "low"
        out[x >= q2] = "high"
        return np.asarray(out)
    if mode == "movement":
        return np.where(x > 0, "high", "low")
    raise ValueError(f"modalità di dicotomizzazione sconosciuta: {mode!r}")


def cell_counts(df, *, regime_col: str, intensity_col: str) -> dict:
    """Contatori celle (regime × intensità). Restituisce dict (regime, intensità) → n."""
    out = {}
    for (r, i), grp in df.groupby([regime_col, intensity_col]):
        out[(str(r), str(i))] = int(len(grp))
    return out


def cells_below_threshold(counts: dict, threshold: int) -> list:
    """Lista delle celle con n < `threshold`. Lista vuota se tutte ≥ soglia.

    NB: una cella *non presente* in `counts` (n=0) viene riportata solo se
    invocata esplicitamente; questa funzione esamina ciò che esiste in counts.
    Per "celle attese ma vuote" si usa `expected_cells_missing` (non implementato
    qui — l'invocante elenca le coppie attese e fa diff).
    """
    return [k for k, v in counts.items() if v < threshold]


# ----- 4. Vettori di cambiamento + distinguibilità --------------------------

def change_vector(cells: dict, label_pos: str, label_neg: str) -> np.ndarray:
    """Δ = cella[pos] − cella[neg] sul vettore (var_e, var_b, cov_eb)."""
    keys = ("var_e", "var_b", "cov_eb")
    pos = cells[label_pos]; neg = cells[label_neg]
    return np.array([pos[k] - neg[k] for k in keys], dtype=float)


def cosine_similarity(u, v) -> float:
    """cos(u, v) = (u·v) / (|u| |v|). NaN se uno dei due ha norma 0."""
    u = np.asarray(u, dtype=float); v = np.asarray(v, dtype=float)
    nu = float(np.linalg.norm(u)); nv = float(np.linalg.norm(v))
    if nu == 0 or nv == 0:
        return float("nan")
    return float(np.dot(u, v) / (nu * nv))


def change_vectors_distinctness(u, v, *, rank_tol: float = 1e-9) -> dict:
    """Misure descrittive di distinguibilità di due vettori 3D.

    - cosine: cos(angolo).
    - angle_deg: angolo in gradi (0=collineari, 90=ortogonali, 180=anticollin.).
    - rank_numerical: rank della matrice [u; v] con tolleranza `rank_tol`.
      1 = collineari; 2 = linearmente indipendenti.
    """
    u = np.asarray(u, dtype=float); v = np.asarray(v, dtype=float)
    c = cosine_similarity(u, v)
    angle = float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0)))) if not np.isnan(c) else float("nan")
    M = np.column_stack([u, v])
    rank = int(np.linalg.matrix_rank(M, tol=rank_tol))
    return {"cosine": c, "angle_deg": angle, "rank_numerical": rank}
