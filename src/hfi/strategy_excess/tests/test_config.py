"""Guard parametri congelati + seeding + split."""
import pandas as pd
import config


def test_legs_only_nfp_cpi_no_spillover():
    assert tuple(config.LEGS) == ("NFP", "CPI")


def test_regime_windows_and_endpoint():
    assert config.REGIME_WINDOW_DAYS == 63
    assert config.REGIME_END_OFFSET_DAYS == 4
    assert tuple(config.EXPECTATION_WINDOW) == (-3, -1)


def test_split_dates_locked():
    assert config.TRAINING_START == pd.Timestamp("2010-01-01")
    assert config.SPLIT_DATE == pd.Timestamp("2021-01-01")
    assert config.TEST_END == pd.Timestamp("2025-12-31")


def test_thresholds_and_seeding():
    assert config.MASTER_SEED == 20260622
    assert config.INV_VOL_ROLLING_EVENTS == 20
    assert config.MIN_ABS_E_FOR_POSITION == 0.0
    assert config.MIN_CELL_N_FOR_VERDICT == 20


def test_seed_for_int_stable():
    # REVIEW #2: serve `seed_for(name) -> int` per scriverlo nel manifest
    s1 = config.seed_for("h1")
    s2 = config.seed_for("h1")
    assert s1 == s2 and isinstance(s1, int)
    assert config.seed_for("h1") != config.seed_for("h2")


def test_make_rng_deterministic():
    a = config.make_rng("x").random(8)
    b = config.make_rng("x").random(8)
    assert (a == b).all()


def test_config_hash_64hex():
    h = config.config_hash()
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)
