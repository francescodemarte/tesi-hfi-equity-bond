"""cell_pipeline.py — Orchestratore per cella (leg, regime).

Costruisce per ciascun evento ΔP^B_e su griglia 12-punti e ΔP^B_b unico, fa
netting (Passo 2), stima β_str su ogni punto griglia (Passo 3), calcola
F-MOP e shrink, banda di costruzione, pre-check §3.3, verdetto.

Input atteso (per cella):
  events: lista di dict, ciascuno con:
    {
      r_e_event, r_e_control,        # log-return (rendimenti grezzi)
      r_b_event, r_b_control,
      delta_f_curve,                  # array Δf_n osservati (m punti)
      D_bond, delta_y_bond,           # per ΔP^B_b
    }
  dp_bar: float (medio log(D/P))
  N: orizzonte di troncamento serie ρ^{n-1} (es. 100 o 200)
  rng: np.random.Generator
  B: numero bootstrap (default config.B_BOOT)

Output:
  dict per-cella con: profile (12 punti × β_str), F_MOP, shrink, banda
  costruzione, banda campionaria (CI bootstrap su β_str al punto centrale),
  banda totale, pre-check, verdetto.
"""
from __future__ import annotations

import math

import numpy as np

import bond_pb
import config
import equity_pb
import estimator as Est
import gates as G
import netting


# Identificatore del punto griglia "centrale": T0, offset 0 ⇒ dp_bar invariato.
CENTRAL_TAIL = "T0"
CENTRAL_RHO_OFFSET = 0.0


def _per_event_pb_equity_profile(events, dp_bar, N, tails=None, rho_offsets=None,
                                   delta_f_key="delta_f_curve"):
    """Per ogni evento: profilo griglia di ΔP^B_e (default: 12 = 4 tail × 3 ρ)."""
    profiles = []
    for ev in events:
        prof = equity_pb.delta_pb_equity_full_grid(
            ev[delta_f_key], dp_bar=dp_bar, N=N,
            tails=tails, rho_offsets=rho_offsets,
        )
        profiles.append(prof)
    # Riorganizzazione: per ciascun grid point, restituiamo array per-evento
    n_pts = len(profiles[0])
    by_grid = []
    for k in range(n_pts):
        by_grid.append({
            "tail": profiles[0][k]["tail"],
            "dp_bar_used": profiles[0][k]["dp_bar_used"],
            "rho": profiles[0][k]["rho"],
            "pb_per_event": np.array([p[k]["value"] for p in profiles], dtype=float),
        })
    return by_grid


def _bootstrap_dvar(rb_e, rb_c, B, rng) -> float:
    """Var bootstrap di ΔVar(r̃_b) per F-MOP (REVIEW #3/#5).

    NB convenzionale: qui un "cluster" è una RIGA = un evento col suo
    control matchato (non "evento + 3–10 controlli" come nel 07). Quindi
    ricampiona `n_e` indici di eventi e `n_c` indici di controlli
    indipendentemente, coerente con la struttura cella del 12.
    """
    n_e = len(rb_e); n_c = len(rb_c)
    samples = np.empty(B)
    for b in range(B):
        ie = rng.integers(0, n_e, n_e); ic = rng.integers(0, n_c, n_c)
        samples[b] = float(np.var(rb_e[ie], ddof=1) - np.var(rb_c[ic], ddof=1))
    return float(np.var(samples, ddof=1))


def _bootstrap_beta_sampling_band(re_e_central, rb_e, re_c_central, rb_c,
                                  B, rng, alpha=0.05) -> dict:
    """CI percentile bootstrap su β_str al punto griglia centrale."""
    n_e = len(rb_e); n_c = len(rb_c)
    samples = np.empty(B)
    for b in range(B):
        ie = rng.integers(0, n_e, n_e); ic = rng.integers(0, n_c, n_c)
        ve = float(np.var(rb_e[ie], ddof=1)); vc = float(np.var(rb_c[ic], ddof=1))
        ce = float(np.cov(re_e_central[ie], rb_e[ie], ddof=1)[0, 1])
        cc = float(np.cov(re_c_central[ic], rb_c[ic], ddof=1)[0, 1])
        dV = ve - vc; dC = ce - cc
        samples[b] = (dC / dV) if abs(dV) >= 1e-20 else float("nan")
    lo = float(np.nanpercentile(samples, 100 * alpha / 2))
    hi = float(np.nanpercentile(samples, 100 * (1 - alpha / 2)))
    return {"low": lo, "high": hi}


def run_cell(events: list, *, dp_bar: float, N: int,
             rng=None, B: int = config.B_BOOT,
             band_threshold: float = config.BAND_WIDTH_THRESHOLD_DEFAULT,
             shrink_floor: float = config.SHRINK_FLOOR_DEFAULT,
             surprise_per_event=None,
             bond_method: str = "duration",
             bond_tail: str = "TC",
             equity_tails=None,
             equity_rho_offsets=None) -> dict:
    """Esegue la pipeline su una cella (events: lista per quella cella).

    Restituisce dict con tutte le sezioni della tabella §6 + profilo griglia.
    """
    if rng is None:
        rng = config.make_rng("cell_pipeline_default")
    if not events:
        raise ValueError("events vuoto per la cella")

    # Estrai arrays per-evento
    r_e_event = np.array([ev["r_e_event"] for ev in events], dtype=float)
    r_e_control = np.array([ev["r_e_control"] for ev in events], dtype=float)
    r_b_event = np.array([ev["r_b_event"] for ev in events], dtype=float)
    r_b_control = np.array([ev["r_b_control"] for ev in events], dtype=float)

    # ΔP^B bond per-evento (unico). Due regimi:
    #
    #   bond_method="duration" (LEGACY, default per backward-compat con i test):
    #     ΔP^B_b = -D · Δy   con (D_bond, delta_y_bond) dal dict event.
    #
    #   bond_method="curve" (2026-06-23 fix v2): rivalutazione CTD lungo la curva
    #     osservata, simmetrica a equity_pb, senza ρ-discount.
    #     ΔP^B_b = -Σ_{n=1..N_b} Δf_n con tail extrapolation `bond_tail`,
    #     N_b = round(D_bond_periods) da ev["D_bond_periods"].
    if bond_method == "curve":
        dpb_b_event = np.array(
            [bond_pb.delta_pb_bond_from_curve(
                ev["delta_f_curve"], ev["D_bond_periods"], tail=bond_tail)
             for ev in events], dtype=float)
    elif bond_method == "duration":
        dpb_b_event = np.array(
            [bond_pb.delta_pb_bond(ev["D_bond"], ev["delta_y_bond"])
             for ev in events], dtype=float)
    else:
        raise ValueError(f"bond_method sconosciuto: {bond_method!r}")

    # NETTING SIMMETRICO (Bug 1 lato bond, 2026-06-23).
    if bond_method == "curve":
        # Simmetria stretta: ΔP^B_b_control = stessa formula sul control con
        # `delta_f_curve_control` (richiesto). Implica gate Bug 1 lato bond.
        if not all("delta_f_curve_control" in ev for ev in events):
            raise ValueError("bond_method='curve' richiede delta_f_curve_control "
                             "in ogni event per il netting simmetrico bond")
        dpb_b_control = np.array(
            [bond_pb.delta_pb_bond_from_curve(
                ev["delta_f_curve_control"], ev["D_bond_periods"], tail=bond_tail)
             for ev in events], dtype=float)
    elif all("delta_y_bond_control" in ev for ev in events):
        # Legacy duration con netting simmetrico via proxy daily.
        dpb_b_control = np.array(
            [bond_pb.delta_pb_bond(ev["D_bond"], ev["delta_y_bond_control"])
             for ev in events], dtype=float)
    else:
        dpb_b_control = np.zeros_like(r_b_control)

    # Netting bond (unico per la cella)
    rb_e_tilde = netting.net_bond(r_b_event, dpb_b_event)
    rb_c_tilde = netting.net_bond(r_b_control, dpb_b_control)

    # ΔP^B equity: griglia (default 12 punti, override possibile) × n_events.
    grid_equity = _per_event_pb_equity_profile(
        events, dp_bar=dp_bar, N=N,
        tails=equity_tails, rho_offsets=equity_rho_offsets,
    )
    # NETTING SIMMETRICO (Bug 1 lato equity, 2026-06-23):
    has_control_curve = all("delta_f_curve_control" in ev for ev in events)
    if has_control_curve:
        events_control_view = [
            {"delta_f_curve": ev["delta_f_curve_control"]} for ev in events
        ]
        grid_equity_control = _per_event_pb_equity_profile(
            events_control_view, dp_bar=dp_bar, N=N,
            tails=equity_tails, rho_offsets=equity_rho_offsets,
        )
    else:
        grid_equity_control = None

    profile = []
    central_re_e = None; central_re_c = None
    for k, gp in enumerate(grid_equity):
        dpb_e_event = gp["pb_per_event"]
        if has_control_curve:
            dpb_e_control = grid_equity_control[k]["pb_per_event"]
        else:
            dpb_e_control = np.zeros_like(r_e_control)
        re_e_tilde = netting.net_equity(r_e_event, dpb_e_event)
        re_c_tilde = netting.net_equity(r_e_control, dpb_e_control)
        est = Est.beta_str(re_e_tilde, rb_e_tilde, re_c_tilde, rb_c_tilde)
        profile.append({
            "tail": gp["tail"], "rho": gp["rho"], "dp_bar_used": gp["dp_bar_used"],
            "beta_str": est["beta_str"],
        })
        if gp["tail"] == CENTRAL_TAIL and abs(gp["dp_bar_used"] - dp_bar) < 1e-12:
            central_re_e = re_e_tilde
            central_re_c = re_c_tilde
    if central_re_e is None:
        # Fallback difensivo: nessun punto centrale trovato → solleva (no fabbrica)
        raise ValueError("punto centrale (T0, dp_bar) non presente nella griglia")

    # Shrink: ΔVar(r̃_b)/ΔVar(r_b) — sui rendimenti grezzi del bond
    shrink = Est.shrink_ratio(rb_e_tilde, rb_c_tilde, r_b_event, r_b_control)

    # F-MOP su ΔVar(r̃_b)
    dVar_tilde = float(np.var(rb_e_tilde, ddof=1) - np.var(rb_c_tilde, ddof=1))
    var_dvar = _bootstrap_dvar(rb_e_tilde, rb_c_tilde, B=B, rng=rng)
    F = G.F_MOP_effective(dVar_tilde, var_dvar)
    gate_a_out = G.gate_a(F, shrink=shrink, shrink_floor=shrink_floor)

    # Banda campionaria: bootstrap β al punto centrale
    sampling = _bootstrap_beta_sampling_band(central_re_e, rb_e_tilde,
                                              central_re_c, rb_c_tilde,
                                              B=B, rng=rng)

    # Banda di costruzione: min/max sui 12 punti griglia
    constr = G.construction_band(profile)
    total = G.total_band(constr, sampling)

    # Pre-check §3.3: Δf_m per-evento — usiamo l'ultimo Δf osservato di ciascun evento
    delta_f_m = np.array([float(ev["delta_f_curve"][-1]) for ev in events], dtype=float)
    precheck = G.tail_border_precheck(delta_f_m,
                                       surprise_per_event=surprise_per_event)

    # β_str punto centrale (T0, ρ calibrato)
    central_pt = next(p for p in profile
                       if p["tail"] == CENTRAL_TAIL and abs(p["dp_bar_used"] - dp_bar) < 1e-12)

    verdict = G.cell_verdict(gate_a=gate_a_out["gate_a"], precheck=precheck["status"],
                              band_width=constr["width"] if not math.isnan(constr["width"]) else float("inf"),
                              band_threshold=band_threshold)

    return {
        "n": int(len(events)),
        "shrink": shrink,
        "F_MOP": F,
        "gate_a": gate_a_out["gate_a"],
        "beta_str_central": central_pt["beta_str"],
        "sampling_band": sampling,
        "construction_band": constr,
        "total_band": total,
        "precheck": precheck,
        "verdict": verdict,
        "profile": profile,
        "dp_bar_used": dp_bar,
        "N": N,
    }
