"""Guard parametri congelati: β_str, regimi, orizzonti, sottocampione FOMC."""
import pandas as pd
import pytest

import config


def test_beta_str_locked_from_spec():
    # Numeri ESATTI dalla spec — nessuna stima, nessuna riottimizzazione
    assert config.BETA_STR["CPI"] == pytest.approx(+0.95)
    assert config.BETA_STR["NFP"] == pytest.approx(-1.40)
    assert config.BETA_STR["FOMC"] == pytest.approx(+0.87)


def test_active_regime_per_strategy_locked():
    # Tutte e tre attive SOLO in regime negativo (spec)
    assert config.ACTIVE_REGIME["CPI"] == "neg"
    assert config.ACTIVE_REGIME["NFP"] == "neg"
    assert config.ACTIVE_REGIME["FOMC"] == "neg"


def test_two_horizons_both_reported():
    # Entrambi obbligatori, mai selezione
    assert tuple(config.HORIZONS) == ("event_window", "end_of_day")


def test_event_window_minutes_match_protocol():
    assert config.EVENT_WINDOW_MIN == 15


def test_regime_window_anti_lookahead():
    # 63 sedute, lag t-1: stessa convenzione del protocollo principale
    assert config.REGIME_WINDOW_DAYS == 63
    assert config.REGIME_LAG_BDAYS == 1


def test_fomc_subsample_cap_locked():
    # JK disponibile fino a gennaio 2024 — sottocampione 2010..2024
    assert config.FOMC_SUBSAMPLE_END == pd.Timestamp("2024-01-31")


def test_portfolio_weights_schemes_a_priori():
    # 2 schemi DICHIARATI a priori, nessuno scelto sui rendimenti
    assert "equal" in config.PORTFOLIO_WEIGHT_SCHEMES
    assert "inverse_vol_on_training" in config.PORTFOLIO_WEIGHT_SCHEMES
    assert config.PORTFOLIO_WEIGHT_DEFAULT == "equal"


def test_strategies_locked():
    assert tuple(config.STRATEGIES) == ("CPI", "NFP", "FOMC")


def test_seed_protocol_aligned():
    assert config.MASTER_SEED == 20260621


def test_config_hash_64hex_and_includes_betas():
    h = config.config_hash()
    assert len(h) == 64
    snap = config.config_snapshot()
    assert snap["beta_str"]["NFP"] == pytest.approx(-1.40)
    assert snap["horizons"] == list(config.HORIZONS)


def test_beta_str_provenance_dichiarata():
    """REVIEW #1 BLOCKER: BETA_STR_PROVENANCE deve esistere e marcare status."""
    prov = config.BETA_STR_PROVENANCE
    assert prov["status"] == "illustrative_pending_07_estimation"
    # Disclaimer cita 'condizionali' o equivalente
    assert "condizional" in prov["disclaimer"].lower()
    # Snapshot include provenance ⇒ config_hash cambia se cambia
    snap = config.config_snapshot()
    assert "beta_str_provenance" in snap


def test_manifest_replicability_dichiarata_provenance_beta():
    import manifest
    m = manifest.build_manifest(run_output={"per_strategy": {}, "portfolio": {}},
                                 input_paths=[], code_paths=[],
                                 seed_name="x", timestamp="T")
    # Punto 8 deve citare la provenance illustrativa dei β
    assert "PROVENANCE β_str" in m["replicability_assumption"]
    assert "ILLUSTRATIVI" in m["replicability_assumption"]
    assert "CONDIZIONALE" in m["replicability_assumption"]


def test_seed_for_int_for_manifest():
    s = config.seed_for("run")
    assert isinstance(s, int) and s == config.seed_for("run")
