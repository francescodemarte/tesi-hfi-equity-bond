"""mechanism.py — Test T9 «meccanismo / due gambe» (inferenza descrittiva).

Per ogni regime (positivo/negativo) si stima la pendenza univariata della
reazione dell'equity e del bond alla sorpresa s:

    pendenza = Cov(r, s, ddof=1) / Var(s, ddof=1).

Il rapporto delle due pendenze è il beta implicito (slope_eq/slope_bond).
Confrontando i due regimi si diagnostica quale «gamba» inverte il segno:
se inverte l'equity, il bond, entrambe o nessuna.

Riempimento gateato (C0.4): un regime alimenta l'inferenza solo se la sua
sorpresa s passa `surprises.coverage_variance_gate` (≥ N_MIN sorprese valide
e varianza non degenere). Se un regime non è alimentabile resta None e il
meccanismo è dichiarato «aperto» (open=True): in tal caso la diagnostica di
inversione non è determinabile (*_inverts = None).
"""
from __future__ import annotations

import numpy as np

import config
import surprises

_EPS = 1e-20


def leg_slope(r, s) -> float:
    """Pendenza OLS univariata: Cov(r, s, ddof=1) / Var(s, ddof=1).

    np.nan se Var(s) <= 0 (sorpresa degenere, pendenza non identificata).
    """
    r = np.asarray(r, dtype=float)
    s = np.asarray(s, dtype=float)
    var_s = float(np.var(s, ddof=1))
    if var_s <= 0.0:
        return np.nan
    cov_rs = float(np.cov(r, s, ddof=1)[0, 1])
    return cov_rs / var_s


def leg_slopes(r_e, r_b, s) -> dict:
    """Pendenze delle due gambe e beta implicito per un regime.

    slope_eq   = leg_slope(r_e, s)
    slope_bond = leg_slope(r_b, s)
    beta_impl  = slope_eq / slope_bond  (np.nan se |slope_bond| < 1e-20)
    n          = numerosità (len(s))
    """
    slope_eq = leg_slope(r_e, s)
    slope_bond = leg_slope(r_b, s)
    if abs(slope_bond) < _EPS:
        beta_impl = np.nan
    else:
        beta_impl = slope_eq / slope_bond
    return {
        "slope_eq": slope_eq,
        "slope_bond": slope_bond,
        "beta_impl": beta_impl,
        "n": int(len(s)),
    }


def mechanism(per_regime, n_min=None, source_label=None) -> dict:
    """Test T9: pendenze per regime e diagnostica della gamba che inverte.

    `source_label` (l'esecutore lo passa, es. da `surprises.surprise_source(t)`):
    se fornito è validato → guardia ΔT5YIE sul percorso del meccanismo.

    `per_regime` = {"positivo": {"r_e":.., "r_b":.., "s":..}, "negativo": {...}}.
    Per ogni regime applica il gate C0.4 su s: se feedable calcola le pendenze
    (leg_slopes), altrimenti il regime è None (meccanismo aperto/dichiarato).

    Se entrambi i regimi sono alimentabili, determina quale gamba inverte il
    segno tra positivo e negativo:
      equity_leg_inverts = sign(slope_eq_pos) != sign(slope_eq_neg)
      bond_leg_inverts   = sign(slope_bond_pos) != sign(slope_bond_neg)
    Se almeno un regime non è alimentabile → open=True e le due diagnostiche
    di inversione sono None (non determinabili).
    """
    if n_min is None:
        n_min = config.N_MIN
    if source_label is not None:
        surprises.validate_source(source_label)

    out: dict = {}
    for regime in ("positivo", "negativo"):
        cell = per_regime[regime]
        s = cell["s"]
        gate = surprises.coverage_variance_gate(s, n_min=n_min)
        if gate["feedable"]:
            out[regime] = leg_slopes(cell["r_e"], cell["r_b"], s)
        else:
            out[regime] = None

    pos = out["positivo"]
    neg = out["negativo"]
    open_ = (pos is None) or (neg is None)

    if open_:
        equity_leg_inverts = None
        bond_leg_inverts = None
    else:
        equity_leg_inverts = bool(
            np.sign(pos["slope_eq"]) != np.sign(neg["slope_eq"])
        )
        bond_leg_inverts = bool(
            np.sign(pos["slope_bond"]) != np.sign(neg["slope_bond"])
        )

    out["equity_leg_inverts"] = equity_leg_inverts
    out["bond_leg_inverts"] = bond_leg_inverts
    out["open"] = open_
    return out
