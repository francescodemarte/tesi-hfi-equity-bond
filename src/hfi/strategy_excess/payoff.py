"""payoff.py — Payoff teorico LORDO (covariance-swap–like).

ASSUNZIONE DI REPLICABILITÀ (da dichiarare in tesi e nel manifest):
il payoff di una posizione long sulla covarianza realizzata equity-bond su un
evento è la covarianza realizzata stessa (base dei covariance swap); la
replicazione esatta richiederebbe un portafoglio dinamico di opzioni, fuori scope.
Non è uno Sharpe eseguibile.
"""
from __future__ import annotations


def strategy_payoff(w: int, eps: float) -> float:
    """π_i = w_i · ε_i (posizione unitaria sul comovimento, diretta dal segno)."""
    return float(w) * float(eps)


def benchmark_payoff(eps: float) -> float:
    """Benchmark naive: w=+1 sempre, π_bench = ε_i."""
    return float(eps)
