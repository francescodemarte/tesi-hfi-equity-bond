"""Guard parametri congelati: candidati a priori, soglie sensibilità, famiglia BY."""
import pytest

import config


def test_protocol_constants_match_run_authoritative():
    assert config.MASTER_SEED == 20260621
    assert config.B_BOOT == 10_000


def test_candidates_locked_a_priori():
    # Tre candidati FISSATI a priori (spec §3): L, V, C
    assert tuple(config.CANDIDATES) == ("L", "V", "C")
    # Segno atteso (spec §3 RIVISTA — risoluzione patologia §2/§3):
    #   L = antisymmetric_pos_eq (λ_e>0, λ_b<0)
    #   V = antisymmetric_neg_eq (λ_e<0, λ_b>0)
    #   C = ambiguous (registrato, non imposto)
    assert config.EXPECTED_SIGN["L"] == "antisymmetric_pos_eq"
    assert config.EXPECTED_SIGN["V"] == "antisymmetric_neg_eq"
    assert config.EXPECTED_SIGN["C"] == "ambiguous"


def test_robust_cells_locked():
    # Spec §1: SOLO celle robuste — FOMC/neg, NFP/neg, CPI/neg, CPI/pos
    expected = {("FOMC", "neg"), ("NFP", "neg"), ("CPI", "neg"), ("CPI", "pos")}
    assert set(tuple(c) for c in config.ROBUST_CELLS) == expected


def test_family_size_for_by():
    # §6: 3 candidati × 4 celle = 12 test primari
    assert config.BY_FAMILY_SIZE == 12
    assert config.BY_Q == 0.10


def test_mop_thresholds_computed_from_source_not_memorized():
    """Spec §7: 'il coder le verifichi alla fonte, non le approssimi a memoria'.
    MOP-Patnaik K=1: cv = ncx2.ppf(0.95, 1, 1/τ)."""
    # τ=10% deve essere 23.1085 (allineato al protocollo)
    assert config.GATE_A_THRESHOLDS["bias_10pct"] == pytest.approx(23.1085, abs=1e-3)
    # τ=20% calcolato (coincide con la stima ~15.1 della spec)
    assert config.GATE_A_THRESHOLDS["bias_20pct"] == pytest.approx(15.0616, abs=1e-2)
    # τ=15% MOP-Patnaik verificato (17.866, NON 19.7 della stima a memoria)
    assert config.GATE_A_THRESHOLDS["bias_15pct"] == pytest.approx(17.8662, abs=1e-2)
    # regola pratica F>10 (Staiger-Stock)
    assert config.GATE_A_THRESHOLDS["practical_F10"] == 10.0


def test_make_rng_deterministic():
    a = config.make_rng("x").random(8); b = config.make_rng("x").random(8)
    assert (a == b).all()


def test_seed_for_int_for_manifest():
    s = config.seed_for("r")
    assert isinstance(s, int) and s == config.seed_for("r")


def test_config_hash_64hex():
    h = config.config_hash()
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)
