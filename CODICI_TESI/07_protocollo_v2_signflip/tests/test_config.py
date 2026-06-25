"""Test di config.py.

Due ruoli:
1. **Guard sui parametri congelati** (§5 spec): bloccano i valori pre-registrati.
   Per un artefatto pre-registrato il drift di un parametro è il peccato capitale,
   quindi questi test passano-subito *di proposito* (regression guard).
2. **TDD stretto sulla logica**: make_rng / seed_for / config_hash sono logica,
   testati prima dell'implementazione.
"""
import config


# --- Guard parametri congelati ---

def test_locked_window_params():
    assert config.HALF_MIN_WINDOW == 15
    assert config.MEDIAN_EDGE_MIN == 5


def test_locked_control_params():
    assert config.K_CONTROL_TARGET == 5
    assert config.K_CONTROL_MIN == 3
    assert config.K_CONTROL_MAX == 10


def test_locked_nmin():
    assert config.N_MIN == 30


def test_locked_mop_params():
    assert config.MOP_K == 1
    assert config.MOP_WORST_CASE_SIZE == 0.10
    assert config.MOP_NOMINAL_LEVEL == 0.05


def test_locked_multiplicity():
    assert config.NFP_PRIMARY == "NFP"
    assert config.NFP_ALPHA == 0.05
    assert config.BY_Q == 0.10
    assert config.BY_M == 3
    assert tuple(config.BY_SECONDARY_FAMILY) == ("CPI", "FOMC", "ECB")
    # NFP è primario → fuori dalla famiglia BY
    assert config.NFP_PRIMARY not in config.BY_SECONDARY_FAMILY
    # m=3 = cardinalità della famiglia, fissa a priori
    assert config.BY_M == len(config.BY_SECONDARY_FAMILY)


def test_locked_bootstrap_and_seed():
    assert config.B_BOOT == 10000
    assert config.MASTER_SEED == 20260621


def test_locked_regime_params():
    assert config.REGIME_WINDOW_DAYS == 63
    assert config.REGIME_WINDOW_DAYS_ROBUST == 126
    assert config.REGIME_LAG_BDAYS == 1
    assert config.REGIME_THRESHOLD == 0.0


def test_locked_ar_grid():
    assert config.AR_BETA_LOW == -3.0
    assert config.AR_BETA_HIGH == 7.0
    assert config.AR_STEP == 0.005


# --- E3: parametri congelati (T7 regimi esogeni + T8(d) soglia inflazionistica) ---

def test_locked_t7_exogenous_e3():
    # T10Y2Y e VIXCLS OBBLIGATORI; MOVE opzionale-se-disponibile
    assert tuple(config.T7_EXOGENOUS_REQUIRED) == ("T10Y2Y", "VIXCLS")
    assert tuple(config.T7_EXOGENOUS_OPTIONAL) == ("MOVE",)
    # Finestra mediana rolling CAUSALE = 252 giorni lavorativi; lag t-1
    assert config.T7_ROLLING_DAYS == 252
    assert config.T7_LAG_BDAYS == 1


def test_locked_t8d_inflation_threshold_e3():
    # 2x target Fed (2%) — ancora a priori
    assert config.T8D_CPI_YOY_THRESHOLD == 0.04
    # serie CPI YoY US (sigla mnemonica FRED del livello, da cui si deriva YoY)
    assert config.T8D_CPI_LEVEL_SERIES == "CPIAUCSL"


def test_event_types_and_maps_consistent():
    assert tuple(config.EVENT_TYPES) == ("FOMC", "CPI", "NFP", "ECB")
    for t in config.EVENT_TYPES:
        assert t in config.INSTRUMENT_MAP
        assert t in config.EVENT_TZ
    # US su ES/TY, EU su STXE/FGBL
    assert config.INSTRUMENT_MAP["NFP"] == ("ES", "TY")
    assert config.INSTRUMENT_MAP["ECB"] == ("STXE", "FGBL")
    assert config.EVENT_TZ["ECB"] == "Europe/Berlin"
    assert config.EVENT_TZ["NFP"] == "America/New_York"


# --- TDD logica ---

def test_make_rng_deterministic_for_same_name():
    a = config.make_rng("t1_relevance").random(8)
    b = config.make_rng("t1_relevance").random(8)
    assert (a == b).all()


def test_make_rng_differs_across_names():
    a = config.make_rng("t1_relevance").random(8)
    b = config.make_rng("t5_signflip").random(8)
    assert not (a == b).all()


def test_seed_for_stable_and_int():
    s1 = config.seed_for("t5_signflip")
    s2 = config.seed_for("t5_signflip")
    assert s1 == s2
    assert isinstance(s1, int)
    assert config.seed_for("t1_relevance") != config.seed_for("t5_signflip")


def test_config_hash_deterministic_and_64hex():
    h1 = config.config_hash()
    h2 = config.config_hash()
    assert h1 == h2
    assert len(h1) == 64
    assert all(c in "0123456789abcdef" for c in h1)


def test_config_snapshot_carries_locked_values():
    snap = config.config_snapshot()
    assert snap["b_boot"] == 10000
    assert snap["by_m"] == 3
    assert snap["n_min"] == 30
    assert snap["config_version"] == config.CONFIG_VERSION
