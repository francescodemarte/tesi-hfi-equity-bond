"""Test report (contratto di output) + run (orchestratore che NON esegue sui reali)."""
import json
from pathlib import Path

import numpy as np
import pytest

import config
import regression as reg
import tests_h as th
import report
import run


def _toy_fit(rng, gamma, delta, n=1500):
    Z_mp = rng.standard_normal(n); Z_cbi = rng.standard_normal(n)
    x = rng.standard_normal(n)
    u = rng.standard_normal(n) * 0.3
    y = gamma * Z_mp + delta * Z_cbi + 0.1 * x + u
    X = np.column_stack([Z_mp, Z_cbi, x])
    return reg.ols_hc(y, X, names=("Z_mp", "Z_cbi", "x"))


# --- contratto OUTPUT: ogni asset porta γ̂, δ̂, SE, t, p, esito BY ---------

def test_build_asset_row_contains_all_required_fields():
    rng = np.random.default_rng(0)
    fit = _toy_fit(rng, gamma=+0.5, delta=-0.3)
    row = report.build_asset_row(asset="BUND_10Y", fit=fit,
                                 hypothesis_test=th.T_H1(fit, coef="Z_mp"),
                                 by_decision=True)
    for k in ("asset", "gamma", "delta", "gamma_se", "delta_se",
              "t", "p_one_sided", "by_decision",
              "reading_existence", "reading_attribution"):
        assert k in row, f"campo mancante: {k}"


def test_build_asset_row_explicit_two_readings():
    rng = np.random.default_rng(1)
    fit = _toy_fit(rng, gamma=+0.7, delta=0.0)
    row = report.build_asset_row(asset="BUND_10Y", fit=fit,
                                 hypothesis_test=th.T_H1(fit, coef="Z_mp"),
                                 by_decision=None)
    # esistenza: precedenza + no-confondente (sempre dichiarata)
    assert "precedenza" in row["reading_existence"].lower()
    # attribuzione: condizionale alla separazione di segno
    assert "separazione" in row["reading_attribution"].lower() or \
           "attribuzione" in row["reading_attribution"].lower()


# --- manifest finale: provenance + seed + B + config_hash -----------------

def test_build_manifest_records_seed_B_and_config_hash():
    m = report.build_manifest(
        included_events=42, excluded_events=8,
        seed_name="run_baseline", timestamp="2026-06-22T12:00:00Z",
    )
    assert m["b_boot"] == 10_000
    assert m["seed"]["name"] == "run_baseline"
    assert m["seed"]["value"] == config.seed_for("run_baseline")
    assert m["config_hash"] == config.config_hash()
    assert m["n_events_included"] == 42 and m["n_events_excluded"] == 8


def test_build_manifest_no_clock_internal():
    # timestamp DEVE essere passato dall'esterno
    with pytest.raises(TypeError):
        report.build_manifest(included_events=0, excluded_events=0,
                              seed_name="x")  # manca timestamp


def test_write_report_serializes_json(tmp_path):
    rng = np.random.default_rng(2)
    fits = {a: _toy_fit(rng, gamma=+0.3, delta=-0.2) for a in ("BUND_10Y", "ESTOXX50")}
    asset_rows = [
        report.build_asset_row(asset=a, fit=fits[a],
                               hypothesis_test=th.T_H1(fits[a], coef="Z_mp"),
                               by_decision=False)
        for a in fits
    ]
    out = report.write_report(tmp_path / "out" / "report.json",
                              asset_rows=asset_rows,
                              manifest=report.build_manifest(
                                  included_events=10, excluded_events=0,
                                  seed_name="run", timestamp="T"),
                              timestamp="T")
    p = Path(out["path"]); assert p.exists()
    loaded = json.loads(p.read_text())
    assert len(loaded["asset_rows"]) == 2
    assert loaded["manifest"]["config_hash"] == config.config_hash()


# --- run.py: orchestratore NON deve eseguire sui dati reali --------------

def test_run_main_refuses_to_run_on_real_data():
    # main() è il blocco difensivo: solleva (esecuzione reale è dell'esecutore).
    with pytest.raises(SystemExit):
        run.main()


def test_run_protocol_full_rejects_forbidden_basket_label():
    # BLOCKER review #4: validate_source DEVE essere invocata sul percorso runtime.
    # Se l'esecutore passa `basket_labels` con una sorgente vietata (es. ΔT5YIE),
    # la pipeline deve SOLLEVARE, non procedere silenziosamente.
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError):
        run.run_protocol_full(
            m=rng.standard_normal(100), s=rng.standard_normal(100),
            responses={"BUND_10Y": rng.standard_normal(100)},
            basket_labels=("FF_c1", "FF_c2", "dT5YIE"),    # ← vietata
            seed_name="x",
        )


def test_run_protocol_full_rejects_forbidden_surprise_label():
    # Anche `surprise_source` (etichetta della sorpresa s_j) va validata.
    rng = np.random.default_rng(1)
    with pytest.raises(ValueError):
        run.run_protocol_full(
            m=rng.standard_normal(100), s=rng.standard_normal(100),
            responses={"BUND_10Y": rng.standard_normal(100)},
            surprise_label="breakeven",                    # ← vietata
            seed_name="x",
        )


def test_run_protocol_full_on_synthetic_inputs_returns_complete_output(tmp_path):
    # Smoke end-to-end su DATI SINTETICI passati come input (mai sui reali).
    # DGP con struttura JK identificata (Cov(m,s) ≠ 0) — necessario per il gate
    # di esistenza in separate_jk (review BLOCKER #1).
    rng = np.random.default_rng(7)
    n = 200
    mp = rng.standard_normal(n); cbi = rng.standard_normal(n)
    m_arr = 1.0 * mp + 1.5 * cbi + 0.05 * rng.standard_normal(n)
    s_arr = -0.5 * mp + 1.5 * cbi + 0.05 * rng.standard_normal(n)
    out = run.run_protocol_full(
        m=m_arr, s=s_arr,
        responses={"BUND_10Y": rng.standard_normal(n) * 5,
                    "ESTOXX50": rng.standard_normal(n) * 0.01,
                    "BTP_BUND_SPREAD": rng.standard_normal(n) * 3},
        controls=np.column_stack([rng.standard_normal(n), rng.standard_normal(n)]),
        controls_names=("global_risk", "subperiod"),
        manifest_path=tmp_path / "m.json",
        manifest_timestamp="2026-06-22T12:00:00Z",
        seed_name="smoke",
        basket_labels=("FF_c1", "FF_c2", "ED_q2", "ED_q3", "ED_q4"),
        surprise_label="ES",
    )
    for k in ("h1", "h2", "h3", "h4", "hierarchy", "asset_rows", "manifest"):
        assert k in out, f"missing section: {k}"
    # Review #8: concordance non orfana, sempre nel return
    assert "concordance" in out
    assert set(out["concordance"]) >= {"mp", "cbi", "n"}
