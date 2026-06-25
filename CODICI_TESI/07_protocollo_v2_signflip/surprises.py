"""surprises.py — Sorprese Z (Lewbel/T2) e s (meccanismo/T9) e gate C0.4.

Mapping CONGELATO (§8 spec):
  FOMC → m_e (PC1 money-market <1y)   ECB → LEVEL (Altavilla)
  CPI  → actual-vs-consensus           NFP → actual-vs-consensus (se reperibile)

VINCOLO: **mai ΔT5YIE né altra componente del bond** come Z o s — è la reazione
del breakeven (non una sorpresa), i regimi sono definiti dalla correlazione
equity-bond e il breakeven è componente del bond ⇒ circolarità (vizio
«CPI direzionale»), oltre al mismatch daily/evento. `validate_source` lo blocca.

Gate C0.4: una cella alimenta T2/T9 solo se ha abbastanza sorprese valide
(≥ N_MIN, parametro già congelato) e varianza non degenere. La rilevanza vera
(τ≠0) è poi il test T2; qui è solo il cancello di alimentabilità.
"""
from __future__ import annotations

import numpy as np

from config import N_MIN

SURPRISE_SOURCE = {
    "FOMC": "m_e",
    "ECB": "LEVEL",
    "CPI": "actual_vs_consensus",
    "NFP": "actual_vs_consensus",
}

# Sorgenti VIETATE come Z/s: componenti del bond / reazioni, non sorprese.
FORBIDDEN_SOURCES = {"dt5yie", "t5yie", "breakeven", "dbreakeven", "t10yie"}


def surprise_source(event_type: str) -> str:
    """Sorgente dichiarata di Z/s per il tipo evento.

    AUTO-VALIDANTE: la sorgente restituita passa sempre da `validate_source`, così
    la guardia ΔT5YIE è sul percorso canonico (non solo nei test). Se la mappa
    fosse mai modificata con una sorgente vietata, qui solleva.
    """
    if event_type not in SURPRISE_SOURCE:
        raise KeyError(f"Tipo evento sconosciuto: {event_type}")
    return validate_source(SURPRISE_SOURCE[event_type])


def validate_source(name: str) -> str:
    """Rifiuta le sorgenti vietate (ΔT5YIE & co.); restituisce `name` se valido."""
    if name.lower() in FORBIDDEN_SOURCES:
        raise ValueError(
            f"Sorgente vietata come Z/s: {name!r} — componente del bond / reazione, "
            "non una sorpresa (circolarità del «CPI direzionale» + mismatch daily/evento)."
        )
    return name


def coverage_variance_gate(values, n_min: int = N_MIN) -> dict:
    """Cancello di alimentabilità C0.4 per una cella.

    feedable = (n_valid ≥ n_min) AND (varianza campionaria > 0).
    Usa il floor N_MIN già congelato; nessuna soglia nuova.
    """
    arr = np.asarray(values, dtype=float)
    valid = arr[~np.isnan(arr)]
    n_valid = int(valid.size)
    n_total = int(arr.size)
    coverage = (n_valid / n_total) if n_total else 0.0
    variance = float(np.var(valid, ddof=1)) if n_valid >= 2 else 0.0
    feedable = (n_valid >= n_min) and (variance > 0.0)
    return {
        "n_valid": n_valid,
        "n_total": n_total,
        "coverage": coverage,
        "variance": variance,
        "feedable": feedable,
    }
