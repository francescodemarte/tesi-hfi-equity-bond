"""Test surprises (Stadio 0): PC1, separazione JK per rotazione a segno, poor man's."""
import numpy as np
import pytest

import config
import surprises as su


def test_validate_source_blocks_breakeven_globally():
    with pytest.raises(ValueError):
        su.validate_source("dT5YIE")
    with pytest.raises(ValueError):
        su.validate_source("breakeven")
    # paniere ammesso
    assert su.validate_source("FF_c1") == "FF_c1"
    assert su.validate_source("ES") == "ES"


def test_pc1_recovers_common_factor():
    # Oracolo indipendente: PC1 ≈ fattore comune (verificato via SVD, path
    # diverso da eigh sulla covarianza usato dall'implementazione)
    rng = np.random.default_rng(0)
    n = 200
    f = rng.standard_normal(n)
    M = np.column_stack([f + 0.1 * rng.standard_normal(n) for _ in range(5)])
    pc1 = su.pc1(M)
    assert abs(np.corrcoef(pc1, f)[0, 1]) > 0.97
    # Convenzione di segno: PC1 ha somma loadings ≥ 0 → corr positiva col fattore
    assert np.corrcoef(pc1, f)[0, 1] > 0


def test_pc1_zero_on_constant_input():
    M = np.tile([1.0, 2.0, 3.0, 4.0, 5.0], (50, 1))
    assert np.allclose(su.pc1(M), 0.0)


# --- Separazione JK per rotazione a restrizione di segno --------------------

def _make_jk_data(rng, n=400):
    """DGP costruito: due shock latenti veri (mp, cbi) con segni opposti su s.

    Asimmetria nei loading così che Cov(m,s) abbia segno e magnitudine ben
    distinte da zero (Σ non-diagonale ⇒ struttura JK identificata, vedi
    gate di feasibility in `separate_jk`):
      m = 1.0·mp + 1.5·cbi + ε,   s = -0.5·mp + 1.5·cbi + ε
      Cov(m,s) = -1·0.5·Var(mp) + 1.5·1.5·Var(cbi) = -0.5 + 2.25 = +1.75 ≫ 0.
    """
    mp = rng.standard_normal(n)
    cbi = rng.standard_normal(n)
    m = 1.0 * mp + 1.5 * cbi + 0.05 * rng.standard_normal(n)
    s = -0.5 * mp + 1.5 * cbi + 0.05 * rng.standard_normal(n)
    return m, s, mp, cbi


def test_separate_jk_satisfies_four_sign_restrictions():
    rng = np.random.default_rng(1)
    m, s, _, _ = _make_jk_data(rng)
    out = su.separate_jk(m, s)
    Zmp, Zcbi = out["Z_mp"], out["Z_cbi"]
    # 4 vincoli di segno (spec §0.2)
    assert np.cov(m, Zmp, ddof=1)[0, 1] > 0
    assert np.cov(s, Zmp, ddof=1)[0, 1] < 0
    assert np.cov(m, Zcbi, ddof=1)[0, 1] > 0
    assert np.cov(s, Zcbi, ddof=1)[0, 1] > 0


def test_separate_jk_components_are_orthogonal():
    rng = np.random.default_rng(2)
    m, s, _, _ = _make_jk_data(rng)
    out = su.separate_jk(m, s)
    Zmp, Zcbi = out["Z_mp"], out["Z_cbi"]
    # ortogonali per costruzione (rotazione ortogonale di 2 fattori scorrelati)
    assert abs(np.corrcoef(Zmp, Zcbi)[0, 1]) < 0.10


def test_separate_jk_recovers_latent_signs_under_construction():
    # Oracolo indipendente: le componenti latenti mp, cbi sono note per
    # costruzione. Z_mp deve correlare positivamente con mp e Z_cbi con cbi
    # (a meno del segno della rotazione, fissato dalla convenzione hawkish>0).
    rng = np.random.default_rng(3)
    m, s, mp, cbi = _make_jk_data(rng, n=2000)
    out = su.separate_jk(m, s)
    assert np.corrcoef(out["Z_mp"], mp)[0, 1] > 0.85
    assert np.corrcoef(out["Z_cbi"], cbi)[0, 1] > 0.85


# --- Poor man's (riscontro semplice) ---------------------------------------

def test_poor_mans_separation_is_indicator_split_of_m():
    m = np.array([+1.0, +1.0, -1.0, -1.0, 0.5])
    s = np.array([-2.0, +2.0, -2.0, +2.0, 0.0])
    # m·s<0 → MP (hawkish con s↓): righe 0, 3
    # m·s>0 → CBI: righe 1, 2
    out = su.poor_mans(m, s)
    np.testing.assert_array_equal(out["Z_mp"], np.array([+1.0, 0.0, 0.0, -1.0, 0.0]))
    np.testing.assert_array_equal(out["Z_cbi"], np.array([0.0, +1.0, -1.0, 0.0, 0.0]))


def test_sign_concordance_high_when_constructions_agree():
    rng = np.random.default_rng(4)
    m, s, _, _ = _make_jk_data(rng, n=400)
    full = su.separate_jk(m, s)
    poor = su.poor_mans(m, s)
    c = su.sign_concordance(full, poor)
    assert 0.0 <= c["mp"] <= 1.0 and 0.0 <= c["cbi"] <= 1.0
    # nello scenario costruito i segni concordano spesso (>60%)
    assert c["mp"] > 0.60
    assert c["cbi"] > 0.60


# --- BLOCKER #1: gate di esistenza della struttura JK ---------------------

def test_separate_jk_refuses_on_independent_noise():
    # Su (m,s) INDIPENDENTI Σ è ~diagonale → niente struttura JK da ruotare.
    # La routine DEVE rifiutarsi (raise o feasible=False), non produrre Z.
    rng = np.random.default_rng(0)
    n_success_on_pure_noise = 0
    n_reps = 200
    for k in range(n_reps):
        m = rng.standard_normal(300); s = rng.standard_normal(300)
        try:
            out = su.separate_jk(m, s)
            # Se non solleva, deve almeno marcare feasible=False
            if out.get("feasible", True):
                n_success_on_pure_noise += 1
        except (ValueError, su.JKNotIdentifiedError):
            pass
    # Atteso: ≤ 5% (livello del test); col 100% di prima era BLOCKER
    assert n_success_on_pure_noise / n_reps <= 0.10, \
        f"Su rumore puro la routine 'identifica' la struttura JK il "\
        f"{100*n_success_on_pure_noise/n_reps:.1f}% delle volte (BLOCKER #1)."


def test_separate_jk_accepts_when_structure_present():
    # Su DGP con shock latenti veri la routine NON deve sollevare.
    # Loading ASIMMETRICI così Cov(m,s) è ben distinto da zero in popolazione
    # (gli stessi di `_make_jk_data`): test robusto al cambio di seed.
    rng = np.random.default_rng(1)
    m, s, _, _ = _make_jk_data(rng, n=600)
    out = su.separate_jk(m, s)
    assert out.get("feasible", True)
    # 4 vincoli di segno restano garantiti
    cov = lambda a, b: float(np.cov(a, b, ddof=1)[0, 1])
    assert cov(m, out["Z_mp"]) > 0 and cov(s, out["Z_mp"]) < 0
    assert cov(m, out["Z_cbi"]) > 0 and cov(s, out["Z_cbi"]) > 0


def test_separate_jk_exposes_feasibility_diagnostics():
    # Diagnostica esplicita: Cov(m,s) e suo CI bootstrap, autovalori, n.
    # Permette all'esecutore di GATE-are la pipeline su questo (non solo "Z").
    # Stesso DGP asimmetrico di sopra: robusto al cambio di seed.
    rng = np.random.default_rng(2)
    m, s, _, _ = _make_jk_data(rng, n=400)
    out = su.separate_jk(m, s, return_diagnostics=True)
    assert "feasibility" in out
    diag = out["feasibility"]
    assert "cov_ms" in diag and "cov_ms_ci95" in diag and "eigvals" in diag
    assert diag["cov_ms_ci95"][0] is not None and diag["cov_ms_ci95"][1] is not None


def test_sign_concordance_reports_per_component_n():
    rng = np.random.default_rng(5)
    m, s, _, _ = _make_jk_data(rng, n=100)
    c = su.sign_concordance(su.separate_jk(m, s), su.poor_mans(m, s))
    assert c["n"] == 100
    assert set(c.keys()) == {"mp", "cbi", "n"}
