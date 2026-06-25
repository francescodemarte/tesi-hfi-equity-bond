"""Test regression (Stadio 2): OLS + SE HC + bootstrap SE.

Oracolo indipendente: statsmodels.OLS(..., cov_type='HC1') sui medesimi dati.
"""
import numpy as np
import pytest

import config
import regression as reg

try:
    import statsmodels.api as sm
    HAS_SM = True
except Exception:
    HAS_SM = False


def _toy_dataset(rng, n=400, gamma=0.7, delta=-0.4):
    Z_mp = rng.standard_normal(n)
    Z_cbi = rng.standard_normal(n)
    x = rng.standard_normal(n)            # controllo
    u = rng.standard_normal(n) * 0.3
    y = 0.2 + gamma * Z_mp + delta * Z_cbi + 0.1 * x + u
    X = np.column_stack([Z_mp, Z_cbi, x])
    return X, y, ("Z_mp", "Z_cbi", "x")


def test_ols_recovers_coefficients_under_known_dgp():
    rng = np.random.default_rng(0)
    X, y, names = _toy_dataset(rng, n=2000, gamma=0.7, delta=-0.4)
    out = reg.ols_hc(y, X, names=names)
    # γ̂ → 0.7, δ̂ → -0.4 entro tolleranza
    coefs = dict(zip(("intercept",) + names, out["coef"]))
    assert coefs["Z_mp"] == pytest.approx(0.7, abs=0.05)
    assert coefs["Z_cbi"] == pytest.approx(-0.4, abs=0.05)


@pytest.mark.skipif(not HAS_SM, reason="statsmodels mancante")
def test_ols_hc1_se_matches_statsmodels_within_eps():
    rng = np.random.default_rng(1)
    X, y, names = _toy_dataset(rng, n=600)
    out = reg.ols_hc(y, X, names=names, cov_type="HC1")
    # statsmodels oracolo indipendente
    res = sm.OLS(y, sm.add_constant(X)).fit(cov_type="HC1")
    np.testing.assert_allclose(out["coef"], res.params, atol=1e-10)
    np.testing.assert_allclose(out["se"], res.bse, atol=1e-8)


def test_ols_t_unilateral_matches_definition():
    rng = np.random.default_rng(2)
    X, y, names = _toy_dataset(rng, n=300)
    out = reg.ols_hc(y, X, names=names)
    # t-statistica = coef/se, p UNILATERALE = 1 - Φ(t) per H1: coef>0
    idx = ("intercept",) + names
    j = idx.index("Z_mp")
    t = out["coef"][j] / out["se"][j]
    from scipy.stats import norm
    p_one_sided = 1.0 - norm.cdf(t)
    p_from_module = reg.p_one_sided(t, side="greater")
    assert p_from_module == pytest.approx(p_one_sided)
    # se chiedo "less", p = Φ(t) = 1 - p_greater
    assert reg.p_one_sided(t, side="less") == pytest.approx(norm.cdf(t))


def test_bootstrap_se_recovers_known_sd_of_estimator():
    # SE bootstrap del coef del SOLO regressore di un OLS = sqrt(var(b̂)).
    # Per y = β·x + u (varianza nota) il SE bootstrap converge a quello teorico.
    rng = np.random.default_rng(3)
    n = 500
    x = rng.standard_normal(n)
    u = rng.standard_normal(n) * 0.5
    y = 1.5 * x + u
    X = x.reshape(-1, 1)
    se_boot = reg.bootstrap_se(y, X, B=500, rng=config.make_rng("test_boot_se"))
    # SE teorico OLS = σ/√(Σ x²); con σ=0.5 e n=500 ≈ 0.5/√500 ≈ 0.0224
    assert se_boot[1] == pytest.approx(0.5 / np.sqrt(n), abs=0.01)


def test_bootstrap_is_seeded_and_reproducible():
    rng = np.random.default_rng(7); X, y, _ = _toy_dataset(rng, n=200)
    se1 = reg.bootstrap_se(y, X, B=200, rng=config.make_rng("rep"))
    se2 = reg.bootstrap_se(y, X, B=200, rng=config.make_rng("rep"))
    np.testing.assert_array_equal(se1, se2)


def test_ols_refuses_collinear_design():
    rng = np.random.default_rng(8)
    n = 100
    z = rng.standard_normal(n)
    X = np.column_stack([z, 2 * z])    # collineari
    y = z + rng.standard_normal(n) * 0.1
    with pytest.raises(np.linalg.LinAlgError):
        reg.ols_hc(y, X, names=("z1", "z2"))
