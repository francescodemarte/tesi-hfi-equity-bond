"""Validazione coder su sintetico (spec §9, 4 casi obbligatori)."""
import math

import numpy as np
import pytest

import config
import pipeline as P
import synthetic as S


def _build_cell_inputs(dgp_out: dict) -> dict:
    """Replica lo STESSO DGP su tutte le 4 celle robuste (per testare la BY su
    famiglia 12). β_str non viene rivisto qui (gli output sono già "netti" per
    costruzione: r̃_e, r̃_b dal DGP). Per la pipeline diamo β_str=1 e una sorpresa
    indipendente dal DGP (s del DGP).
    """
    out = {}
    for cell in config.ROBUST_CELLS:
        out[tuple(cell)] = {
            "r_e_tilde": dgp_out["r_e_tilde"],
            "r_b_tilde": dgp_out["r_b_tilde"],
            "beta_str": 1.0,
            "surprise": dgp_out["s"],
        }
    return out


def _build_candidate_proxies(z, candidates=("L", "V", "C")) -> dict:
    """Stessa proxy z usata su tutti i 3 candidati per stress-test della BY.

    NB: in produzione i 3 candidati hanno PROXY diverse (L, V, C). Qui usiamo
    la stessa per esercitare il meccanismo end-to-end. Il segno atteso resta
    quello a priori (concordant, both_negative, ambiguous) — il test sarà
    soddisfatto se il sign atteso coincide col DGP costruito.
    """
    out = {}
    for cell in config.ROBUST_CELLS:
        out[tuple(cell)] = {c: {"z": z, "expected_sign": config.EXPECTED_SIGN[c]}
                             for c in candidates}
    return out


# ===== §9.1: terzo canale PRESENTE (concordant per λ_e=+1.5, λ_b=+1.2) =====

def test_dgp_case1_detects_third_channel_for_concordant_candidate():
    rng = config.make_rng("case1")
    dgp = S.dgp_case1_third_channel_present(rng, n=500,
        lambda_e=+1.5, lambda_b=+1.2)
    out = P.run_full_protocol(_build_cell_inputs(dgp),
                                _build_candidate_proxies(dgp["z"]))
    # Per "L" (concordant): segni positivi → sign_ok=True; comunalità + BY → terzo canale
    found_any_L = any(out["verdicts"][(c, "L")]["third_channel"]
                       for c in [tuple(x) for x in config.ROBUST_CELLS])
    assert found_any_L, "DGP §9.1 con λ_e=λ_b=+ deve dichiarare L su almeno una cella"


# ===== §9.2: NESSUN terzo canale (falsificazione) =========================

def test_dgp_case2_no_third_channel_declared():
    rng = config.make_rng("case2")
    dgp = S.dgp_case2_no_third_channel(rng, n=500)
    out = P.run_full_protocol(_build_cell_inputs(dgp),
                                _build_candidate_proxies(dgp["z"]))
    # Su rumore, nessuna delle 12 deve dichiarare terzo canale (BY controlla FPR)
    declared = sum(1 for v in out["verdicts"].values() if v["third_channel"])
    assert declared == 0, f"falsi positivi attesi 0, trovati {declared}"


# ===== §9.3: fattore solo-equity (λ_b = 0) — comunalità deve FALLIRE ======

def test_dgp_case3_equity_only_documents_structural_false_positive_for_L():
    """DGP solo-equity (λ_b=0 nel DGP, λ_e=+1.5).

    Sotto la spec §3 RIVISTA ("antisymmetric_*_eq"):
      - La patologia §2 produce empiricamente coef_e ≈ +1.5 e coef_b ≈ −1.5/β
        (segno opposto, antisimmetria forzata).
      - "L" = `antisymmetric_pos_eq`: λ_e > 0 ∧ λ_b < 0 → sign_ok = True
        (la patologia produce esattamente quel pattern di segni).
      - Comunalità soddisfatta (entrambi statisticamente ≠ 0 dato il
        carico equity grande).
      → L può essere DICHIARATO terzo canale anche su un DGP equity-only.
      Questo è il FALSO POSITIVO STRUTTURALE documentato della spec §2:
      la sign rule rivista non distingue "vero terzo canale" da "fattore
      solo-equity" perché la spec §2 forza l'antisimmetria nei residui.

      - "V" = `antisymmetric_neg_eq`: richiede λ_e < 0. Qui λ_e ≈ +1.5 > 0
        → sign_ok = False → V NON dichiarato. La sign rule mantiene quindi
        la discriminazione di SENSO (positivo vs negativo) anche se non
        quella di "magnitudine del bond".

    Lettura interpretativa (dichiarata nel report dell'esecutore):
      una dichiarazione "L" sotto la nuova spec significa che la cella ha
      attività residua significativa con λ_e > 0; non garantisce che il
      bond contribuisca indipendentemente al canale.
    """
    rng = config.make_rng("case3")
    dgp = S.dgp_case3_equity_only(rng, n=500, lambda_e=+1.5)
    out = P.run_full_protocol(_build_cell_inputs(dgp),
                                _build_candidate_proxies(dgp["z"]))
    # L può essere dichiarato (falso positivo strutturale). V no (sign su λ_e fallisce).
    for c in [tuple(x) for x in config.ROBUST_CELLS]:
        assert out["verdicts"][(c, "V")]["third_channel"] is False, \
            f"V su {c}: dichiarato terzo canale — sign rule λ_e<0 doveva fallire"
    # Almeno una cella dichiara L (è il falso positivo strutturale post-patologia).
    declared_L = sum(1 for c in [tuple(x) for x in config.ROBUST_CELLS]
                     if out["verdicts"][(c, "L")]["third_channel"])
    assert declared_L >= 1, (
        "Atteso falso positivo strutturale su L (DGP equity-only): "
        "la patologia §2 forza coef_b<0 dato λ_e>0, e la sign rule "
        "'antisymmetric_pos_eq' accetta il pattern. Nessuna cella ha "
        "dichiarato L → la sign rule non è coerente con la spec rivista."
    )


# ===== §9.4: Z correlato con sorpresa → dopo ortogonalizzazione svanisce ==

def test_dgp_case4_z_correlated_with_surprise_orthogonalization_kills_signal():
    """Senza ortogonalizzazione: Z spiegherebbe il residuo perché è α·s + η.
    Con ortogonalizzazione (default in pipeline): la componente di Z legata
    a s viene tolta, e poiché NON c'è λ genuino, il residuo del residuo
    è rumore → no terzo canale.
    """
    rng = config.make_rng("case4")
    dgp = S.dgp_case4_z_correlated_with_surprise(rng, n=500, alpha_zs=1.5)
    out = P.run_full_protocol(_build_cell_inputs(dgp),
                                _build_candidate_proxies(dgp["z"]))
    declared = sum(1 for v in out["verdicts"].values() if v["third_channel"])
    assert declared == 0, (f"ortogonalizzazione deve spegnere il falso positivo "
                            f"da Z correlato a sorpresa; dichiarati: {declared}")
