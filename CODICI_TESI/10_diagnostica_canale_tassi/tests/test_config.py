"""Guard parametri congelati del cancello."""
import config


def test_window_half_min_match_protocol():
    # ±15 min: stessa finestra usata per equity/bond nel protocollo v2
    assert config.HALF_MIN_WINDOW == 15
    assert config.MEDIAN_EDGE_MIN == 5


def test_default_rate_contract_is_FFc2():
    assert config.RATE_CONTRACT_DEFAULT == "FFc2"
    assert "FFc3" in config.RATE_CONTRACT_SUPPORTED
    assert "FEIc1" in config.RATE_CONTRACT_SUPPORTED


def test_event_types_supported():
    assert tuple(config.EVENT_TYPES) == ("NFP", "CPI", "FOMC", "ECB")


def test_min_cell_threshold():
    # PARTE: "Una cella sotto soglia non identifica il canale lì" — default 30
    assert config.MIN_CELL_EVENTS == 30


def test_master_seed_dedicated():
    assert config.MASTER_SEED == 20260622   # dedicato (separazione provenance)


def test_make_rng_deterministic():
    a = config.make_rng("x").random(8)
    b = config.make_rng("x").random(8)
    assert (a == b).all()


def test_partition_modes_supported():
    # dicotomizzazione: mediana within-sample (default) + opzione terzili (estremi)
    assert "median" in config.PARTITION_MODES
    assert "tertile_extremes" in config.PARTITION_MODES
