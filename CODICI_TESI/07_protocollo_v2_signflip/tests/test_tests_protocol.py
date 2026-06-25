"""Test di tests_protocol.py — cuore inferenziale (T1, T4, T5).

Celle sintetiche da DGP noto: r^e = β·r^b + u, σ_eb=0 (invarianza) ⇒ b_H=ΔCov/ΔVar=β.
Varianza evento > controllo ⇒ strumento rilevante (ΔVar>0).
T5 segue E2 (inferenza AR), R1 (parte 2 = peso inferenziale, parte 1 = direzione)
e state_dep = testabilità (n≥n_min in entrambe le celle).
"""
import numpy as np
import pandas as pd
import pytest

import config
import weakiv
import tests_protocol as tp


def _grid():
    return np.arange(config.AR_BETA_LOW,
                     config.AR_BETA_HIGH + config.AR_STEP / 2, config.AR_STEP)


def _meta_cell(beta, n_events, rng, year_start=2018):
    cl = _make_cell(beta, n_events, rng)
    for i, c in enumerate(cl):
        c["meta"] = {"year": year_start + (i % 4), "magnitude": abs(c["event"]["r_b"])}
    return cl


def _make_cell(beta, n_events, rng, sigma_e=0.02, sigma_c=0.005, k=5):
    """Cluster sintetici (evento + k controlli). σ_eb=0 ⇒ b_H≈β; var evento>controllo."""
    clusters = []
    for _ in range(n_events):
        rb_e = rng.normal(0, sigma_e); u_e = rng.normal(0, sigma_e)
        ctrls = []
        for _ in range(k):
            rb_c = rng.normal(0, sigma_c); u_c = rng.normal(0, sigma_c)
            ctrls.append({"r_e": beta * rb_c + u_c, "r_b": rb_c})
        clusters.append({"event": {"r_e": beta * rb_e + u_e, "r_b": rb_e}, "controls": ctrls})
    return clusters


_CV = weakiv.mop_critical_value(K=1, worst_case_size=0.10, nominal=0.05)


def test_cell_moments_pools_events_and_controls():
    rng = config.make_rng("cm")
    cl = _make_cell(2.0, 5, rng, k=3)
    re_e, rb_e, re_c, rb_c = tp.cell_moments(cl)
    assert len(re_e) == 5 and len(rb_e) == 5
    assert len(re_c) == 15 and len(rb_c) == 15   # 5 eventi × 3 controlli


def test_cell_estimate_recovers_beta_under_invariance():
    rng = config.make_rng("ce")
    est = tp.cell_estimate(_make_cell(2.0, 300, rng), rng, B=400)
    assert est["dVar"] > 0
    assert est["b_H"] == pytest.approx(2.0, abs=0.4)   # b_H≈β (σ_eb=0)
    assert est["n_e"] == 300


def test_t1_strong_cell_routes_pointwise():
    rng = config.make_rng("t1s")
    est = tp.cell_estimate(_make_cell(2.0, 300, rng), rng, B=400)
    r = tp.t1_relevance(est, _CV)
    assert r["dvar_sig"] is True
    assert r["f_eff"] > _CV
    assert r["route"] == "pointwise"


def test_t1_thin_cell_routes_ar_only():
    rng = config.make_rng("t1t")
    est = tp.cell_estimate(_make_cell(2.0, 20, rng), rng, B=400)   # n=20 < n_min
    r = tp.t1_relevance(est, _CV)
    assert r["route"] == "ar_only"


def test_t5_strong_flip_detected():
    rng = config.make_rng("flip")
    pos = tp.cell_estimate(_make_cell(2.0, 300, rng), rng, B=400)
    neg = tp.cell_estimate(_make_cell(-2.0, 300, rng), rng, B=400)
    per_type = {"NFP": {"pos": pos, "neg": neg},
                "CPI": {"pos": None, "neg": None},
                "FOMC": {"pos": None, "neg": None},
                "ECB": {"pos": None, "neg": None}}
    out = tp.t5_signflip(per_type, _grid())
    assert out["per_type"]["NFP"]["testable"] is True
    assert out["per_type"]["NFP"]["opposite_sides"] is True   # parte 1: direzione
    assert out["per_type"]["NFP"]["delta_p"] < 0.05           # parte 2: differenza
    assert out["flip_detected"]["NFP"] is True
    assert out["by"]["m_used"] == 3                           # famiglia fissa


def test_t5_null_no_flip():
    rng = config.make_rng("null")
    pos = tp.cell_estimate(_make_cell(1.0, 300, rng), rng, B=400)
    neg = tp.cell_estimate(_make_cell(1.0, 300, rng), rng, B=400)
    per_type = {"NFP": {"pos": pos, "neg": neg},
                "CPI": {"pos": None, "neg": None},
                "FOMC": {"pos": None, "neg": None},
                "ECB": {"pos": None, "neg": None}}
    out = tp.t5_signflip(per_type, _grid())
    assert out["flip_detected"]["NFP"] is False
    # nessun flip: o stessa direzione (parte 1 falsa) o differenza non significativa
    assert (out["per_type"]["NFP"]["opposite_sides"] is False
            or out["per_type"]["NFP"]["delta_p"] > 0.05)


def test_t2_lewbel_relevant_and_recovers_bL():
    rng = config.make_rng("t2")
    n = 200
    rb = rng.normal(0, 0.02, n); u = rng.normal(0, 0.02, n)
    re = 2.0 * rb + u
    Z = rb ** 2 + rng.normal(0, 1e-5, n)   # correlato con (r^b)² → τ>0
    out = tp.t2_lewbel(re, rb, Z, rng, B=300)
    assert out["tau"] > 0
    assert out["b_L"] == pytest.approx(2.0, abs=0.5)
    assert out["feedable"] is True


def test_t2_gate_not_feedable_when_thin():
    rng = config.make_rng("t2thin")
    n = 20                                  # < n_min
    rb = rng.normal(0, 0.02, n); Z = rng.normal(0, 1, n); re = rng.normal(0, 0.02, n)
    out = tp.t2_lewbel(re, rb, Z, rng, B=300)
    assert out["feedable"] is False


def test_t2_lewbel_rejects_forbidden_source_label():
    # #1: il guard ΔT5YIE è cablato nel percorso inferenziale (consumatore di Z)
    rng = config.make_rng("t2guard")
    n = 40
    rb = rng.normal(0, 0.02, n); re = 2.0 * rb + rng.normal(0, 0.02, n); Z = rb ** 2
    with pytest.raises(ValueError):
        tp.t2_lewbel(re, rb, Z, rng, B=100, source_label="dT5YIE")


def test_t3_amplitude_difference_and_ci():
    rng = config.make_rng("t3")
    est = tp.cell_estimate(_make_cell(2.0, 300, rng), rng, B=400)
    out = tp.t3_amplitude(est)
    assert out["diff"] == pytest.approx(est["b_OLS"] - est["b_H"], abs=1e-9)
    assert out["ci_low"] <= out["diff"] <= out["ci_high"]


def test_t6_cochran_q_and_nfp_vs_cpi():
    rng = config.make_rng("t6")
    estA = tp.cell_estimate(_make_cell(2.0, 300, rng), rng, B=300)    # b_H≈+2
    estB = tp.cell_estimate(_make_cell(-1.0, 300, rng), rng, B=300)   # b_H≈-1
    est_by_regime = {"positivo": {"NFP": estA, "CPI": estB}}
    t5_result = {"flip_detected": {"NFP": True, "CPI": False}}
    out = tp.t6_type_specificity(t5_result, est_by_regime)
    assert out["nfp_vs_cpi"]["nfp_flips"] is True
    assert out["nfp_vs_cpi"]["cpi_flips"] is False
    assert out["cochran_q"]["positivo"]["Q"] > 0     # b_H eterogenei tra tipi


def test_t7_exogenous_reruns_t5_per_criterion():
    rng = config.make_rng("t7")
    pos = tp.cell_estimate(_make_cell(2.0, 60, rng), rng, B=120)
    neg = tp.cell_estimate(_make_cell(-2.0, 60, rng), rng, B=120)
    pt = {"NFP": {"pos": pos, "neg": neg}, "CPI": {"pos": None, "neg": None},
          "FOMC": {"pos": None, "neg": None}, "ECB": {"pos": None, "neg": None}}
    out = tp.t7_exogenous({"infl_high": pt, "rate_high": pt}, _grid())
    assert set(out) == {"infl_high", "rate_high"}
    assert out["infl_high"]["flip_detected"]["NFP"] is True   # flip sopravvive ai regimi esogeni


def test_t8_robustness_baseline_and_perturbations():
    rng = config.make_rng("t8")
    ptc = {"NFP": {"pos": _meta_cell(2.0, 80, rng), "neg": _meta_cell(-2.0, 80, rng)},
           "CPI": {"pos": None, "neg": None}, "FOMC": {"pos": None, "neg": None},
           "ECB": {"pos": None, "neg": None}}
    transforms = {
        "exclude_extreme": tp.per_cell_transform(lambda c: tp.exclude_extreme(c, 0.1)),
        "loyo_2018": tp.per_cell_transform(lambda c: tp.leave_year_out(c, 2018)),
    }
    out = tp.t8_robustness(ptc, rng, _grid(), transforms, B=120)
    assert {"baseline", "exclude_extreme", "loyo_2018"} <= set(out)
    assert out["baseline"]["flip_detected"]["NFP"] is True


def test_t8_perturbation_thinning_breaks_flip_via_routing():
    # il routing si applica DENTRO la perturbazione: assottigliare sotto n_min → non testabile → no flip
    rng = config.make_rng("t8b")
    ptc = {"NFP": {"pos": _meta_cell(2.0, 80, rng), "neg": _meta_cell(-2.0, 80, rng)},
           "CPI": {"pos": None, "neg": None}, "FOMC": {"pos": None, "neg": None},
           "ECB": {"pos": None, "neg": None}}
    transforms = {"thin": tp.per_cell_transform(lambda c: c[:20] if c else c)}  # 20 < n_min
    out = tp.t8_robustness(ptc, rng, _grid(), transforms, B=120)
    assert out["thin"]["per_type"]["NFP"]["testable"] is False
    assert out["thin"]["flip_detected"]["NFP"] is False


def test_t8d_classify_event_is_inflationary_uses_predetermined_yoy():
    # E3 T8(d): YoY CPI predeterminato (ultimo pubblicato PRIMA dell'evento), soglia 4%.
    idx = pd.to_datetime(["2020-12-10", "2021-06-10", "2022-06-10"])
    cpi_yoy = pd.Series([0.012, 0.054, 0.082], index=idx)
    # evento il 2022-07-15 → ultimo YoY pubblicato = 2022-06-10 = 0.082 ≥ 0.04 → inflazionistico
    assert tp.t8d_is_inflationary(pd.Timestamp("2022-07-15"), cpi_yoy) is True
    # evento il 2021-01-15 → ultimo YoY = 2020-12-10 = 0.012 < 0.04 → non inflazionistico
    assert tp.t8d_is_inflationary(pd.Timestamp("2021-01-15"), cpi_yoy) is False
    # evento prima del primo YoY disponibile → None (non classificabile)
    assert tp.t8d_is_inflationary(pd.Timestamp("2020-01-01"), cpi_yoy) is None


def test_t8d_filter_drops_inflationary_events():
    cl = [{"event": {"center": pd.Timestamp("2020-06-01"), "r_e": 0, "r_b": 0}, "controls": []},
          {"event": {"center": pd.Timestamp("2022-06-01"), "r_e": 0, "r_b": 0}, "controls": []}]
    idx = pd.to_datetime(["2020-01-31", "2022-05-31"])
    cpi_yoy = pd.Series([0.02, 0.08], index=idx)
    kept = tp.t8d_exclude_inflationary(cl, cpi_yoy)
    assert len(kept) == 1
    assert kept[0]["event"]["center"] == pd.Timestamp("2020-06-01")


def test_t5_not_testable_stays_in_family():
    rng = config.make_rng("nt")
    pos = tp.cell_estimate(_make_cell(2.0, 20, rng), rng, B=400)    # n<n_min → non testabile
    neg = tp.cell_estimate(_make_cell(-2.0, 300, rng), rng, B=400)
    per_type = {"NFP": {"pos": pos, "neg": neg},
                "CPI": {"pos": None, "neg": None},
                "FOMC": {"pos": None, "neg": None},
                "ECB": {"pos": None, "neg": None}}
    out = tp.t5_signflip(per_type, _grid())
    assert out["per_type"]["NFP"]["testable"] is False
    assert out["per_type"]["NFP"]["delta_p"] == 1.0     # flip-non-rilevato
    assert out["flip_detected"]["NFP"] is False
    assert out["by"]["m_used"] == 3                     # resta nella famiglia
