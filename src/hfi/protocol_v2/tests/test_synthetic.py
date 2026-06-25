"""Test di synthetic.py — TDD stretto con ORACOLO INDIPENDENTE.

`synthetic.py` genera i dati SINTETICI dei 3 DGP per lo smoke-test della
pipeline Rigobon-Sack a due regimi (SPEC §10). Modello: r^e = β·r^b + u, con
finestre EVENTO a varianza di r^b maggiore (σ_e) delle finestre CONTROLLO
(σ_c) ⇒ ΔVar>0. Lo shock comune σ_eb = Cov(u, r^b) è iniettato generando
(r^b, u) come normale bivariata, separatamente per evento e controllo.

La b_H trasversale di una cella vale b_H = ΔCov/ΔVar = β + (c_event-c_control)/ΔVar.

ORACOLO INDIPENDENTE: la b_H qui sotto è ricalcolata dalle celle generate con
numpy puro (ΔCov/ΔVar impilando eventi e controlli), SENZA usare alcuna
funzione di estimators/tests_protocol. Così il test verifica i DATI, non
ricicla l'implementazione che li produce.
"""
import numpy as np
import pytest

import synthetic

TYPES = ("NFP", "CPI", "FOMC", "ECB")


# --- oracolo indipendente (numpy puro) ----------------------------------

def _bH_oracle(cell):
    """b_H trasversale = ΔCov/ΔVar dalle finestre della cella (numpy puro).

    Impila gli eventi (un (r_e, r_b) per cluster) e mette in pool TUTTI i
    controlli dei cluster; momenti campionari ddof=1; ΔCov=cov_e-cov_c,
    ΔVar=var_e-var_c. Nessun import dalla pipeline.
    """
    re_e = np.array([c["event"]["r_e"] for c in cell], dtype=float)
    rb_e = np.array([c["event"]["r_b"] for c in cell], dtype=float)
    re_c, rb_c = [], []
    for c in cell:
        for ct in c["controls"]:
            re_c.append(ct["r_e"])
            rb_c.append(ct["r_b"])
    re_c = np.array(re_c, dtype=float)
    rb_c = np.array(rb_c, dtype=float)

    cov_e = np.cov(re_e, rb_e, ddof=1)[0, 1]
    cov_c = np.cov(re_c, rb_c, ddof=1)[0, 1]
    var_e = np.var(rb_e, ddof=1)
    var_c = np.var(rb_c, ddof=1)
    return (cov_e - cov_c) / (var_e - var_c)


def _rng():
    return np.random.default_rng(20260621)


# --- struttura dati (comune ai 3 DGP) -----------------------------------

@pytest.mark.parametrize("gen", [
    synthetic.dgp_structural_flip,
    synthetic.dgp_null,
    synthetic.dgp_bias_flip,
])
def test_struttura_per_type(gen):
    pt = gen(_rng())
    # quattro tipi, ciascuno con regime pos e neg
    assert set(pt) == set(TYPES)
    for t in TYPES:
        assert set(pt[t]) == {"pos", "neg"}
        for regime in ("pos", "neg"):
            cell = pt[t][regime]
            assert isinstance(cell, list) and len(cell) > 0
            for cluster in cell:
                assert set(cluster) == {"event", "controls"}
                assert set(cluster["event"]) == {"r_e", "r_b"}
                assert isinstance(cluster["event"]["r_e"], float)
                assert isinstance(cluster["event"]["r_b"], float)
                assert isinstance(cluster["controls"], list)
                assert len(cluster["controls"]) > 0
                for ct in cluster["controls"]:
                    assert set(ct) == {"r_e", "r_b"}
                    assert isinstance(ct["r_e"], float)
                    assert isinstance(ct["r_b"], float)


# --- DGP A: flip strutturale --------------------------------------------

def test_structural_flip_nfp_flippa():
    # NFP: β=+2 nel regime pos, β=-2 nel neg, σ_eb invariante ⇒ b_H flippa
    pt = synthetic.dgp_structural_flip(_rng())
    bH_pos = _bH_oracle(pt["NFP"]["pos"])
    bH_neg = _bH_oracle(pt["NFP"]["neg"])
    assert bH_pos > 0
    assert bH_neg < 0


def test_structural_flip_cpi_non_flippa():
    # CPI: stesso β nei due regimi ⇒ b_H ha lo STESSO segno (niente flip)
    pt = synthetic.dgp_structural_flip(_rng())
    bH_pos = _bH_oracle(pt["CPI"]["pos"])
    bH_neg = _bH_oracle(pt["CPI"]["neg"])
    assert np.sign(bH_pos) == np.sign(bH_neg)


def test_structural_flip_fomc_ecb_non_flippano():
    pt = synthetic.dgp_structural_flip(_rng())
    for t in ("FOMC", "ECB"):
        bH_pos = _bH_oracle(pt[t]["pos"])
        bH_neg = _bH_oracle(pt[t]["neg"])
        assert np.sign(bH_pos) == np.sign(bH_neg)


# --- DGP B: nullo --------------------------------------------------------

def test_null_nfp_non_flippa():
    # nullo: stesso β nei due regimi ⇒ b_H stesso segno, nessun flip
    pt = synthetic.dgp_null(_rng())
    bH_pos = _bH_oracle(pt["NFP"]["pos"])
    bH_neg = _bH_oracle(pt["NFP"]["neg"])
    assert np.sign(bH_pos) == np.sign(bH_neg)


def test_null_tutti_i_tipi_non_flippano():
    pt = synthetic.dgp_null(_rng())
    for t in TYPES:
        bH_pos = _bH_oracle(pt[t]["pos"])
        bH_neg = _bH_oracle(pt[t]["neg"])
        assert np.sign(bH_pos) == np.sign(bH_neg)


# --- DGP C: flip-del-bias -----------------------------------------------

def test_bias_flip_nfp_flippa_pur_con_beta_costante():
    # CARDINE epistemico: il β strutturale è IDENTICO nei due regimi (beta0),
    # eppure b_H flippa per via del Δσ_eb (il bias), non per via di β.
    # Il flip OSSERVATO non è un flip di β.
    beta0 = 0.5
    pt = synthetic.dgp_bias_flip(_rng(), beta0=beta0)
    bH_pos = _bH_oracle(pt["NFP"]["pos"])
    bH_neg = _bH_oracle(pt["NFP"]["neg"])
    # flip osservato sullo stimatore...
    assert bH_pos > 0
    assert bH_neg < 0
    # ...mentre il β passato ai due regimi era lo stesso segno (positivo):
    # il flip NON può venire da β, viene dal bias.
    assert beta0 > 0


def test_bias_flip_altri_tipi_non_flippano():
    pt = synthetic.dgp_bias_flip(_rng())
    for t in ("CPI", "FOMC", "ECB"):
        bH_pos = _bH_oracle(pt[t]["pos"])
        bH_neg = _bH_oracle(pt[t]["neg"])
        assert np.sign(bH_pos) == np.sign(bH_neg)
