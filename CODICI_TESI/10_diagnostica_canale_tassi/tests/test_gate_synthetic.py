"""Validazione del cancello su DGP sintetici a VERITÀ NOTA.

Due scenari costruiti:
  - PASS: intensità-tasso indipendente dal regime ⇒ criteri (a) e (b) soddisfatti;
    celle popolate ⇒ (c); vettori di cambiamento non collineari per costruzione ⇒ (d).
  - FAIL: intensità SCHIACCIATA sul regime (shock alti solo nel regime positivo)
    ⇒ (a) e (b) falliscono.
"""
import numpy as np
import pandas as pd

import config
import gate


def _build_events(rng, *, intensity_by_regime):
    """Costruisce un DataFrame di eventi sintetici con intensità per regime.

    `intensity_by_regime`: dict {"positivo": (n_eventi, mean, sd),
                                  "negativo": (n_eventi, mean, sd)}.
    """
    rows = []
    for regime, (n, mean, sd) in intensity_by_regime.items():
        for i in range(n):
            leg = ("NFP", "CPI", "FOMC", "ECB")[i % 4]
            rows.append({
                "timestamp": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
                "leg": leg,
                "regime": regime,
                "intensity_raw": rng.normal(loc=mean, scale=sd),
            })
    return pd.DataFrame(rows)


def _moments_pass_case():
    """Momenti costruiti perché i vettori di cambiamento non siano collineari."""
    return {
        ("positivo", "high"): {"var_e": 0.05, "var_b": 0.02, "cov_eb": -0.01},
        ("positivo", "low"):  {"var_e": 0.02, "var_b": 0.01, "cov_eb": -0.003},
        ("negativo", "high"): {"var_e": 0.04, "var_b": 0.025, "cov_eb": +0.012},
        ("negativo", "low"):  {"var_e": 0.018, "var_b": 0.012, "cov_eb": +0.004},
    }


def _moments_fail_d_collinear():
    """Momenti costruiti perché i Δ lungo tasso ∝ Δ lungo regime ⇒ collineari."""
    # pos×high - pos×low = (1, 1, 1); pos×high - neg×high = (1, 1, 1) ⇒ cosine=1
    return {
        ("positivo", "high"): {"var_e": 2.0, "var_b": 2.0, "cov_eb": 2.0},
        ("positivo", "low"):  {"var_e": 1.0, "var_b": 1.0, "cov_eb": 1.0},
        ("negativo", "high"): {"var_e": 1.0, "var_b": 1.0, "cov_eb": 1.0},
        ("negativo", "low"):  {"var_e": 0.0, "var_b": 0.0, "cov_eb": 0.0},
    }


def test_gate_PASS_when_intensity_independent_of_regime():
    rng = config.make_rng("gate_pass")
    events = _build_events(rng, intensity_by_regime={
        "positivo": (120, 10.0, 3.0),
        "negativo": (120, 10.0, 3.0),    # stessa distribuzione ⇒ η²≈0, κ≈0
    })
    out = gate.run_gate(events, event_moments=_moments_pass_case())
    v = out["verdicts"]
    # (a) varianza dell'intensità in larga parte within-regime → η² basso
    assert v["a"] is True
    # (b) kappa basso → dimensioni distinte
    assert v["b"] is True
    # (c) celle ≥ 30
    assert v["c"] is True
    # (d) vettori non collineari (costruito così)
    assert v["d"] is True


def test_gate_FAIL_a_and_b_when_intensity_collapsed_on_regime():
    rng = config.make_rng("gate_fail_ab")
    events = _build_events(rng, intensity_by_regime={
        "positivo": (120, 30.0, 1.0),   # intensità ALTE solo qui
        "negativo": (120, 1.0, 1.0),    # intensità BASSE qui
    })
    out = gate.run_gate(events, event_moments=_moments_pass_case())
    v = out["verdicts"]
    # (a) η² alto: tutta la varianza è between-regime
    assert v["a"] is False
    # (b) kappa alto: alta ↔ positivo, bassa ↔ negativo
    assert v["b"] is False


def test_gate_FAIL_d_when_change_vectors_collinear():
    rng = config.make_rng("gate_fail_d")
    events = _build_events(rng, intensity_by_regime={
        "positivo": (120, 10.0, 3.0),
        "negativo": (120, 10.0, 3.0),
    })
    out = gate.run_gate(events, event_moments=_moments_fail_d_collinear())
    v = out["verdicts"]
    assert v["d"] is False
    # (a),(b),(c) restano OK per costruzione
    assert v["a"] is True and v["b"] is True and v["c"] is True


def test_gate_FAIL_c_when_cells_underpopulated():
    rng = config.make_rng("gate_fail_c")
    # solo 20 eventi per regime → max ~10 per cella regime×intensità → sotto 30
    events = _build_events(rng, intensity_by_regime={
        "positivo": (20, 10.0, 3.0),
        "negativo": (20, 10.0, 3.0),
    })
    out = gate.run_gate(events, event_moments=_moments_pass_case())
    assert out["verdicts"]["c"] is False


def test_gate_reports_thresholds_and_provenance():
    rng = config.make_rng("gate_prov")
    events = _build_events(rng, intensity_by_regime={
        "positivo": (60, 10.0, 3.0),
        "negativo": (60, 10.0, 3.0),
    })
    out = gate.run_gate(events, event_moments=_moments_pass_case())
    assert "thresholds_used" in out
    assert out["thresholds_used"]["min_cell"] == config.MIN_CELL_EVENTS
    assert out["config_hash"] == config.config_hash()


def test_gate_raises_on_missing_columns():
    events = pd.DataFrame({"timestamp": [pd.Timestamp("2024-01-01")],
                            "leg": ["FOMC"]})  # manca regime e intensity
    import pytest
    with pytest.raises(ValueError):
        gate.run_gate(events, event_moments={})


def test_gate_handles_missing_cells_in_moments_with_status():
    rng = config.make_rng("gate_missing_d")
    events = _build_events(rng, intensity_by_regime={
        "positivo": (60, 10.0, 3.0),
        "negativo": (60, 10.0, 3.0),
    })
    partial_moments = {
        ("positivo", "high"): {"var_e": 0.05, "var_b": 0.02, "cov_eb": -0.01},
        # mancano 3 celle
    }
    out = gate.run_gate(events, event_moments=partial_moments)
    assert out["criterion_d"]["status"] == "missing_cells"
    assert out["verdicts"]["d"] is None
