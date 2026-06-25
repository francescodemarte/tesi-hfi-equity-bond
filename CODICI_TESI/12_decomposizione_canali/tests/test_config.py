"""Guard parametri congelati: allineati al run autoritativo a9c13a7b."""
import config


def test_protocol_constants_match_authoritative_run():
    assert config.MASTER_SEED == 20260621
    assert config.B_BOOT == 10_000
    assert config.MOP_CV == 23.1085
    assert config.BY_Q == 0.10


def test_grid_definitions():
    # Coda: 4 punti (T0, TC, TD(0.5), TD(0.8))
    assert tuple(config.TAIL_GRID) == ("T0", "TC", "TD_0.5", "TD_0.8")
    # ρ: 3 valori — dp_bar + offsets {-Δ, 0, +Δ}
    assert tuple(config.RHO_OFFSETS) == (-0.25, 0.0, +0.25)
    assert config.RHO_DEFAULT_DELTA == 0.25
    # 12 punti per evento (equity)
    assert config.GRID_POINTS_PER_EVENT == 12


def test_band_width_threshold_in_config_snapshot():
    """REVIEW #2: il band_threshold DEVE essere un parametro pre-registrato
    nello snapshot (entra in config_hash), non un argomento hardcoded di run_cell."""
    assert config.BAND_WIDTH_THRESHOLD_DEFAULT == 0.30
    snap = config.config_snapshot()
    assert snap["band_width_threshold_default"] == 0.30


def test_seeding_deterministic():
    a = config.make_rng("x").random(8)
    b = config.make_rng("x").random(8)
    assert (a == b).all()


def test_seed_for_int_for_manifest():
    s = config.seed_for("run")
    assert isinstance(s, int)
    assert config.seed_for("run") == s
    assert config.seed_for("run") != config.seed_for("other")


def test_config_hash_64hex():
    h = config.config_hash()
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)
