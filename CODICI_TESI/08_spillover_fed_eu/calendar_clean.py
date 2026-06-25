"""calendar_clean.py — Stadio 0.4: pulizia del calendario eventi.

Lavora SU INPUT (DataFrame passati): non scarica nulla. L'utente fornisce
gli snapshot CONGELATI (FRED/Treasury/Eurostat/BCE/fonti tedesche) e questo
modulo costruisce gli eventi inclusi/esclusi con manifest.

`mode`:
  - "baseline": comunicazione Fed in [t_j, t_j+1] è PARTE dello spillover (γ è
    l'effetto della stance comunicata) → non esclude per Fed major.
  - "robust_drop_fed_t1": rimuove eventi con intervento Fed major in T+1.
"""
from __future__ import annotations

import pandas as pd
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


def is_jobless_thursday(center: pd.Timestamp) -> bool:
    """Vero se `center` cade di giovedì alle 08:30 ET (rilascio jobless claims)."""
    loc = center.tz_convert(_ET) if center.tzinfo is not None \
        else center.tz_localize("UTC").tz_convert(_ET)
    return loc.weekday() == 3 and loc.hour == 8 and loc.minute == 30


def filter_events(events: pd.DataFrame, contaminants: pd.DataFrame,
                  fed_major_speeches: pd.Series | None = None,
                  mode: str = "baseline",
                  window_days: int = 1) -> dict:
    """Filtra gli eventi escludendo quelli con contaminanti in [t_j, t_j+window_days].

    `events.event_time` (UTC) → finestra forward `window_days` giorni.
    `contaminants` colonne: `time` (UTC), `kind` (etichetta → motivo esclusione).
    `fed_major_speeches`: serie/array di timestamp UTC degli interventi Fed
    major; usata solo se `mode == "robust_drop_fed_t1"`.

    Ritorna `{"included": DataFrame, "excluded": DataFrame, "mode": str}` —
    `excluded` ha colonna `reason` con la KIND del contaminante che ha causato
    l'esclusione (FED_T1 per interventi Fed in modalità robust).
    """
    if mode not in ("baseline", "robust_drop_fed_t1"):
        raise ValueError(f"mode sconosciuto: {mode!r}")
    ev = events.copy()
    ev["event_time"] = pd.to_datetime(ev["event_time"], utc=True)
    cont = contaminants.copy() if contaminants is not None else pd.DataFrame(
        {"time": pd.to_datetime([], utc=True), "kind": []})
    cont["time"] = pd.to_datetime(cont["time"], utc=True)

    window = pd.Timedelta(days=window_days)
    included_rows = []
    excluded_rows = []

    for _, row in ev.iterrows():
        t0 = row["event_time"]
        t1 = t0 + window
        # contaminanti datati in (t0, t1]
        mask = (cont["time"] > t0) & (cont["time"] <= t1)
        hits = cont.loc[mask]
        reasons = list(hits["kind"].astype(str))

        if mode == "robust_drop_fed_t1" and fed_major_speeches is not None:
            fms = pd.to_datetime(pd.Index(fed_major_speeches), utc=True)
            if ((fms > t0) & (fms <= t1)).any():
                reasons.append("FED_T1")

        if reasons:
            for r in reasons:
                excluded_rows.append({**row.to_dict(), "reason": r})
        else:
            included_rows.append(row.to_dict())

    return {
        "included": pd.DataFrame(included_rows, columns=ev.columns),
        "excluded": pd.DataFrame(excluded_rows,
                                 columns=list(ev.columns) + ["reason"]),
        "mode": mode,
    }


def manifest(filter_result: dict) -> dict:
    """Sintesi del filtro: numerosità in/out + ragioni."""
    inc = filter_result["included"]; exc = filter_result["excluded"]
    by_reason = (exc["reason"].astype(str).value_counts().to_dict()
                 if "reason" in exc.columns and len(exc) else {})
    return {"mode": filter_result["mode"],
            "n_included": int(len(inc)),
            "n_excluded": int(len(exc)),
            "excluded_by_reason": by_reason}
