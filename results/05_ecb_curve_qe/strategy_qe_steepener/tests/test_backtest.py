"""test_backtest.py — Sanity tests del backtest QE-Steepener Bund 2-10.

Tre test verificano:
 (a) la formula del P&L per evento e' coerente con la pre-registrazione
     (slope_change = DE10Y - DE2Y in bp, pnl_gross = sign * size *
     slope_change, sign = +1 se QE>0);
 (b) la riproducibilita' del bootstrap con seed fisso (B=200 per
     velocita' nel test; due chiamate con stesso seed devono dare
     output identico bit-per-bit);
 (c) la coerenza del segno con la monotonicita' beta_QE: per ogni
     evento il segno della strategia coincide con sign(QE), che e' la
     specifica pre-registrata.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PARENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PARENT))
import extract_qe_steepener_backtest as bt  # noqa: E402


def _build_synthetic_df() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    n = 50
    dates = pd.date_range("2015-01-01", periods=n, freq="60D")
    qe = rng.normal(0, 1, size=n)
    de2 = rng.normal(0, 1, size=n)
    de10 = de2 + 0.5 * qe + rng.normal(0, 0.5, size=n)
    return pd.DataFrame(
        {"date": dates, "Target": 0.0, "Path": 0.0, "QE": qe,
         "DE2Y": de2, "DE10Y": de10, "year": dates.year}
    )


def test_pnl_formula_consistent_with_pre_registration():
    """Test (a). Verifica formula P&L per evento.

    Costruisce 5 eventi sintetici controllati, calcola pnl_gross e
    confronta col risultato atteso dalla formula esplicita.
    """
    df = pd.DataFrame({
        "date": pd.to_datetime(
            ["2020-01-01", "2020-02-01", "2020-03-01",
             "2020-04-01", "2020-05-01"]
        ),
        "Target": [0.0] * 5,
        "Path": [0.0] * 5,
        "QE": [1.0, -1.0, 2.0, -2.0, 0.5],
        "DE2Y": [0.0, 1.0, 2.0, -1.0, 0.5],
        "DE10Y": [2.0, 0.0, 5.0, -3.0, 1.0],
        "year": [2020] * 5,
    })

    df_sig = bt.compute_signal(df)
    df_pnl = bt.compute_pnl(df_sig, cost_per_leg_bp=0.0)

    expected_signs = [+1, -1, +1, -1, +1]
    expected_slope = [2.0, -1.0, 3.0, -2.0, 0.5]
    expected_gross = [
        s * sl for s, sl in zip(expected_signs, expected_slope)
    ]

    np.testing.assert_array_equal(df_pnl["sign"].values, expected_signs)
    np.testing.assert_allclose(
        df_pnl["slope_change_bp"].values, expected_slope, rtol=1e-12
    )
    np.testing.assert_allclose(
        df_pnl["pnl_gross_binary"].values, expected_gross, rtol=1e-12
    )


def test_bootstrap_deterministic_with_fixed_seed():
    """Test (b). Stesso seed → stesso output bit-per-bit; due seed
    diversi su un pnl ricco di variabilita' devono produrre intervalli
    non-identici (sanity check sul ricampionamento, non sull'algoritmo
    della distribuzione)."""
    rng = np.random.default_rng(7)
    pnl = rng.normal(0.5, 1.5, size=80)
    years = np.repeat(np.arange(2010, 2026), 5)

    seed = 12345
    out1 = bt.cluster_bootstrap_sharpe(pnl, years, B=200, seed=seed)
    out2 = bt.cluster_bootstrap_sharpe(pnl, years, B=200, seed=seed)

    # Stesso seed ⇒ identita' bit-per-bit
    assert out1["ic95_lo"] == out2["ic95_lo"]
    assert out1["ic95_hi"] == out2["ic95_hi"]
    assert out1["p_one_sided_mean_gt0"] == out2["p_one_sided_mean_gt0"]

    # Seed diverso ⇒ almeno una metrica differente (su pnl ricco)
    out3 = bt.cluster_bootstrap_sharpe(pnl, years, B=200, seed=seed + 1)
    assert (
        out1["ic95_lo"] != out3["ic95_lo"]
        or out1["ic95_hi"] != out3["ic95_hi"]
        or out1["p_one_sided_mean_gt0"] != out3["p_one_sided_mean_gt0"]
    ), "Bootstrap su seed diversi non puo' dare gli stessi 3 valori"


def test_sign_matches_beta_qe_monotonicity():
    """Test (c). Il segno della strategia coincide con sign(QE).

    La monotonicita' beta_QE_10Y > beta_QE_2Y giustifica steepener su
    QE>0. Il codice deve riflettere esattamente questa pre-registrazione.
    """
    df = _build_synthetic_df()
    df_sig = bt.compute_signal(df)
    for _, row in df_sig.iterrows():
        if row["QE"] > 0:
            assert row["sign"] == +1, (
                f"QE={row['QE']:+.4f} > 0 ⇒ atteso steepener (+1), "
                f"trovato {row['sign']}"
            )
        else:
            assert row["sign"] == -1, (
                f"QE={row['QE']:+.4f} ≤ 0 ⇒ atteso flattener (-1), "
                f"trovato {row['sign']}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
