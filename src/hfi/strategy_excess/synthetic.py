"""synthetic.py — 4 DGP a verità nota per validazione del coder.

I 4 scenari (spec §"Validazione su DGP sintetici"):
  - "signal"          : ε ha media condizionata al regime di SEGNO OPPOSTO
                         (e_pos > 0, e_neg < 0) → strategia batte naive.
  - "noise"           : ε iid, nessuna dipendenza dal regime → no payoff sistematico.
  - "lookahead_trap"  : i training events sono rumore; gli eventi del test hanno
                         segnale concentrato in cui calibrare sul TEST darebbe payoff
                         spurio. Lo split corretto blocca il leakage e dà ≈ 0 OOS.
  - "imbalanced"      : regime positivo raro (pochi eventi nel test) → la cella
                         positiva di test dovrà risultare 'inconclusive'.

Tutti gli output hanno colonne: date, leg, regime, epsilon.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config


def _events_frame(dates, legs, regimes, epsilons) -> pd.DataFrame:
    return pd.DataFrame({"date": pd.to_datetime(dates),
                          "leg": legs, "regime": regimes, "epsilon": epsilons})


def dgp_signal(rng, n_train: int = 200, n_test: int = 100) -> pd.DataFrame:
    """ε pos vs neg ben separati (segno opposto)."""
    rows = []
    train_dates = pd.date_range("2010-01-15", "2020-12-15", periods=n_train)
    test_dates = pd.date_range("2021-01-15", "2025-12-15", periods=n_test)
    for d in train_dates:
        leg = rng.choice(["NFP", "CPI"])
        reg = rng.choice(["pos", "neg"])
        mu = +0.30 if reg == "pos" else -0.30   # SEGNO OPPOSTO per regime
        rows.append((d, leg, reg, mu + 0.10 * rng.standard_normal()))
    for d in test_dates:
        leg = rng.choice(["NFP", "CPI"])
        reg = rng.choice(["pos", "neg"])
        mu = +0.30 if reg == "pos" else -0.30
        rows.append((d, leg, reg, mu + 0.10 * rng.standard_normal()))
    df = pd.DataFrame(rows, columns=["date", "leg", "regime", "epsilon"])
    return df


def dgp_noise(rng, n_train: int = 200, n_test: int = 100) -> pd.DataFrame:
    """ε iid, indipendente da regime: e_{g,k} → 0, no falso positivo OOS."""
    rows = []
    train_dates = pd.date_range("2010-01-15", "2020-12-15", periods=n_train)
    test_dates = pd.date_range("2021-01-15", "2025-12-15", periods=n_test)
    for d in list(train_dates) + list(test_dates):
        leg = rng.choice(["NFP", "CPI"])
        reg = rng.choice(["pos", "neg"])
        rows.append((d, leg, reg, 0.10 * rng.standard_normal()))
    return pd.DataFrame(rows, columns=["date", "leg", "regime", "epsilon"])


def dgp_lookahead_trap(rng, n_train: int = 200, n_test: int = 100) -> pd.DataFrame:
    """Training rumore; nel test ε ha medie condizionate non zero MA con
    SEGNO INVERSO rispetto a un'eventuale calibrazione training: se l'algoritmo
    calibrasse sul TEST darebbe payoff positivo (spurio); se calibra SOLO sul
    training, e_{g,k} ≈ 0 → su test la posizione è ~sign(0)=0 oppure ±1 al caso
    → payoff OOS ≈ 0. Il presidio strutturale impedisce il leakage.
    """
    rows = []
    train_dates = pd.date_range("2010-01-15", "2020-12-15", periods=n_train)
    test_dates = pd.date_range("2021-01-15", "2025-12-15", periods=n_test)
    for d in train_dates:
        leg = rng.choice(["NFP", "CPI"])
        reg = rng.choice(["pos", "neg"])
        rows.append((d, leg, reg, 0.10 * rng.standard_normal()))    # rumore puro
    for d in test_dates:
        leg = rng.choice(["NFP", "CPI"])
        reg = rng.choice(["pos", "neg"])
        # nel test: segnale concentrato, OPPOSTO fra regimi (per maschere l'illusione)
        mu = +0.40 if reg == "pos" else -0.40
        rows.append((d, leg, reg, mu + 0.10 * rng.standard_normal()))
    return pd.DataFrame(rows, columns=["date", "leg", "regime", "epsilon"])


def dgp_imbalanced(rng, n_train: int = 200, n_test: int = 100,
                   pos_test_frac: float = 0.05) -> pd.DataFrame:
    """Regime positivo raro nel test (frazione `pos_test_frac` molto bassa).

    Anche con segnale presente, la cella (pos, test) deve risultare 'inconclusive'
    perché n < soglia di verdetto.
    """
    rows = []
    train_dates = pd.date_range("2010-01-15", "2020-12-15", periods=n_train)
    test_dates = pd.date_range("2021-01-15", "2025-12-15", periods=n_test)
    for d in train_dates:
        leg = rng.choice(["NFP", "CPI"])
        reg = rng.choice(["pos", "neg"], p=[0.5, 0.5])
        mu = +0.30 if reg == "pos" else -0.30
        rows.append((d, leg, reg, mu + 0.10 * rng.standard_normal()))
    for d in test_dates:
        leg = rng.choice(["NFP", "CPI"])
        reg = rng.choice(["pos", "neg"], p=[pos_test_frac, 1.0 - pos_test_frac])
        mu = +0.30 if reg == "pos" else -0.30
        rows.append((d, leg, reg, mu + 0.10 * rng.standard_normal()))
    return pd.DataFrame(rows, columns=["date", "leg", "regime", "epsilon"])
