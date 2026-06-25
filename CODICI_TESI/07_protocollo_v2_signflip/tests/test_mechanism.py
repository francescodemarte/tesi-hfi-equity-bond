"""Test di mechanism.py (T9, due gambe) — TDD stretto, oracoli ANALITICI.

T9: stima la pendenza univariata della reazione del bond e dell'equity alla
sorpresa s, per regime (positivo/negativo), e diagnostica quale gamba inverte
il segno tra i due regimi. Inferenza descrittiva.

Pendenza univariata = Cov(r, s, ddof=1) / Var(s, ddof=1).
Il riempimento per inferenza è gateato da `surprises.coverage_variance_gate`:
regime non alimentabile → None (meccanismo aperto/dichiarato per quel regime).
"""
import numpy as np
import pytest

import config
import mechanism


# --- leg_slope ----------------------------------------------------------

def test_leg_slope_exact_two_when_r_is_double_s():
    # se r = 2*s (s non costante) → pendenza == 2.0 esatta
    s = np.array([1.0, 2.0, 4.0, 8.0, 3.0])
    r = 2.0 * s
    assert mechanism.leg_slope(r, s) == pytest.approx(2.0)


def test_leg_slope_hand_computed():
    # s = [1,1,2,2], r = [1,2,3,4]
    # mean s = 1.5; dev_s = [-.5,-.5,.5,.5]; var_s = (4*.25)/3 = 1/3
    # mean r = 2.5; dev_r = [-1.5,-.5,.5,1.5]
    # cov = [(-1.5)(-.5)+(-.5)(-.5)+(.5)(.5)+(1.5)(.5)]/3
    #     = [.75+.25+.25+.75]/3 = 2/3
    # slope = (2/3)/(1/3) = 2.0
    s = np.array([1.0, 1.0, 2.0, 2.0])
    r = np.array([1.0, 2.0, 3.0, 4.0])
    assert mechanism.leg_slope(r, s) == pytest.approx(2.0)


def test_leg_slope_nan_when_s_constant():
    s = np.array([5.0, 5.0, 5.0, 5.0])  # Var(s) = 0
    r = np.array([1.0, 2.0, 3.0, 4.0])
    assert np.isnan(mechanism.leg_slope(r, s))


# --- leg_slopes ---------------------------------------------------------

def test_leg_slopes_hand_computed():
    # s arbitrario non costante; r_b = 2*s, r_e = 3*s
    # slope_bond = 2, slope_eq = 3, beta_impl = 3/2 = 1.5 (esatto, no rumore)
    s = np.array([1.0, 2.0, 4.0, 8.0, 3.0])
    r_b = 2.0 * s
    r_e = 3.0 * s
    out = mechanism.leg_slopes(r_e, r_b, s)
    assert set(out) == {"slope_eq", "slope_bond", "beta_impl", "n"}
    assert out["slope_bond"] == pytest.approx(2.0)
    assert out["slope_eq"] == pytest.approx(3.0)
    assert out["beta_impl"] == pytest.approx(1.5)
    assert out["n"] == 5


def test_leg_slopes_beta_impl_nan_when_slope_bond_zero():
    # bond non reagisce a s (r_b costante) → slope_bond = nan → beta_impl nan
    s = np.array([1.0, 2.0, 3.0, 4.0])
    r_b = np.array([7.0, 7.0, 7.0, 7.0])  # Var ok, ma Cov(r_b,s)=0 ⇒ slope_bond=0
    r_e = 3.0 * s
    out = mechanism.leg_slopes(r_e, r_b, s)
    assert out["slope_bond"] == pytest.approx(0.0)
    assert np.isnan(out["beta_impl"])


# --- mechanism: caso alimentabile (entrambi i regimi) -------------------

def test_mechanism_both_feedable_equity_leg_inverts():
    # Costruisco due regimi alimentabili (n >= N_MIN, Var(s) > 0).
    # s: stesso pattern nei due regimi; r_b = +2*s in entrambi (bond NON inverte),
    # r_e = +3*s nel positivo, r_e = -3*s nel negativo (equity INVERTE segno).
    n = config.N_MIN + 5
    rng = np.random.default_rng(123)
    s_pos = rng.standard_normal(n)
    s_neg = rng.standard_normal(n)

    pos = {"r_e": 3.0 * s_pos, "r_b": 2.0 * s_pos, "s": s_pos}
    neg = {"r_e": -3.0 * s_neg, "r_b": 2.0 * s_neg, "s": s_neg}
    out = mechanism.mechanism({"positivo": pos, "negativo": neg})

    assert set(out) == {"positivo", "negativo", "equity_leg_inverts",
                        "bond_leg_inverts", "open"}
    assert out["open"] is False
    # slopes calcolate (non None) in entrambi i regimi
    assert out["positivo"] is not None and out["negativo"] is not None
    assert out["positivo"]["slope_eq"] == pytest.approx(3.0)
    assert out["positivo"]["slope_bond"] == pytest.approx(2.0)
    assert out["negativo"]["slope_eq"] == pytest.approx(-3.0)
    assert out["negativo"]["slope_bond"] == pytest.approx(2.0)
    # equity cambia segno tra regimi, bond no
    assert out["equity_leg_inverts"] is True
    assert out["bond_leg_inverts"] is False


def test_mechanism_both_feedable_no_inversion():
    # entrambe le gambe con segno positivo in entrambi i regimi → nessuna inverte
    n = config.N_MIN + 2
    rng = np.random.default_rng(7)
    s_pos = rng.standard_normal(n)
    s_neg = rng.standard_normal(n)
    pos = {"r_e": 3.0 * s_pos, "r_b": 2.0 * s_pos, "s": s_pos}
    neg = {"r_e": 1.5 * s_neg, "r_b": 0.5 * s_neg, "s": s_neg}
    out = mechanism.mechanism({"positivo": pos, "negativo": neg})
    assert out["open"] is False
    assert out["equity_leg_inverts"] is False
    assert out["bond_leg_inverts"] is False


# --- mechanism: caso gateato (regime non alimentabile) ------------------

def test_mechanism_gated_regime_below_nmin_is_open():
    # regime negativo con n < N_MIN → gate non feedable → regime None, open True,
    # *_inverts None (meccanismo aperto/dichiarato).
    n_ok = config.N_MIN + 3
    rng = np.random.default_rng(42)
    s_pos = rng.standard_normal(n_ok)
    pos = {"r_e": 3.0 * s_pos, "r_b": 2.0 * s_pos, "s": s_pos}

    n_bad = config.N_MIN - 1
    s_neg = rng.standard_normal(n_bad)
    neg = {"r_e": 3.0 * s_neg, "r_b": 2.0 * s_neg, "s": s_neg}

    out = mechanism.mechanism({"positivo": pos, "negativo": neg})
    assert out["open"] is True
    assert out["negativo"] is None
    assert out["positivo"] is not None  # il regime alimentabile resta calcolato
    assert out["equity_leg_inverts"] is None
    assert out["bond_leg_inverts"] is None


def test_mechanism_gated_degenerate_variance_is_open():
    # regime con varianza di s degenere (s costante) → non feedable → open
    n_ok = config.N_MIN + 3
    rng = np.random.default_rng(99)
    s_pos = rng.standard_normal(n_ok)
    pos = {"r_e": 3.0 * s_pos, "r_b": 2.0 * s_pos, "s": s_pos}

    s_neg = np.ones(config.N_MIN + 3)  # Var(s) = 0
    neg = {"r_e": 3.0 * s_neg, "r_b": 2.0 * s_neg, "s": s_neg}

    out = mechanism.mechanism({"positivo": pos, "negativo": neg})
    assert out["open"] is True
    assert out["negativo"] is None
    assert out["equity_leg_inverts"] is None
    assert out["bond_leg_inverts"] is None


def test_mechanism_respects_explicit_n_min():
    # n_min esplicito sovrascrive il default config.N_MIN
    rng = np.random.default_rng(5)
    s_pos = rng.standard_normal(10)
    s_neg = rng.standard_normal(10)
    pos = {"r_e": 3.0 * s_pos, "r_b": 2.0 * s_pos, "s": s_pos}
    neg = {"r_e": -3.0 * s_neg, "r_b": 2.0 * s_neg, "s": s_neg}
    # con n_min=5 (≤10) entrambi alimentabili
    out = mechanism.mechanism({"positivo": pos, "negativo": neg}, n_min=5)
    assert out["open"] is False
    assert out["positivo"] is not None and out["negativo"] is not None


def test_mechanism_rejects_forbidden_source_label():
    # #1: guardia ΔT5YIE cablata anche nel percorso del meccanismo (T9)
    raised = False
    try:
        mechanism.mechanism({"positivo": {}, "negativo": {}}, source_label="dT5YIE")
    except ValueError:
        raised = True
    assert raised
