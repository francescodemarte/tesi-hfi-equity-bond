"""Test di weakiv.py (R2, R5, T1) — TDD stretto, kernel delicati.

- mop_critical_value: cv MOP CALCOLATO (K=1, size worst-case 10%, nominale 5%),
  validato contro il valore pubblicato ≈23.1; NON lo Stock–Yogo omoschedastico
  (16.38); monotòno decrescente nella tolleranza di size.
- ar_set: insieme di Anderson–Rubin per inversione di g(β)=ΔCov−β·ΔVar con se
  da bootstrap clusterizzato; strumento forte → insieme stretto attorno a b_H;
  strumento debolissimo → insieme illimitato sui bordi della griglia (mai troncato).
"""
import numpy as np
import pytest

import config
import weakiv


def _grid():
    return np.arange(config.AR_BETA_LOW,
                     config.AR_BETA_HIGH + config.AR_STEP / 2,
                     config.AR_STEP)


# --- cv MOP (R5) -------------------------------------------------------

def test_mop_cv_k1_size10_about_23():
    cv = weakiv.mop_critical_value(K=1, worst_case_size=0.10, nominal=0.05)
    assert cv == pytest.approx(23.1, abs=1.5)   # valore pubblicato MOP per K=1


def test_mop_cv_not_stock_yogo():
    cv = weakiv.mop_critical_value(K=1, worst_case_size=0.10, nominal=0.05)
    assert abs(cv - 16.38) > 2.0                # NON il valore omoschedastico


def test_mop_cv_monotone_decreasing_in_size():
    cv10 = weakiv.mop_critical_value(K=1, worst_case_size=0.10, nominal=0.05)
    cv20 = weakiv.mop_critical_value(K=1, worst_case_size=0.20, nominal=0.05)
    assert cv20 < cv10                          # size maggiore → soglia minore


def test_mop_effective_f_ratio():
    # F_eff = (ΔVar)^2 / V̂
    assert weakiv.mop_effective_f(2.0, 0.5) == pytest.approx(8.0)   # 2^2 / 0.5
    assert weakiv.mop_effective_f(3.0, 9.0) == pytest.approx(1.0)   # 3^2 / 9


# --- AR set (R2) -------------------------------------------------------

def test_ar_set_strong_instrument_tight_around_bh():
    rng = config.make_rng("ar_strong")
    dCov_hat, dVar_hat = 2.0, 1.0      # b_H = 2
    dCov_bs = dCov_hat + 0.05 * rng.standard_normal(3000)
    dVar_bs = dVar_hat + 0.02 * rng.standard_normal(3000)
    out = weakiv.ar_set(dCov_hat, dVar_hat, dCov_bs, dVar_bs, _grid(), z_crit=1.96)
    assert not out["empty"]
    assert not out["unbounded_low"] and not out["unbounded_high"]
    assert out["low"] < 2.0 < out["high"]
    assert (out["high"] - out["low"]) < 1.0


def test_ar_set_weak_instrument_unbounded():
    rng = config.make_rng("ar_weak")
    dCov_hat, dVar_hat = 0.0, 0.0      # strumento inerte
    dCov_bs = 0.01 * rng.standard_normal(3000)
    dVar_bs = 0.01 * rng.standard_normal(3000)
    out = weakiv.ar_set(dCov_hat, dVar_hat, dCov_bs, dVar_bs, _grid(), z_crit=1.96)
    assert out["unbounded_low"] and out["unbounded_high"]


# --- AR per inferenza T4/T5 (E2) --------------------------------------

def test_ar_pvalue_one_at_point_estimate():
    # proprietà nota: in β=b_H=ΔCov/ΔVar si ha g(β)=0 → z=0 → p=1
    rng = config.make_rng("arp")
    dCov_hat, dVar_hat = 2.0, 1.0   # b_H = 2
    dCov_bs = dCov_hat + 0.1 * rng.standard_normal(2000)
    dVar_bs = dVar_hat + 0.05 * rng.standard_normal(2000)
    p = weakiv.ar_pvalue(dCov_hat, dVar_hat, dCov_bs, dVar_bs, beta0=2.0)
    assert p == pytest.approx(1.0, abs=1e-9)


def test_ar_pvalue_matches_closed_form_z():
    # oracolo chiuso indipendente: z = g/se, p = 2(1-Φ(|z|))
    from scipy.stats import norm
    rng = config.make_rng("arp2")
    dCov_hat, dVar_hat, beta0 = 2.0, 0.3, 0.0
    dCov_bs = dCov_hat + 0.4 * rng.standard_normal(5000)
    dVar_bs = dVar_hat + 0.1 * rng.standard_normal(5000)
    g = dCov_hat - beta0 * dVar_hat
    se = np.std(dCov_bs - beta0 * dVar_bs, ddof=1)
    p_oracle = 2 * (1 - norm.cdf(abs(g / se)))
    assert weakiv.ar_pvalue(dCov_hat, dVar_hat, dCov_bs, dVar_bs, beta0) == pytest.approx(p_oracle)


def test_ar_one_side():
    assert weakiv.ar_one_side({"empty": False, "low": 0.5, "high": 2.0,
                               "unbounded_low": False, "unbounded_high": False}) == "+"
    assert weakiv.ar_one_side({"empty": False, "low": -2.0, "high": -0.5,
                               "unbounded_low": False, "unbounded_high": False}) == "-"
    assert weakiv.ar_one_side({"empty": False, "low": -1.0, "high": 1.0,
                               "unbounded_low": False, "unbounded_high": False}) is None
    # se illimitato verso il basso, include negativi → non "interamente +"
    assert weakiv.ar_one_side({"empty": False, "low": -3.0, "high": 2.0,
                               "unbounded_low": True, "unbounded_high": False}) is None
    assert weakiv.ar_one_side({"empty": True, "low": None, "high": None,
                               "unbounded_low": False, "unbounded_high": False}) is None
    # R2 — bordi aperti: aperto verso l'alto MA limite inferiore > 0 → "+"
    assert weakiv.ar_one_side({"empty": False, "low": 0.5, "high": 7.0,
                               "unbounded_low": False, "unbounded_high": True}) == "+"
    # aperto verso il basso MA limite superiore < 0 → "-"
    assert weakiv.ar_one_side({"empty": False, "low": -3.0, "high": -0.5,
                               "unbounded_low": True, "unbounded_high": False}) == "-"
    # tocca entrambi i bordi (largo, a cavallo dello zero) → None
    assert weakiv.ar_one_side({"empty": False, "low": -3.0, "high": 7.0,
                               "unbounded_low": True, "unbounded_high": True}) is None


def test_delta_ar_pvalue_high_when_identical_cells():
    # celle identiche → esiste un β comune (b=b_H dà T=0) → p≈1
    rng = config.make_rng("delta_id")
    cell = (2.0, 1.0, 2.0 + 0.1 * rng.standard_normal(2000),
            1.0 + 0.05 * rng.standard_normal(2000))
    p = weakiv.delta_ar_pvalue(cell, cell, _grid())
    assert p == pytest.approx(1.0, abs=1e-6)


def test_delta_ar_pvalue_small_when_disjoint_strong():
    rng = config.make_rng("delta_disj")
    pos = (2.0, 1.0, 2.0 + 0.03 * rng.standard_normal(3000),
           1.0 + 0.01 * rng.standard_normal(3000))   # b_H ≈ +2, forte
    neg = (-2.0, 1.0, -2.0 + 0.03 * rng.standard_normal(3000),
           1.0 + 0.01 * rng.standard_normal(3000))    # b_H ≈ -2, forte
    p = weakiv.delta_ar_pvalue(pos, neg, _grid())
    assert p < 1e-3
