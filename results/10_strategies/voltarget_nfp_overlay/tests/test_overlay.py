"""Tests pytest per Vol-target NFP overlay."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT))


def test_seed_determinism():
    """Stesso MASTER_SEED + nome → stesso seed int."""
    import extract_voltarget_backtest as m
    s1 = m.seed_for("voltarget_nfp_overlay")
    s2 = m.seed_for("voltarget_nfp_overlay")
    assert s1 == s2
    assert s1 != m.seed_for("other_name")


def test_size_factor_formula():
    """size factor = 1/sqrt(r_hat) deterministico."""
    import math
    import extract_voltarget_backtest as m
    # Carica r_hat e ricalcola
    import json
    r = json.loads((m.BETA_H_FILE).read_text())
    r_hat = None
    for c in r["robust_cells"]:
        if c["cell"] == "NFP/neg":
            r_hat = c["r_hat"]
            break
    assert r_hat is not None
    expected_factor = 1.0 / math.sqrt(r_hat)
    # Confronto con il numero atteso ~0.2549
    assert abs(expected_factor - 0.2549) < 0.001
    # Conferma magnitudine
    assert expected_factor < 0.30
    assert expected_factor > 0.20


def test_filter_only_nfp_only_dichiarato():
    """Il filtro ex-post (overlay SOLO su NFP) è dichiarato esplicitamente nei file
    di output. Test che legge il backtest e verifica il dichiarato."""
    p = PARENT / "backtest_combined.json"
    if not p.exists():
        import pytest
        pytest.skip("backtest_combined.json non presente")
    r = json.loads(p.read_text())
    # Filtro ex-post must be declared
    assert "filter_ex_post_declared" in r
    txt = r["filter_ex_post_declared"]
    assert "NFP" in txt
    assert "Check 1" in txt or "bridge" in txt
    # Strategie devono includere baseline e overlay
    assert "A_baseline_long_bond" in r["strategies"]
    assert "B_vol_target_NFP_only_bond" in r["strategies"]
    assert "C_baseline_60_40" in r["strategies"]
    assert "D_60_40_vol_target_NFP_only" in r["strategies"]
