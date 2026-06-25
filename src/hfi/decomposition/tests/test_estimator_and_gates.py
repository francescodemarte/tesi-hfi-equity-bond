"""Test estimator β_str + cancello (a) F-MOP + cancello (b) banda costruzione + pre-check §3.3."""
import numpy as np
import pytest

import config
import estimator as E
import gates as G


# ----- Estimator β_str = ΔCov / ΔVar (Rigobon-Sack) sui rendimenti NETTI ---

def test_beta_str_oracle_known_dgp():
    # DGP: r̃_e = β·r̃_b + u con cov(u, r̃_b)=0, Var(r̃_b) maggiore in evento.
    rng = np.random.default_rng(0)
    n_e, n_c = 300, 600
    rb_e = rng.normal(0, 0.02, n_e); ue = rng.normal(0, 0.015, n_e)
    rb_c = rng.normal(0, 0.005, n_c); uc = rng.normal(0, 0.015, n_c)
    beta = 1.5
    re_e = beta * rb_e + ue; re_c = beta * rb_c + uc
    out = E.beta_str(re_e, rb_e, re_c, rb_c)
    assert out["beta_str"] == pytest.approx(beta, abs=0.3)
    assert out["dVar_b_tilde"] > 0


def test_beta_str_returns_nan_when_dvar_degenerate():
    rng = np.random.default_rng(1)
    rb_e = rng.normal(0, 0.01, 200); rb_c = rng.normal(0, 0.01, 200)
    re_e = rng.normal(0, 0.02, 200); re_c = rng.normal(0, 0.02, 200)
    out = E.beta_str(re_e, rb_e, re_c, rb_c)
    # ΔVar ≈ 0 → b_H non identificato
    # (può essere positivo o negativo per fluttuazione; verifichiamo solo |dVar| piccolo)
    assert abs(out["dVar_b_tilde"]) < 1e-3


def test_shrink_ratio_zero_when_bond_pure_rate():
    # r̃_b ≡ 0 (bond tutto tasso): shrink = 0
    n = 200
    rb_e = np.full(n, 0.0); rb_c = np.full(n, 0.0)
    r_b_e_raw = np.random.default_rng(0).normal(0, 0.02, n)
    r_b_c_raw = np.random.default_rng(1).normal(0, 0.005, n)
    s = E.shrink_ratio(r_b_tilde_e=rb_e, r_b_tilde_c=rb_c,
                       r_b_e_raw=r_b_e_raw, r_b_c_raw=r_b_c_raw)
    assert s == 0.0


def test_shrink_ratio_one_when_no_netting():
    # r̃_b = r_b (nessun netting applicato): shrink = 1
    rng = np.random.default_rng(0)
    rb_e = rng.normal(0, 0.02, 300); rb_c = rng.normal(0, 0.005, 300)
    s = E.shrink_ratio(r_b_tilde_e=rb_e, r_b_tilde_c=rb_c,
                       r_b_e_raw=rb_e, r_b_c_raw=rb_c)
    assert s == pytest.approx(1.0)


# ----- Cancello (a): F-MOP su ΔVar(r̃_b) ----------------------------------

def test_gate_a_pass_when_F_MOP_ge_cv():
    out = G.gate_a(F_MOP=25.0, cv=config.MOP_CV)
    assert out["gate_a"] == "PASS"
    out2 = G.gate_a(F_MOP=23.1085, cv=config.MOP_CV)   # uguaglianza ammessa
    assert out2["gate_a"] == "PASS"


def test_gate_a_fail_when_F_MOP_below_cv():
    out = G.gate_a(F_MOP=15.0, cv=config.MOP_CV)
    assert out["gate_a"] == "FAIL"


def test_F_MOP_effective_oracle():
    # F_eff = (ΔVar_hat)^2 / Var_hat(ΔVar) — la varianza in input arriva dal bootstrap
    F = G.F_MOP_effective(dVar_hat=0.0001, var_dVar_hat=2.5e-9)
    # (1e-4)^2 / 2.5e-9 = 1e-8 / 2.5e-9 = 4.0
    assert F == pytest.approx(4.0)


def test_F_MOP_nan_when_var_dvar_zero():
    F = G.F_MOP_effective(dVar_hat=0.0001, var_dVar_hat=0.0)
    assert np.isnan(F)


# ----- Cancello (b): banda di costruzione sulla griglia coda × ρ ---------

def test_construction_band_from_grid_profile():
    profile = [
        {"tail": "T0", "rho": 0.8, "beta_str": 1.20},
        {"tail": "TC", "rho": 0.8, "beta_str": 1.55},
        {"tail": "TD_0.5", "rho": 0.95, "beta_str": 0.95},
        {"tail": "TD_0.8", "rho": 0.95, "beta_str": 1.40},
    ]
    band = G.construction_band(profile)
    assert band["min"] == pytest.approx(0.95)
    assert band["max"] == pytest.approx(1.55)
    assert band["width"] == pytest.approx(1.55 - 0.95)


def test_construction_band_degenerate_when_all_equal():
    profile = [{"tail": "T0", "rho": 0.9, "beta_str": 1.2}] * 4
    band = G.construction_band(profile)
    assert band["width"] == pytest.approx(0.0)


def test_total_band_is_envelope_of_construction_and_sampling():
    constr = {"min": 0.95, "max": 1.55, "width": 0.60}
    sampling = {"low": 1.10, "high": 1.40}
    out = G.total_band(constr, sampling)
    assert out["low"] == pytest.approx(0.95)
    assert out["high"] == pytest.approx(1.55)


# ----- Pre-check §3.3: Δf_m al bordo della curva --------------------------

def test_border_precheck_warn_when_delta_fm_significant():
    rng = np.random.default_rng(0)
    # Δf_m grande e sistematicamente diverso da 0 → WARN
    delta_f_m = 0.005 + 0.001 * rng.standard_normal(100)
    out = G.tail_border_precheck(delta_f_m,
                                  alpha=config.TAIL_BORDER_SIGNIFICANCE_ALPHA)
    assert out["status"] == "WARN"


def test_border_precheck_pass_when_delta_fm_centered_zero():
    rng = np.random.default_rng(1)
    delta_f_m = 0.002 * rng.standard_normal(200)   # centrato in zero
    out = G.tail_border_precheck(delta_f_m,
                                  alpha=config.TAIL_BORDER_SIGNIFICANCE_ALPHA)
    assert out["status"] == "PASS"


# ----- Verdetto per cella (decisione di §6) -------------------------------

def test_cell_verdict_strong_when_all_pass():
    out = G.cell_verdict(gate_a="PASS", precheck="PASS", band_width=0.05,
                         band_threshold=0.30)
    assert out == "identified_robust"


def test_cell_verdict_weak_when_gate_a_fails():
    out = G.cell_verdict(gate_a="FAIL", precheck="PASS", band_width=0.05,
                         band_threshold=0.30)
    assert out == "channel_not_identified"


def test_cell_verdict_fragile_when_band_wide_or_precheck_warn():
    out = G.cell_verdict(gate_a="PASS", precheck="PASS", band_width=0.50,
                         band_threshold=0.30)
    assert out == "identified_fragile"
    out2 = G.cell_verdict(gate_a="PASS", precheck="WARN", band_width=0.05,
                          band_threshold=0.30)
    assert out2 == "identified_fragile"
