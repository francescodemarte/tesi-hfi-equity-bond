"""responses.py — Stadio 1: risposte dell'area euro a T+1.

- `yield_change_bp`: Δy in punti base = (post − pre) × 100 (yield in %).
- `log_return`: log-return da prezzo pre/post (NaN se prezzi non positivi).
- `spread_change_bp`: Δsp = Δy_BTP − Δy_Bund, in bp.
- `compute_eu_responses_single`: assembla `(dy_bund_bp, r_estoxx, dsp_bp)`
  per un singolo evento da `(pre, post)` di ciascun asset.

Nessuna fetch: l'orchestratore fornisce le quote/yields close-to-close T+1.
"""
from __future__ import annotations

import math


def yield_change_bp(pre: float, post: float) -> float:
    """Variazione di yield in punti base (yield in %): (post − pre) × 100."""
    return float((post - pre) * 100.0)


def log_return(pre: float, post: float) -> float:
    """Log-return; NaN se uno dei prezzi non è > 0 (nessun fallback silenzioso)."""
    if not (pre > 0 and post > 0):
        return float("nan")
    return float(math.log(post / pre))


def spread_change_bp(y_btp_pre: float, y_btp_post: float,
                     y_bund_pre: float, y_bund_post: float) -> float:
    """Δ spread BTP–Bund in p.b."""
    return float(yield_change_bp(y_btp_pre, y_btp_post)
                 - yield_change_bp(y_bund_pre, y_bund_post))


def compute_eu_responses_single(pre_post: dict) -> dict:
    """Risposte EU per un evento da `pre_post = {asset: (pre, post)}`.

    Atteso: `bund_yield_pct`, `estoxx_price`, `btp_yield_pct`.
    """
    b_pre, b_post = pre_post["bund_yield_pct"]
    p_pre, p_post = pre_post["estoxx_price"]
    btp_pre, btp_post = pre_post["btp_yield_pct"]
    return {
        "dy_bund_bp": yield_change_bp(b_pre, b_post),
        "r_estoxx": log_return(p_pre, p_post),
        "dsp_bp": spread_change_bp(btp_pre, btp_post, b_pre, b_post),
    }
