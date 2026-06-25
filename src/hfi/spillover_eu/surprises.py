"""surprises.py — Stadio 0: m_j (PC1 paniere tassi), s_j (E-mini), separazione
Jarociński–Karadi per rotazione a restrizione di segno + riscontro poor man's.

Disciplina anti-fabbricazione: ogni funzione produce un calcolo onesto o
SOLLEVA. Nessun valore costante "verosimile" al posto di un risultato.
"""
from __future__ import annotations

import numpy as np

from config import FORBIDDEN_SOURCES


class JKNotIdentifiedError(ValueError):
    """Separazione JK non identificata sui dati forniti.

    Sollevata da `separate_jk` quando la struttura JK NON è empiricamente
    distinguibile da una Σ(m,s) ≈ diagonale (rumore indipendente). In quel
    caso la decomposizione spettrale esisterebbe ma sarebbe dominata dal
    rumore campionario sugli autoassi: NON si fabbrica un Z (vedi review
    agente 4, Bug 08-#1).
    """


def validate_source(name: str) -> str:
    """Rifiuta breakeven/T5YIE come strumento (coerenza col protocollo principale).
    Restituisce `name` invariato se valido, altrimenti solleva ValueError.
    """
    forbidden = {s.lower() for s in FORBIDDEN_SOURCES}
    if name.lower() in forbidden:
        raise ValueError(
            f"Sorgente vietata come strumento: {name!r}. ΔT5YIE/breakeven sono "
            "componenti del bond → circolarità + mismatch di frequenza."
        )
    return name


def pc1(matrix) -> np.ndarray:
    """Prima componente principale di una matrice (n_obs × k_serie).

    - Centra le colonne.
    - Estrae il primo autovettore della covarianza (k piccolo).
    - Convenzione di segno: somma dei loading ≥ 0 (orientazione coerente
      cross-evento). Se la varianza totale è nulla, ritorna zeri.
    """
    M = np.asarray(matrix, dtype=float)
    if M.ndim != 2:
        raise ValueError("input deve essere 2D (n_obs × k_serie)")
    if not np.isfinite(M).all():
        raise ValueError("input contiene valori non finiti")
    Mc = M - M.mean(axis=0, keepdims=True)
    cov2 = np.atleast_2d(np.cov(Mc, rowvar=False, ddof=1) if Mc.shape[1] > 1
                         else np.var(Mc, ddof=1))
    if cov2.trace() <= 0:
        return np.zeros(M.shape[0])
    vals, vecs = np.linalg.eigh(cov2)
    v = vecs[:, -1]
    if v.sum() < 0:
        v = -v
    return Mc @ v


def _cov(x, y):
    return float(np.cov(x, y, ddof=1)[0, 1])


def separate_jk(m, s, *, B: int = 1000, alpha: float = 0.05,
                rng=None, return_diagnostics: bool = False) -> dict:
    """Separazione Jarociński–Karadi 2×2.

    Implementazione esatta: **decomposizione spettrale di Σ(m,s)** seguita da
    una scelta di SEGNO degli autovettori (non una rotazione di Givens
    R(θ) generica — gli autoassi sono determinati da Σ, non parametrizzati).
    Per Σ 2×2 non-degenere gli autovettori sono ortogonali per costruzione;
    le 8 combinazioni segno×assegnazione coprono i quadranti necessari ai
    4 vincoli (spec §0.2):
        Cov(m, Z_mp) > 0,  Cov(s, Z_mp) < 0   (restrittivo: tasso↑, equity↓)
        Cov(m, Z_cbi) > 0, Cov(s, Z_cbi) > 0  (informativo: concordi)

    **Gate di esistenza (review agente 4 #1 — BLOCKER risolto).** Per Σ 2×2
    non-degenere, una qualche orientazione di segno soddisfa SEMPRE i 4
    vincoli (cfr. l'osservazione Cov(m, Z_i) = D_ii · v_i[0]): di per sé,
    la procedura NON è un test di esistenza della struttura JK. Per evitare
    di ruotare il rumore campionario, qui si gateava `feasible` su un test
    di non-isotropia di Σ:
      H0: Cov(m, s) = 0  (Σ diagonale, niente da ruotare)
      contro H1: Cov(m, s) ≠ 0  (assi principali non allineati a (m, s)).
    Bootstrap su Cov(m,s) (B repliche, riproducibile, seed dichiarato);
    se 0 ∈ CI 100·(1-α)% → `JKNotIdentifiedError` (o `feasible=False` se
    `return_diagnostics=True` per uso diagnostico).

    Args:
        B: repliche bootstrap per il CI di Cov(m, s) (default 1000).
        alpha: livello del CI (default 0.05 → CI 95%).
        rng: np.random.Generator opzionale; se None usa `config.make_rng("separate_jk")`.
        return_diagnostics: se True, ritorna anche `feasibility` invece di sollevare.
    """
    m = np.asarray(m, dtype=float); s = np.asarray(s, dtype=float)
    if m.shape != s.shape:
        raise ValueError("m e s devono avere stessa lunghezza")
    n = len(m)
    mc = m - m.mean(); sc = s - s.mean()
    Sigma = np.cov(np.column_stack([mc, sc]), rowvar=False, ddof=1)
    if not np.isfinite(Sigma).all() or np.linalg.matrix_rank(Sigma) < 2:
        raise ValueError("Σ non a rango pieno: separazione non identificata")

    # --- Gate di esistenza JK (BLOCKER #1 review agente 4) -----------------
    # H0: Cov(m,s)=0 ⇒ Σ diagonale ⇒ niente struttura da ruotare.
    if rng is None:
        from config import make_rng
        rng = make_rng("separate_jk_feasibility")
    cov_ms_hat = float(Sigma[0, 1])
    cov_bs = np.empty(B)
    for b in range(B):
        idx = rng.integers(0, n, n)
        cov_bs[b] = float(np.cov(m[idx], s[idx], ddof=1)[0, 1])
    lo = float(np.quantile(cov_bs, alpha / 2.0))
    hi = float(np.quantile(cov_bs, 1.0 - alpha / 2.0))
    feasible = not (lo <= 0.0 <= hi)
    eigvals, _ = np.linalg.eigh(Sigma)
    feasibility = {
        "cov_ms": cov_ms_hat,
        "cov_ms_ci95": (lo, hi),
        "eigvals": (float(eigvals[0]), float(eigvals[1])),
        "n": int(n),
        "feasible": feasible,
    }
    if not feasible:
        if return_diagnostics:
            return {"Z_mp": None, "Z_cbi": None, "loadings": None,
                    "feasible": False, "feasibility": feasibility}
        raise JKNotIdentifiedError(
            "Σ(m,s) non distinguibile da diagonale al 95%: 0 ∈ CI bootstrap di "
            f"Cov(m,s) = {cov_ms_hat:.4g} ∈ [{lo:.4g}, {hi:.4g}]. La struttura "
            "JK NON è identificata dai dati. Non si fabbrica un Z."
        )

    # --- Decomposizione spettrale + orientazione segni ---------------------
    _, V = np.linalg.eigh(Sigma)
    # 8 combinazioni: 2 assegnazioni {axis0→mp / axis1→mp} × 4 scelte di segno
    for swap in (False, True):
        ax_mp_idx, ax_cbi_idx = (1, 0) if swap else (0, 1)
        v_mp = V[:, ax_mp_idx]; v_cbi = V[:, ax_cbi_idx]
        for s_mp in (+1, -1):
            for s_cbi in (+1, -1):
                Z_mp = s_mp * (np.column_stack([mc, sc]) @ v_mp)
                Z_cbi = s_cbi * (np.column_stack([mc, sc]) @ v_cbi)
                if (_cov(m, Z_mp) > 0 and _cov(s, Z_mp) < 0
                        and _cov(m, Z_cbi) > 0 and _cov(s, Z_cbi) > 0):
                    out = {"Z_mp": Z_mp, "Z_cbi": Z_cbi,
                           "loadings": {"mp": s_mp * v_mp, "cbi": s_cbi * v_cbi},
                           "feasible": True}
                    if return_diagnostics:
                        out["feasibility"] = feasibility
                    return out
    raise JKNotIdentifiedError(
        "Σ(m,s) non degenere ma nessuna delle 8 orientazioni rispetta tutte e 4 "
        "le disuguaglianze. Caso teorico atipico, non si fabbrica Z."
    )


def poor_mans(m, s) -> dict:
    """Riscontro poor man's: Z_mp ≈ m·1[m·s<0], Z_cbi ≈ m·1[m·s>0] (spec §0.3).

    Definizione semplice (cintura sopra le bretelle) per il check di
    concordanza di segno. Non è uno stimatore alternativo, è un termine di
    paragone — divergenze dichiarate, non sanate.
    """
    m = np.asarray(m, dtype=float); s = np.asarray(s, dtype=float)
    prod = m * s
    Z_mp = np.where(prod < 0, m, 0.0)
    Z_cbi = np.where(prod > 0, m, 0.0)
    return {"Z_mp": Z_mp, "Z_cbi": Z_cbi}


def sign_concordance(full: dict, poor: dict) -> dict:
    """Frazione di osservazioni in cui i segni concordano fra rotazione e poor man's.

    - Per CBI: frazione in cui sign(Z_cbi_full) == sign(Z_cbi_poor) su elementi non nulli del poor.
    - Per MP:  frazione in cui sign(Z_mp_full) == sign(Z_mp_poor) su elementi non nulli del poor.
    - n: numerosità totale del campione.
    """
    def _agree(zf, zp):
        nz = zp != 0
        if not nz.any():
            return 0.0
        return float(np.mean(np.sign(zf[nz]) == np.sign(zp[nz])))
    return {"mp": _agree(full["Z_mp"], poor["Z_mp"]),
            "cbi": _agree(full["Z_cbi"], poor["Z_cbi"]),
            "n": int(len(full["Z_mp"]))}
