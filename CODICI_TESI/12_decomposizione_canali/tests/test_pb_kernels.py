"""Test kernel ΔP^B: bond (lettura diretta) ed equity (costruzione tail-dependent)."""
import math

import numpy as np
import pytest

import bond_pb
import config
import equity_pb


# ----- ΔP^B bond: -D · Δy (lettura diretta) -------------------------------

def test_bond_pb_is_minus_duration_times_delta_yield():
    # Δy = +5 bp = +0.0005, D=7y ⇒ ΔP^B = -7 · 0.0005 = -0.0035
    assert bond_pb.delta_pb_bond(D=7.0, delta_y=0.0005) == pytest.approx(-0.0035)


def test_bond_pb_zero_when_no_yield_change():
    assert bond_pb.delta_pb_bond(D=10.0, delta_y=0.0) == 0.0


def test_bond_pb_rejects_negative_duration():
    with pytest.raises(ValueError):
        bond_pb.delta_pb_bond(D=-1.0, delta_y=0.0001)


# ----- ΔP^B equity: -Σ ρ^{n-1} · Δf_n con coda dalla griglia --------------

def test_equity_pb_truncation_T0_no_tail():
    # Δf osservati su n=1..3, ρ=0.5, T0 (coda nulla):
    # ΔP^B = -(1·Δf1 + 0.5·Δf2 + 0.25·Δf3)
    delta_f = np.array([0.001, 0.002, 0.003])
    out = equity_pb.delta_pb_equity(delta_f, rho=0.5, tail="T0", N=3)
    expected = -(1.0 * 0.001 + 0.5 * 0.002 + 0.25 * 0.003)
    assert out == pytest.approx(expected)


def test_equity_pb_constant_tail_TC():
    # T0 con Δf=[0.001, 0.002] e ρ=0.5, N=3 ⇒ -(0.001 + 0.5·0.002) = -0.002
    # TC con stesso input e N=3: la coda estesa di Δf_m=Δf_2=0.002 ⇒ termine in più = ρ^2·0.002
    # Atteso: -(0.001 + 0.5·0.002 + 0.25·0.002) = -0.0025
    delta_f = np.array([0.001, 0.002])
    out = equity_pb.delta_pb_equity(delta_f, rho=0.5, tail="TC", N=3)
    expected = -(0.001 + 0.5 * 0.002 + 0.25 * 0.002)
    assert out == pytest.approx(expected)


def test_equity_pb_decay_tail_TD():
    # TD λ=0.5: Δf_3 = Δf_2 · 0.5 = 0.001
    delta_f = np.array([0.001, 0.002])
    out = equity_pb.delta_pb_equity(delta_f, rho=0.5, tail="TD_0.5", N=3)
    # -(0.001 + 0.5·0.002 + 0.25·(0.002·0.5)) = -(0.001 + 0.001 + 0.00025) = -0.00225
    expected = -(0.001 + 0.5 * 0.002 + 0.25 * (0.002 * 0.5))
    assert out == pytest.approx(expected)


def test_equity_pb_T0_equals_observed_only_sum():
    # T0 con N=m: coda azzerata. Confronto con somma esplicita.
    delta_f = np.array([0.001, 0.002, 0.003, 0.004])
    rho = 0.9
    weights = rho ** np.arange(len(delta_f))
    out = equity_pb.delta_pb_equity(delta_f, rho=rho, tail="T0", N=len(delta_f))
    assert out == pytest.approx(-float(np.dot(weights, delta_f)))


def test_equity_pb_tail_value_TC_long_horizon():
    # ρ=0.9, N=100, Δf=[0.001], TC: Δf_n = 0.001 ∀ n≥2
    # ΔP^B = -Σ_{n=1..N} ρ^{n-1}·0.001 = -0.001·(1-ρ^N)/(1-ρ)
    delta_f = np.array([0.001])
    rho = 0.9; N = 100
    out = equity_pb.delta_pb_equity(delta_f, rho=rho, tail="TC", N=N)
    expected = -0.001 * (1 - rho ** N) / (1 - rho)
    assert out == pytest.approx(expected, rel=1e-9)


def test_equity_pb_rejects_unknown_tail():
    with pytest.raises(ValueError, match="tail"):
        equity_pb.delta_pb_equity(np.array([0.001]), rho=0.5, tail="WHATEVER", N=3)


def test_equity_pb_rejects_N_less_than_m():
    # Non si tronca SOTTO il numero di osservazioni: solleva.
    with pytest.raises(ValueError):
        equity_pb.delta_pb_equity(np.array([0.001, 0.002, 0.003]),
                                    rho=0.5, tail="T0", N=2)


def test_rho_from_dp_bar_oracle():
    # ρ_a = 1/(1 + exp(dp_bar))
    rho = equity_pb.rho_from_dp_bar(-3.44)
    expected = 1.0 / (1.0 + math.exp(-3.44))
    assert rho == pytest.approx(expected)
    assert rho == pytest.approx(0.969, abs=0.001)


def test_rho_quarterly_from_annual():
    rho_a = 0.969
    rho_q = equity_pb.rho_quarterly(rho_a)
    assert rho_q == pytest.approx(rho_a ** 0.25)


def test_equity_pb_full_grid_yields_12_points():
    delta_f = np.array([0.001, 0.002, 0.003, 0.004])
    dp_bar = -3.44
    out = equity_pb.delta_pb_equity_full_grid(delta_f, dp_bar=dp_bar, N=80)
    # 12 punti = 4 tail × 3 rho
    assert len(out) == config.GRID_POINTS_PER_EVENT
    # ogni punto ha tail, dp_bar_used, rho, value
    for pt in out:
        assert {"tail", "dp_bar_used", "rho", "value"} <= set(pt)


def test_equity_pb_TC_dominates_T0_when_curve_moves_at_border():
    """Se Δf_m è grande e positivo, TC contribuisce coda positiva ⇒ |ΔP^B(TC)| > |ΔP^B(T0)|."""
    delta_f = np.array([0.001, 0.005])    # Δf_m = +0.005 grosso
    rho = 0.95; N = 50
    pb_t0 = equity_pb.delta_pb_equity(delta_f, rho=rho, tail="T0", N=N)
    pb_tc = equity_pb.delta_pb_equity(delta_f, rho=rho, tail="TC", N=N)
    # entrambi negativi (Δf positivo ⇒ -Σρ^{n-1}Δf<0); TC più negativo perché coda aggiunge contributo
    assert pb_tc < pb_t0
