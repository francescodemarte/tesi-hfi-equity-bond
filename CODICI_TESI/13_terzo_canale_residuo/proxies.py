"""proxies.py — Ortogonalizzazione delle proxy alla sorpresa (spec §4).

ΔZ⊥_i = residuo di OLS di ΔZ_i su [costante, sorpresa, eventuali controlli].
Test di terzo canale usa ΔZ⊥, NON ΔZ grezzo — protegge da rimozione imperfetta
dei primi due canali.
"""
from __future__ import annotations

import numpy as np


def orthogonalize(z, surprise, extra_controls=None) -> np.ndarray:
    """Residuo OLS di z su [const, surprise, extra_controls?]."""
    z = np.asarray(z, dtype=float)
    s = np.asarray(surprise, dtype=float)
    if z.shape != s.shape:
        raise ValueError(f"z {z.shape} ≠ surprise {s.shape}")
    cols = [np.ones_like(z), s]
    if extra_controls is not None:
        ec = np.asarray(extra_controls, dtype=float)
        if ec.ndim == 1:
            if ec.shape != z.shape:
                raise ValueError(f"extra_controls {ec.shape} ≠ z {z.shape}")
            cols.append(ec)
        else:
            if ec.shape[0] != z.size:
                raise ValueError("extra_controls n_righe ≠ z lunghezza")
            for j in range(ec.shape[1]):
                cols.append(ec[:, j])
    X = np.column_stack(cols)
    beta, *_ = np.linalg.lstsq(X, z, rcond=None)
    return z - X @ beta
