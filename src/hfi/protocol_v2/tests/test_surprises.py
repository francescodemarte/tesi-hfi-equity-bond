"""Test di surprises.py (C0.4) — mapping Z/s e gate copertura/varianza.

Vincolo congelato: MAI ΔT5YIE (o altra componente del bond) come Z o s.
"""
import numpy as np
import pytest

import config
import surprises


def test_surprise_source_per_type():
    assert surprises.surprise_source("FOMC") == "m_e"
    assert surprises.surprise_source("ECB") == "LEVEL"
    assert surprises.surprise_source("CPI") == "actual_vs_consensus"
    assert surprises.surprise_source("NFP") == "actual_vs_consensus"


def test_dt5yie_forbidden_as_source():
    with pytest.raises(ValueError):
        surprises.validate_source("dT5YIE")
    with pytest.raises(ValueError):
        surprises.validate_source("T5YIE")
    with pytest.raises(ValueError):
        surprises.validate_source("breakeven")
    # le sorgenti dichiarate per i 4 tipi sono ammesse
    for t in ("FOMC", "ECB", "CPI", "NFP"):
        assert surprises.validate_source(surprises.surprise_source(t))


def test_gate_feedable_when_enough_valid_and_variance():
    rng = np.random.default_rng(0)
    vals = rng.standard_normal(config.N_MIN + 5)
    g = surprises.coverage_variance_gate(vals)
    assert g["n_valid"] == config.N_MIN + 5
    assert g["variance"] > 0
    assert g["feedable"] is True


def test_gate_not_feedable_below_nmin():
    vals = np.arange(config.N_MIN - 1, dtype=float)  # 29 < n_min
    g = surprises.coverage_variance_gate(vals)
    assert g["feedable"] is False


def test_gate_not_feedable_degenerate_variance():
    vals = np.ones(config.N_MIN + 5)  # varianza 0
    g = surprises.coverage_variance_gate(vals)
    assert g["variance"] == 0.0
    assert g["feedable"] is False


def test_surprise_source_self_validates(monkeypatch):
    # #1: se la mappa fosse avvelenata con una sorgente vietata, surprise_source SOLLEVA
    # (la guardia è ora sul percorso canonico, non solo nei test).
    monkeypatch.setitem(surprises.SURPRISE_SOURCE, "NFP", "dT5YIE")
    with pytest.raises(ValueError):
        surprises.surprise_source("NFP")


def test_gate_counts_nan_in_coverage():
    vals = [1.0, 2.0, np.nan, 4.0]
    g = surprises.coverage_variance_gate(vals)
    assert g["n_valid"] == 3
    assert g["n_total"] == 4
    assert g["coverage"] == pytest.approx(0.75)
