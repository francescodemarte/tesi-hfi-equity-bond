"""Test orchestratore: filtri regime, sottocampione FOMC, payoff a due orizzonti."""
import pandas as pd
import pytest

import config
import manifest
import run_strategies as R


def _events_df(rows):
    return pd.DataFrame(rows)


def test_filter_skips_positive_regime_for_cpi():
    df = _events_df([
        {"date": "2015-06-10", "regime": "neg", "surprise": 0.5,
         "r_e_event": 0.01, "r_b_event": 0.01, "r_e_eod": 0.02, "r_b_eod": 0.02},
        {"date": "2015-07-10", "regime": "pos", "surprise": 0.5,
         "r_e_event": 0.01, "r_b_event": 0.01, "r_e_eod": 0.02, "r_b_eod": 0.02},
    ])
    out = R.run_single_strategy(df, "CPI")
    assert out["n_active"] == 1   # solo il neg


def test_fomc_subsample_cap():
    df = _events_df([
        {"date": "2023-06-14", "regime": "neg", "surprise": 0.1,
         "r_e_event": 0.005, "r_b_event": 0.001, "r_e_eod": 0.01, "r_b_eod": 0.002},
        {"date": "2024-03-20", "regime": "neg", "surprise": 0.1,
         "r_e_event": 0.005, "r_b_event": 0.001, "r_e_eod": 0.01, "r_b_eod": 0.002},
    ])
    out = R.run_single_strategy(df, "FOMC")
    # 2024-03-20 oltre il cap 2024-01-31 → 1 solo evento attivo
    assert out["n_active"] == 1


def test_run_all_returns_three_strategies_and_portfolio():
    df_cpi = _events_df([
        {"date": "2015-06-10", "regime": "neg", "surprise": 0.5,
         "r_e_event": 0.01, "r_b_event": 0.01, "r_e_eod": 0.02, "r_b_eod": -0.005},
        {"date": "2015-09-10", "regime": "neg", "surprise": -0.3,
         "r_e_event": -0.005, "r_b_event": -0.005, "r_e_eod": 0.01, "r_b_eod": 0.0},
    ])
    df_nfp = _events_df([
        {"date": "2015-07-03", "regime": "neg", "surprise": 0.7,
         "r_e_event": 0.005, "r_b_event": -0.002, "r_e_eod": 0.01, "r_b_eod": -0.001},
    ])
    df_fomc = _events_df([
        {"date": "2018-03-21", "regime": "neg", "surprise": 0.2,
         "r_e_event": 0.002, "r_b_event": 0.001, "r_e_eod": 0.005, "r_b_eod": 0.002},
        {"date": "2019-09-18", "regime": "neg", "surprise": -0.1,
         "r_e_event": -0.001, "r_b_event": -0.0005, "r_e_eod": -0.003, "r_b_eod": 0.0},
    ])
    out = R.run_all({"CPI": df_cpi, "NFP": df_nfp, "FOMC": df_fomc})
    assert set(out["per_strategy"]) == {"CPI", "NFP", "FOMC"}
    assert out["portfolio"]["scheme"] == "equal"
    assert sum(out["portfolio"]["weights"].values()) == pytest.approx(1.0)
    # entrambi gli orizzonti riportati
    for h in ("event_window", "end_of_day"):
        assert h in out["portfolio"]["metrics"]


def test_run_all_refuses_maximize_sharpe():
    df = _events_df([{"date": "2015-06-10", "regime": "neg", "surprise": 0.5,
                      "r_e_event": 0.01, "r_b_event": 0.01,
                      "r_e_eod": 0.02, "r_b_eod": -0.005}])
    events = {"CPI": df, "NFP": df, "FOMC": df}
    with pytest.raises(ValueError):
        R.run_all(events, scheme="maximize_sharpe")


def test_main_is_blocked():
    with pytest.raises(SystemExit):
        R.main()


def test_manifest_includes_sharpe_table_and_seed_value(tmp_path):
    df = _events_df([{"date": "2015-06-10", "regime": "neg", "surprise": 0.5,
                      "r_e_event": 0.01, "r_b_event": 0.01,
                      "r_e_eod": 0.02, "r_b_eod": -0.005},
                     {"date": "2015-09-10", "regime": "neg", "surprise": -0.3,
                      "r_e_event": -0.005, "r_b_event": -0.005,
                      "r_e_eod": 0.01, "r_b_eod": 0.0}])
    out = R.run_all({"CPI": df, "NFP": df, "FOMC": df})
    fake = tmp_path / "events.csv"; fake.write_text("a\n1\n")
    m = manifest.build_manifest(run_output=out, input_paths=[fake], code_paths=[],
                                 seed_name="run_2026-06-23",
                                 timestamp="2026-06-23T12:00:00Z")
    # 6 voci = 3 strategie × 2 orizzonti + 2 portafoglio
    assert len(m["sharpe_table"]) == 8
    assert m["seed"]["value"] == config.seed_for("run_2026-06-23")
    assert "LORDO" in m["replicability_assumption"]
