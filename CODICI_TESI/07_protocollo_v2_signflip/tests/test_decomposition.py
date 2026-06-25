"""Test di decomposition.py — TDD stretto, ORACOLO INDIPENDENTE.

Decomposizione in canali a frequenza GIORNALIERA (daily): evidenza
SECONDARIA, NON la frequenza-evento dello stimatore principale b_H.

Tutti i valori attesi sono calcolati a mano (aritmetica chiusa nei
commenti), MAI tramite una seconda chiamata della funzione testata.
"""
import numpy as np
import pytest

import decomposition


# --- bond_channels ------------------------------------------------------

def test_bond_channels_hand_computed():
    # r_b=0.01, delta_r_real=0.001, delta_pi=0.0005, d_bond=8.5
    # c_b_rate = -0.001 * 8.5      = -0.0085
    # c_b_pi   = -0.0005 * 8.5     = -0.00425
    # c_b_res  = 0.01 - (-0.0085) - (-0.00425)
    #          = 0.01 + 0.0085 + 0.00425 = 0.02275
    out = decomposition.bond_channels(r_b=0.01, delta_r_real=0.001,
                                      delta_pi=0.0005, d_bond=8.5)
    assert set(out) == {"c_b_rate", "c_b_pi", "c_b_res"}
    assert out["c_b_rate"] == pytest.approx(-0.0085)
    assert out["c_b_pi"] == pytest.approx(-0.00425)
    assert out["c_b_res"] == pytest.approx(0.02275)


def test_bond_channels_residual_is_additive_identity():
    # Indipendentemente dai valori, deve valere
    #   r_b == c_b_rate + c_b_pi + c_b_res
    # (è la proprietà di decomposizione esatta dei canali bond).
    # r_b=-0.003, delta_r_real=0.002, delta_pi=-0.001, d_bond=6.0
    # c_b_rate = -0.002*6 = -0.012
    # c_b_pi   = -(-0.001)*6 = 0.006
    # c_b_res  = -0.003 - (-0.012) - 0.006 = -0.003 +0.012 -0.006 = 0.003
    out = decomposition.bond_channels(r_b=-0.003, delta_r_real=0.002,
                                      delta_pi=-0.001, d_bond=6.0)
    assert out["c_b_rate"] == pytest.approx(-0.012)
    assert out["c_b_pi"] == pytest.approx(0.006)
    assert out["c_b_res"] == pytest.approx(0.003)
    assert (out["c_b_rate"] + out["c_b_pi"] + out["c_b_res"]
            == pytest.approx(-0.003))


# --- equity_partial_duration -------------------------------------------

def test_equity_partial_duration_hand_computed():
    # weights=[0.5,0.3,0.2], horizons=[1,2,3]
    # num = 0.5*1 + 0.3*2 + 0.2*3 = 0.5 + 0.6 + 0.6 = 1.7
    # den = 0.5 + 0.3 + 0.2 = 1.0
    # -> 1.7 / 1.0 = 1.7
    val = decomposition.equity_partial_duration([0.5, 0.3, 0.2], [1, 2, 3])
    assert val == pytest.approx(1.7)


def test_equity_partial_duration_nan_safe_weight():
    # un peso NaN va ignorato via np.nansum.
    # weights=[0.5, nan, 0.2], horizons=[1, 2, 3]
    # num = 0.5*1 + (ignorato) + 0.2*3 = 0.5 + 0.6 = 1.1
    # den = 0.5 + 0.2 = 0.7
    # -> 1.1 / 0.7 = 1.5714285714...
    val = decomposition.equity_partial_duration([0.5, np.nan, 0.2], [1, 2, 3])
    assert val == pytest.approx(1.1 / 0.7)


def test_equity_partial_duration_nan_when_weights_sum_nonpositive():
    # somma pesi == 0 -> nan
    assert np.isnan(decomposition.equity_partial_duration([0.0, 0.0], [1, 2]))
    # somma pesi < 0 -> nan
    assert np.isnan(decomposition.equity_partial_duration([-0.4, -0.6],
                                                          [1, 2]))


# --- equity_channels ----------------------------------------------------

def test_equity_channels_hand_computed():
    # r_e=0.02, delta_r_real=0.001, duration_partial=5.0
    # c_e_rate = -0.001 * 5.0 = -0.005
    # c_e_res  = 0.02 - (-0.005) = 0.025
    out = decomposition.equity_channels(r_e=0.02, delta_r_real=0.001,
                                        duration_partial=5.0)
    assert set(out) == {"c_e_rate", "c_e_res"}
    assert out["c_e_rate"] == pytest.approx(-0.005)
    assert out["c_e_res"] == pytest.approx(0.025)


def test_equity_channels_residual_is_additive_identity():
    # r_e == c_e_rate + c_e_res, per costruzione.
    # r_e=-0.01, delta_r_real=-0.002, duration_partial=4.0
    # c_e_rate = -(-0.002)*4 = 0.008
    # c_e_res  = -0.01 - 0.008 = -0.018
    out = decomposition.equity_channels(r_e=-0.01, delta_r_real=-0.002,
                                        duration_partial=4.0)
    assert out["c_e_rate"] == pytest.approx(0.008)
    assert out["c_e_res"] == pytest.approx(-0.018)
    assert out["c_e_rate"] + out["c_e_res"] == pytest.approx(-0.01)


# --- twin_cov -----------------------------------------------------------

def test_twin_cov_hand_computed():
    # c_e_res = [1,2,3,4], c_b_res = [2,4,6,8] = 2*c_e_res
    # mean_e=2.5 dev_e=[-1.5,-.5,.5,1.5]
    # mean_b=5.0 dev_b=[-3,-1,1,3]
    # cov = [(-1.5)(-3)+(-.5)(-1)+(.5)(1)+(1.5)(3)]/3
    #     = [4.5 + 0.5 + 0.5 + 4.5]/3 = 10/3
    ce = np.array([1.0, 2.0, 3.0, 4.0])
    cb = np.array([2.0, 4.0, 6.0, 8.0])
    assert decomposition.twin_cov(ce, cb) == pytest.approx(10.0 / 3.0)


def test_twin_cov_negative_relationship():
    # c_e_res = [1,2,3,4], c_b_res = [4,3,2,1]
    # dev_e=[-1.5,-.5,.5,1.5]; mean_b=2.5 dev_b=[1.5,.5,-.5,-1.5]
    # cov = [(-1.5)(1.5)+(-.5)(.5)+(.5)(-.5)+(1.5)(-1.5)]/3
    #     = [-2.25 -0.25 -0.25 -2.25]/3 = -5/3
    ce = np.array([1.0, 2.0, 3.0, 4.0])
    cb = np.array([4.0, 3.0, 2.0, 1.0])
    assert decomposition.twin_cov(ce, cb) == pytest.approx(-5.0 / 3.0)


# --- coerenza vettoriale ------------------------------------------------

def test_bond_channels_vectorized_elementwise():
    # input np.array -> output np.array elemento-per-elemento.
    r_b = np.array([0.01, -0.003])
    dr = np.array([0.001, 0.002])
    dpi = np.array([0.0005, -0.001])
    d_bond = np.array([8.5, 6.0])
    out = decomposition.bond_channels(r_b, dr, dpi, d_bond)
    # Elemento 0: come test_bond_channels_hand_computed
    # Elemento 1: come test_bond_channels_residual_is_additive_identity
    assert isinstance(out["c_b_rate"], np.ndarray)
    np.testing.assert_allclose(out["c_b_rate"], [-0.0085, -0.012])
    np.testing.assert_allclose(out["c_b_pi"], [-0.00425, 0.006])
    np.testing.assert_allclose(out["c_b_res"], [0.02275, 0.003])


def test_equity_channels_vectorized_elementwise():
    r_e = np.array([0.02, -0.01])
    dr = np.array([0.001, -0.002])
    dp = np.array([5.0, 4.0])
    out = decomposition.equity_channels(r_e, dr, dp)
    assert isinstance(out["c_e_rate"], np.ndarray)
    np.testing.assert_allclose(out["c_e_rate"], [-0.005, 0.008])
    np.testing.assert_allclose(out["c_e_res"], [0.025, -0.018])
