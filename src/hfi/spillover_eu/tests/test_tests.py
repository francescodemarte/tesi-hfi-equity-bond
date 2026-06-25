"""Test tests.py (Stadio 2): T-H1..T-H4 + Benjamini–Yekutieli locale.

Per evitare lo scontro col nome del file e di pytest, nel codice il modulo
si chiama `tests_h` (rinomina necessaria) — NB: file di test rimane test_tests.
"""
import numpy as np
import pytest

import config
import tests_h as th
import regression as reg


def _toy_dataset(rng, n=500, gamma=0.5, delta=-0.3):
    Z_mp = rng.standard_normal(n)
    Z_cbi = rng.standard_normal(n)
    x = rng.standard_normal(n)
    u = rng.standard_normal(n) * 0.3
    y = gamma * Z_mp + delta * Z_cbi + 0.1 * x + u
    X = np.column_stack([Z_mp, Z_cbi, x])
    return X, y, ("Z_mp", "Z_cbi", "x")


# --- T-H1 (γ_yB > 0, unilaterale, p < 0.05 SENZA correzione) ---------------

def test_T_H1_rejects_for_positive_gamma_yB():
    rng = np.random.default_rng(1)
    X, y, names = _toy_dataset(rng, n=2000, gamma=+0.7, delta=0.0)
    fit = reg.ols_hc(y, X, names=names)
    out = th.T_H1(fit, coef="Z_mp", alpha=config.T_H1_ALPHA)
    assert out["reject"] is True
    assert out["side"] == "greater"
    assert out["p_one_sided"] < config.T_H1_ALPHA


def test_T_H1_does_not_reject_negative_or_zero_gamma():
    rng = np.random.default_rng(2)
    # Caso 1: gamma fortemente NEGATIVO → H1 (unilaterale >0) non rigetta
    X, y, names = _toy_dataset(rng, n=2000, gamma=-0.7, delta=0.0)
    fit = reg.ols_hc(y, X, names=names)
    out = th.T_H1(fit, coef="Z_mp")
    assert out["reject"] is False
    # Caso 2: gamma ≈ 0 → non rigetta
    rng2 = np.random.default_rng(22)
    X, y, names = _toy_dataset(rng2, n=2000, gamma=0.0, delta=0.0)
    fit = reg.ols_hc(y, X, names=names)
    out = th.T_H1(fit, coef="Z_mp")
    assert out["reject"] is False


# --- T-H2 (γ_rES < 0, unilaterale) -----------------------------------------

def test_T_H2_rejects_when_gamma_negative_enough():
    rng = np.random.default_rng(3)
    X, y, names = _toy_dataset(rng, n=2000, gamma=-0.7, delta=0.0)
    fit = reg.ols_hc(y, X, names=names)
    out = th.T_H2(fit, coef="Z_mp")
    assert out["reject_uncorrected_alpha05"] is True
    assert out["side"] == "less"


def test_T_H2_does_not_reject_when_positive():
    rng = np.random.default_rng(4)
    X, y, names = _toy_dataset(rng, n=2000, gamma=+0.7, delta=0.0)
    fit = reg.ols_hc(y, X, names=names)
    out = th.T_H2(fit, coef="Z_mp")
    assert out["reject_uncorrected_alpha05"] is False


# --- T-H3 (γ_sp > 0, unilaterale, secondaria BY) ---------------------------

def test_T_H3_rejects_for_positive_gamma():
    rng = np.random.default_rng(5)
    X, y, names = _toy_dataset(rng, n=2000, gamma=+0.6, delta=0.0)
    fit = reg.ols_hc(y, X, names=names)
    out = th.T_H3(fit, coef="Z_mp")
    assert out["reject_uncorrected_alpha05"] is True
    assert out["side"] == "greater"


# --- T-H4: attribuzione via Wald su (γ − δ) o rapporto |γ|/|δ| -------------

def test_T_H4_wald_difference_rejects_when_gamma_and_delta_differ():
    rng = np.random.default_rng(6)
    # qui γ=+0.7, δ=-0.5 → differenza grande positiva → rigetto H0:γ-δ=0
    X, y, names = _toy_dataset(rng, n=2000, gamma=+0.7, delta=-0.5)
    fit = reg.ols_hc(y, X, names=names)
    out = th.T_H4(fit, coef_mp="Z_mp", coef_cbi="Z_cbi")
    assert out["diff"] == pytest.approx(1.2, abs=0.1)
    assert out["p_two_sided"] < 0.01


def test_T_H4_does_not_reject_when_gamma_equals_delta():
    rng = np.random.default_rng(7)
    X, y, names = _toy_dataset(rng, n=2000, gamma=+0.5, delta=+0.5)
    fit = reg.ols_hc(y, X, names=names)
    out = th.T_H4(fit, coef_mp="Z_mp", coef_cbi="Z_cbi")
    assert out["p_two_sided"] > 0.05


# --- Benjamini–Yekutieli locale (oracolo indipendente sulle soglie) --------

def test_BY_rejects_only_below_threshold_with_m3():
    # m=3, q=0.10, c_3 = 1 + 1/2 + 1/3 = 11/6
    # soglie rank i: i*q/(m*c_3) → 1: 0.10/(3*11/6)=0.01818..., 2: 0.0363..., 3: 0.0545...
    # p=[0.04, 0.01, 0.5] → step-up: ordino [0.01, 0.04, 0.5], rank max che passa = 1 (0.01<0.01818)
    out = th.benjamini_yekutieli(p=[0.04, 0.01, 0.5], q=0.10, m=3)
    assert list(out["rejected"]) == [False, True, False]
    assert out["m"] == 3


def test_BY_m_is_fixed_a_priori_even_if_some_p_missing():
    # In hierarchy: anche se H4 non viene computato (es. gamma non significativo),
    # m resta 3. Lo simula passando p=1.0 per quel test.
    out = th.benjamini_yekutieli(p=[0.001, 0.5, 1.0], q=0.10, m=3)
    assert list(out["rejected"]) == [True, False, False]
    assert out["m"] == 3


# --- Pipeline integrata: hierarchy H1 + BY su {H2,H3,H4} -------------------

def test_hierarchy_reports_H1_primary_and_BY_secondary():
    rng = np.random.default_rng(9)
    # Costruisco un setup in cui solo H1 rigetta (DGP solo MP, niente effetti
    # negativi sull'equity nel SETUP minimo).
    X, y, names = _toy_dataset(rng, n=2000, gamma=+0.7, delta=0.0)
    fit = reg.ols_hc(y, X, names=names)
    p_h2 = th.T_H2(fit, coef="Z_mp")["p_one_sided"]
    p_h3 = th.T_H3(fit, coef="Z_mp")["p_one_sided"]
    p_h4 = th.T_H4(fit, coef_mp="Z_mp", coef_cbi="Z_cbi")["p_two_sided"]
    out = th.hierarchy(
        h1=th.T_H1(fit, coef="Z_mp"),
        h2={"p": p_h2}, h3={"p": p_h3}, h4={"p": p_h4},
        q=config.BY_Q,
    )
    assert out["m_secondary"] == 3
    assert out["h1_reject"] is True       # γ positivo → H1 primaria rigetta
    # H2 NON rigetta (γ positivo, H2 cerca γ<0)
    assert out["secondary"]["H2"] is False
