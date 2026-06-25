"""Test kernel: excess, calibration, weighting, payoff, metrics.

Oracoli analitici (calcoli a mano nei commenti) — niente seconda esecuzione
della stessa logica come "verifica".
"""
import numpy as np
import pandas as pd
import pytest

import calibration
import config
import excess
import metrics
import payoff
import weighting


# --- excess: c, a, σ²_pre, ε ----------------------------------------------

def test_realized_comovement_is_product_of_returns():
    assert excess.realized_comovement(0.01, -0.02) == pytest.approx(-2e-4)
    assert excess.realized_comovement(0.0, 0.5) == 0.0


def test_expected_comovement_is_mean_of_daily_products():
    r_eq = np.array([0.01, -0.005, 0.002])
    r_bo = np.array([0.003, 0.001, -0.004])
    # media di [3e-5, -5e-6, -8e-6] = (3e-5 - 5e-6 - 8e-6)/3 = 1.7e-5/3 ≈ 5.67e-6
    expected = float(np.mean(r_eq * r_bo))
    assert excess.expected_comovement(r_eq, r_bo) == pytest.approx(expected)


def test_pre_variance_is_mean_of_squared_returns_combined():
    # spec: σ²_pre = media dei quadrati dei rendimenti giornalieri (proxy varianza
    # del comovimento). Convenzione esplicitata: media degli ε_eq² + ε_bo² combinati.
    r_eq = np.array([0.01, -0.02, 0.01])
    r_bo = np.array([0.005, 0.005, -0.01])
    # media dei quadrati equity = (1e-4 + 4e-4 + 1e-4)/3 = 2e-4
    # media dei quadrati bond = (2.5e-5 + 2.5e-5 + 1e-4)/3 = 5e-5
    # combinato = (2e-4 + 5e-5)/2 = 1.25e-4
    expected = float((np.mean(r_eq ** 2) + np.mean(r_bo ** 2)) / 2.0)
    assert excess.pre_variance(r_eq, r_bo) == pytest.approx(expected)


def test_excess_epsilon_oracle():
    # ε = (c - a) / σ²_pre
    c = 5e-5; a = 1e-5; var = 1e-4
    assert excess.epsilon(c, a, var) == pytest.approx((c - a) / var)


def test_excess_nan_when_variance_zero():
    assert np.isnan(excess.epsilon(c=1e-5, a=0.0, sigma2_pre=0.0))


# --- calibration: e_{g,k} = mean ε su training events della cella ---------

def _events_df(rows):
    return pd.DataFrame(rows)


def test_calibration_mean_per_cell():
    df = _events_df([
        {"date": pd.Timestamp("2015-01-01"), "leg": "NFP", "regime": "neg", "epsilon": 0.10},
        {"date": pd.Timestamp("2015-02-01"), "leg": "NFP", "regime": "neg", "epsilon": 0.20},
        {"date": pd.Timestamp("2015-03-01"), "leg": "NFP", "regime": "pos", "epsilon": -0.05},
        {"date": pd.Timestamp("2015-04-01"), "leg": "CPI", "regime": "neg", "epsilon": 0.01},
        {"date": pd.Timestamp("2015-05-01"), "leg": "CPI", "regime": "neg", "epsilon": 0.03},
    ])
    out = calibration.calibrate(df, training_end=config.SPLIT_DATE)
    e = out["e_gk"]
    assert e[("NFP", "neg")] == pytest.approx(0.15)
    assert e[("NFP", "pos")] == pytest.approx(-0.05)
    assert e[("CPI", "neg")] == pytest.approx(0.02)


def test_calibration_rejects_events_at_or_after_split_date():
    # PRESIDIO STRUTTURALE: la calibrazione DEVE rifiutare eventi col date ≥ SPLIT.
    df = _events_df([
        {"date": pd.Timestamp("2015-01-01"), "leg": "NFP", "regime": "neg", "epsilon": 0.1},
        {"date": pd.Timestamp("2022-06-01"), "leg": "NFP", "regime": "neg", "epsilon": 99.0},  # leak
    ])
    with pytest.raises(ValueError, match="training"):
        calibration.calibrate(df, training_end=config.SPLIT_DATE)


def test_position_sign_rule():
    # versione base: posizione = sign(e_{g,k})
    e_gk = {("NFP", "neg"): +0.2, ("NFP", "pos"): -0.1,
            ("CPI", "neg"): 0.0, ("CPI", "pos"): +0.05}
    assert calibration.position_for("NFP", "neg", e_gk) == +1
    assert calibration.position_for("NFP", "pos", e_gk) == -1
    assert calibration.position_for("CPI", "neg", e_gk) == 0     # sign(0) = 0
    assert calibration.position_for("CPI", "pos", e_gk) == +1


def test_position_rule_with_min_abs_threshold_zero_default():
    e_gk = {("NFP", "neg"): +0.001}
    # default min_abs=0 ⇒ posizione = +1
    assert calibration.position_for("NFP", "neg", e_gk, min_abs=0.0) == +1
    # con soglia 0.01, |e|<soglia ⇒ posizione 0
    assert calibration.position_for("NFP", "neg", e_gk, min_abs=0.01) == 0


# --- weighting: inverse-vol su eventi PASSATI, lunghezza congelata --------

def test_inverse_vol_uses_only_past_events():
    """Per evento i, σ_roll,k stimato su eventi PASSATI della gamba k,
    finestra di L=4 eventi (per oracolo a mano)."""
    eps_history = pd.Series([0.10, 0.20, 0.30, 0.40, 999.0],
                             index=pd.to_datetime(["2015-01-01", "2015-02-01",
                                                    "2015-03-01", "2015-04-01",
                                                    "2015-05-01"]))
    # per l'evento del 2015-05-01, σ stimata sui 4 PASSATI: σ([0.1,0.2,0.3,0.4])
    sigma = weighting.rolling_vol_at(eps_history, t=pd.Timestamp("2015-05-01"),
                                      window_events=4)
    expected = float(np.std([0.10, 0.20, 0.30, 0.40], ddof=1))
    assert sigma == pytest.approx(expected)


def test_inverse_vol_raises_when_not_enough_past_events():
    eps_history = pd.Series([0.1, 0.2], index=pd.to_datetime(["2015-01-01", "2015-02-01"]))
    # finestra L=4, ma ho solo 2 eventi passati ⇒ raise
    with pytest.raises(ValueError):
        weighting.rolling_vol_at(eps_history, t=pd.Timestamp("2015-03-01"), window_events=4)


def test_combine_legs_inverse_vol_weights():
    sigmas = {"NFP": 1.0, "CPI": 0.5}      # CPI metà più "stabile"
    payoffs = {"NFP": 0.10, "CPI": 0.20}
    # ω_NFP ∝ 1/1, ω_CPI ∝ 1/0.5=2; somma=3 → ω_NFP=1/3, ω_CPI=2/3
    # combinato = 0.1·1/3 + 0.2·2/3 = 0.0333 + 0.1333 = 0.1667
    out = weighting.combine_legs(payoffs, sigmas)
    assert out["payoff_combined"] == pytest.approx(0.1 / 3 + 0.4 / 3)
    assert out["weights"]["NFP"] == pytest.approx(1.0 / 3.0)
    assert out["weights"]["CPI"] == pytest.approx(2.0 / 3.0)


def test_combine_legs_two_legs_same_day_weights_truly_inv_vol():
    """REVIEW #3: ramo "due gambe stesso giorno" non coperto prima.
    σ_NFP=2, σ_CPI=1 ⇒ ω_NFP ∝ 0.5, ω_CPI ∝ 1.0; somma=1.5
    ⇒ ω_NFP=1/3, ω_CPI=2/3. payoff_NFP=0.6, payoff_CPI=0.3
    ⇒ combinato = 0.6·1/3 + 0.3·2/3 = 0.2 + 0.2 = 0.4
    """
    out = weighting.combine_legs(payoffs={"NFP": 0.6, "CPI": 0.3},
                                  sigmas={"NFP": 2.0, "CPI": 1.0})
    assert out["weights"]["NFP"] == pytest.approx(1.0 / 3.0)
    assert out["weights"]["CPI"] == pytest.approx(2.0 / 3.0)
    assert out["payoff_combined"] == pytest.approx(0.4)


def test_combine_legs_skips_missing_leg_at_event():
    # se una gamba manca a quell'evento (es. solo NFP), peso e payoff sulla sola NFP
    out = weighting.combine_legs(payoffs={"NFP": 0.05}, sigmas={"NFP": 1.0})
    assert out["payoff_combined"] == pytest.approx(0.05)


# --- payoff: π = w · ε, benchmark π_bench = ε -----------------------------

def test_payoff_strategy_oracle():
    assert payoff.strategy_payoff(w=+1, eps=0.05) == pytest.approx(0.05)
    assert payoff.strategy_payoff(w=-1, eps=0.05) == pytest.approx(-0.05)
    assert payoff.strategy_payoff(w=0, eps=99.0) == 0.0


def test_payoff_benchmark_naive_always_long():
    # benchmark: w=+1 sempre, π_bench = ε
    assert payoff.benchmark_payoff(eps=0.05) == pytest.approx(0.05)
    assert payoff.benchmark_payoff(eps=-0.03) == pytest.approx(-0.03)


# --- metrics: mean, Sharpe, hit_rate, diff vs naive, conteggi -------------

def test_sharpe_oracle():
    # mean=1, std(ddof=1)=1 ⇒ Sharpe=1
    p = np.array([0.0, 1.0, 2.0])
    assert metrics.sharpe(p) == pytest.approx(p.mean() / p.std(ddof=1))


def test_sharpe_nan_on_zero_std():
    assert np.isnan(metrics.sharpe([1.0, 1.0, 1.0]))


def test_hit_rate():
    assert metrics.hit_rate([0.1, -0.1, 0.0, 0.05]) == pytest.approx(2 / 4)


def test_cell_summary_marks_inconclusive_below_threshold():
    s = metrics.cell_summary([0.1] * 5, n_min_verdict=20)   # 5 < 20
    assert s["verdict"] == "inconclusive"
    assert s["n"] == 5
    s2 = metrics.cell_summary([0.1] * 25, n_min_verdict=20)
    assert s2["verdict"] != "inconclusive"
    assert s2["n"] == 25


def test_diff_strategy_minus_benchmark():
    strat = np.array([0.1, -0.1, 0.2])
    bench = np.array([0.05, 0.05, 0.05])
    out = metrics.diff_vs_benchmark(strat, bench)
    assert out["mean_diff"] == pytest.approx((strat - bench).mean())
