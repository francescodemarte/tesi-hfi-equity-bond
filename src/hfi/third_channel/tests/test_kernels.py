"""Test kernel: residual, proxies, tests_channel, multiplicity, sensitivity, whitening."""
import math

import numpy as np
import pytest

import config
import multiplicity as M
import proxies as PR
import residual as R
import sensitivity as S
import tests_channel as TC
import whitening as W


# ===== §2 residual =========================================================

def test_residuals_oracle():
    r_e_tilde = np.array([0.10, 0.20, -0.05])
    r_b_tilde = np.array([0.05, 0.10, -0.02])
    beta_str = 2.0
    out = R.residuals(r_e_tilde, r_b_tilde, beta_str)
    # ũ_e = r̃_e − β · r̃_b = 0.10 − 0.10 = 0; 0.20 − 0.20 = 0; -0.05 − (-0.04) = -0.01
    np.testing.assert_allclose(out["u_e"], [0.0, 0.0, -0.01], atol=1e-12)
    # ũ_b = r̃_b − (1/β) · r̃_e = 0.05 − 0.05 = 0; 0.10 − 0.10 = 0; -0.02 − (-0.025) = 0.005
    np.testing.assert_allclose(out["u_b"], [0.0, 0.0, 0.005], atol=1e-12)


def test_residuals_raises_on_zero_beta():
    with pytest.raises(ValueError, match="beta_str"):
        R.residuals(np.array([0.1]), np.array([0.05]), beta_str=0.0)


# ===== §4 proxies — ortogonalizzazione alla sorpresa =======================

def test_orthogonalize_proxy_to_surprise_orthogonality():
    rng = np.random.default_rng(0)
    n = 400
    s = rng.standard_normal(n)
    # Z = α·s + η: una parte è correlata con s, una pulita
    z = 1.5 * s + rng.standard_normal(n) * 0.5
    z_perp = PR.orthogonalize(z, surprise=s)
    # corr(z_perp, s) deve essere ≈ 0 per costruzione (residuo OLS)
    corr = float(np.corrcoef(z_perp, s)[0, 1])
    assert abs(corr) < 1e-10


def test_orthogonalize_multiple_columns():
    rng = np.random.default_rng(1)
    n = 200
    s = rng.standard_normal(n); rate = rng.standard_normal(n)
    z = 0.5 * s + 0.3 * rate + 0.4 * rng.standard_normal(n)
    z_perp = PR.orthogonalize(z, surprise=s, extra_controls=rate)
    assert abs(np.corrcoef(z_perp, s)[0, 1]) < 1e-10
    assert abs(np.corrcoef(z_perp, rate)[0, 1]) < 1e-10


def test_orthogonalize_raises_on_shape_mismatch():
    with pytest.raises(ValueError):
        PR.orthogonalize(np.array([1.0, 2.0]), surprise=np.array([1.0, 2.0, 3.0]))


# ===== §5 tests_channel — regressioni HAC + comunalità + segno =============

def test_loading_regression_oracle_recovers_lambda():
    rng = np.random.default_rng(2)
    n = 400
    z = rng.standard_normal(n)
    lam = 1.5
    u = lam * z + rng.standard_normal(n) * 0.3
    out = TC.loading_regression(u, z_perp=z)
    assert out["lambda"] == pytest.approx(lam, abs=0.1)
    assert out["p_value"] < 0.001


def test_loading_regression_high_p_when_no_relationship():
    rng = np.random.default_rng(3)
    z = rng.standard_normal(300)
    u = rng.standard_normal(300)
    out = TC.loading_regression(u, z_perp=z)
    assert out["p_value"] > 0.05


def test_commonality_holds_when_antisymmetric_pos_eq_pattern():
    # Sotto spec §3 RIVISTA: L = antisymmetric_pos_eq richiede λ_e>0 ∧ λ_b<0
    # (coerente con la patologia §2: coef_b = −coef_e/β, β>0).
    out = TC.commonality(lambda_e=+1.5, p_e=0.001, lambda_b=-1.2, p_b=0.005,
                          expected_sign="antisymmetric_pos_eq", alpha=0.05)
    assert out["commonality"] is True
    assert out["sign_ok"] is True


def test_commonality_fails_when_antisymmetric_pos_eq_violated_concordant_signs():
    # Stesso segno (sotto la spec rivista NON è il pattern atteso) → sign_ok False.
    out = TC.commonality(lambda_e=+1.5, p_e=0.001, lambda_b=+0.8, p_b=0.01,
                          expected_sign="antisymmetric_pos_eq", alpha=0.05)
    assert out["commonality"] is True
    assert out["sign_ok"] is False


def test_commonality_fails_when_only_one_significant():
    out = TC.commonality(lambda_e=+1.5, p_e=0.001, lambda_b=+0.1, p_b=0.6,
                          expected_sign="antisymmetric_pos_eq")
    assert out["commonality"] is False


def test_expected_sign_antisymmetric_neg_eq():
    # V = antisymmetric_neg_eq richiede λ_e<0 ∧ λ_b>0.
    out = TC.commonality(lambda_e=-1.5, p_e=0.001, lambda_b=+0.8, p_b=0.01,
                          expected_sign="antisymmetric_neg_eq")
    assert out["sign_ok"] is True
    out2 = TC.commonality(lambda_e=+1.5, p_e=0.001, lambda_b=+0.8, p_b=0.01,
                           expected_sign="antisymmetric_neg_eq")
    assert out2["sign_ok"] is False


def test_legacy_sign_rules_raise():
    # Le etichette legacy ("concordant", "both_negative") sono ora vietate.
    import pytest
    for legacy in ("concordant", "both_negative"):
        with pytest.raises(ValueError, match="LEGACY"):
            TC.commonality(lambda_e=+1.5, p_e=0.001, lambda_b=+1.2, p_b=0.005,
                            expected_sign=legacy, alpha=0.05)


def test_expected_sign_ambiguous_always_ok_when_significant():
    out = TC.commonality(lambda_e=+1.5, p_e=0.001, lambda_b=-0.8, p_b=0.01,
                          expected_sign="ambiguous")
    assert out["sign_ok"] is True   # ambiguo: si registra, non si impone


# ===== §6 multiplicity — BY su famiglia 12 con c(m) ========================

def test_benjamini_yekutieli_step_up_with_dependency_factor():
    # m=12, q=0.10, c(m) = Σ_{i=1}^{12} 1/i ≈ 3.1032
    # soglie i·q/(m·c(m)) per i=1..12
    # con un unico p molto piccolo (0.0001) ⇒ rigetta solo quello
    p = [0.0001] + [0.5] * 11
    out = M.benjamini_yekutieli(p, q=0.10, m=12)
    rejected = [bool(r) for r in out["rejected"]]   # np.True_ → bool Python
    assert rejected[0] is True
    assert all(r is False for r in rejected[1:])
    # c_m correttamente calcolato
    assert out["c_m"] == pytest.approx(sum(1.0 / i for i in range(1, 13)))


def test_by_rejects_all_when_all_p_below_lowest_threshold():
    out = M.benjamini_yekutieli([1e-6] * 12, q=0.10, m=12)
    assert all(out["rejected"])


def test_by_refuses_len_mismatch():
    with pytest.raises(ValueError):
        M.benjamini_yekutieli([0.01] * 5, q=0.10, m=12)


# ===== §7 sensitivity — gate_a a soglie multiple ==========================

def test_gate_a_sensitivity_classifies_per_threshold():
    # F=20: passa a 15/20/practical, FAIL a 10% (23.1)
    out = S.gate_a_sensitivity(F_MOP=20.0)
    assert out["passes"]["bias_10pct"] is False
    assert out["passes"]["bias_15pct"] is True       # 20 > 17.87
    assert out["passes"]["bias_20pct"] is True
    assert out["passes"]["practical_F10"] is True
    assert out["robustness"] == "weak"               # non passa a 10%


def test_gate_a_sensitivity_strong_when_passes_strictest():
    out = S.gate_a_sensitivity(F_MOP=30.0)
    assert all(out["passes"].values())
    assert out["robustness"] == "strong"


def test_gate_a_sensitivity_fail_when_below_practical():
    out = S.gate_a_sensitivity(F_MOP=8.0)
    assert all(v is False for v in out["passes"].values())
    assert out["robustness"] == "fail"


# ===== whitening — bianchezza del residuo =================================

def test_residual_autocorr_low_when_white():
    rng = np.random.default_rng(4)
    u = rng.standard_normal(400)
    out = W.autocorrelation(u, lag=1)
    assert abs(out["rho"]) < 0.15
    assert out["p_value"] > 0.05


def test_residual_autocorr_high_when_ar1():
    rng = np.random.default_rng(5)
    n = 400; u = np.zeros(n); u[0] = rng.standard_normal()
    for t in range(1, n):
        u[t] = 0.7 * u[t-1] + rng.standard_normal()
    out = W.autocorrelation(u, lag=1)
    assert out["rho"] > 0.5
    assert out["p_value"] < 0.001


def test_regime_dependence_test():
    rng = np.random.default_rng(6)
    u = rng.standard_normal(200)
    reg = np.array(["pos"] * 100 + ["neg"] * 100)
    out = W.regime_dependence(u, regimes=reg)
    assert "f_stat" in out and "p_value" in out
    assert out["p_value"] > 0.05   # white ⇒ no regime dependence


# ===== Whitening summary: residuo bianco se passa TUTTI ===================

def test_whiteness_summary_passes_when_all_white():
    out = W.whiteness_summary(
        autocorr_p=0.5, regime_dep_p=0.5,
        cross_corr_p={"L": 0.4, "V": 0.6, "C": 0.5}, alpha=0.05)
    assert out["is_white"] is True


def test_whiteness_summary_fails_on_any_dimension():
    out = W.whiteness_summary(
        autocorr_p=0.5, regime_dep_p=0.5,
        cross_corr_p={"L": 0.001, "V": 0.6, "C": 0.5}, alpha=0.05)
    assert out["is_white"] is False
