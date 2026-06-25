"""run_strategies.py — Orchestratore delle 4 strategie event-driven.

⚠️ `main()` BLOCCATO. Esecuzione sui dati reali è di un altro anello.
Questo modulo espone `run_all(events_by_strategy, ...)` che gira su DataFrame
PASSATI DALL'ESTERNO (date, regime, surprise, r_e_event, r_b_event,
r_e_eod, r_b_eod) per ciascuna strategia.

Vincoli strutturali rispettati:
  - Attivazione filtra per regime PRIMA del payoff (anti-look-ahead a livello regime).
  - Sottocampione FOMC ≤ 2024-01-31 (limite serie JK).
  - Sharpe ai 2 orizzonti ENTRAMBI riportati (no selezione).
"""
from __future__ import annotations

import pandas as pd

import config
import metrics as M
import payoff as P
import portfolio as PF
import strategy_rule as SR


def _filter_events(df: pd.DataFrame, strategy: str) -> pd.DataFrame:
    """Filtra per regime ammesso + sottocampione FOMC (se strategy='FOMC')."""
    needed = {"date", "regime", "surprise",
              "r_e_event", "r_b_event", "r_e_eod", "r_b_eod"}
    if not needed.issubset(df.columns):
        raise ValueError(f"events serve colonne {needed}, ha {set(df.columns)}")
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    # 1) regime ammesso
    mask = out["regime"] == config.ACTIVE_REGIME[strategy]
    # 2) sottocampione FOMC (serie JK termina a gennaio 2024)
    if strategy == "FOMC":
        mask &= out["date"] <= config.FOMC_SUBSAMPLE_END
    return out.loc[mask].copy()


def run_single_strategy(events: pd.DataFrame, strategy: str) -> dict:
    """Payoff per-evento ai due orizzonti + Sharpe."""
    events_f = _filter_events(events, strategy)
    n = len(events_f)
    p_event, p_eod = [], []
    for _, row in events_f.iterrows():
        pay = P.event_payoff(
            strategy=strategy, surprise=float(row["surprise"]),
            r_e_event=float(row["r_e_event"]), r_b_event=float(row["r_b_event"]),
            r_e_eod=float(row["r_e_eod"]), r_b_eod=float(row["r_b_eod"]),
        )
        p_event.append(pay["event_window"])
        p_eod.append(pay["end_of_day"])
    payoffs = {"event_window": p_event, "end_of_day": p_eod}
    if n == 0:
        period = "vuoto"
    else:
        period = f"{events_f['date'].min().date()}..{events_f['date'].max().date()}"
    return {
        "strategy": strategy,
        "n_active": int(n),
        "period": period,
        "payoffs": payoffs,
        "metrics": M.summary(payoffs, period=period),
    }


def run_all(events_by_strategy: dict, *,
            scheme: str = config.PORTFOLIO_WEIGHT_DEFAULT,
            train_payoffs: dict | None = None) -> dict:
    """Strategie 1-3 + portafoglio (strategia 4) con pesi a priori.

    `events_by_strategy`: dict {"CPI": df, "NFP": df, "FOMC": df}.
    `scheme`: "equal" (default) o "inverse_vol_on_training".
    `train_payoffs`: richiesto solo per "inverse_vol_on_training" — dict
      {strategy: array di training payoffs}. Anti-look-ahead: l'esecutore
      DEVE costruirlo su un training set congelato a priori.
    """
    if set(events_by_strategy.keys()) != set(config.STRATEGIES):
        raise ValueError(f"events_by_strategy deve coprire {config.STRATEGIES}")
    per_strat = {}
    for s in config.STRATEGIES:
        per_strat[s] = run_single_strategy(events_by_strategy[s], s)

    # Portafoglio: pesi PRE-DICHIARATI
    if scheme == "equal":
        weights = PF.compute_weights(
            train_payoffs={s: [0.0] for s in config.STRATEGIES}, scheme="equal")
    elif scheme == "inverse_vol_on_training":
        if train_payoffs is None:
            raise ValueError("scheme=inverse_vol_on_training richiede train_payoffs")
        weights = PF.compute_weights(train_payoffs=train_payoffs,
                                      scheme="inverse_vol_on_training")
    else:
        raise ValueError(f"scheme {scheme!r} non ammesso")

    per_strat_payoffs = {s: per_strat[s]["payoffs"] for s in config.STRATEGIES}
    combined = PF.combine_payoffs(per_strat_payoffs, weights=weights)
    # Periodo del portafoglio = unione dei periodi (col vincolo FOMC≤2024 già applicato)
    all_dates = []
    for s in config.STRATEGIES:
        f = _filter_events(events_by_strategy[s], s)
        all_dates.extend(f["date"].tolist())
    if all_dates:
        period_portfolio = f"{min(all_dates).date()}..{max(all_dates).date()}"
    else:
        period_portfolio = "vuoto"
    portfolio_metrics = M.summary(combined, period=period_portfolio)
    return {
        "per_strategy": per_strat,
        "portfolio": {
            "scheme": scheme,
            "weights": weights,
            "period": period_portfolio,
            "payoffs": combined,
            "metrics": portfolio_metrics,
        },
        "config_hash": config.config_hash(),
        "fomc_subsample_end": str(config.FOMC_SUBSAMPLE_END.date()),
    }


def main():   # pragma: no cover
    raise SystemExit(
        "run_strategies.py: l'esecuzione sui dati reali è di un altro anello. "
        "Importa run_all(events_by_strategy, ...) con DataFrame congelati."
    )


if __name__ == "__main__":
    main()
