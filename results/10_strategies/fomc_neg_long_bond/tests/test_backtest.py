"""Tests pytest per FOMC/neg long bond backtest."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(PARENT))


def test_seed_determinism():
    """Stesso MASTER_SEED + nome → stesso seed int."""
    import extract_fomc_backtest as m
    s1 = m.seed_for("fomc_kfold")
    s2 = m.seed_for("fomc_kfold")
    assert s1 == s2
    assert s1 != m.seed_for("fomc_full_sample")


def test_pnl_formula_long_bond():
    """P&L per evento = β × r_bond − costo."""
    import extract_fomc_backtest as m
    import pandas as pd
    import numpy as np
    # Mini event series
    ev = pd.DataFrame({
        "date": pd.to_datetime(["2020-01-29", "2020-03-18"]),
        "regime_neg": [True, True],
    })
    ty = pd.Series(
        [100.0, 100.5, 100.0, 99.0],
        index=pd.to_datetime(["2020-01-28", "2020-01-29", "2020-03-17", "2020-03-18"]),
    )
    pnl = m.compute_event_pnl(ev, ty, beta=0.875, cost_bps=0.3)
    # r_bond evento 1: 100.5/100 - 1 = +0.005
    assert abs(pnl.iloc[0]["r_bond"] - 0.005) < 1e-12
    # pnl_gross = 0.875 × 0.005 = 0.004375
    assert abs(pnl.iloc[0]["pnl_gross"] - 0.875 * 0.005) < 1e-12
    # pnl_net = pnl_gross - 0.3e-4
    assert abs(pnl.iloc[0]["pnl_net"] - (0.875 * 0.005 - 0.3e-4)) < 1e-12
    # r_bond evento 2: 99/100 - 1 = -0.01
    assert abs(pnl.iloc[1]["r_bond"] - (-0.01)) < 1e-12


def test_sign_is_always_positive_long_bond():
    """In regime negativo la strategia è SEMPRE long bond (size positive |β|).
    Il segno NON è back-fit sul rendimento — l'esecutore non lo cambia mai.
    Verifica leggendo il manifest output."""
    p = PARENT / "backtest_full_sample.json"
    if not p.exists():
        # Se non è stato ancora runnato, skipa
        import pytest
        pytest.skip("backtest_full_sample.json non presente, skip sign check")
    r = json.loads(p.read_text())
    # beta_str è sempre +0.8748 in valore assoluto (sign-locked)
    assert r["beta_str_used"] > 0
    assert abs(r["beta_str_used"] - 0.8748) < 1e-4
