"""Smoke-test end-to-end sui 3 DGP sintetici (SPEC §10). NESSUN dato reale.

Valida la pipeline T5 sui tre scenari:
  A. flip strutturale (β cambia segno, σ_eb invariante) → flip RILEVATO;
  B. nullo (β costante) → niente flip (controllo della size);
  C. flip-del-bias (β COSTANTE, Δσ_eb cambia segno) → flip OSSERVATO, rilevato
     ESATTAMENTE come in A → la pipeline NON lo distingue da un β-flip: è il
     cardine epistemico (flip «osservato e non identificato», non promosso a
     β-flip). Vedi SPEC §2bis E2 e §4.
"""
import numpy as np
import pytest

import config
import synthetic
import tests_protocol as tp


def _grid():
    return np.arange(config.AR_BETA_LOW,
                     config.AR_BETA_HIGH + config.AR_STEP / 2, config.AR_STEP)


def _bH(cell):
    """b_H trasversale ricalcolata a mano (oracolo indipendente)."""
    re_e = np.array([c["event"]["r_e"] for c in cell])
    rb_e = np.array([c["event"]["r_b"] for c in cell])
    re_c = np.array([ct["r_e"] for c in cell for ct in c["controls"]])
    rb_c = np.array([ct["r_b"] for c in cell for ct in c["controls"]])
    dCov = np.cov(re_e, rb_e, ddof=1)[0, 1] - np.cov(re_c, rb_c, ddof=1)[0, 1]
    dVar = np.var(rb_e, ddof=1) - np.var(rb_c, ddof=1)
    return dCov / dVar


# === META-CONTROLLO sul GENERATORE (sui PARAMETRI veri, non sull'output) =====
# Il pass dello smoke C è vuoto se il generatore non produce DAVVERO un flip-del-bias
# (β costante) anziché un β-flip. Questi controlli lo blindano sui parametri noti.

def test_metacontrol_dgpC_is_bias_flip_not_beta_flip():
    truth = synthetic.bias_flip_truth()
    # (a) β IDENTICO nei due regimi → NON è un β-flip
    assert truth["beta_pos"] == truth["beta_neg"]
    # (b) plim b_H = β + Δσ_eb/ΔVar a segni OPPOSTI → è un flip-del-bias
    assert np.sign(truth["plim_bH_pos"]) != np.sign(truth["plim_bH_neg"])
    # (c) coerenza della formula del plim coi parametri Δσ_eb/ΔVar
    assert truth["plim_bH_pos"] == pytest.approx(
        truth["beta_pos"] + truth["delta_sigma_eb_pos"] / truth["dVar"])
    assert truth["plim_bH_neg"] == pytest.approx(
        truth["beta_neg"] + truth["delta_sigma_eb_neg"] / truth["dVar"])


def test_metacontrol_dgpC_realized_bH_follows_plim_signs():
    # output↔truth: la b_H realizzata dal generatore segue il segno del plim per costruzione
    rng = config.make_rng("metaC")
    pt = synthetic.dgp_bias_flip(rng, n_events=400)
    truth = synthetic.bias_flip_truth()
    assert np.sign(_bH(pt["NFP"]["pos"])) == np.sign(truth["plim_bH_pos"])
    assert np.sign(_bH(pt["NFP"]["neg"])) == np.sign(truth["plim_bH_neg"])


def test_metacontrol_dgpA_contrast_is_beta_flip_with_invariant_bias():
    truth = synthetic.structural_flip_truth()
    assert np.sign(truth["beta_pos"]) != np.sign(truth["beta_neg"])          # in A è β a flippare
    assert truth["delta_sigma_eb_pos"] == 0.0 and truth["delta_sigma_eb_neg"] == 0.0  # σ_eb invariante


def _run(per_type_clusters, rng, B=200):
    est = tp.estimate_per_type(per_type_clusters, rng, B=B)
    return tp.t5_signflip(est, _grid())


def test_smoke_A_structural_flip_detected():
    rng = config.make_rng("smokeA")
    out = _run(synthetic.dgp_structural_flip(rng, n_events=150), rng)
    assert out["flip_detected"]["NFP"] is True      # NFP ambiguo → flippa
    assert out["flip_detected"]["CPI"] is False      # CPI univoco → non flippa


def test_smoke_B_null_no_flip_controls_size():
    rng = config.make_rng("smokeB")
    out = _run(synthetic.dgp_null(rng, n_events=150), rng)
    assert out["flip_detected"]["NFP"] is False       # nessun flip falso


def test_smoke_C_bias_flip_detected_but_not_identified():
    rng = config.make_rng("smokeC")
    out = _run(synthetic.dgp_bias_flip(rng, n_events=150), rng)
    # b_H flippa per il BIAS (β costante): la pipeline rileva un flip OSSERVATO,
    # esattamente come in A, e non può distinguerlo da un β-flip.
    assert out["flip_detected"]["NFP"] is True
    assert out["per_type"]["NFP"]["opposite_sides"] is True
    assert out["per_type"]["NFP"]["delta_p"] < 0.05
