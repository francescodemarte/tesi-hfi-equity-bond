"""Test di inference.py — bootstrap clusterizzato, routing R5, BY R7, Cochran Q.

Target ANALITICI/pubblicati (riuso test-gated, §9 spec): ogni kernel è
riconfermato contro un valore calcolabile a mano, non «per fiducia».
"""
import numpy as np
import pytest

import config
import inference


# --- benjamini_yekutieli (R7) ------------------------------------------

def test_by_rejects_only_smallest_analytic():
    # c_3 = 1 + 1/2 + 1/3 ≈ 1.8333; soglie del rango i = i*q/(m*c_3):
    #   rango 1: 1*0.10/(3*1.8333) ≈ 0.01818
    #   rango 2: 2*0.10/(3*1.8333) ≈ 0.03636
    #   rango 3: 3*0.10/(3*1.8333) ≈ 0.05454
    # p = [0.001, 0.2, 0.5] → solo 0.001 <= soglia_1 → rigetta SOLO il primo.
    res = inference.benjamini_yekutieli([0.001, 0.2, 0.5], q=0.10, m=3)
    assert res["rejected"] == [True, False, False]
    assert res["m"] == 3
    assert res["c_m"] == pytest.approx(1.0 + 1.0 / 2.0 + 1.0 / 3.0)
    # crit = soglia del rango massimo rigettato (rango 1)
    assert res["crit"] == pytest.approx(1 * 0.10 / (3 * res["c_m"]))


def test_by_default_m_is_len():
    res = inference.benjamini_yekutieli([0.001, 0.2, 0.5], q=0.10)
    assert res["m"] == 3


def test_by_preserves_original_order():
    # p più piccolo NON in prima posizione: il flag True deve seguire l'ordine input.
    res = inference.benjamini_yekutieli([0.5, 0.001, 0.2], q=0.10, m=3)
    assert res["rejected"] == [False, True, False]


def test_by_no_rejection_returns_none_crit():
    res = inference.benjamini_yekutieli([0.4, 0.6, 0.9], q=0.10, m=3)
    assert res["rejected"] == [False, False, False]
    assert res["crit"] is None


def test_by_stepup_rejects_below_max_rank():
    # Step-up: trovato il rango massimo che passa, si rigettano TUTTI i ranghi <=.
    # Con p = [0.001, 0.03, 0.5]: soglia_2 ≈ 0.03636 > 0.03 → rango 2 passa,
    # quindi si rigettano sia il rango 1 sia il rango 2 (anche se 0.03 da solo
    # rispetta la sua soglia, è la logica step-up a includerlo).
    res = inference.benjamini_yekutieli([0.001, 0.03, 0.5], q=0.10, m=3)
    assert res["rejected"] == [True, True, False]
    assert res["crit"] == pytest.approx(2 * 0.10 / (3 * res["c_m"]))


# --- route_cell (R5) ----------------------------------------------------

def test_route_pointwise_only_when_all_true():
    out = inference.route_cell(
        dvar_significant=True, f_eff=30.0, cv_mop=23.0, n=config.N_MIN
    )
    assert out == "pointwise"


def test_route_ar_only_when_dvar_not_significant():
    out = inference.route_cell(
        dvar_significant=False, f_eff=30.0, cv_mop=23.0, n=config.N_MIN
    )
    assert out == "ar_only"


def test_route_ar_only_when_weak_instrument():
    # cella RILEVANTE-ma-DEBOLE: ΔVar sig. ma F_eff sotto cv_MOP → AR-only.
    out = inference.route_cell(
        dvar_significant=True, f_eff=10.0, cv_mop=23.0, n=config.N_MIN
    )
    assert out == "ar_only"


def test_route_ar_only_when_too_few_obs():
    out = inference.route_cell(
        dvar_significant=True, f_eff=30.0, cv_mop=23.0, n=config.N_MIN - 1
    )
    assert out == "ar_only"


def test_route_boundary_n_equal_nmin_is_pointwise():
    # n >= n_min → uguaglianza ammessa.
    out = inference.route_cell(
        dvar_significant=True, f_eff=30.0, cv_mop=23.0, n=config.N_MIN
    )
    assert out == "pointwise"


def test_route_boundary_f_eq_cv_is_ar_only():
    # f_eff > cv_mop è STRETTO: uguaglianza → AR-only.
    out = inference.route_cell(
        dvar_significant=True, f_eff=23.0, cv_mop=23.0, n=config.N_MIN
    )
    assert out == "ar_only"


# --- hierarchical_by (R7) ----------------------------------------------

def test_hier_by_fomc_t4_fail_never_rejected_m_stays_3():
    # FOMC fallisce T4 (state_dep=False) → flip-non-rilevato: p=1.0 imposto,
    # mai rigettato, MA occupa comunque uno slot: m_used == 3.
    results = {
        "NFP": {"p": 0.5, "testable": True},
        "CPI": {"p": 0.4, "testable": True},
        "FOMC": {"p": 0.0001, "testable": False},  # p piccolo ma T4 fallito
        "ECB": {"p": 0.4, "testable": True},
    }
    res = inference.hierarchical_by(results)
    assert res["m_used"] == 3
    assert res["secondary"]["FOMC"] is False


def test_hier_by_cpi_small_p_rejected():
    # CPI con p molto piccolo e state_dep True → rigettato.
    results = {
        "NFP": {"p": 0.5, "testable": False},
        "CPI": {"p": 0.0001, "testable": True},
        "FOMC": {"p": 0.6, "testable": True},
        "ECB": {"p": 0.7, "testable": True},
    }
    res = inference.hierarchical_by(results)
    assert res["secondary"]["CPI"] is True
    assert res["m_used"] == 3


def test_hier_by_nfp_primary_uncorrected_reject():
    # NFP primario: p<0.05 e state_dep True → nfp_reject True (NON corretto).
    results = {
        "NFP": {"p": 0.03, "testable": True},
        "CPI": {"p": 0.5, "testable": True},
        "FOMC": {"p": 0.6, "testable": True},
        "ECB": {"p": 0.7, "testable": True},
    }
    res = inference.hierarchical_by(results)
    assert res["nfp_reject"] is True


def test_hier_by_nfp_not_rejected_when_t4_fail():
    # NFP con state_dep False → nfp_reject False anche se p è piccolo.
    results = {
        "NFP": {"p": 0.001, "testable": False},
        "CPI": {"p": 0.5, "testable": True},
        "FOMC": {"p": 0.6, "testable": True},
        "ECB": {"p": 0.7, "testable": True},
    }
    res = inference.hierarchical_by(results)
    assert res["nfp_reject"] is False


def test_hier_by_nfp_not_rejected_when_p_above_alpha():
    results = {
        "NFP": {"p": 0.20, "testable": True},
        "CPI": {"p": 0.5, "testable": True},
        "FOMC": {"p": 0.6, "testable": True},
        "ECB": {"p": 0.7, "testable": True},
    }
    res = inference.hierarchical_by(results)
    assert res["nfp_reject"] is False


# --- cochran_q (T6) -----------------------------------------------------

def test_cochran_q_homogeneous_is_zero():
    # beta tutti uguali → Q ≈ 0, p ≈ 1.
    betas = [0.5, 0.5, 0.5]
    ses = [0.1, 0.2, 0.15]
    res = inference.cochran_q(betas, ses)
    assert res["Q"] == pytest.approx(0.0, abs=1e-12)
    assert res["df"] == 2
    assert res["p"] == pytest.approx(1.0)
    assert res["b_pooled"] == pytest.approx(0.5)


def test_cochran_q_heterogeneous_large_q_small_p():
    # beta molto diversi con se piccoli → Q grande, p piccolo.
    betas = [0.0, 5.0]
    ses = [0.1, 0.1]
    res = inference.cochran_q(betas, ses)
    assert res["df"] == 1
    assert res["Q"] > 100.0
    assert res["p"] < 1e-6


def test_cochran_q_pooled_is_inverse_variance_weighted():
    betas = [1.0, 3.0]
    ses = [1.0, 1.0]  # pesi uguali → media semplice = 2.0
    res = inference.cochran_q(betas, ses)
    assert res["b_pooled"] == pytest.approx(2.0)
    # Q = sum w*(b-bp)^2 = 1*1 + 1*1 = 2
    assert res["Q"] == pytest.approx(2.0)


# --- event_cluster_bootstrap (T1) --------------------------------------

def test_bootstrap_shape():
    clusters = [{"x": float(i)} for i in range(10)]
    rng = np.random.default_rng(0)
    out = inference.event_cluster_bootstrap(
        clusters, stat_fn=lambda cs: np.mean([c["x"] for c in cs]), B=50, rng=rng
    )
    assert isinstance(out, np.ndarray)
    assert out.shape == (50,)
    assert out.dtype == np.float64


def test_bootstrap_recovers_sample_mean():
    # stat_fn = media di una statistica per-cluster nota; su molti B e seed
    # fisso, la media delle repliche bootstrap ≈ statistica campionaria.
    clusters = [{"x": float(i)} for i in range(40)]
    sample_mean = np.mean([c["x"] for c in clusters])
    rng = np.random.default_rng(config.MASTER_SEED)
    out = inference.event_cluster_bootstrap(
        clusters, stat_fn=lambda cs: np.mean([c["x"] for c in cs]), B=20000, rng=rng
    )
    assert out.mean() == pytest.approx(sample_mean, abs=0.05)


def test_bootstrap_resamples_at_cluster_level():
    # Con un solo cluster, ogni replica deve ricampionare quell'unico cluster:
    # tutte le statistiche coincidono col valore del cluster (nessun mix).
    clusters = [{"x": 7.0}]
    rng = np.random.default_rng(1)
    out = inference.event_cluster_bootstrap(
        clusters, stat_fn=lambda cs: cs[0]["x"], B=30, rng=rng
    )
    assert np.all(out == 7.0)
