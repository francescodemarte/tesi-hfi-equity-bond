"""Guard parametri congelati + logica seeding."""
import config


def test_locked_window_us():
    # W^US_j = [t_j − 10min, t_j + 20min]
    assert config.TAU_PRE_MIN == 10
    assert config.TAU_POST_MIN == 20


def test_locked_bootstrap_and_seed():
    assert config.B_BOOT == 10_000
    assert config.SPILLOVER_MASTER_SEED == 20260622  # dedicato, separa provenance dal 07


def test_locked_multiplicity():
    assert config.BY_Q == 0.10
    assert config.T_H1_ALPHA == 0.05   # primaria, fuori BY
    # Famiglia secondaria FISSA: H2, H3, H4 (m=3 a priori)
    assert tuple(config.BY_SECONDARY_FAMILY) == ("H2", "H3", "H4")
    assert config.BY_M == 3
    assert config.BY_M == len(config.BY_SECONDARY_FAMILY)


def test_locked_us_rate_basket():
    # m_j = PC1 di queste 5 serie nella finestra W^US (Fed funds c1/c2 + ED 2/3/4)
    basket = tuple(config.US_SHORT_RATE_BASKET)
    assert basket == ("FF_c1", "FF_c2", "ED_q2", "ED_q3", "ED_q4")
    assert config.SP500_INSTRUMENT == "ES"


def test_locked_eu_assets():
    # Stadio 1: Bund 10Y (bp), Euro Stoxx 50 (log-return), BTP–Bund 10Y (bp)
    assert config.EU_ASSETS["BUND_10Y"] == "yield_bp"
    assert config.EU_ASSETS["ESTOXX50"] == "log_return"
    assert config.EU_ASSETS["BTP_BUND_SPREAD"] == "yield_bp"


def test_locked_t5yie_banned_globally():
    # ΔT5YIE / breakeven banditi come strumento (coerenza col protocollo principale)
    assert "dt5yie" in {s.lower() for s in config.FORBIDDEN_SOURCES}
    assert "breakeven" in {s.lower() for s in config.FORBIDDEN_SOURCES}


def test_make_rng_deterministic_per_name():
    a = config.make_rng("h1_yB").random(8)
    b = config.make_rng("h1_yB").random(8)
    assert (a == b).all()


def test_make_rng_differs_across_names():
    a = config.make_rng("h1_yB").random(8)
    b = config.make_rng("h2_rES").random(8)
    assert not (a == b).all()


def test_seed_for_int_and_stable():
    s1 = config.seed_for("h4_attrib")
    s2 = config.seed_for("h4_attrib")
    assert s1 == s2 and isinstance(s1, int)
    assert config.seed_for("h1_yB") != config.seed_for("h2_rES")


def test_config_hash_deterministic_64hex():
    h = config.config_hash()
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)
    assert config.config_hash() == h


def test_config_snapshot_records_locked_values():
    snap = config.config_snapshot()
    assert snap["b_boot"] == 10_000
    assert snap["spillover_master_seed"] == 20260622
    assert snap["by_m"] == 3
    assert snap["tau_pre_min"] == 10 and snap["tau_post_min"] == 20
