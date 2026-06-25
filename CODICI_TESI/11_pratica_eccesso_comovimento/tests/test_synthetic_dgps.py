"""I 4 DGP a verità nota richiesti dalla spec.

Tutto su DGP sintetici, mai sui dati reali.
"""
import numpy as np
import pandas as pd
import pytest

import config
import run
import synthetic


def _mean(cells, key, sub="strategy", field="mean"):
    return cells[key][sub][field]


# ---- 1. SIGNAL: strategia condizionata batte naive OOS ----------------------

def test_dgp_signal_strategy_beats_benchmark_out_of_sample():
    rng = config.make_rng("signal")
    df = synthetic.dgp_signal(rng, n_train=300, n_test=150)
    out = run.run_strategy(df)
    test_m = out["test_metrics"]
    # gambe e regimi: il payoff atteso medio della strategia condizionata è |e_{g,k}|≈0.30
    # (segno + |ε| nel regime), mentre il naive media i due regimi → ~0.
    for leg in config.LEGS:
        for reg in ("pos", "neg"):
            strat_mean = test_m[(leg, reg)]["strategy"]["mean"]
            assert strat_mean > 0.10, f"({leg}, {reg}): strategy mean troppo bassa: {strat_mean:.3f}"
    # confronto col naive: payoff medio strategia − benchmark deve essere ben positivo
    # in entrambi i regimi (dove la strategia inverte segno coerentemente con e_{g,k})
    for reg in ("pos", "neg"):
        diff = test_m[("COMBINED", reg)]["diff"]["mean_diff"]
        # in pos: naive segue ε pos (≈+0.30, lo stesso della strategia, diff ≈ 0)
        # in neg: naive segue ε neg (≈−0.30) MENTRE la strategia inverte (+0.30) → diff ≈ +0.60
        if reg == "neg":
            assert diff > 0.30, f"diff (combined, neg): {diff:.3f}"


# ---- 2. NOISE: nessun payoff sistematico OOS --------------------------------

def test_dgp_noise_no_systematic_payoff_out_of_sample():
    rng = config.make_rng("noise")
    df = synthetic.dgp_noise(rng, n_train=400, n_test=200)
    out = run.run_strategy(df)
    test_m = out["test_metrics"]
    # ε ~ 0.10·N(0,1) → mean payoff strategia ≈ 0 (entro ~ 0.10/√n ≈ 0.014 per n=50)
    # Soglia conservativa: |mean OOS| < 0.06 per ogni cella (ben sotto il caso "signal").
    for leg in config.LEGS:
        for reg in ("pos", "neg"):
            m = test_m[(leg, reg)]["strategy"]["mean"]
            if test_m[(leg, reg)]["strategy"]["n"] >= 10:
                assert abs(m) < 0.06, f"({leg}, {reg}): mean OOS troppo alto su rumore: {m:.3f}"


# ---- 3. LOOK-AHEAD TRAP: lo split blocca il leakage -------------------------

def test_dgp_lookahead_trap_split_prevents_leakage():
    """Se l'algoritmo calibrasse sul TEST avrebbe payoff alto in OOS (per
    costruzione del DGP). Lo split corretto: e_{g,k} stimato sui SOLI training
    events (rumore puro) ≈ 0 → posizione ≈ 0 o segno casuale → payoff ≈ 0.
    """
    rng = config.make_rng("trap")
    df = synthetic.dgp_lookahead_trap(rng, n_train=400, n_test=200)
    out = run.run_strategy(df)
    # e_{g,k} calibrato sul training: vicino a 0 in tutte le celle
    for (leg, reg), e in out["calibration"]["e_gk"].items():
        assert abs(e) < 0.05, f"e_{leg},{reg} dopo training-rumore: {e:.3f} (deve ≈ 0)"


def test_dgp_lookahead_trap_test_payoff_near_zero_in_expectation_monte_carlo():
    """REVIEW #4 rinforzo: il payoff OOS è ≈ 0 IN ATTESA su molti seed.

    Diagnosi della logica: con `min_abs=0` (default) `position_for` restituisce
    sempre ±1 anche per e_{g,k}≈0 (training-rumore ⇒ segno CASUALE). Sul
    singolo run l'OOS è ≈ ±|μ_test|. Solo MEDIANDO su molti seed la media dei
    sign-casuali si annulla e l'OOS_mean tende a 0 — questa è la lettura
    matematicamente corretta del "trap blocca il leakage".
    """
    n_seeds = 30
    means_per_cell = {(leg, reg): [] for leg in config.LEGS for reg in ("pos", "neg")}
    for s in range(n_seeds):
        rng = config.make_rng(f"trap_oos_{s}")
        df = synthetic.dgp_lookahead_trap(rng, n_train=400, n_test=200)
        out = run.run_strategy(df)
        for leg in config.LEGS:
            for reg in ("pos", "neg"):
                cell = out["test_metrics"][(leg, reg)]["strategy"]
                if cell["n"] >= 10:
                    means_per_cell[(leg, reg)].append(cell["mean"])
    for k, vs in means_per_cell.items():
        assert len(vs) >= n_seeds // 2, f"troppi seed senza n≥10 per {k}"
        avg = float(np.mean(vs))
        # In attesa: media dei sign casuali ≈ 0 ⇒ media degli OOS ≈ 0.
        # Su 30 seed, |avg| < 0.15 con tolleranza generosa.
        assert abs(avg) < 0.15, f"{k} OOS_mean medio su {n_seeds} seed: {avg:.3f}"


def test_calibrate_raises_if_test_events_leak_in():
    """PRESIDIO STRUTTURALE: passando eventi del test a `calibration.calibrate`
    direttamente (bypassando lo split di run_strategy), la funzione SOLLEVA."""
    import calibration as C
    rng = config.make_rng("trap_struct")
    df = synthetic.dgp_lookahead_trap(rng, n_train=10, n_test=10)
    with pytest.raises(ValueError, match="leakage"):
        C.calibrate(df, training_end=config.SPLIT_DATE)


# ---- 4. IMBALANCED: regime positivo raro OOS → inconcludente ---------------

def test_dgp_imbalanced_positive_regime_inconclusive_on_test():
    rng = config.make_rng("imbal")
    df = synthetic.dgp_imbalanced(rng, n_train=400, n_test=200, pos_test_frac=0.05)
    out = run.run_strategy(df)
    # nel test, il regime positivo ha pochissimi eventi → verdetto inconclusive
    for leg in config.LEGS:
        cell = out["test_metrics"][(leg, "pos")]["strategy"]
        # n basso (qui n_test=200·0.05/2 gambe ≈ 5)
        assert cell["n"] < config.MIN_CELL_N_FOR_VERDICT
        assert cell["verdict"] == "inconclusive"
    # il regime negativo invece è ben popolato → verdetto reportable
    neg_n_total = sum(out["test_metrics"][(l, "neg")]["strategy"]["n"] for l in config.LEGS)
    assert neg_n_total >= config.MIN_CELL_N_FOR_VERDICT
