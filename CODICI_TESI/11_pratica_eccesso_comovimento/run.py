"""run.py — Orchestratore della strategia eccesso di comovimento.

⚠️ `main()` è BLOCCATO. L'esecuzione sui dati reali è di un altro anello.
Questo modulo espone `run_strategy(events_df, ...)` che gira su un DataFrame
di eventi PASSATO DALL'ESTERNO (date, leg, regime, epsilon).

Presidio strutturale:
  1. Lo split temporale è APPLICATO QUI (config.SPLIT_DATE). La calibrazione
     riceve SOLO il training; passare eventi non filtrati a `calibration.calibrate`
     fa sollevare la funzione (anti-leakage by construction).
  2. Il test è calcolato UNA SOLA VOLTA (no ricalibrazione possibile).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import calibration
import config
import metrics as M
import payoff as P
import weighting as Wt
import windows as W


def _apply_strategy(events: pd.DataFrame, e_gk: dict,
                    min_abs: float) -> pd.DataFrame:
    """Applica la regola di posizione e calcola payoff per ogni evento."""
    out = events.copy()
    out["w"] = [calibration.position_for(l, r, e_gk, min_abs=min_abs)
                for l, r in zip(out["leg"], out["regime"])]
    out["payoff_strategy"] = [P.strategy_payoff(w, eps)
                               for w, eps in zip(out["w"], out["epsilon"])]
    out["payoff_benchmark"] = [P.benchmark_payoff(eps) for eps in out["epsilon"]]
    return out


def _combine_inv_vol(events_with_payoff: pd.DataFrame,
                     window_events: int) -> pd.DataFrame:
    """Per ogni evento i, combina le due gambe con pesi inverse-vol calcolati
    su eventi PASSATI a i, separatamente per gamba. Aggiunge colonne:
      payoff_combined_strategy, payoff_combined_benchmark.

    REVIEW #3 — chiarezza: nel caso reale NFP e CPI generalmente NON cadono
    lo stesso giorno, quindi sotto la convenzione "un evento per data" la
    combinazione è di fatto un PASSA-ATTRAVERSO single-leg (la sola gamba
    presente quel giorno, scalata 1/1=1). L'aggregazione "COMBINED" nelle
    metriche è quindi un raggruppamento PER REGIME su tutto il periodo, non
    una vera media pesata cross-leg per-evento. Il ramo "due gambe stesso
    giorno" è gestito da `weighting.combine_legs` (testato separatamente:
    `tests/test_kernels.py::test_combine_legs_two_legs_same_day_*`).
    """
    df = events_with_payoff.sort_values("date").reset_index(drop=True)
    per_leg_history = {leg: df[df["leg"] == leg].set_index("date")["epsilon"]
                       for leg in config.LEGS}
    combined_strat, combined_bench = [], []
    for _, row in df.iterrows():
        leg_at_event = row["leg"]
        # σ_roll della SOLA gamba dell'evento (è quella effettivamente "presente"
        # a quella data nella nostra struttura "un evento per riga")
        eps_hist = per_leg_history[leg_at_event]
        try:
            sigma = Wt.rolling_vol_at(eps_hist, t=row["date"], window_events=window_events)
        except ValueError:
            # warmup: prima di accumulare abbastanza eventi passati la combinazione
            # non è definita. Per coerenza con "una sola occhiata al test", l'evento
            # è SCARTATO (no fabbricazione di un peso) — segnalato a valle dai conteggi.
            combined_strat.append(float("nan"))
            combined_bench.append(float("nan"))
            continue
        out = Wt.combine_legs(payoffs={leg_at_event: row["payoff_strategy"]},
                               sigmas={leg_at_event: sigma})
        combined_strat.append(out["payoff_combined"])
        bench = Wt.combine_legs(payoffs={leg_at_event: row["payoff_benchmark"]},
                                 sigmas={leg_at_event: sigma})
        combined_bench.append(bench["payoff_combined"])
    df = df.copy()
    df["payoff_combined_strategy"] = combined_strat
    df["payoff_combined_benchmark"] = combined_bench
    return df


def run_strategy(events_df: pd.DataFrame,
                 *, split_date: pd.Timestamp = config.SPLIT_DATE,
                 min_abs: float = config.MIN_ABS_E_FOR_POSITION,
                 inv_vol_window: int = config.INV_VOL_ROLLING_EVENTS,
                 event_calendar: dict | None = None) -> dict:
    """End-to-end: split → calibrate(train only) → apply su entrambi → metriche.

    Eseguito SOLO sull'input passato (DataFrame di eventi con date/leg/regime/epsilon).

    `event_calendar` (opzionale): dict con
        - `calendar`: lista di Timestamp di sedute di mercato;
        - `event_to_idx`: dict {date_evento → indice nel calendario}.
    Se passato, **wiring del presidio intra-evento** (REVIEW #1): per ciascun
    evento si invoca `windows.three_windows` + `windows.assert_no_lookahead`
    sul calendario fornito; un evento con calendario incoerente fa SOLLEVARE
    run_strategy (non si fabbrica un risultato). Se non passato, il return
    contiene `intra_event_lookahead_check="delegated_to_executor"` e
    l'esecutore è responsabile di aver costruito ε rispettando le 3 finestre.
    """
    needed = {"date", "leg", "regime", "epsilon"}
    if not needed.issubset(events_df.columns):
        raise ValueError(f"events_df serve colonne {needed}, ha {set(events_df.columns)}")

    df = events_df.copy()
    df["date"] = pd.to_datetime(df["date"])

    # ---- REVIEW #1: presidio intra-evento STRUTTURALE quando passa il calendario
    intra_event_check = "delegated_to_executor"
    if event_calendar is not None:
        cal = event_calendar.get("calendar")
        ev2idx = event_calendar.get("event_to_idx")
        if cal is None or ev2idx is None:
            raise ValueError("event_calendar deve avere chiavi 'calendar' e 'event_to_idx'")
        for d in df["date"]:
            key = pd.Timestamp(d).normalize()
            if key not in ev2idx:
                raise ValueError(f"data evento {key.date()} non in event_calendar.event_to_idx")
            idx = int(ev2idx[key])
            r_idx, p_idx, ev_idx = W.three_windows(cal, idx)   # solleva se cal corto
            W.assert_no_lookahead(r_idx + p_idx, event_idx=ev_idx)
        intra_event_check = "validated"

    train = df[df["date"] < split_date].copy()
    test = df[df["date"] >= split_date].copy()
    if len(train) == 0:
        raise ValueError(f"training vuoto (split_date={split_date.date()})")
    if len(test) == 0:
        raise ValueError(f"test vuoto (split_date={split_date.date()})")

    cal = calibration.calibrate(train, training_end=split_date)

    train_app = _apply_strategy(train, cal["e_gk"], min_abs=min_abs)
    test_app = _apply_strategy(test, cal["e_gk"], min_abs=min_abs)

    # Combinazione inverse-vol calcolata SUL TUTTO il df ordinato in tempo,
    # ma σ è solo eventi PASSATI a ciascuna data (presidio interno a weighting).
    full = pd.concat([train_app, test_app], ignore_index=True).sort_values("date")
    combined = _combine_inv_vol(full, window_events=inv_vol_window)
    train_c = combined[combined["date"] < split_date]
    test_c = combined[combined["date"] >= split_date]

    def cells(frame, *, mark_period):
        out = {"_period": mark_period}
        for leg in config.LEGS:
            for reg in ("pos", "neg"):
                sub = frame[(frame["leg"] == leg) & (frame["regime"] == reg)]
                strat = sub["payoff_strategy"].dropna().values
                bench = sub["payoff_benchmark"].dropna().values
                out[(leg, reg)] = {
                    "n": int(len(sub)),
                    "strategy": M.cell_summary(strat),
                    "benchmark": M.cell_summary(bench),
                    "diff": M.diff_vs_benchmark(strat, bench),
                }
        # combinato per regime (su tutto il period)
        for reg in ("pos", "neg"):
            sub = frame[frame["regime"] == reg]
            strat_c = sub["payoff_combined_strategy"].dropna().values
            bench_c = sub["payoff_combined_benchmark"].dropna().values
            out[("COMBINED", reg)] = {
                "n": int(len(strat_c)),
                "strategy": M.cell_summary(strat_c),
                "benchmark": M.cell_summary(bench_c),
                "diff": M.diff_vs_benchmark(strat_c, bench_c)
                        if len(strat_c) == len(bench_c) else {"mean_diff": float("nan"), "n": 0},
            }
        return out

    return {
        "calibration": {"e_gk": cal["e_gk"], "n_train": cal["n_train"]},
        "training_metrics": cells(train_c, mark_period="training"),
        "test_metrics": cells(test_c, mark_period="test"),
        "split_date": str(split_date.date()),
        "config_hash": config.config_hash(),
        "n_total": int(len(df)),
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "intra_event_lookahead_check": intra_event_check,
    }


def main():  # pragma: no cover
    raise SystemExit(
        "run.py: l'esecuzione sui dati reali è di un altro anello (esecutore). "
        "Importa run_strategy(events_df, ...); gli unit test girano su DGP sintetici."
    )


if __name__ == "__main__":
    main()
