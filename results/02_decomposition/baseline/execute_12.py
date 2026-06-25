"""execute_12.py — Esecutore pacchetto 12 (decomposizione canali, doppio cancello).

Anello finale per il pacchetto 12. Riusa i cluster del 07 (coerenza inter-pacchetto,
stesso MASTER_SEED=20260621, MOP_CV=23.1085) e applica `cell_pipeline.run_cell`
per ogni cella (leg × regime) con:
  - delta_f_curve = (delta_rate_1, delta_rate_2, delta_rate_3) in DECIMALE (÷10000)
  - D_bond = 8.9709 (costante v2)
  - delta_y_bond = delta_rate_3 in DECIMALE (proxy del Δy long-end via term structure)
  - dp_bar = -3.85 (canonico esterno, log(D/P) S&P 500 ≈ 2.1% media; pre-registrato)
  - N = 100, B = 10000, surprise_per_event = m_e (PC1 money-market) dal CSV eventi.

Convenzione del 12: per ogni cluster del 07 produciamo UNA riga events con il
control matchato dato dalla MEDIA dei rendimenti dei controlli del cluster.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/francesco/TESI/tesi-hfi-equity-bond")
PKG07 = ROOT / "CODICI_TESI" / "07_protocollo_v2_signflip"
PKG12 = ROOT / "CODICI_TESI" / "12_decomposizione_canali"

# I due pacchetti hanno entrambi un modulo "config". Per evitare collisione di
# namespace, importo il 07 (config 07 → bindings interni di run07/windows07/data07
# fissati al suo config) e POI rimuovo `config` dalla cache prima di importare i
# moduli del 12 (così `gates.py`/`cell_pipeline.py` del 12 trovano il proprio config).
sys.path.insert(0, str(PKG07))
import config as cfg07           # noqa: E402
import data as data07            # noqa: E402
import run as run07              # noqa: E402
import windows as win07          # noqa: E402
# Bindings interni del 07 sono ora fissati; rimuovo "config" dalla cache.
for mod_name in ("config",):
    sys.modules.pop(mod_name, None)
sys.path.remove(str(PKG07))
sys.path.insert(0, str(PKG12))
import config as cfg12           # noqa: E402 — ora prende il config del 12
import cell_pipeline as CP       # noqa: E402
import gates as G12              # noqa: E402 — alt precheck con sorprese esterne
import manifest as MF12          # noqa: E402
assert cfg07.MASTER_SEED == cfg12.MASTER_SEED == 20260621, "MASTER_SEED non allineato 07/12"

OUT_DIR = ROOT / "09_risultati" / "decomp_canali"
OUT_DIR.mkdir(parents=True, exist_ok=True)

EVENTS_CSV = ROOT / "DATASET_TESI" / "01_eventi_hfi" / "events_with_regime_classifier.csv"
CONTAMINANTS_CSV = Path("/home/francesco/TESI/Dati/calendari/contaminants_build_2026-06-22/"
                         "contaminants_v2_2026-06-22.csv")
PICKLE_AUTH_07 = ROOT / "09_risultati" / "v2_signflip" / "result_authoritative.pkl"

# Daily benchmark yields (req10c via bridge, 2010-2025).
# Usato come PROXY DAILY per Δy_bond di evento e controllo dopo Bug 2 fix
# 2026-06-23. Bias dichiarato: Δy_daily = close(t)-close(t-1) include rumore
# extra-finestra; nei giorni di evento incorpora segnale dell'annuncio,
# nei giorni di controllo è quasi puro rumore. Documentato in external_constants.
BENCHMARK_YIELDS_CSV = ROOT / "bridge" / "data" / "req10c_yields_full.csv"
BENCHMARK_YIELD_COL = "US10YT=RR"   # 10Y on-the-run benchmark, in PERCENT

# Costanti pre-registrate per questo run
D_BOND = 8.970865529245179         # UST 10Y duration (anni)
D_BOND_PERIODS = D_BOND * 4.0      # in trimestri (Δf da FFc1/2/3 = quarterly forwards)
DP_BAR = -3.85                     # canonico: log(D/P) S&P500 ≈ 2.1% media (esterno)
N_HORIZON = 100                    # orizzonte di troncamento ρ^(n-1) (equity)
BOND_METHOD = "curve"              # Bug 2 fix v2 (2026-06-23): bond da curva, no duration·Δy
BOND_TAIL = "T0"                   # Δf_n = 0 oltre il bordo osservato (defensivo)

# 2026-06-23 estensione curva: bordo osservato esteso usando l'intero strip
# short-rate disponibile in TSDB/CSV (FF+SR per US, FEI per EU). Bond e equity
# leggono il delta_f_curve dall'intraday — la pipeline non legge più
# delta_rate_1/2/3 dal CSV (questi restano materializzati per m_e).
CURVE_RICS_US = ("FFc1", "FFc2", "FFc3")                    # 3 punti front
CURVE_RICS_EU = ("FEIc1", "FEIc2")                          # 2 punti front (FEIc3-4 hanno gap intraday su ~68% ECB events)
# 2026-06-23 estensione long-end (improvement "curva estesa al 10Y"):
# proxy del bordo a 10Y derivato da future bond intraday — Δy_implicita =
# -log_return_future / D_CTD_anni (annualizzata, stesse unità di Δrate FF/FEI).
# Si aggiunge come ultimo elemento del delta_f_curve ⇒ il "bordo" del precheck
# Nagel-Xu diventa il 10Y, non più il 9-mese (front).
LONG_END_RIC_US = "TY"      # 10Y T-Note future, già in INTRADAY_FILES (07)
LONG_END_RIC_EU = "FGBL"    # 10Y Bund future, già in INTRADAY_FILES (07)
LONG_END_DUR_US = 7.5       # CTD Macaulay-ish (anni, approx)
LONG_END_DUR_EU = 8.0       # CTD Bund (anni, approx)

# 2026-06-23 griglia equity ridotta a singolo punto (T0, ρ centrale): pre-
# registrazione del tail più conservativo. Banda di costruzione = 0 by design,
# verdict robust = (gate_a PASS) AND (precheck PASS).
EQUITY_TAILS = ("T0",)
EQUITY_RHO_OFFSETS = (0.0,)

SEED_NAME = "decomp_canali_2026-06-23"
TASK_TIMESTAMP = (
    datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
)
BPS_TO_DECIMAL = 1.0 / 10000.0


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_contaminant_centers(path: Path) -> set:
    import csv
    out = set()
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.add(pd.Timestamp(r["center_utc"]))
    return out


def load_bs_mps_orth_by_date() -> dict:
    """{date: MPS_ORTH} Bauer-Swanson 2023 (FOMC only). NaN-safe."""
    df = pd.read_excel(
        ROOT / "DATASET_TESI/02_shocks_monetari/BauerSwanson2023_FOMC.xlsx",
        sheet_name="FOMC (update 2023)",
        usecols=["Date", "MPS_ORTH"],
    )
    df["Date"] = pd.to_datetime(df["Date"]).dt.date
    df = df.dropna(subset=["MPS_ORTH"])
    return dict(zip(df["Date"], df["MPS_ORTH"].astype(float)))


def load_bs_nfp_surp_by_ym() -> dict:
    """{(year, month_release): NFP_SURP} da BauerSwanson2023 'Monthly (update 2023)'."""
    df = pd.read_excel(
        ROOT / "DATASET_TESI/02_shocks_monetari/BauerSwanson2023_FOMC.xlsx",
        sheet_name="Monthly (update 2023)",
        usecols=["Year", "Month", "NFP_SURP"],
    )
    df = df.dropna(subset=["NFP_SURP"])
    return {(int(y), int(m)): float(v)
            for y, m, v in zip(df["Year"], df["Month"], df["NFP_SURP"])}


def load_cpi_surprise_mom_by_release_ym() -> dict:
    """{(release_year, release_month): surprise_mom_decimal} da req08.

    `reference_month_end` nel file = ultimo giorno del mese di RIFERIMENTO dei
    dati CPI; il release avviene ~giorno 10-15 del mese SUCCESSIVO. Mappiamo a
    (release_year, release_month) shiftando di +1 mese. `surprise_mom` in pp:
    dividiamo /100 per ottenere decimal coerente con altre sorprese.
    """
    df = pd.read_csv(ROOT / "bridge/data/req08_cpi_surprise.csv",
                      usecols=["reference_month_end", "surprise_mom"])
    df = df.dropna(subset=["surprise_mom"])
    out = {}
    for ref, surp in zip(df["reference_month_end"], df["surprise_mom"]):
        ref_ts = pd.Timestamp(ref)
        rel_ts = ref_ts + pd.offsets.MonthBegin(1)  # primo del mese release
        out[(rel_ts.year, rel_ts.month)] = float(surp) / 100.0
    return out


def load_breakeven_diff_decimal_by_date() -> dict:
    """{date: Δbreakeven_5Y_daily_decimal}. Proxy sorpresa inflazione per CPI.

    Usa T5YIE (FRED breakeven 5Y) dal snapshot parquet: più sensibile a sorprese
    CPI di breve-medio termine rispetto al 10Y. Bias daily dichiarato.
    """
    df = pd.read_parquet(ROOT / "DATASET_TESI/04_yields/fred_yields_snapshot.parquet")
    df = df[df["series_id"] == "T5YIE"][["date", "value"]].copy()
    df["Date"] = pd.to_datetime(df["date"]).dt.date
    df = df.dropna(subset=["value"]).sort_values("Date").reset_index(drop=True)
    df["dbe_decimal"] = df["value"].diff() / 100.0
    df = df.dropna(subset=["dbe_decimal"])
    return dict(zip(df["Date"], df["dbe_decimal"]))


def load_delta_y_30y_daily_decimal() -> dict:
    """{date: Δy_30Y daily decimal} da req10c (US30YT=RR). Proxy bordo curva long US."""
    df = pd.read_csv(BENCHMARK_YIELDS_CSV, usecols=["Date", "US30YT=RR"])
    df["Date"] = pd.to_datetime(df["Date"]).dt.date
    df = df.dropna(subset=["US30YT=RR"]).sort_values("Date").reset_index(drop=True)
    df["dy_decimal"] = df["US30YT=RR"].diff() / 100.0
    df = df.dropna(subset=["dy_decimal"])
    return dict(zip(df["Date"], df["dy_decimal"]))


def load_delta_y_de30y_daily_decimal() -> dict:
    """{date: Δy_DE30Y daily decimal} da req22 (DE30YT=RR). Proxy bordo curva long EU."""
    df = pd.read_csv(ROOT / "bridge/data/req22_de30y_daily.csv",
                      usecols=["Date", "DE30YT=RR"])
    df["Date"] = pd.to_datetime(df["Date"]).dt.date
    df = df.dropna(subset=["DE30YT=RR"]).sort_values("Date").reset_index(drop=True)
    df["dy_decimal"] = df["DE30YT=RR"].diff() / 100.0
    df = df.dropna(subset=["dy_decimal"])
    return dict(zip(df["Date"], df["dy_decimal"]))


def load_eampd_shock_by_date(window: str, ois_col: str) -> dict:
    """{date: ΔOIS_{ois_col}_decimal} dal foglio `window` di EA-MPD (Altavilla 2019).

    window ∈ {'Press Release Window', 'Press Conference Window', 'Monetary Event Window'}
    ois_col ∈ {'OIS_1M', 'OIS_2Y', 'OIS_10Y', ...}
    Valori EA-MPD in bp → diviso per 10000 → decimal coerente con altre sorprese.
    """
    df = pd.read_excel(
        ROOT / "DATASET_TESI/01_eventi_hfi/EA-MPD_ECB_Altavilla2019.xlsx",
        sheet_name=window, usecols=["date", ois_col],
    )
    df["Date"] = pd.to_datetime(df["date"]).dt.date
    df = df.dropna(subset=[ois_col])
    return {d: float(v) / 10000.0 for d, v in zip(df["Date"], df[ois_col])}


def load_jk_mp_pm_by_date(region: str) -> dict:
    """{date: MP_pm} Jarocinski-Karadi. region ∈ {'Fed','ECB'}."""
    if region == "Fed":
        path = ROOT / "DATASET_TESI/02_shocks_monetari/JarocinskiKaradi_Fed_shocks.csv"
        date_col = "start"
    else:
        path = ROOT / "DATASET_TESI/02_shocks_monetari/JarocinskiKaradi_ECB_shocks.csv"
        date_col = "date"
    df = pd.read_csv(path, usecols=[date_col, "MP_pm"])
    df["Date"] = pd.to_datetime(df[date_col]).dt.date
    df = df.dropna(subset=["MP_pm"])
    return dict(zip(df["Date"], df["MP_pm"].astype(float)))


def load_delta_y_10y_daily_decimal() -> dict:
    """Δy_10Y daily come dict {date.date(): Δy_decimal} (PROXY).

    Da req10c_yields_full.csv col `US10YT=RR` in PERCENT. Δy_decimal[t] =
    (y_pct[t] - y_pct[t-1]) / 100. Bias: include tutto il giorno, non solo
    la finestra HFI. Documentato come proxy. Per giorni con NaN nello yield
    (festività benchmark), Δy non disponibile → la chiave NON è inclusa
    e l'evento/control verrà filtrato a valle.
    """
    df = pd.read_csv(BENCHMARK_YIELDS_CSV, usecols=["Date", BENCHMARK_YIELD_COL])
    df["Date"] = pd.to_datetime(df["Date"]).dt.date
    df = df.dropna(subset=[BENCHMARK_YIELD_COL]).sort_values("Date").reset_index(drop=True)
    df["dy_decimal"] = df[BENCHMARK_YIELD_COL].diff() / 100.0
    df = df.dropna(subset=["dy_decimal"])
    return dict(zip(df["Date"], df["dy_decimal"]))


def delta_rate_ff_window(price_series: pd.Series, t_center: pd.Timestamp,
                          half_min: int = 15, edge_min: int = 5):
    """Δrate_decimal di un FF future sulla finestra ±half_min attorno a t_center.

    Convenzione coerente col 07 (median first/last edge_min): Δrate_decimal
    = -(median_post - median_pre) / 100 perché price_FF = 100·(1 - rate_decimal).
    Ritorna None se la finestra non ha quote valide.
    """
    t0 = t_center - pd.Timedelta(minutes=half_min)
    t1 = t_center + pd.Timedelta(minutes=half_min)
    w = price_series.loc[t0:t1].dropna()
    if w.empty:
        return None
    pre_w = w.loc[t0:t0 + pd.Timedelta(minutes=edge_min)]
    post_w = w.loc[t1 - pd.Timedelta(minutes=edge_min):t1]
    if pre_w.empty or post_w.empty:
        return None
    pre, post = float(pre_w.median()), float(post_w.median())
    if (np.isnan(pre) or np.isnan(post)):
        return None
    return -(post - pre) / 100.0


def delta_y_from_bond_future(price_series: pd.Series, t_center: pd.Timestamp,
                              D_years: float, half_min: int = 15,
                              edge_min: int = 5):
    """Δy_implicita decimal annualizzata derivata dal future bond (TY/FGBL).

    Convenzione coerente con extract_window del 07 (median first/last edge_min):
      log_return = log(P_post/P_pre)
      Δy ≈ -log_return / D_CTD_anni    (annualizzata, in decimal)
    Ritorna None se la finestra non ha quote sufficienti.
    """
    t0 = t_center - pd.Timedelta(minutes=half_min)
    t1 = t_center + pd.Timedelta(minutes=half_min)
    w = price_series.loc[t0:t1].dropna()
    if w.empty:
        return None
    pre_w = w.loc[t0:t0 + pd.Timedelta(minutes=edge_min)]
    post_w = w.loc[t1 - pd.Timedelta(minutes=edge_min):t1]
    if pre_w.empty or post_w.empty:
        return None
    pre, post = float(pre_w.median()), float(post_w.median())
    if not (pre > 0 and post > 0):
        return None
    import math as _math
    log_ret = _math.log(post / pre)
    return -log_ret / float(D_years)


def event_delta_f_curve(t_event: pd.Timestamp, prices: dict, ric_list,
                         long_end_ric: str = None, long_end_dur: float = None,
                         ultra_long_proxy_by_date: dict = None):
    """Δrate_decimal per i RIC front + (opzionale) Δy_long_end al 10Y + (opz.) ultra-long daily.

    Ritorna np.array di lunghezza len(ric_list) (+1 se long_end) (+1 se ultra),
    o None se una qualunque ancora intraday manca.
    L'ultra-long daily NON è bloccante (drop solo se la data manca proprio dal dict).
    """
    vals = []
    for r in ric_list:
        v = delta_rate_ff_window(prices[r], t_event)
        if v is None:
            return None
        vals.append(v)
    if long_end_ric is not None:
        v_long = delta_y_from_bond_future(prices[long_end_ric], t_event,
                                          D_years=long_end_dur)
        if v_long is None:
            return None
        vals.append(v_long)
    if ultra_long_proxy_by_date is not None:
        d = t_event.date()
        v_ultra = ultra_long_proxy_by_date.get(d)
        if v_ultra is None:
            return None
        vals.append(float(v_ultra))
    return np.array(vals, dtype=float)


def cluster_control_delta_f_curve(controls: list, prices: dict, ric_list,
                                    long_end_ric: str = None,
                                    long_end_dur: float = None,
                                    ultra_long_proxy_by_date: dict = None):
    """Δrate_decimal medio (front + long-end + ultra-long opzionali) sui controlli."""
    rows = []
    for c in controls:
        t_c = pd.Timestamp(c["center"])
        v = event_delta_f_curve(t_c, prices, ric_list,
                                 long_end_ric=long_end_ric,
                                 long_end_dur=long_end_dur,
                                 ultra_long_proxy_by_date=ultra_long_proxy_by_date)
        if v is None:
            continue
        rows.append(v)
    if not rows:
        return None
    return np.array(rows, dtype=float).mean(axis=0)


def cluster_control_delta_y_bond(controls: list, dy_10y_by_date: dict):
    """Δy_10Y_daily medio sui giorni dei controlli (decimal). None se vuoto."""
    vals = []
    for c in controls:
        d = pd.Timestamp(c["center"]).date()
        if d in dy_10y_by_date:
            vals.append(dy_10y_by_date[d])
    return float(np.mean(vals)) if vals else None


def alt_precheck(events_cell: list, alt_dict: dict, alpha: float,
                  key_by: str = "date"):
    """Precheck Nagel-Xu con sorpresa esterna (dict {date:value} o {(y,m):value}).

    key_by='date' (default) match per data dell'evento. key_by='year_month'
    match per (year, month) della data di rilascio (per NFP_SURP Bauer-Swanson).
    """
    df_m, surprise = [], []
    for ev in events_cell:
        t = pd.Timestamp(ev["ts_event"])
        if key_by == "date":
            k = t.date()
        elif key_by == "year_month":
            k = (t.year, t.month)
        else:
            raise ValueError(f"key_by sconosciuto: {key_by!r}")
        if k in alt_dict:
            df_m.append(float(ev["delta_f_curve"][-1]))
            surprise.append(alt_dict[k])
    if len(df_m) < 3:
        return {"status": "INSUFF", "n": int(len(df_m))}
    pc = G12.tail_border_precheck(
        np.asarray(df_m, dtype=float),
        np.asarray(surprise, dtype=float),
        alpha=alpha,
    )
    return pc


def build_events_for_cell(clusters, leg, me_by_ts,
                            dy_10y_by_date, prices, ric_list,
                            long_end_ric=None, long_end_dur=None,
                            ultra_long_proxy_by_date=None):
    """Trasforma i cluster (07) in events del 12 con control = MEDIA dei controlli.

    Bug 2 fix (2026-06-23): `delta_y_bond` NON è più `delta_rate_3` (= ΔFFc3
    money-market) ma il PROXY DAILY Δy_10Y benchmark (req10c, US10YT=RR), con
    bias documentato. Stesso proxy per il control day → netting simmetrico bond.

    Bug 1 fix (2026-06-23): `delta_f_curve_control` ricavato dai FFc1/2/3
    intraday sui control window dei cluster del 07 (mediana sui control del cluster).

    Esclude i cluster privi di delta_rate_*/m_e/Δy_10Y_daily nel CSV (non si fabbrica).
    Ritorna (events_list, surprise_array_per_event, drop_log).
    """
    events, surprises = [], []
    drop_log = {"no_curve_event": 0, "no_controls": 0, "no_curve_control": 0}
    for cl in clusters:
        ts_event = pd.Timestamp(cl["event"]["center"])
        df_curve_ev = event_delta_f_curve(ts_event, prices, ric_list,
                                           long_end_ric=long_end_ric,
                                           long_end_dur=long_end_dur,
                                           ultra_long_proxy_by_date=ultra_long_proxy_by_date)
        if df_curve_ev is None:
            drop_log["no_curve_event"] += 1
            continue
        controls = cl.get("controls") or []
        if not controls:
            drop_log["no_controls"] += 1
            continue
        df_curve_ctrl = cluster_control_delta_f_curve(controls, prices, ric_list,
                                                       long_end_ric=long_end_ric,
                                                       long_end_dur=long_end_dur,
                                                       ultra_long_proxy_by_date=ultra_long_proxy_by_date)
        if df_curve_ctrl is None:
            drop_log["no_curve_control"] += 1
            continue
        re_c = float(np.mean([c["r_e"] for c in controls]))
        rb_c = float(np.mean([c["r_b"] for c in controls]))
        events.append({
            "ts_event": ts_event,                                  # per lookup sorprese esterne
            "r_e_event": float(cl["event"]["r_e"]),
            "r_e_control": re_c,
            "r_b_event": float(cl["event"]["r_b"]),
            "r_b_control": rb_c,
            "delta_f_curve": df_curve_ev,                          # decimal, n=len(ric_list)
            "delta_f_curve_control": df_curve_ctrl,                # decimal, n=len(ric_list)
            "D_bond_periods": D_BOND_PERIODS,
        })
        me = me_by_ts.get(ts_event, np.nan)
        surprises.append(me if not np.isnan(me) else 0.0)
    return events, np.array(surprises, dtype=float), drop_log


def main() -> int:
    print(f"=== execute_12.py — {TASK_TIMESTAMP} (seed_name={SEED_NAME}) ===")
    print(f"  D_bond={D_BOND:.6f}  dp_bar={DP_BAR}  N={N_HORIZON}  B={cfg12.B_BOOT}")

    # 1) CSV eventi: estrai delta_rate_1/2/3 + m_e per timestamp
    print("  loading events CSV (delta_rate_*, m_e) ...")
    ev_csv = pd.read_csv(EVENTS_CSV, usecols=["timestamp", "event_class",
                                                "delta_rate_1", "delta_rate_2",
                                                "delta_rate_3", "m_e"])
    ev_csv["timestamp"] = pd.to_datetime(ev_csv["timestamp"], utc=True)
    delta_curve_by_ts = {ts: (d1, d2, d3) for ts, d1, d2, d3 in
                          zip(ev_csv["timestamp"], ev_csv["delta_rate_1"],
                              ev_csv["delta_rate_2"], ev_csv["delta_rate_3"])}
    me_by_ts = dict(zip(ev_csv["timestamp"], ev_csv["m_e"]))
    # 2026-06-24 — split ECB decision vs press (15 min finestra ciascuno,
    # eventi separati da ~45 min): mappa timestamp → subtype per riconoscere
    # i due eventi distinti dentro il cluster ECB.
    ev_csv_full = pd.read_csv(EVENTS_CSV, usecols=["timestamp", "event_class", "subtype"])
    ev_csv_full["timestamp"] = pd.to_datetime(ev_csv_full["timestamp"], utc=True)
    subtype_by_ts = dict(zip(ev_csv_full["timestamp"], ev_csv_full["subtype"]))
    print(f"    eventi CSV: {len(ev_csv)}")

    # 1bis) Δy_10Y daily (residuo Bug 2 v1 — non più nel calcolo bond, solo
    # diagnostico/manifesto) e short-rate strip intraday (FF/SR/FEI) per
    # ricostruzione delta_f_curve evento + controllo.
    print("  loading Δy_10Y daily (diagnostico) + short-rate strip intraday ...")
    dy_10y_by_date = load_delta_y_10y_daily_decimal()
    print(f"    Δy_10Y daily: {len(dy_10y_by_date)} giorni in [{min(dy_10y_by_date)}, {max(dy_10y_by_date)}]")

    # 1ter) Sorprese ESTERNE per il precheck (improvement 6 esteso 2026-06-23):
    #  - BS_MPS_ORTH (FOMC, ortogonalizzato vs SP500)
    #  - JK_MP_pm (FOMC e ECB, posterior monetary-policy shock)
    #  - BS_NFP_SURP (NFP, surprise consensus-actual, mensile)
    #  - Δbreakeven_inflation_10Y daily (CPI, proxy della reazione attesa
    #    di inflazione — bias daily dichiarato)
    print("  loading sorprese esterne (BS_MPS_ORTH/NFP_SURP, JK_MP_pm, breakeven) ...")
    bs_mps_orth_by_date = load_bs_mps_orth_by_date()
    bs_nfp_surp_by_ym = load_bs_nfp_surp_by_ym()
    jk_fed_by_date = load_jk_mp_pm_by_date("Fed")
    jk_ecb_by_date = load_jk_mp_pm_by_date("ECB")
    dbe_by_date = load_breakeven_diff_decimal_by_date()
    cpi_surp_by_ym = load_cpi_surprise_mom_by_release_ym()
    # EA-MPD finestre separate decision (Target) vs conference (Path, QE)
    eampd_target_by_date = load_eampd_shock_by_date("Press Release Window", "OIS_1M")
    eampd_path_by_date   = load_eampd_shock_by_date("Press Conference Window", "OIS_2Y")
    eampd_qe_by_date     = load_eampd_shock_by_date("Press Conference Window", "OIS_10Y")
    print(f"    BS_MPS_ORTH (FOMC): {len(bs_mps_orth_by_date)} obs")
    print(f"    BS_NFP_SURP (NFP, monthly): {len(bs_nfp_surp_by_ym)} obs")
    print(f"    JK Fed MP_pm: {len(jk_fed_by_date)} obs / JK ECB MP_pm: {len(jk_ecb_by_date)} obs")
    print(f"    Δbreakeven 5Y daily (CPI proxy daily): {len(dbe_by_date)} obs")
    print(f"    CPI surprise MoM (req08, consensus Reuters): {len(cpi_surp_by_ym)} obs")
    print(f"    EA-MPD Target (decision OIS_1M): {len(eampd_target_by_date)} obs")
    print(f"    EA-MPD Path (conf OIS_2Y): {len(eampd_path_by_date)} obs")
    print(f"    EA-MPD QE (conf OIS_10Y): {len(eampd_qe_by_date)} obs")

    # 1quater) Ultra-long-end daily proxy (improvement "curva oltre 10Y"):
    # Δy_30Y daily da req10c, usato come ulteriore ancora US (dopo il 10Y
    # intraday). Bias daily dichiarato (rumore extra-finestra).
    dy_30y_by_date = load_delta_y_30y_daily_decimal()
    dy_de30y_by_date = load_delta_y_de30y_daily_decimal()
    print(f"    Δy_30Y daily (US ultra-long proxy): {len(dy_30y_by_date)} obs")
    print(f"    Δy_DE30Y daily (EU ultra-long proxy, req22): {len(dy_de30y_by_date)} obs")

    # 2) Ricostruisco i cluster del 07 (riuso esatto: stesso MASTER_SEED, stessi parametri)
    print("  reconstructing per_type_clusters via 07 pipeline ...")
    events_full = data07.load_events(EVENTS_CSV)
    prices = run07.load_prices()  # ora include FF, SR, FEI via config 07 aggiornato
    regs = run07.compute_regimes(prices)
    cont = load_contaminant_centers(CONTAMINANTS_CSV)
    ev_centers = set(pd.to_datetime(events_full["timestamp"], utc=True))
    reject = run07.build_calendar_reject(ev_centers, cont)
    per_type, _accounting = run07.assemble(events_full, prices, regs, reject)
    per_type, dedup_report = win07.dedup_shared_controls(per_type)
    print(f"    per_type built. dedup_shared = {dedup_report}")
    for t in cfg07.EVENT_TYPES:
        n_pos = len(per_type[t]["pos"]); n_neg = len(per_type[t]["neg"])
        print(f"    {t}: pos={n_pos}  neg={n_neg}")

    # 3) Per ciascuna delle 8 celle, costruisci events + surprise, esegui run_cell
    print("  running cell_pipeline on 4×2 cells ...")
    rng = cfg12.make_rng(SEED_NAME)
    cell_outputs = {}
    diagnostics = {}
    # Itero le celle. Per ECB suddivido decision vs press in due sotto-celle
    # separate (eventi distinti a ~45 min di distanza; mescolarli dilavi il segnale).
    def iter_cells():
        for leg in cfg07.EVENT_TYPES:
            if leg == "ECB":
                for sub in ("decision", "press"):
                    yield leg, sub
            else:
                yield leg, None

    for leg, ecb_subtype in iter_cells():
        if leg == "ECB":
            ric_list = list(CURVE_RICS_EU)
            long_end_ric, long_end_dur = LONG_END_RIC_EU, LONG_END_DUR_EU
            ultra_long_proxy = dy_de30y_by_date  # DE30Y daily, req22 (2026-06-24)
        else:
            ric_list = list(CURVE_RICS_US)
            long_end_ric, long_end_dur = LONG_END_RIC_US, LONG_END_DUR_US
            ultra_long_proxy = dy_30y_by_date
        for reg in ("pos", "neg"):
            clusters_all = per_type[leg][reg]
            if ecb_subtype is not None:
                # filtra per subtype usando il mapping timestamp→subtype del CSV
                clusters = [cl for cl in clusters_all
                            if subtype_by_ts.get(pd.Timestamp(cl["event"]["center"]).tz_convert("UTC")
                                                  if pd.Timestamp(cl["event"]["center"]).tz
                                                  else pd.Timestamp(cl["event"]["center"], tz="UTC")) == ecb_subtype]
                cell_label = f"{leg}_{ecb_subtype}/{reg}"
            else:
                clusters = clusters_all
                cell_label = f"{leg}/{reg}"
            events_cell, surprise, drop_log = build_events_for_cell(
                clusters, leg, me_by_ts,
                dy_10y_by_date, prices, ric_list,
                long_end_ric=long_end_ric, long_end_dur=long_end_dur,
                ultra_long_proxy_by_date=ultra_long_proxy)
            diagnostics[cell_label] = {
                "n_clusters": len(clusters),
                "n_events_emitted": len(events_cell),
                "n_dropped_total": len(clusters) - len(events_cell),
                "drop_log": drop_log,
            }
            if len(events_cell) < 5:
                print(f"    {cell_label}: n_events_emitted={len(events_cell)} <5 → cella SKIP")
                cell_outputs[(cell_label, reg)] = {
                    "n": len(events_cell),
                    "verdict": "channel_not_identified",
                    "gate_a": "FAIL",
                    "skipped_reason": "n<5_post_curve_match",
                }
                continue
            try:
                out = CP.run_cell(events_cell, dp_bar=DP_BAR, N=N_HORIZON,
                                    rng=rng, surprise_per_event=surprise,
                                    bond_method=BOND_METHOD, bond_tail=BOND_TAIL,
                                    equity_tails=EQUITY_TAILS,
                                    equity_rho_offsets=EQUITY_RHO_OFFSETS)
                # Alternative precheck con sorprese esterne (improvement 6)
                alpha_pc = cfg12.TAIL_BORDER_SIGNIFICANCE_ALPHA
                alts = {}
                if leg == "FOMC":
                    alts["BS_MPS_ORTH"] = alt_precheck(events_cell, bs_mps_orth_by_date, alpha_pc)
                    alts["JK_MP_pm"] = alt_precheck(events_cell, jk_fed_by_date, alpha_pc)
                elif leg == "ECB":
                    # JK ECB shocks sono per meeting → validi su entrambi i subtype.
                    alts["JK_MP_pm"] = alt_precheck(events_cell, jk_ecb_by_date, alpha_pc)
                    # EA-MPD sorprese specifiche per finestra (Altavilla 2019):
                    # decision → Target (Δ OIS_1M sulla press release window)
                    # press → Path (Δ OIS_2Y conf window, FG) e QE (Δ OIS_10Y conf, QE).
                    if ecb_subtype == "decision":
                        alts["EA_MPD_Target_OIS1M"] = alt_precheck(
                            events_cell, eampd_target_by_date, alpha_pc)
                    elif ecb_subtype == "press":
                        alts["EA_MPD_Path_OIS2Y"] = alt_precheck(
                            events_cell, eampd_path_by_date, alpha_pc)
                        alts["EA_MPD_QE_OIS10Y"] = alt_precheck(
                            events_cell, eampd_qe_by_date, alpha_pc)
                elif leg == "NFP":
                    alts["BS_NFP_SURP"] = alt_precheck(events_cell, bs_nfp_surp_by_ym,
                                                        alpha_pc, key_by="year_month")
                elif leg == "CPI":
                    alts["CPI_SURP_MOM"] = alt_precheck(events_cell, cpi_surp_by_ym,
                                                         alpha_pc, key_by="year_month")
                    alts["dbreakeven_5Y"] = alt_precheck(events_cell, dbe_by_date, alpha_pc)
                out["precheck_alt"] = alts
                cell_outputs[(cell_label, reg)] = out
                pc_str = " ".join(f"{k}={v.get('status','-')}" for k, v in alts.items())
                print(f"    {cell_label}: n={out['n']:3d} F_MOP={out['F_MOP']:.3g} "
                      f"shrink={out['shrink']:.4g} gate_a={out['gate_a']} "
                      f"precheck(m_e)={out['precheck']['status']} {pc_str}")
            except Exception as e:
                print(f"    {cell_label}: FAIL run_cell with {type(e).__name__}: {e}")
                cell_outputs[(cell_label, reg)] = {
                    "n": len(events_cell),
                    "verdict": "channel_not_identified",
                    "gate_a": "FAIL",
                    "error": f"{type(e).__name__}: {e}",
                }

    # 4) Manifest via kernel del 12
    pkl_sha = sha256_file(PICKLE_AUTH_07)
    input_paths = [EVENTS_CSV, CONTAMINANTS_CSV, PICKLE_AUTH_07]
    code_paths = [PKG12 / f for f in ("cell_pipeline.py", "bond_pb.py", "equity_pb.py",
                                        "estimator.py", "gates.py", "netting.py",
                                        "config.py", "manifest.py")]
    m = MF12.build_manifest(
        cell_outputs={k: v for k, v in cell_outputs.items()
                       if "verdict" in v and "skipped_reason" not in v},
        input_paths=input_paths, code_paths=code_paths,
        seed_name=SEED_NAME, timestamp=TASK_TIMESTAMP,
    )
    m["executor"] = {
        "script_path": str(Path(__file__).resolve()),
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "package_path": str(PKG12),
        "namespace_output_dir": str(OUT_DIR),
        "reuse_of_07_clusters": {
            "pickle_07_authoritative": {"path": str(PICKLE_AUTH_07), "sha256": pkl_sha},
            "dedup_shared_report": dedup_report,
        },
    }
    m["external_constants"] = {
        "D_bond": D_BOND,
        "dp_bar": DP_BAR,
        "dp_bar_provenance": "canonico esterno, log(D/P) S&P 500 ≈ -3.85 (D/P ≈ 2.1% media 2010-2025), pre-registrato",
        "N_horizon": N_HORIZON,
        "bond_method": (
            "curve (2026-06-23 fix v2): ΔP^B_b ricostruito dalla curva osservata "
            "(Δf_1,2,3 dei FFc1/2/3) come rivalutazione CTD lungo la curva, senza "
            "ρ-discount perché bond a maturità finita. Formula: ΔP^B_b = "
            "-Σ_{n=1..N_b} Δf_n con tail extrapolation 'TC' (Δf_n=Δf_3 oltre il "
            "bordo osservato). N_b = round(D_BOND·4) = round(35.88) = 36 trimestri. "
            "Sostituisce la formula precedente ΔP^B_b = -D·Δy_daily (Bug 2 v1 "
            "abbandonato perché il proxy daily gonfiava la varianza ⇒ shrink > 1)."
        ),
        "bond_tail_extrapolation": (
            "TC (constant): Δf_n = Δf_m per n > m=3, dove m è la lunghezza dei "
            "Δf osservati (3 punti). Hp implicita: oltre il bordo osservato della "
            "curva front, la term structure si è spostata uniformemente al livello "
            "del bordo. Alternative T0 (Δf=0 dopo m, più defensivo) e TD_λ "
            "(decadimento) non scelte: T0 sottostima il segnale rate, TD non "
            "calibrabile senza più punti curva."
        ),
        "bond_control_treatment": (
            "Bug 1 fix lato bond (2026-06-23): netting simmetrico tramite stessa "
            "formula curve-based applicata a delta_f_curve_control (Δrate FFc1/2/3 "
            "intraday sui control window). L'asimmetria storica (ΔP^B_b=0 sui "
            "controlli) è eliminata."
        ),
        "delta_f_curve_control_source": (
            "FFc1/2/3 intraday 2026-06-23 (Bug 1 fix lato equity, netting simmetrico): "
            "Δrate_decimal = -(median_post - median_pre)/100 sulla finestra ±15 min "
            "con bordi median 5 min — convenzione coerente con extract_window del 07. "
            "Aggregato come media dei control window del cluster. Sostituisce "
            "l'assunzione storica ΔP^B_e=0 sui controlli."
        ),
        "delta_f_curve_units": "decimale (BPS÷10000) sui front 1/2/3 della term-structure money-market",
        "surprise_per_event": "m_e (PC1 money-market PCA) dal CSV eventi v2",
    }
    m["diagnostics_per_cell"] = diagnostics
    MF12.write_manifest(OUT_DIR / "decomp_canali.manifest.json", m)
    print("  wrote decomp_canali.manifest.json")

    # 5) Report
    rows = []
    for (leg, reg), out in sorted(cell_outputs.items()):
        if "skipped_reason" in out:
            rows.append({
                "cell": f"{leg}/{reg}", "n": out["n"], "shrink": None,
                "F_MOP": None, "gate_a": out["gate_a"], "beta_str_central": None,
                "constr_band_min": None, "constr_band_max": None,
                "constr_band_width": None,
                "sampling_band_low": None, "sampling_band_high": None,
                "total_band_low": None, "total_band_high": None,
                "precheck_status": None, "precheck_method": None,
                "verdict": out["verdict"], "skipped_reason": out.get("skipped_reason"),
                "error": out.get("error"),
            })
            continue
        cb = out["construction_band"]; sb = out["sampling_band"]; tb = out["total_band"]
        pc = out["precheck"]
        rows.append({
            "cell": f"{leg}/{reg}",
            "n": int(out["n"]),
            "shrink": float(out["shrink"]),
            "F_MOP": float(out["F_MOP"]),
            "gate_a": str(out["gate_a"]),
            "beta_str_central": float(out["beta_str_central"]),
            "constr_band_min": float(cb["min"]),
            "constr_band_max": float(cb["max"]),
            "constr_band_width": float(cb["width"]),
            "sampling_band_low": float(sb["low"]),
            "sampling_band_high": float(sb["high"]),
            "total_band_low": float(tb["low"]),
            "total_band_high": float(tb["high"]),
            "precheck_status": str(pc.get("status")),
            "precheck_method": str(pc.get("method")),
            "precheck_slope": (float(pc["slope"]) if pc.get("slope") is not None else None),
            "precheck_p": (float(pc["p"]) if pc.get("p") is not None else None),
            "verdict": str(out["verdict"]),
        })

    report = {
        "task_timestamp": TASK_TIMESTAMP,
        "package": "12_decomposizione_canali",
        "seed_name": SEED_NAME,
        "config_hash": cfg12.config_hash(),
        "config_version": cfg12.CONFIG_VERSION,
        "external_constants": m["external_constants"],
        "diagnostics_per_cell": diagnostics,
        "table_section_6_per_cell": rows,
        "labeling": (
            "verdetto per cella ∈ {channel_not_identified, identified_fragile, "
            "identified_robust}, NON una singola cifra 'il canale spiega X%'. "
            "Le tre etichette sono pre-registrate."
        ),
        "replicability_assumption_5_points": m["replicability_assumption"],
    }
    (OUT_DIR / "decomp_canali.report.json").write_bytes(
        json.dumps(report, indent=2, sort_keys=True, default=str).encode("utf-8"))
    print("  wrote decomp_canali.report.json")

    # 6) Log di custodia
    lines = [
        "=== Log di custodia — pacchetto 12 (decomposizione canali) ===",
        f"task_timestamp:       {TASK_TIMESTAMP}",
        f"seed_name:            {SEED_NAME}",
        f"seed_value:           {cfg12.seed_for(SEED_NAME)}",
        f"config_version:       {cfg12.CONFIG_VERSION}",
        f"config_hash:          {cfg12.config_hash()}",
        f"MOP_CV (soglia gate_a):    {cfg12.MOP_CV}",
        f"SHRINK_FLOOR (gate_a aux): {cfg12.SHRINK_FLOOR_DEFAULT}",
        f"BAND_WIDTH_THRESHOLD (b):  {cfg12.BAND_WIDTH_THRESHOLD_DEFAULT}",
        f"D_bond:               {D_BOND}",
        f"dp_bar (canonico):    {DP_BAR}",
        f"N_horizon:            {N_HORIZON}",
        f"B_BOOT:               {cfg12.B_BOOT}",
        "",
        "Riuso cluster 07 (coerenza inter-pacchetto):",
        f"  pickle_07_sha256:   {pkl_sha}",
        f"  dedup_shared:       {dedup_report}",
        "",
        "Inputs (sha256):",
        f"  events_CSV          sha256={sha256_file(EVENTS_CSV)}",
        f"  contaminants_CSV    sha256={sha256_file(CONTAMINANTS_CSV)}",
        f"  pickle_07_auth      sha256={pkl_sha}",
        "",
        "Code modules (sha256):",
    ]
    for p in code_paths:
        lines.append(f"  {p.name:24s} sha256={sha256_file(p)}")
    lines += [
        "",
        "Tabella §6 (per cella):",
        f"  {'cella':14s} {'n':>4s}  {'F_MOP':>10s}  {'shrink':>9s}  {'gate_a':>6s}  "
        f"{'β_str_C':>10s}  {'constr_width':>13s}  {'precheck':>10s}  {'verdict':>22s}",
    ]
    for r in rows:
        n = r["n"]; gate = r["gate_a"]
        F_str = f"{r['F_MOP']:10.4f}" if r["F_MOP"] is not None else "         -"
        s_str = f"{r['shrink']:9.4f}" if r["shrink"] is not None else "        -"
        b_str = f"{r['beta_str_central']:10.4f}" if r["beta_str_central"] is not None else "         -"
        w_str = f"{r['constr_band_width']:13.4f}" if r["constr_band_width"] is not None else "            -"
        pc_str = (r["precheck_status"] or "-")[:10]
        lines.append(f"  {r['cell']:14s} {n:>4d}  {F_str}  {s_str}  {gate:>6s}  "
                     f"{b_str}  {w_str}  {pc_str:>10s}  {r['verdict']:>22s}")
    lines += [
        "",
        "Verdetto pre-registrato: per cella ∈ {channel_not_identified, identified_fragile, identified_robust}.",
        "Caveat: bond_pb usa Δy=delta_rate_3 (proxy long-end via term structure); shrink≈0 ⇒ FAIL atteso (caso 2 §7).",
    ]
    (OUT_DIR / "decomp_canali.log.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("  wrote decomp_canali.log.txt")

    print(f"\nDONE → {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
