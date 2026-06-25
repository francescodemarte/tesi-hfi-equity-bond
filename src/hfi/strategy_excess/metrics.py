"""metrics.py — Mean, Sharpe per-evento, hit rate, diff vs benchmark, soglia n."""
from __future__ import annotations

import numpy as np

import config


def sharpe(payoffs) -> float:
    """Sharpe per-evento: mean / std(ddof=1). NaN se std=0 (no fabbrica)."""
    p = np.asarray(payoffs, dtype=float)
    if p.size < 2:
        return float("nan")
    sd = float(p.std(ddof=1))
    if sd == 0:
        return float("nan")
    return float(p.mean() / sd)


def hit_rate(payoffs) -> float:
    """Frazione di payoff strettamente positivi."""
    p = np.asarray(payoffs, dtype=float)
    if p.size == 0:
        return float("nan")
    return float(np.mean(p > 0))


def diff_vs_benchmark(strategy_payoffs, benchmark_payoffs) -> dict:
    """Differenza paired strategia − benchmark (stesso evento)."""
    s = np.asarray(strategy_payoffs, dtype=float)
    b = np.asarray(benchmark_payoffs, dtype=float)
    if s.shape != b.shape:
        raise ValueError(f"strategy ({s.shape}) e benchmark ({b.shape}) lunghezze diverse")
    if s.size == 0:
        return {"mean_diff": float("nan"), "n": 0}
    return {"mean_diff": float((s - b).mean()), "n": int(s.size)}


def cell_summary(payoffs, n_min_verdict: int = config.MIN_CELL_N_FOR_VERDICT) -> dict:
    """Sintesi per una cella + verdetto 'inconclusive' se n < soglia (spec)."""
    p = np.asarray(payoffs, dtype=float)
    n = int(p.size)
    if n == 0:
        return {"n": 0, "verdict": "empty", "mean": float("nan"),
                "sharpe": float("nan"), "hit_rate": float("nan")}
    base = {"n": n,
            "mean": float(p.mean()),
            "sharpe": sharpe(p),
            "hit_rate": hit_rate(p)}
    base["verdict"] = "inconclusive" if n < n_min_verdict else "reportable"
    return base
