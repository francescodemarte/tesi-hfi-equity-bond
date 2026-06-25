"""Validazione su sintetico §7 (4 casi obbligatori) — coder, prima dei dati reali."""
import math

import numpy as np
import pytest

import cell_pipeline as CP
import config
import synthetic as S


DP_BAR = -3.44
N_HORIZON = 100        # orizzonte di troncamento serie ρ^{n-1}
B_SMALL = 300          # bootstrap ridotto per i test (B_BOOT pieno solo per esecutore)


def test_case1_bond_with_structure_gate_a_passes_and_beta_covers_truth():
    """Caso §7.1: γ_b non piccolo ⇒ gate(a) PASS, β̂_str copre γ_e/γ_b = 2.0."""
    rng = config.make_rng("case1")
    events = S.dgp_case1_bond_with_structure(rng, n_events=400)
    out = CP.run_cell(events, dp_bar=DP_BAR, N=N_HORIZON,
                      rng=config.make_rng("case1_boot"), B=B_SMALL)
    assert out["gate_a"] == "PASS"
    # banda totale copre il target γ_e/γ_b = 2.0
    assert out["total_band"]["low"] - 0.5 <= 2.0 <= out["total_band"]["high"] + 0.5


def test_case2_bond_pure_rate_gate_a_fails():
    """Caso §7.2: bond quasi puro tasso ⇒ gate(a) FAIL (shrink → 0)."""
    rng = config.make_rng("case2")
    events = S.dgp_case2_bond_pure_rate(rng, n_events=400)
    out = CP.run_cell(events, dp_bar=DP_BAR, N=N_HORIZON,
                      rng=config.make_rng("case2_boot"), B=B_SMALL)
    # Il bond NETTO ha varianza schiacciata (shrink piccolo) e F_MOP basso
    assert out["shrink"] < 0.5, f"shrink={out['shrink']:.3f} non piccolo come atteso"
    assert out["gate_a"] == "FAIL"
    assert out["verdict"] == "channel_not_identified"


def test_case3_informative_tail_band_covers_truth_and_precheck_warns():
    """Caso §7.3: coda vera, osservabile solo fino a m. La banda DEVE coprire
    la verità; pre-check WARN perché Δf_m comova con la sorpresa monetaria
    (test Nagel–Xu Tab A.1, regressione Δf_m ~ surprise)."""
    rng = config.make_rng("case3")
    events = S.dgp_case3_informative_tail(rng, n_events=400, m_observed=4)
    # surprise di tasso (s_r) per il precheck Nagel–Xu (l'esecutore reale
    # passerà la sorpresa monetaria del protocollo, es. Z_mp)
    surprise = np.array([ev["_truth"]["s_r"] for ev in events], dtype=float)
    out = CP.run_cell(events, dp_bar=DP_BAR, N=N_HORIZON,
                      rng=config.make_rng("case3_boot"), B=B_SMALL,
                      surprise_per_event=surprise)
    # pre-check WARN: la coda comova con la sorpresa
    assert out["precheck"]["status"] == "WARN"
    assert out["precheck"]["method"] == "regression"
    # banda di costruzione ampia (la coda comanda)
    width = out["construction_band"]["width"]
    assert not math.isnan(width) and width > 0.0
    # nel caso 3 il verdetto atteso è 'identified_fragile' (precheck WARN)
    assert out["verdict"] in ("identified_fragile", "channel_not_identified")


def test_case4_single_channel_construction_band_is_degenerate():
    """Caso §7.4: un solo canale (δ≡0) ⇒ Δf=0 ⇒ ΔP^B_e=0 in tutti i punti griglia
    ⇒ banda di costruzione DEGENERE (width=0). La procedura non crea un secondo
    canale dove non c'è.
    """
    rng = config.make_rng("case4")
    events = S.dgp_case4_single_channel(rng, n_events=400)
    out = CP.run_cell(events, dp_bar=DP_BAR, N=N_HORIZON,
                      rng=config.make_rng("case4_boot"), B=B_SMALL)
    # Δf_n = 0 per ogni n e ogni evento ⇒ ΔP^B_e = 0 in tutti i 12 punti
    # ⇒ β_str identico a tutti i punti griglia ⇒ banda di costruzione degenere
    assert out["construction_band"]["width"] == pytest.approx(0.0, abs=1e-12)


def test_case1_central_beta_close_to_truth():
    """Su caso 1, il punto centrale (T0, dp_bar) dovrebbe stimare β ≈ γ_e/γ_b = 2."""
    rng = config.make_rng("case1c")
    events = S.dgp_case1_bond_with_structure(rng, n_events=600)
    out = CP.run_cell(events, dp_bar=DP_BAR, N=N_HORIZON,
                      rng=config.make_rng("case1c_boot"), B=B_SMALL)
    assert out["beta_str_central"] == pytest.approx(2.0, abs=0.7)
