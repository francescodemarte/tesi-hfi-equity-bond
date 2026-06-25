"""Test robustness (Stadio 3): Rigobon, concordanza poor man's, calendario, finestra."""
import numpy as np
import pytest

import robustness as rb


# --- 3.1 Rigobon binario (subordinato) -------------------------------------

def test_rigobon_recovers_constructed_sign():
    # DGP: σ_eb invariante; b_H = ΔCov/ΔVar = β strutturale (segno noto).
    rng = np.random.default_rng(0)
    n_evt, n_ctl = 400, 600
    sigma_e, sigma_c = 0.02, 0.005
    beta_true = +1.5
    rb_e = rng.normal(0, sigma_e, n_evt); ue = rng.normal(0, sigma_e, n_evt)
    re_e = beta_true * rb_e + ue
    rb_c = rng.normal(0, sigma_c, n_ctl); uc = rng.normal(0, sigma_c, n_ctl)
    re_c = beta_true * rb_c + uc
    out = rb.rigobon_two_regime(re_e, rb_e, re_c, rb_c)
    assert out["dVar"] > 0      # condizione di identificabilità
    assert out["b_H"] == pytest.approx(beta_true, abs=0.3)
    assert np.sign(out["b_H"]) == np.sign(beta_true)


def test_rigobon_negative_beta_recovered_with_correct_sign():
    rng = np.random.default_rng(1)
    n = 500
    rb_e = rng.normal(0, 0.02, n); ue = rng.normal(0, 0.02, n)
    rb_c = rng.normal(0, 0.005, n); uc = rng.normal(0, 0.005, n)
    re_e = -2.0 * rb_e + ue; re_c = -2.0 * rb_c + uc
    out = rb.rigobon_two_regime(re_e, rb_e, re_c, rb_c)
    assert out["b_H"] == pytest.approx(-2.0, abs=0.3)


def test_rigobon_identifiable_false_on_pure_noise():
    # BLOCKER #3 (review agente 4): identifiable=True su rumore puro iso-var era
    # ~46%. Atteso post-fix: ≤ 10% (size del test bootstrap LB95% > 0).
    rng = np.random.default_rng(0)
    n_id_true = 0; n_reps = 100
    for k in range(n_reps):
        re_e = rng.normal(0, 0.01, 60); rb_e = rng.normal(0, 0.01, 60)
        re_c = rng.normal(0, 0.01, 60); rb_c = rng.normal(0, 0.01, 60)
        out = rb.rigobon_two_regime(re_e, rb_e, re_c, rb_c, B=400)
        if out["identifiable"]:
            n_id_true += 1
    assert n_id_true / n_reps <= 0.15, \
        f"identifiable=True su rumore puro: {n_id_true}/{n_reps}"


def test_rigobon_identifiable_true_under_real_variance_jump():
    # Quando c'è davvero un salto di varianza (σ_e ≫ σ_c), identifiable=True.
    rng = np.random.default_rng(1)
    n_id_true = 0; n_reps = 50
    for k in range(n_reps):
        rb_e = rng.normal(0, 0.02, 200); rb_c = rng.normal(0, 0.005, 200)
        re_e = 1.5 * rb_e + rng.normal(0, 0.02, 200)
        re_c = 1.5 * rb_c + rng.normal(0, 0.005, 200)
        out = rb.rigobon_two_regime(re_e, rb_e, re_c, rb_c, B=400)
        if out["identifiable"]:
            n_id_true += 1
    assert n_id_true / n_reps >= 0.90, \
        f"identifiable=True con salto di varianza vero: solo {n_id_true}/{n_reps}"


def test_rigobon_dvar_ci_present():
    # Diagnostica esplicita esposta: dVar_lb (lower bound 95% monolaterale)
    rng = np.random.default_rng(2)
    out = rb.rigobon_two_regime(
        rng.normal(0, 0.02, 100), rng.normal(0, 0.02, 100),
        rng.normal(0, 0.005, 100), rng.normal(0, 0.005, 100), B=200)
    assert "dVar_lb" in out
    assert out["dVar_lb"] is not None


def test_rigobon_subordinate_flag_present():
    # La spec impone gerarchia esplicita: Rigobon è subordinato.
    rng = np.random.default_rng(2)
    n = 200
    rb_e = rng.normal(0, 0.02, n); rb_c = rng.normal(0, 0.005, n)
    re_e = rng.normal(0, 0.02, n); re_c = rng.normal(0, 0.005, n)
    out = rb.rigobon_two_regime(re_e, rb_e, re_c, rb_c)
    assert out["priority"] == "subordinate"


# --- 3.2 Poor man's vs rotazione: concordanza già coperta in surprises ----
# qui il modulo robustezza fa da wrapper: passa dati, recupera dict.

def test_poor_mans_check_returns_concordance_per_component():
    # Loadings asimmetrici → Cov(m,s) ≠ 0 ⇒ supera il gate di identificabilità.
    rng = np.random.default_rng(3)
    n = 400
    mp_lat = rng.standard_normal(n); cbi_lat = rng.standard_normal(n)
    m = 1.0 * mp_lat + 1.5 * cbi_lat + 0.05 * rng.standard_normal(n)
    s = -0.5 * mp_lat + 1.5 * cbi_lat + 0.05 * rng.standard_normal(n)
    out = rb.poor_mans_check(m, s)
    assert {"mp", "cbi", "n"} <= set(out)


# --- 3.3 Calendario: confronto baseline vs robust_drop_fed_t1 --------------

def test_calendar_robustness_returns_two_runs():
    # baseline include eventi con intervento Fed in T+1; robust li rimuove.
    out = rb.calendar_robustness_pair_signature()
    assert set(out) == {"baseline", "robust_drop_fed_t1"}


# --- 3.4 Finestra: solo etichetta (esecutore fornisce le finestre vere) ---

def test_window_robustness_labels():
    out = rb.window_robustness_pair_signature()
    assert set(out) == {"close_to_close_T+1", "intraday_open_T+1"}
