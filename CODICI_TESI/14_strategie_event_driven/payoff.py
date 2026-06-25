"""payoff.py — Payoff per evento ai DUE orizzonti (entrambi obbligatori).

  payoff_horizon = size · (sign_equity · r_e_horizon + sign_bond · r_b_horizon)

Sharpe LORDO di costi di transazione (spec). I rendimenti devono essere già
calcolati dall'esecutore sui due orizzonti: 15-min event window + EOD.
"""
from __future__ import annotations

import strategy_rule as SR


def event_payoff(*, strategy: str, surprise: float,
                 r_e_event: float, r_b_event: float,
                 r_e_eod: float, r_b_eod: float) -> dict:
    """Payoff ai due orizzonti per un singolo evento ATTIVO (regime già filtrato)."""
    pos = SR.position(strategy, surprise)
    s_e, s_b, size = pos["sign_equity"], pos["sign_bond"], pos["size"]
    p_event = float(size * (s_e * r_e_event + s_b * r_b_event))
    p_eod = float(size * (s_e * r_e_eod + s_b * r_b_eod))
    return {"event_window": p_event, "end_of_day": p_eod}
