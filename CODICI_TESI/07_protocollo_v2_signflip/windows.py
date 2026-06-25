"""windows.py — Finestre evento e di controllo (C0.1, C0.2).

- `extract_window`: log-return su finestra ±half_min; pre/post = mediana dei
  prezzi nei primi/ultimi `edge_min` MINUTI (basato sul tempo, non sulle righe).
- `control_window_centers`: centri delle finestre di controllo, allineati sul
  TEMPO LOCALE di mercato e convertiti in UTC per-data con DST (§13bis), con la
  regola 5 / min 3 / tetto 10 (estensione del lookback solo sotto il minimo).

Riferimento riscritto e test-gated del kernel `extract_window` di
`09_risultati/scripts/analysis_pipeline.py` (che però usava le prime/ultime 5
RIGHE e un matching a UTC costante — entrambi corretti qui).
"""
from __future__ import annotations

from datetime import datetime, date as date_cls, time as time_cls
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from config import (
    HALF_MIN_WINDOW, MEDIAN_EDGE_MIN,
    K_CONTROL_TARGET, K_CONTROL_MIN, K_CONTROL_MAX, LOOKBACK_CAP_DAYS,
)

_UTC = ZoneInfo("UTC")


def extract_window(prices: pd.Series, t_center: pd.Timestamp,
                   half_min: int = HALF_MIN_WINDOW,
                   edge_min: int = MEDIAN_EDGE_MIN) -> float | None:
    """Log-return su finestra ±half_min attorno a t_center.

    pre  = mediana dei prezzi nei primi `edge_min` minuti [t0, t0+edge_min],
    post = mediana dei prezzi negli ultimi `edge_min` minuti [t1-edge_min, t1].
    Ritorna None se manca un edge o i prezzi non sono validi (>0).
    """
    t0 = t_center - pd.Timedelta(minutes=half_min)
    t1 = t_center + pd.Timedelta(minutes=half_min)
    w = prices.loc[t0:t1].dropna()
    if w.empty:
        return None
    pre_w = w.loc[t0:t0 + pd.Timedelta(minutes=edge_min)]
    post_w = w.loc[t1 - pd.Timedelta(minutes=edge_min):t1]
    if pre_w.empty or post_w.empty:
        return None
    pre = float(pre_w.median())
    post = float(post_w.median())
    if not (pre > 0 and post > 0) or np.isnan(pre) or np.isnan(post):
        return None
    return float(np.log(post / pre))


def _same_local_time_utc(d: date_cls, local_t: time_cls, tz_name: str) -> pd.Timestamp:
    """Timestamp UTC dell'ora locale `local_t` nel giorno `d` nel fuso `tz_name`.

    DST-aware: la stessa ora locale mappa su UTC diversi a seconda della data
    (le ore usate — 08:30 ET, 13:45/14:15 CET — non cadono mai nel buco DST).
    """
    aware = datetime.combine(d, local_t).replace(tzinfo=ZoneInfo(tz_name))
    return pd.Timestamp(aware.astimezone(_UTC))


def _preceding_trading_days(d: date_cls, n: int) -> list[date_cls]:
    """Gli `n` giorni feriali immediatamente precedenti `d` (più recente prima).

    I giorni festivi di mercato sono gestiti a valle: un controllo senza dati
    intraday produce extract_window=None e viene scartato (e l'estensione 5/3/10
    opera sul predicato `reject`, che in uso reale include 'nessun dato valido').
    """
    out: list[date_cls] = []
    cur = pd.Timestamp(d)
    while len(out) < n:
        cur = cur - pd.Timedelta(days=1)
        if cur.dayofweek < 5:
            out.append(cur.date())
    return out


def control_window_centers(event_utc: pd.Timestamp, tz_name: str,
                           reject=None,
                           k_target: int = K_CONTROL_TARGET,
                           k_min: int = K_CONTROL_MIN,
                           k_max: int = K_CONTROL_MAX,
                           lookback_cap: int = LOOKBACK_CAP_DAYS) -> list[pd.Timestamp]:
    """Centri delle finestre di controllo per un evento (C0.2).

    Regola: i `k_target` (5) giorni di trading precedenti, una finestra alla
    stessa ora LOCALE di mercato ciascuno; si scarta ciò che `reject(center)`
    segnala. Se i sopravvissuti sono < `k_min` (3) si estende il lookback un
    giorno alla volta fino a `lookback_cap` (10), ripristinando verso `k_target`,
    con tetto `k_max` (10). `reject` combina esclusioni di calendario e (in uso
    reale) l'assenza di un rendimento valido.
    """
    if reject is None:
        def reject(_t):
            return False

    ev_local = event_utc.tz_convert(tz_name)
    local_t = ev_local.time()
    ev_date = ev_local.date()

    # Fase A: i k_target giorni di trading immediatamente precedenti
    base_days = _preceding_trading_days(ev_date, k_target)
    collected: list[pd.Timestamp] = []
    for d in base_days:
        c = _same_local_time_utc(d, local_t, tz_name)
        if not reject(c):
            collected.append(c)
    if len(collected) >= k_min:
        return collected[:k_max]

    # Fase B: sotto il minimo → estendi (giorni k_target+1 .. lookback_cap)
    extra_days = _preceding_trading_days(ev_date, lookback_cap)[k_target:]
    for d in extra_days:
        if len(collected) >= k_target or len(collected) >= k_max:
            break
        c = _same_local_time_utc(d, local_t, tz_name)
        if not reject(c):
            collected.append(c)
    return collected[:k_max]


def assemble_event_controls(event_utc: pd.Timestamp, tz_name: str,
                            price_eq: pd.Series, price_bond: pd.Series,
                            is_calendar_excluded=None) -> dict:
    """Per un evento: rendimenti evento + controlli, con DROP-LOG per la provenienza.

    `reject` (passato a control_window_centers) fonde l'esclusione di calendario
    e l'assenza di un rendimento valido (eq o bond), così l'estensione 5/3/10
    opera sui controlli DAVVERO usabili. Ogni candidato scartato finisce nel
    drop-log con la sua ragione: 'calendar' | 'no_data_eq' | 'no_data_bond'
    (verify-2: il manifest deve poter spiegare come la cella è arrivata al suo
    numero di controlli).
    """
    if is_calendar_excluded is None:
        def is_calendar_excluded(_t):
            return False

    dropped: list[dict] = []
    kept: dict[pd.Timestamp, tuple] = {}

    def reject(c):
        if is_calendar_excluded(c):
            dropped.append({"center": c, "reason": "calendar"})
            return True
        re_ = extract_window(price_eq, c)
        if re_ is None:
            dropped.append({"center": c, "reason": "no_data_eq"})
            return True
        rb_ = extract_window(price_bond, c)
        if rb_ is None:
            dropped.append({"center": c, "reason": "no_data_bond"})
            return True
        kept[c] = (re_, rb_)
        return False

    centers = control_window_centers(event_utc, tz_name, reject=reject)
    controls = [{"center": c, "r_e": kept[c][0], "r_b": kept[c][1]} for c in centers]
    return {
        "event": {
            "center": event_utc,
            "r_e": extract_window(price_eq, event_utc),
            "r_b": extract_window(price_bond, event_utc),
        },
        "controls": controls,
        "dropped": dropped,
        "n_controls": len(controls),
    }


def shared_control_diagnostic(pos_control_keys, neg_control_keys) -> dict:
    """Controlli condivisi tra celle di regime opposto (validità di T*, R3/E2).

    Il χ²₁ di `delta_ar_pvalue` poggia sull'indipendenza di S_pos e S_neg, che
    vale perché gli eventi sono disgiunti tra regimi. Ma un giorno di controllo
    potrebbe servire due eventi di regime opposto vicini nel tempo: se accade, le
    finestre di controllo si sovrappongono e i df di T* non sono esattamente 1.
    Questa diagnostica conta la sovrapposizione (chiavi = timestamp dei centri di
    controllo). Se `n_shared` > 0, l'esecutore deduplica (assegna a un solo
    regime) o documenta che l'effetto sui df è trascurabile.
    """
    pos = set(pos_control_keys)
    neg = set(neg_control_keys)
    shared = sorted(pos & neg, key=str)
    return {"n_shared": len(shared), "shared": shared,
            "n_pos": len(pos), "n_neg": len(neg)}


def dedup_shared_controls(per_type_clusters: dict) -> tuple[dict, dict]:
    """Rimuove i controlli condivisi tra celle di regime OPPOSTO dello stesso tipo.

    Così l'indipendenza di S_pos e S_neg — e quindi il χ²₁ di `delta_ar_pvalue`
    (T4/T5) — regge **per costruzione**, senza rinviare la dedup all'esecutore
    (R3/E2). Un centro di controllo condiviso è ambiguo ⇒ scartato da ENTRAMBE le
    celle. I controlli sono identificati dal timestamp del centro (`center`); le
    voci senza `center` sono lasciate intatte. Ritorna (cluster_puliti, report
    {tipo: n_centri_condivisi_rimossi}).
    """
    cleaned, report = {}, {}
    for t, cells in per_type_clusters.items():
        pos, neg = cells.get("pos"), cells.get("neg")
        pos_ctr = {ct["center"] for cl in (pos or []) for ct in cl["controls"]
                   if ct.get("center") is not None}
        neg_ctr = {ct["center"] for cl in (neg or []) for ct in cl["controls"]
                   if ct.get("center") is not None}
        shared = pos_ctr & neg_ctr

        def _clean(cell):
            if cell is None:
                return None
            return [{**cl, "controls": [ct for ct in cl["controls"]
                                        if ct.get("center") not in shared]}
                    for cl in cell]

        cleaned[t] = {"pos": _clean(pos), "neg": _clean(neg)}
        report[t] = len(shared)
    return cleaned, report
