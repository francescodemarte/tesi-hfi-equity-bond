"""windows.py — Tre finestre disgiunte (presidio anti-look-ahead intra-evento).

Per evento all'indice `event_idx` del calendario di sedute:
  - regime:     [t-(63+3), ..., t-4]  (63 sedute, termina a t-4)
  - aspettativa:[t-3, t-2, t-1]       (3 sedute pre-evento)
  - evento:     t                     (la finestra intraday del comov. realizzato
                                       è altrove; qui basta l'indice)

`assert_no_lookahead(used_indices, event_idx)` solleva se un qualsiasi indice
usato per la decisione è ≥ event_idx.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np

import config


def three_windows(calendar, event_idx: int) -> tuple[list[int], list[int], int]:
    cal = list(calendar)
    n = len(cal)
    if not (0 <= event_idx < n):
        raise ValueError(f"event_idx={event_idx} fuori dal calendario (n={n})")
    end_regime = event_idx - config.REGIME_END_OFFSET_DAYS
    start_regime = end_regime - config.REGIME_WINDOW_DAYS + 1
    if start_regime < 0:
        raise ValueError(
            f"calendario insufficiente: servono {config.REGIME_WINDOW_DAYS + config.REGIME_END_OFFSET_DAYS} "
            f"sedute prima di event_idx={event_idx}, disponibili {event_idx}."
        )
    regime_idx = list(range(start_regime, end_regime + 1))
    proxy_idx = [event_idx - 3, event_idx - 2, event_idx - 1]
    return regime_idx, proxy_idx, event_idx


def regime_sign(r_eq_window, r_bo_window) -> str:
    """Segno della corr equity-bond sulla finestra-regime: 'pos' se >0, 'neg' altrimenti."""
    eq = np.asarray(r_eq_window, dtype=float)
    bo = np.asarray(r_bo_window, dtype=float)
    if eq.shape != bo.shape:
        raise ValueError("equity e bond devono avere stessa lunghezza")
    if eq.std(ddof=1) == 0 or bo.std(ddof=1) == 0:
        raise ValueError("varianza degenere nella finestra-regime")
    rho = float(np.corrcoef(eq, bo)[0, 1])
    return "pos" if rho > 0 else "neg"


def assert_no_lookahead(used_indices: Iterable[int], event_idx: int) -> None:
    bad = [i for i in used_indices if i >= event_idx]
    if bad:
        raise AssertionError(f"look-ahead: indici {bad} ≥ event_idx={event_idx}")
