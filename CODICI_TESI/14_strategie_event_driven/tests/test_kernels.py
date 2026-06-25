"""Test kernel: strategy_rule, payoff, portfolio, metrics."""
import math

import numpy as np
import pandas as pd
import pytest

import config
import metrics as M
import payoff as P
import portfolio as PF
import strategy_rule as SR


# ===== strategy_rule =======================================================

def test_active_event_only_in_negative_regime():
    # Tutte le 3 strategie sono attive SOLO in regime negativo
    for s in ("CPI", "NFP", "FOMC"):
        assert SR.is_active(s, regime="neg") is True
        assert SR.is_active(s, regime="pos") is False


def test_active_event_refuses_unknown_strategy():
    with pytest.raises(KeyError):
        SR.is_active("BCE", regime="neg")


def test_position_direction_momentum_on_sign_of_surprise():
    # CPI β_str=+0.95: sorpresa +1 → posizione su entrambi i mercati nel verso
    # del movimento "comune" (β positivo ⇒ stessa direzione equity/bond).
    pos = SR.position(strategy="CPI", surprise=+1.0)
    assert pos["sign_equity"] == +1 and pos["sign_bond"] == +1
    # Sorpresa negativa: verso opposto
    pos = SR.position(strategy="CPI", surprise=-1.0)
    assert pos["sign_equity"] == -1 and pos["sign_bond"] == -1


def test_position_direction_nfp_negative_comovement():
    # NFP β_str=-1.40: comovimento negativo ⇒ equity e bond in versi opposti
    pos = SR.position(strategy="NFP", surprise=+1.0)
    assert pos["sign_equity"] == +1 and pos["sign_bond"] == -1
    pos = SR.position(strategy="NFP", surprise=-1.0)
    assert pos["sign_equity"] == -1 and pos["sign_bond"] == +1


def test_position_size_proportional_to_abs_beta_str():
    # Sizing in proporzione a β_str (spec): tagli normalizzati a |β| sulla coppia
    pos = SR.position(strategy="CPI", surprise=+1.0)
    assert pos["size"] == pytest.approx(abs(config.BETA_STR["CPI"]))
    pos = SR.position(strategy="NFP", surprise=+1.0)
    assert pos["size"] == pytest.approx(abs(config.BETA_STR["NFP"]))


def test_position_zero_on_zero_surprise():
    # Sorpresa nulla → posizione zero (momentum richiede un verso)
    pos = SR.position(strategy="FOMC", surprise=0.0)
    assert pos["sign_equity"] == 0 and pos["sign_bond"] == 0


# ===== payoff per-evento ai due orizzonti =================================

def test_event_payoff_oracle_event_window_cpi():
    # CPI surprise +0.5, r_e ed r_b a 15min entrambi +1% — payoff = sign·size·(r_e + r_b)
    # sign equity=+1, sign bond=+1, size=|β|=0.95
    # payoff = 0.95·(+1·0.01 + +1·0.01) = 0.95·0.02 = 0.019
    out = P.event_payoff(strategy="CPI", surprise=+0.5,
                          r_e_event=0.01, r_b_event=0.01,
                          r_e_eod=0.02, r_b_eod=-0.005)
    assert out["event_window"] == pytest.approx(0.019)
    # EOD: 0.95·(+1·0.02 + +1·(-0.005)) = 0.95·0.015 = 0.01425
    assert out["end_of_day"] == pytest.approx(0.01425)


def test_event_payoff_nfp_opposite_signs():
    # NFP surprise +1: sign_e=+1, sign_b=-1, size=1.40
    # event: r_e=+0.005, r_b=-0.002 → 1.40·(0.005 - (-0.002)) = 1.40·0.007 = 0.0098
    out = P.event_payoff(strategy="NFP", surprise=+1.0,
                          r_e_event=0.005, r_b_event=-0.002,
                          r_e_eod=0.0, r_b_eod=0.0)
    assert out["event_window"] == pytest.approx(0.0098)
    assert out["end_of_day"] == 0.0


def test_event_payoff_zero_when_zero_surprise():
    out = P.event_payoff(strategy="CPI", surprise=0.0,
                          r_e_event=0.1, r_b_event=0.1,
                          r_e_eod=0.1, r_b_eod=0.1)
    assert out["event_window"] == 0.0 and out["end_of_day"] == 0.0


def test_event_skipped_when_wrong_regime():
    # In regime "pos" la CPI è INATTIVA → payoff None/skip per quell'evento
    out = SR.skip_if_inactive(strategy="CPI", regime="pos")
    assert out is True   # da saltare
    assert SR.skip_if_inactive(strategy="CPI", regime="neg") is False


# ===== portfolio: equal + inverse_vol_on_training ========================

def test_portfolio_equal_weights_oracle():
    train = {"CPI": np.array([0.01, -0.005, 0.02]),
              "NFP": np.array([0.0, 0.01, 0.005]),
              "FOMC": np.array([0.003, 0.0, -0.002])}
    w = PF.compute_weights(train_payoffs=train, scheme="equal")
    assert w == {"CPI": 1/3, "NFP": 1/3, "FOMC": 1/3}


def test_portfolio_inverse_vol_uses_only_training():
    # σ_CPI=alta, σ_NFP=bassa → ω_NFP > ω_CPI
    train = {"CPI": np.array([1.0, -1.0, 1.0, -1.0]),     # σ alta
              "NFP": np.array([0.01, -0.01, 0.01, -0.01]), # σ piccolissima
              "FOMC": np.array([0.1, -0.1, 0.1, -0.1])}    # σ media
    w = PF.compute_weights(train_payoffs=train, scheme="inverse_vol_on_training")
    assert w["NFP"] > w["FOMC"] > w["CPI"]
    assert sum(w.values()) == pytest.approx(1.0)


def test_portfolio_rejects_scheme_chosen_post_hoc():
    # Schemi non in WEIGHT_SCHEMES → solleva (anti-overfitting)
    with pytest.raises(ValueError, match="schema"):
        PF.compute_weights(train_payoffs={"CPI": np.array([0.0])},
                            scheme="maximize_sharpe")


def test_portfolio_combine_payoffs():
    # Combinazione ai due orizzonti, per evento (cross-strategy)
    per_strat_payoffs = {
        "CPI":  {"event_window": np.array([0.01,  0.02, -0.01]),
                  "end_of_day":   np.array([0.005, 0.01, -0.02])},
        "NFP":  {"event_window": np.array([-0.01, 0.005, 0.0]),
                  "end_of_day":   np.array([0.0, 0.0, 0.01])},
        "FOMC": {"event_window": np.array([0.002, 0.0, 0.001]),
                  "end_of_day":   np.array([0.001, 0.001, 0.0])},
    }
    w = {"CPI": 0.4, "NFP": 0.4, "FOMC": 0.2}
    out = PF.combine_payoffs(per_strat_payoffs, weights=w)
    # Aggregazione per-evento (concatena tutti gli eventi nelle 3 strategie,
    # ognuno pesato col w della propria strategia)
    assert "event_window" in out and "end_of_day" in out
    assert len(out["event_window"]) == 9
    # primo evento (CPI #0): 0.4·0.01 = 0.004
    assert out["event_window"][0] == pytest.approx(0.4 * 0.01)


# ===== metrics ============================================================

def test_sharpe_oracle():
    # mean=1, std(ddof=1)=1 ⇒ Sharpe=1
    p = np.array([0.0, 1.0, 2.0])
    assert M.sharpe(p) == pytest.approx(p.mean() / p.std(ddof=1))


def test_sharpe_nan_on_constant_payoffs():
    assert math.isnan(M.sharpe([0.1, 0.1, 0.1]))


def test_sharpe_per_horizon_returns_both():
    rng = np.random.default_rng(0)
    payoffs = {"event_window": rng.standard_normal(50) * 0.01 + 0.001,
               "end_of_day":   rng.standard_normal(50) * 0.02 + 0.0005}
    out = M.sharpe_per_horizon(payoffs)
    assert set(out) == {"event_window", "end_of_day"}
    assert "sharpe" in out["event_window"]
    assert "n" in out["event_window"] and out["event_window"]["n"] == 50


def test_metrics_summary_structure():
    rng = np.random.default_rng(1)
    payoffs = {"event_window": rng.standard_normal(40),
               "end_of_day":   rng.standard_normal(40)}
    out = M.summary(payoffs, period="2010-2024")
    assert out["period"] == "2010-2024"
    assert out["n"] == 40
    for h in ("event_window", "end_of_day"):
        for k in ("sharpe", "mean", "vol", "n"):
            assert k in out[h]
