"""Test dei 4 calcoli descrittivi del cancello — oracoli analitici."""
import math

import numpy as np
import pandas as pd
import pytest

import diagnostics as D


# ----- 1. Within/between variance decomposition (η² classico ANOVA) -----------

def test_variance_decomposition_pure_between_eta2_eq_1():
    # tutti gli eventi in 2 regimi con valori DIVERSI ma costanti dentro regime
    # → between = totale, within = 0, η² = 1
    values = np.array([1.0]*50 + [5.0]*50)
    groups = np.array(["pos"]*50 + ["neg"]*50)
    out = D.variance_decomposition(values, groups)
    assert out["eta_squared"] == pytest.approx(1.0)
    assert out["within_var"] == pytest.approx(0.0, abs=1e-12)


def test_variance_decomposition_pure_within_eta2_eq_0():
    # stessa distribuzione nei due gruppi (medie uguali) → between ≈ 0, η² ≈ 0
    rng = np.random.default_rng(0)
    a = rng.standard_normal(100); b = rng.standard_normal(100)
    values = np.concatenate([a, b])
    groups = np.array(["pos"]*100 + ["neg"]*100)
    out = D.variance_decomposition(values, groups)
    assert out["eta_squared"] < 0.02


def test_variance_decomposition_reports_n():
    out = D.variance_decomposition(np.array([1.0, 2.0, 3.0, 4.0]),
                                    np.array(["a", "a", "b", "b"]))
    assert out["n"] == 4 and set(out["group_n"]) == {"a", "b"}


# ----- 2. Cohen's kappa fra due partizioni -----------------------------------

def test_cohens_kappa_perfect_agreement_equals_one():
    p1 = np.array(["A", "B", "A", "B", "A"])
    p2 = np.array(["A", "B", "A", "B", "A"])
    assert D.cohens_kappa(p1, p2) == pytest.approx(1.0)


def test_cohens_kappa_perfect_disagreement_equals_minus_one_in_2x2():
    p1 = np.array(["A"]*4 + ["B"]*4)
    p2 = np.array(["B"]*4 + ["A"]*4)
    assert D.cohens_kappa(p1, p2) == pytest.approx(-1.0)


def test_partition_alignment_kappa_recovers_structural_agreement_with_disjoint_labels():
    # Caso del prompt: una partizione {high,low}, l'altra {positivo,negativo}.
    # Accordo strutturale perfetto (high↔positivo, low↔negativo) ⇒ |κ|_aligned = 1.
    p1 = np.array(["high"]*50 + ["low"]*50)
    p2 = np.array(["positivo"]*50 + ["negativo"]*50)
    out = D.partition_alignment_kappa(p1, p2)
    assert out["kappa_aligned"] == pytest.approx(1.0)
    # raw Cohen su label disgiunti = 0 (verifica della patologia)
    assert abs(out["raw_kappa"]) < 1e-9


def test_partition_alignment_kappa_independent_partitions_low():
    rng = np.random.default_rng(0)
    p1 = rng.choice(["A", "B"], 500)
    p2 = rng.choice(["X", "Y"], 500)
    out = D.partition_alignment_kappa(p1, p2)
    # indipendenti ⇒ |κ|_aligned vicino a 0 (margine bootstrap)
    assert out["kappa_aligned"] < 0.15


def test_cohens_kappa_independent_partitions_near_zero():
    rng = np.random.default_rng(1)
    p1 = rng.choice(["A", "B"], 500)
    p2 = rng.choice(["A", "B"], 500)
    assert abs(D.cohens_kappa(p1, p2)) < 0.15


# ----- 3. Dicotomizzazione dell'intensità ------------------------------------

def test_dichotomize_median_balanced_50_50():
    x = np.arange(100, dtype=float)
    labels = D.dichotomize(x, mode="median")
    high = (labels == "high").sum()
    assert high == 50 and (labels == "low").sum() == 50


def test_dichotomize_tertile_extremes_drops_middle():
    x = np.arange(99, dtype=float)
    labels = D.dichotomize(x, mode="tertile_extremes")
    # 33 high, 33 low, 33 drop (NaN-like marker "drop")
    assert (labels == "high").sum() == 33
    assert (labels == "low").sum() == 33
    assert (labels == "drop").sum() == 33


def test_dichotomize_movement_zero_versus_positive():
    # x>0 → 'high', x==0 → 'low'. Coerente con |Δprice| (massa puntuale in 0).
    x = np.array([0.0, 0.0, 0.0, 0.001, 0.5, 1.0])
    labels = D.dichotomize(x, mode="movement")
    assert (labels == "high").sum() == 3
    assert (labels == "low").sum() == 3
    # tutti zeri → tutti low (NO collasso a 'high' come avverrebbe con 'median')
    z = np.zeros(50)
    assert (D.dichotomize(z, mode="movement") == "low").all()


def test_dichotomize_unsupported_mode_raises():
    with pytest.raises(ValueError):
        D.dichotomize(np.arange(10), mode="quantile_4")


# ----- 4. Popolamento celle regime × intensità -------------------------------

def test_cell_counts_2x2():
    df = pd.DataFrame({
        "regime": ["pos"]*30 + ["neg"]*40,
        "intensity_label": ["high"]*15 + ["low"]*15 + ["high"]*20 + ["low"]*20,
    })
    cnt = D.cell_counts(df, regime_col="regime", intensity_col="intensity_label")
    assert cnt[("pos", "high")] == 15
    assert cnt[("pos", "low")] == 15
    assert cnt[("neg", "high")] == 20
    assert cnt[("neg", "low")] == 20


def test_cells_below_threshold_flagged():
    cnt = {("pos","high"): 35, ("pos","low"): 12,
            ("neg","high"): 50, ("neg","low"): 40}
    below = D.cells_below_threshold(cnt, threshold=30)
    assert below == [("pos","low")]


# ----- 5. Vettori di cambiamento + angolo / collinearità --------------------

def test_change_vector_subtracts_means_correctly():
    # cella "alta" - cella "bassa" sul vettore (var_e, var_b, cov_eb)
    cells = {
        "high": {"var_e": 0.05, "var_b": 0.02, "cov_eb": -0.01},
        "low":  {"var_e": 0.02, "var_b": 0.01, "cov_eb": -0.005},
    }
    delta = D.change_vector(cells, "high", "low")
    np.testing.assert_allclose(delta, [0.03, 0.01, -0.005])


def test_cosine_angle_orthogonal_vectors_zero():
    u = np.array([1.0, 0.0, 0.0])
    v = np.array([0.0, 1.0, 0.0])
    assert D.cosine_similarity(u, v) == pytest.approx(0.0)


def test_cosine_angle_collinear_vectors_one():
    u = np.array([1.0, 2.0, 3.0])
    v = np.array([2.0, 4.0, 6.0])
    assert D.cosine_similarity(u, v) == pytest.approx(1.0)


def test_cosine_angle_anticollinear_vectors_minus_one():
    u = np.array([1.0, 2.0, 3.0])
    v = -np.array([1.0, 2.0, 3.0])
    assert D.cosine_similarity(u, v) == pytest.approx(-1.0)


def test_change_vectors_distinctness_measures():
    # due vettori distinti
    u = np.array([1.0, 0.0, 0.0]); v = np.array([0.0, 1.0, 0.0])
    out = D.change_vectors_distinctness(u, v)
    assert out["cosine"] == pytest.approx(0.0)
    assert abs(out["angle_deg"] - 90.0) < 1e-9
    assert out["rank_numerical"] == 2


def test_change_vectors_collinear_rank_one():
    u = np.array([1.0, 2.0, 3.0]); v = np.array([2.0, 4.0, 6.0])
    out = D.change_vectors_distinctness(u, v)
    assert out["rank_numerical"] == 1
    assert out["cosine"] == pytest.approx(1.0)
