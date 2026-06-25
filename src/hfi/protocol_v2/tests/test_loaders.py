"""Test loaders: m_e_pca (PC1 money-market intraday), equity_duration_partial.

ECB LEVEL (Excel Altavilla foglio interno) è dichiarato GATED — un loader
fittizio che solleva è registrato; l'esecutore lo cabla quando il file è
autorizzato e congelato.
"""
import numpy as np
import pandas as pd
import pytest

import loaders


# --- m_e_pca: prima componente principale delle variazioni money-market < 1y

def test_m_e_pca_returns_sign_aligned_first_component():
    # Costruisco 3 serie con un comune fattore + rumore: la PC1 ≈ fattore.
    rng = np.random.default_rng(0)
    n = 200
    factor = rng.standard_normal(n)
    M = np.column_stack([factor + 0.1 * rng.standard_normal(n),
                         factor + 0.1 * rng.standard_normal(n),
                         factor + 0.1 * rng.standard_normal(n)])
    pc1 = loaders.m_e_pca(M)
    # correlazione |.| con il fattore deve essere alta
    assert abs(np.corrcoef(pc1, factor)[0, 1]) > 0.95
    # convenzione di segno: correlazione positiva col fattore comune dei tassi
    # (i loading sono tutti positivi per costruzione, segno della PC1 fissato a +)
    assert np.corrcoef(pc1, factor)[0, 1] > 0


def test_m_e_pca_zero_when_constant_inputs():
    M = np.tile(np.array([1.0, 2.0, 3.0]), (50, 1))   # nessuna variazione → varianza 0
    pc1 = loaders.m_e_pca(M)
    assert np.allclose(pc1, 0.0)


# --- equity_duration_partial: ∑ w·h / ∑ w (peso normalizzato), nan-safe

def test_equity_duration_partial_matches_hand_computation():
    w = np.array([0.5, 0.3, 0.2])
    h = np.array([1.0, 2.0, 3.0])
    # (0.5*1 + 0.3*2 + 0.2*3) / 1 = 1.7
    assert loaders.equity_duration_partial(w, h) == pytest.approx(1.7)


def test_equity_duration_partial_handles_nan_weights():
    w = np.array([0.5, np.nan, 0.2])
    h = np.array([1.0, 2.0, 3.0])
    # (0.5*1 + 0.2*3) / (0.5+0.2) = 1.1/0.7
    assert loaders.equity_duration_partial(w, h) == pytest.approx(1.1 / 0.7)


def test_equity_duration_partial_nan_when_zero_weights():
    assert np.isnan(loaders.equity_duration_partial(np.array([0.0, 0.0]),
                                                    np.array([1.0, 2.0])))


# --- ECB LEVEL: GATED (foglio Excel non-tabulare, autorizzazione separata)

def test_ecb_level_loader_is_gated_until_authorized(tmp_path):
    fake_xlsx = tmp_path / "altavilla.xlsx"
    fake_xlsx.write_bytes(b"not a real xlsx")
    with pytest.raises(NotImplementedError):
        loaders.load_ecb_level(fake_xlsx)
