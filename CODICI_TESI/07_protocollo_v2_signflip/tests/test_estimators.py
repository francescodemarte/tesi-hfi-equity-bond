"""Test di estimators.py — TDD stretto, target ANALITICI (non tautologici).

Tre stimatori del comovimento equity-bond:
  - b_OLS = Cov/Var sulle finestre evento;
  - b_H   = ΔCov/ΔVar (Rigobon-Sack a due regimi: evento vs controllo);
  - b_L   = Cov(Zc, re*rb)/Cov(Zc, rb**2) (Lewbel, eteroschedasticità).
Tutti i momenti con ddof=1 (varianza/covarianza campionaria).
"""
import numpy as np
import pytest

import estimators


# --- b_ols --------------------------------------------------------------

def test_b_ols_exact_two_when_re_is_double_rb():
    # se r_e = 2*r_b (r_b non costante) → b_ols == 2.0 esatto
    rb = np.array([1.0, 2.0, 4.0, 8.0, 3.0])
    re = 2.0 * rb
    assert estimators.b_ols(re, rb) == pytest.approx(2.0)


def test_b_ols_hand_computed():
    # re = [1,2,3,4], rb = [1,1,2,2]
    # mean rb = 1.5; dev_rb = [-.5,-.5,.5,.5]; var = (4*.25)/3 = 1/3
    # mean re = 2.5; dev_re = [-1.5,-.5,.5,1.5]
    # cov = [(-1.5)(-.5)+(-.5)(-.5)+(.5)(.5)+(1.5)(.5)]/3
    #     = [.75+.25+.25+.75]/3 = 2/3
    # b_ols = (2/3)/(1/3) = 2.0
    re = np.array([1.0, 2.0, 3.0, 4.0])
    rb = np.array([1.0, 1.0, 2.0, 2.0])
    assert estimators.b_ols(re, rb) == pytest.approx(2.0)


# --- rs_two_regime ------------------------------------------------------

def test_rs_two_regime_hand_computed():
    # Evento:  re_e = rb_e = [1,2,3,4]
    #   var_e = 5/3, cov_e = 5/3, b_OLS = 1.0
    # Controllo: re_c = [1,1,2,2], rb_c = [1,2,1,2]
    #   var_c = 1/3, cov_c = 0
    # dVar = 5/3 - 1/3 = 4/3; dCov = 5/3 - 0 = 5/3
    # b_H = (5/3)/(4/3) = 1.25; r_hat = (5/3)/(1/3) = 5.0
    re_e = np.array([1.0, 2.0, 3.0, 4.0])
    rb_e = np.array([1.0, 2.0, 3.0, 4.0])
    re_c = np.array([1.0, 1.0, 2.0, 2.0])
    rb_c = np.array([1.0, 2.0, 1.0, 2.0])

    out = estimators.rs_two_regime(re_e, rb_e, re_c, rb_c)

    assert out["var_e"] == pytest.approx(5.0 / 3.0)
    assert out["var_c"] == pytest.approx(1.0 / 3.0)
    assert out["dVar"] == pytest.approx(4.0 / 3.0)
    assert out["cov_e"] == pytest.approx(5.0 / 3.0)
    assert out["cov_c"] == pytest.approx(0.0)
    assert out["dCov"] == pytest.approx(5.0 / 3.0)
    assert out["b_OLS"] == pytest.approx(1.0)
    assert out["b_H"] == pytest.approx(1.25)
    assert out["r_hat"] == pytest.approx(5.0)


def test_rs_two_regime_keys_exact():
    out = estimators.rs_two_regime([1.0, 2.0, 3.0], [3.0, 2.0, 1.0],
                                   [1.0, 0.0, 2.0], [0.0, 1.0, 2.0])
    assert set(out) == {"var_e", "var_c", "dVar", "cov_e", "cov_c",
                        "dCov", "b_OLS", "b_H", "r_hat"}


def test_rs_two_regime_b_H_nan_when_dVar_zero():
    # var_e == var_c (stesso rb) → dVar ≈ 0 → b_H = nan
    rb = np.array([1.0, 2.0, 3.0, 4.0])
    re_e = np.array([2.0, 1.0, 4.0, 3.0])
    re_c = np.array([0.0, 1.0, 2.0, 9.0])
    out = estimators.rs_two_regime(re_e, rb, re_c, rb)
    assert out["dVar"] == pytest.approx(0.0)
    assert np.isnan(out["b_H"])


def test_rs_two_regime_r_hat_nan_when_var_c_nonpositive():
    rb_c = np.array([5.0, 5.0, 5.0, 5.0])  # var_c = 0
    out = estimators.rs_two_regime([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0],
                                   [1.0, 2.0, 3.0, 4.0], rb_c)
    assert np.isnan(out["r_hat"])


# --- lewbel -------------------------------------------------------------

def test_lewbel_hand_computed():
    # Z = [1,2,3,4] → Zc = [-1.5,-.5,.5,1.5]
    # rb = [1,2,3,4]; rb**2 = [1,4,9,16], mean 7.5; dev = [-6.5,-3.5,1.5,8.5]
    #   tau = [( -1.5)(-6.5)+(-.5)(-3.5)+(.5)(1.5)+(1.5)(8.5)]/3
    #       = [9.75+1.75+.75+12.75]/3 = 25/3
    # re = [2,1,1,2]; re*rb = [2,2,3,8], mean 3.75; dev = [-1.75,-1.75,-.75,4.25]
    #   cov_Zeb = [(-1.5)(-1.75)+(-.5)(-1.75)+(.5)(-.75)+(1.5)(4.25)]/3
    #           = [2.625+.875-.375+6.375]/3 = 9.5/3
    # b_L = (9.5/3)/(25/3) = 9.5/25 = 0.38
    Z = np.array([1.0, 2.0, 3.0, 4.0])
    re = np.array([2.0, 1.0, 1.0, 2.0])
    rb = np.array([1.0, 2.0, 3.0, 4.0])

    out = estimators.lewbel(Z, re, rb)

    assert set(out) == {"tau", "cov_Zeb", "b_L"}
    assert out["tau"] == pytest.approx(25.0 / 3.0)
    assert out["cov_Zeb"] == pytest.approx(9.5 / 3.0)
    assert out["b_L"] == pytest.approx(0.38)


def test_lewbel_b_L_nan_when_tau_zero():
    # rb**2 costante → Cov(Zc, rb**2) = 0 → tau ≈ 0 → b_L = nan
    Z = np.array([1.0, 2.0, 3.0, 4.0])
    re = np.array([1.0, 2.0, 3.0, 4.0])
    rb = np.array([1.0, -1.0, 1.0, -1.0])  # rb**2 = [1,1,1,1] costante
    out = estimators.lewbel(Z, re, rb)
    assert out["tau"] == pytest.approx(0.0)
    assert np.isnan(out["b_L"])
