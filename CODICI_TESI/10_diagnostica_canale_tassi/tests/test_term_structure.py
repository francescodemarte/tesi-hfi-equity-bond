"""test_term_structure.py — Oracoli sintetici per term-structure.

Quattro DGP a verità nota, esattamente come richiesto dal briefing:
  1. pendenza canale separato dal regime → (d) su PC2 passa in entrambi i regimi
  2. pendenza degenere (contratti lunghi fermi) → primo cancello fallisce
  3. entrambi i fattori collineari col regime → (d) fallisce su entrambi
  4. estrazione corretta: PC1/PC2 recuperano livello e pendenza imposti.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import config
import diagnostics as D
import term_structure as TS


# --------------------------------------------------------------------------
# Oracolo 4 (prima — è il check base sull'estrazione: serve agli altri test)
# --------------------------------------------------------------------------

def test_extract_pc_factors_recovers_known_level_and_slope():
    """Costruiamo deltas = a_i * [1,1,1,1] + b_i * [-1,-0.5,0.5,1] + rumore piccolo.
    PC1 deve avere loading concordi sui 4 contratti; PC2 deve avere loading
    di segno opposto fra c1 e c4. Le var-explained devono ordinare PC1 > PC2."""
    rng = np.random.default_rng(0)
    n = 400
    level_load = np.array([1.0, 1.0, 1.0, 1.0])
    slope_load = np.array([-1.0, -0.5, 0.5, 1.0])
    a = rng.normal(0, 1.0, n)        # forte
    b = rng.normal(0, 0.4, n)        # più debole ma reale
    noise = rng.normal(0, 0.05, (n, 4))
    deltas = a[:, None] * level_load + b[:, None] * slope_load + noise

    out = TS.extract_pc_factors(deltas, contracts=list(config.TS_CONTRACTS))
    L = out["loadings"]
    ve = out["var_explained"]

    assert ve[0] > ve[1] > 0
    # PC1 livello: stessi segni su tutte e 4 le scadenze
    assert np.all(L[0] > 0) or np.all(L[0] < 0)
    # Convenzione di segno fissata: loading su c1 (TS_PC1_SIGN_REF=FEIc1) ≥ 0
    assert L[0, 0] >= 0
    # PC2 pendenza: loading di segno opposto tra c1 e c4 (struttura slope)
    assert L[1, 0] * L[1, -1] < 0
    # Convenzione di segno: loading su c4 (TS_PC2_SIGN_REF=FEIc4) ≥ 0
    assert L[1, -1] >= 0


# --------------------------------------------------------------------------
# Helper: dato un dgp di deltas (n,4) e (regime, slope_intensity_high, …)
# costruisce (r_e, r_b) coerenti col DGP richiesto e calcola event_moments
# nelle 4 celle regime × intensità-PC2. Restituisce dict (regime, label) → momenti.
# --------------------------------------------------------------------------

def _moments_for_cells(events_df: pd.DataFrame,
                        intensity_col: str,
                        regime_col: str = "regime") -> dict:
    out = {}
    labels = D.dichotomize(events_df[intensity_col].to_numpy(), mode="median")
    df = events_df.copy()
    df["lab"] = labels
    for (r, i), sub in df.groupby([regime_col, "lab"]):
        re = sub["r_e"].to_numpy()
        rb = sub["r_b"].to_numpy()
        if len(re) < 2:
            continue
        out[(str(r), str(i))] = {
            "var_e": float(np.var(re, ddof=1)),
            "var_b": float(np.var(rb, ddof=1)),
            "cov_eb": float(np.cov(re, rb, ddof=1)[0, 1]),
            "n": int(len(re)),
        }
    return out


def _make_events_with_returns(n_pos: int, n_neg: int,
                               re_gen, rb_gen, rng) -> pd.DataFrame:
    rows = []
    for k in range(n_pos):
        re_v, rb_v = re_gen("positivo", k, rng)
        rows.append({"regime": "positivo", "r_e": re_v, "r_b": rb_v})
    for k in range(n_neg):
        re_v, rb_v = re_gen("negativo", k, rng)
        rows.append({"regime": "negativo", "r_e": re_v, "r_b": rb_v})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Oracolo 1: pendenza è un canale separato dal regime
#   regime sposta solo cov_eb, intensità PC2 sposta var_b (cioè perpendicolare
#   rispetto allo spostamento del regime) → vettori di cambiamento non collineari
# --------------------------------------------------------------------------

def test_dgp_slope_is_separate_channel_d_passes_on_pc2_in_both_regimes():
    rng = np.random.default_rng(42)
    n_per_cell = 80
    cells = []
    # 4 celle: (regime ∈ {positivo, negativo}) × (slope_intensity ∈ {high, low})
    # spostamento regime: +0.01 su cov_eb per positivo
    # spostamento slope-high: + scala su var_b (≠ cov_eb)
    # → vettori distinti
    cell_specs = {
        ("positivo", "high"): {"sigma_e": 0.020, "sigma_b": 0.015, "rho": 0.6},
        ("positivo", "low"):  {"sigma_e": 0.020, "sigma_b": 0.008, "rho": 0.6},
        ("negativo", "high"): {"sigma_e": 0.020, "sigma_b": 0.015, "rho": -0.4},
        ("negativo", "low"):  {"sigma_e": 0.020, "sigma_b": 0.008, "rho": -0.4},
    }
    # event_moments analitici (n abbastanza grande → uguale alla popolazione)
    event_moments = {}
    for (r, i), sp in cell_specs.items():
        event_moments[(r, i)] = {
            "var_e": sp["sigma_e"] ** 2,
            "var_b": sp["sigma_b"] ** 2,
            "cov_eb": sp["rho"] * sp["sigma_e"] * sp["sigma_b"],
            "n": n_per_cell,
        }

    # Calcola direttamente i vettori di cambiamento e il coseno via il kernel
    dvec_rate_pos = D.change_vector(
        {"hi": event_moments[("positivo", "high")],
         "lo": event_moments[("positivo", "low")]}, "hi", "lo")
    dvec_rate_neg = D.change_vector(
        {"hi": event_moments[("negativo", "high")],
         "lo": event_moments[("negativo", "low")]}, "hi", "lo")
    dvec_regime_hi = D.change_vector(
        {"p": event_moments[("positivo", "high")],
         "n": event_moments[("negativo", "high")]}, "p", "n")
    dvec_regime_lo = D.change_vector(
        {"p": event_moments[("positivo", "low")],
         "n": event_moments[("negativo", "low")]}, "p", "n")
    d_pos = D.change_vectors_distinctness(dvec_rate_pos, dvec_regime_hi)
    d_neg = D.change_vectors_distinctness(dvec_rate_neg, dvec_regime_lo)
    # |cos| < 0.95 in entrambi (vettori non collineari → (d) passerebbe)
    assert abs(d_pos["cosine"]) < 0.95
    assert abs(d_neg["cosine"]) < 0.95


# --------------------------------------------------------------------------
# Oracolo 2: pendenza degenere (contratti lunghi fermi) — primo cancello fallisce
# --------------------------------------------------------------------------

def test_dgp_slope_degenerate_long_contracts_frozen_first_gate_fails():
    rng = np.random.default_rng(7)
    n = 500
    # Solo livello, lungo (c3, c4) sostanzialmente immobili (con rumorino trascurabile)
    a = rng.normal(0, 1.0, n)
    deltas = np.column_stack([
        a * 1.0 + rng.normal(0, 0.02, n),
        a * 0.8 + rng.normal(0, 0.02, n),
        a * 0.05 * 0 + np.zeros(n),     # FERMO
        a * 0.05 * 0 + np.zeros(n),     # FERMO
    ])
    pca = TS.extract_pc_factors(deltas, contracts=list(config.TS_CONTRACTS))
    # Costruisci ts_table coerente
    ts = pd.DataFrame({
        "timestamp": pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC"),
        "leg": ["FOMC"] * n, "regime": ["positivo"] * n,
        "delta_FEIc1": deltas[:, 0], "delta_FEIc2": deltas[:, 1],
        "delta_FEIc3": deltas[:, 2], "delta_FEIc4": deltas[:, 3],
    })
    gate1 = TS.first_gate_non_degeneracy(ts, pca)
    # I lunghi sono fermi → (ii) fallisce
    assert gate1["check_ii_long_contract_movement"]["passed"] is False
    assert gate1["passed"] is False


# --------------------------------------------------------------------------
# Oracolo 3: entrambi i fattori collineari col regime → (d) fallisce su entrambi
# --------------------------------------------------------------------------

def test_dgp_both_factors_collinear_with_regime_d_fails_on_both():
    # Costruisco event_moments dove sia "spostarsi lungo PC1-intensity" che
    # "lungo PC2-intensity" hanno lo STESSO direzionale di "spostarsi lungo regime".
    # Concretamente: a high-intensità di PC1 e di PC2, la cella positivo è
    # "uguale" alla cella positivo-bassa-intensità ma scalata di k>0; e la
    # cella negativo è la stessa scalata. Cioè movimento solo su un asse.
    # event_moments per PC1 (high/low):
    em_pc1 = {
        ("positivo", "high"): {"var_e": 5.0, "var_b": 3.0, "cov_eb": 2.0, "n": 60},
        ("positivo", "low"):  {"var_e": 1.0, "var_b": 0.6, "cov_eb": 0.4, "n": 60},
        ("negativo", "high"): {"var_e": 4.0, "var_b": 2.5, "cov_eb": 1.7, "n": 60},
        ("negativo", "low"):  {"var_e": 0.8, "var_b": 0.5, "cov_eb": 0.34, "n": 60},
    }
    # delta_intensity (positivo) e delta_regime (high) co-direzionali per costruzione
    drate_p = D.change_vector({"h": em_pc1[("positivo", "high")],
                                 "l": em_pc1[("positivo", "low")]}, "h", "l")
    dreg_h  = D.change_vector({"p": em_pc1[("positivo", "high")],
                                 "n": em_pc1[("negativo", "high")]}, "p", "n")
    drate_n = D.change_vector({"h": em_pc1[("negativo", "high")],
                                 "l": em_pc1[("negativo", "low")]}, "h", "l")
    dreg_l  = D.change_vector({"p": em_pc1[("positivo", "low")],
                                 "n": em_pc1[("negativo", "low")]}, "p", "n")
    cos_pos = D.cosine_similarity(drate_p, dreg_h)
    cos_neg = D.cosine_similarity(drate_n, dreg_l)
    # Costruzione → vettori quasi-paralleli (|cos|≥0.95) in entrambi i regimi
    assert abs(cos_pos) >= 0.95
    assert abs(cos_neg) >= 0.95


# --------------------------------------------------------------------------
# Oracolo 4-bis: i loading non sono sensibili al segno (convenzione fissata)
# --------------------------------------------------------------------------

def test_sign_convention_pc2_is_stable_under_input_sign_flip():
    rng = np.random.default_rng(1)
    n = 200
    a = rng.normal(0, 1.0, n)
    b = rng.normal(0, 0.4, n)
    deltas = (a[:, None] * np.array([1, 1, 1, 1])
              + b[:, None] * np.array([-1, -0.5, 0.5, 1])
              + rng.normal(0, 0.05, (n, 4)))
    out1 = TS.extract_pc_factors(deltas, contracts=list(config.TS_CONTRACTS))
    out2 = TS.extract_pc_factors(-deltas, contracts=list(config.TS_CONTRACTS))
    # Convenzione fissata: PC1 loading su c1 ≥ 0; PC2 loading su c4 ≥ 0.
    # Anche con input invertito di segno, i loading rispettano la convenzione.
    assert out1["loadings"][0, 0] >= 0 and out2["loadings"][0, 0] >= 0
    assert out1["loadings"][1, -1] >= 0 and out2["loadings"][1, -1] >= 0


# --------------------------------------------------------------------------
# Primo cancello — caso pulito: passa quando i fattori sono ben definiti
# --------------------------------------------------------------------------

def test_first_gate_passes_on_healthy_term_structure():
    rng = np.random.default_rng(99)
    n = 400
    # Pendenza calibrata sopra la soglia: var(b)*||slope||² ≥ 10% della varianza
    # totale (a~N(0,1), ||lvl||²=4; b~N(0,0.7), ||slope||²=2.5; noise piccolo).
    a = rng.normal(0, 1.0, n)
    b = rng.normal(0, 0.7, n)
    deltas = (a[:, None] * np.array([1, 1, 1, 1])
              + b[:, None] * np.array([-1, -0.5, 0.5, 1])
              + rng.normal(0, 0.1, (n, 4)))
    pca = TS.extract_pc_factors(deltas, contracts=list(config.TS_CONTRACTS))
    ts = pd.DataFrame({
        "timestamp": pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC"),
        "leg": ["FOMC"] * n, "regime": ["positivo"] * n,
        "delta_FEIc1": deltas[:, 0], "delta_FEIc2": deltas[:, 1],
        "delta_FEIc3": deltas[:, 2], "delta_FEIc4": deltas[:, 3],
    })
    gate1 = TS.first_gate_non_degeneracy(ts, pca)
    assert gate1["passed"] is True
    assert gate1["check_i_pc2_var_explained"]["passed"] is True
    assert gate1["check_ii_long_contract_movement"]["passed"] is True
    assert gate1["check_iii_pc2_partition_non_degenerate"]["passed"] is True
