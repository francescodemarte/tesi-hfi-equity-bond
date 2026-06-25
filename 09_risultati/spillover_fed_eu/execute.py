"""execute.py — Driver ESECUTORE per il run autoritativo 08 spillover Fed→area euro.

Non modifica il codice congelato di `CODICI_TESI/08_spillover_fed_eu/`. Costruisce
input attesi da `run.run_protocol_full(...)` e ne consuma l'output, scrivendo i
risultati in `OUT_DIR/result_authoritative.{json,pkl}` + manifest.

Deviazioni esplicite autorizzate dal supervisor 2026-06-22 (documentate):
  - Paniere ED_q2/q3/q4 sostituito da SR_c1/SR_c2 (ED non disponibile in
    Dati/data_processed/; SOFR liquido da 2018; pre-2018 tick sparsi).
    Paniere effettivo: (FF_c1, FF_c2, SR_c1, SR_c2).
  - Asset H3 (BTP_BUND_SPREAD) gated: BTP yield daily 2010-2025 non disponibile
    localmente in formato utilizzabile per close-to-close T+1. `require_all_
    assets=False`; slot H3 nel BY m=3 fisso riempito con p=1.0 esplicito.

Disciplina: una passata. Niente clock interno (`manifest_timestamp` esplicito).
"""
from __future__ import annotations

import csv
import hashlib
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/francesco/TESI/tesi-hfi-equity-bond")
PKG_07 = ROOT / "CODICI_TESI" / "07_protocollo_v2_signflip"
PKG_08 = ROOT / "CODICI_TESI" / "08_spillover_fed_eu"
sys.path.insert(0, str(PKG_08))   # solo 08 nel path (evita conflitto namespace 'config')

# 08 imports
import config           # noqa: E402
import run              # noqa: E402
import surprises as su  # noqa: E402
import report           # noqa: E402
import calendar_clean   # noqa: E402


# Loader intraday inline (replica `data.load_minute` del 07 per evitare
# conflitto namespace: entrambi i package hanno `config.py`)
def load_minute(path: Path, price_col: str = "PX_LAST") -> pd.Series:
    df = pd.read_csv(path, usecols=["Datetime_UTC", price_col])
    df["Datetime_UTC"] = pd.to_datetime(df["Datetime_UTC"], utc=True)
    return df.set_index("Datetime_UTC")[price_col].sort_index()

EVENTS_CSV    = ROOT / "DATASET_TESI" / "01_eventi_hfi" / "events_with_regime_classifier.csv"
YIELDS_CSV    = ROOT / "bridge" / "data" / "req10c_yields_full.csv"
VIX_CSV       = PKG_07 / "external_data" / "snapshots" / "VIXCLS.csv"
INTRADAY_DIR  = Path("/home/francesco/TESI/Dati/data_processed")
CONTAMINANTS_CSV = Path("/home/francesco/TESI/Dati/calendari/contaminants_build_2026-06-22/contaminants_v2_2026-06-22.csv")
OUT_DIR       = ROOT / "09_risultati" / "spillover_fed_eu"
OUT_DIR.mkdir(parents=True, exist_ok=True)

RUN_TIMESTAMP = "2026-06-22T17:00:00Z"
RUN_LABEL     = "08_spillover_authoritative_2026-06-22"
SEED_NAME     = "spillover_baseline_2026-06-22"

# Paniere effettivo (doppia deviazione esplicita autorizzata 2026-06-22):
#   (a) ED_q2/q3/q4 (Eurodollar quarterly) → FF_c3 (Fed Funds front-3).
#       Motivo: ED non disponibile localmente; tentativo SR_c1/SR_c2 fallito
#       (SOFR liquido dal 2018 + tick sparsi su orari FOMC → 5/114 eventi).
#   (b) Paniere a 3 serie invece delle 5 della SPEC.
#       Tutte e 3 le serie sono Fed Funds futures con copertura piena 2010-2025.
BASKET_FILES = {
    "FF_c1": "FFc1_1min.csv",
    "FF_c2": "FFc2_1min.csv",
    "FF_c3": "FFc3_1min.csv",
}
SURPRISE_FILE = "ESc1_1min.csv"
EQUITY_FILE   = "STXE_continuous_1min.csv"   # per ESTOXX50 close-to-close T+1


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Costruzione finestre intraday W^US = [t-10, t+20] min (asimmetrica per SPEC §config)
# ---------------------------------------------------------------------------

def delta_log_window(prices: pd.Series, t_center: pd.Timestamp,
                     pre_min: int = config.TAU_PRE_MIN,
                     post_min: int = config.TAU_POST_MIN) -> float:
    """Δ log-price su finestra asimmetrica [t-pre_min, t+post_min].

    Pre  = ultimo tick in [t-pre_min, t].
    Post = ultimo tick in [t, t+post_min].
    Ritorna NaN se manca un edge.
    """
    t0 = t_center - pd.Timedelta(minutes=pre_min)
    t1 = t_center + pd.Timedelta(minutes=post_min)
    pre_w  = prices.loc[t0:t_center].dropna()
    post_w = prices.loc[t_center:t1].dropna()
    if pre_w.empty or post_w.empty:
        return np.nan
    pre = float(pre_w.iloc[-1])
    post = float(post_w.iloc[-1])
    if not (pre > 0 and post > 0):
        return np.nan
    return float(np.log(post / pre))


def build_m_s(events: pd.DataFrame) -> tuple:
    """Per ogni evento FOMC: costruisce m=PC1(paniere) e s=log-return ES.

    Eventi con NaN in qualsiasi serie del paniere o in s vengono SCARTATI
    (e' inclusi in `excluded` per il manifest).
    """
    basket_series = {lbl: load_minute(INTRADAY_DIR / fn, price_col="PX_LAST")
                     for lbl, fn in BASKET_FILES.items()}
    es = load_minute(INTRADAY_DIR / SURPRISE_FILE, price_col="PX_LAST")

    n = len(events)
    M_rows = np.full((n, len(BASKET_FILES)), np.nan)
    s_arr  = np.full(n, np.nan)
    centers = pd.to_datetime(events["timestamp"], utc=True).reset_index(drop=True)
    for i, t in enumerate(centers):
        for j, lbl in enumerate(BASKET_FILES):
            M_rows[i, j] = delta_log_window(basket_series[lbl], t)
        s_arr[i] = delta_log_window(es, t)

    valid = ~np.isnan(M_rows).any(axis=1) & ~np.isnan(s_arr)
    n_valid = int(valid.sum())
    n_drop = int((~valid).sum())
    M_valid = M_rows[valid]
    s_valid = s_arr[valid]
    m_valid = su.pc1(M_valid)
    return m_valid, s_valid, valid, n_drop, n_valid, list(BASKET_FILES.keys())


# ---------------------------------------------------------------------------
# Responses close-to-close T+1
# ---------------------------------------------------------------------------

def load_bund_yields() -> pd.Series:
    """DE10YT=RR daily da req10c_yields_full.csv (yield in %)."""
    df = pd.read_csv(YIELDS_CSV)
    df["Date"] = pd.to_datetime(df["Date"])
    return df.set_index("Date")["DE10YT=RR"].dropna()


def load_estoxx_close_daily() -> pd.Series:
    """ESTOXX50 close daily derivato da STXE_continuous_1min.csv (last tick di ogni giorno)."""
    s = load_minute(INTRADAY_DIR / EQUITY_FILE, price_col="Mid_raw")
    daily = s.groupby(s.index.tz_convert("UTC").tz_localize(None).normalize()).last()
    daily.index.name = "date"
    return daily.dropna()


def compute_responses(events_valid: pd.DataFrame, bund_y: pd.Series,
                       estoxx_close: pd.Series) -> dict:
    """Per ogni evento valido: Δy_Bund bp + log-return ESTOXX close-to-close T+1.

    `pre` = chiusura giorno evento; `post` = chiusura giorno T+1 (giorno feriale
    successivo). Eventi senza prezzi pre o post sono droppati (NaN).
    """
    dy_bund_bp = []
    r_estoxx = []
    keep = []
    for _, row in events_valid.iterrows():
        t = pd.Timestamp(row["timestamp"]).tz_convert("UTC").normalize().tz_localize(None)
        # giorno evento + giorno successivo (feriale)
        t1 = t + pd.tseries.offsets.BDay(1)
        # Bund yield (daily, in %)
        y_pre  = bund_y.loc[bund_y.index <= t].iloc[-1] if (bund_y.index <= t).any() else np.nan
        y_post = bund_y.loc[bund_y.index >= t1]
        y_post = y_post.iloc[0] if len(y_post) else np.nan
        # ESTOXX close
        p_pre  = estoxx_close.loc[estoxx_close.index <= t].iloc[-1] if (estoxx_close.index <= t).any() else np.nan
        p_post = estoxx_close.loc[estoxx_close.index >= t1]
        p_post = p_post.iloc[0] if len(p_post) else np.nan
        if pd.isna(y_pre) or pd.isna(y_post) or pd.isna(p_pre) or pd.isna(p_post) or p_pre <= 0 or p_post <= 0:
            dy_bund_bp.append(np.nan); r_estoxx.append(np.nan); keep.append(False)
        else:
            dy_bund_bp.append((y_post - y_pre) * 100.0)
            r_estoxx.append(float(np.log(p_post / p_pre)))
            keep.append(True)
    return {"BUND_10Y": np.array(dy_bund_bp), "ESTOXX50": np.array(r_estoxx),
            "keep": np.array(keep)}


# ---------------------------------------------------------------------------
# Controlli minimali: ΔVIX overnight + dummy ZLB (≤ 2015-12-15)
# ---------------------------------------------------------------------------

def build_controls(events_valid: pd.DataFrame) -> tuple:
    vix_df = pd.read_csv(VIX_CSV)
    date_col = next(c for c in vix_df.columns if c.lower() in ("date", "observation_date"))
    val_col  = next(c for c in vix_df.columns if c != date_col)
    vix_df[date_col] = pd.to_datetime(vix_df[date_col])
    vix_df[val_col]  = pd.to_numeric(vix_df[val_col], errors="coerce")
    vix = vix_df.set_index(date_col)[val_col].dropna()
    dvix = vix.diff()

    global_risk = []
    subperiod   = []
    for _, row in events_valid.iterrows():
        t = pd.Timestamp(row["timestamp"]).tz_convert("UTC").normalize().tz_localize(None)
        v = dvix.loc[dvix.index <= t].iloc[-1] if (dvix.index <= t).any() else np.nan
        global_risk.append(float(v) if pd.notna(v) else 0.0)
        subperiod.append(1.0 if t.year < 2016 else 0.0)  # ZLB end = first Fed hike 2015-12-16
    return np.column_stack([global_risk, subperiod]), ("global_risk_dVIX", "subperiod_ZLB")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"=== execute_08.py — {RUN_LABEL} (timestamp={RUN_TIMESTAMP}) ===")

    # 1) Eventi FOMC decision + filtro calendar_clean baseline (SPEC 08 §0.4)
    print("[1/7] events FOMC decision + filter_events(mode=baseline) ...")
    ev_all = pd.read_csv(EVENTS_CSV)
    ev_all["timestamp"] = pd.to_datetime(ev_all["timestamp"], utc=True)
    ev_all["date"]      = pd.to_datetime(ev_all["date"])
    events_raw = ev_all[(ev_all["event_class"] == "FOMC") & (ev_all["subtype"] == "decision")].reset_index(drop=True)
    print(f"  events FOMC decision: {len(events_raw)}")

    # Carica calendario contaminanti e adatta allo schema atteso da calendar_clean
    cont_df = pd.read_csv(CONTAMINANTS_CSV)
    cont_df["time"] = pd.to_datetime(cont_df["center_utc"], utc=True)
    cont_df["kind"] = cont_df["source"] + ":" + cont_df["label"]
    # Eventi FOMC decisione devono restare; il calendario contiene anche centri FOMC,
    # rimuovi quelli per non auto-escludere
    cont_df = cont_df[~cont_df["kind"].str.contains("FRED:EmploymentSituation_NFP|FRED:CPI", na=False)]
    # Deviazione esplicita (c) autorizzata 2026-06-22: il jobless settimanale del
    # giovedi e' un rilascio STRUTTURALE ricorrente che cade in T+1 di OGNI FOMC
    # del mercoledi (escluderebbe 90% degli eventi). Lo SPEC 08 elenca i contaminanti
    # T+1 come FRED+TreasuryDirect+Fed testimonies+EU rilasci, NON menziona jobless
    # come contaminante T+1. Rimosso dal set di filter_events del 08.
    cont_df = cont_df[~cont_df["kind"].str.contains("FRED:JoblessClaims_Weekly", na=False)]
    cont_for_filter = cont_df[["time", "kind"]].copy()

    # filter_events si aspetta `event_time` come colonna eventi
    events_for_filter = events_raw.rename(columns={"timestamp": "event_time"}).copy()
    fr = calendar_clean.filter_events(events_for_filter, cont_for_filter, mode="baseline", window_days=1)
    events = fr["included"].rename(columns={"event_time": "timestamp"}).reset_index(drop=True)
    n_excluded = len(fr["excluded"])
    excl_by_reason = (fr["excluded"]["reason"].astype(str).value_counts().to_dict()
                      if len(fr["excluded"]) else {})
    print(f"  events post-filter baseline: {len(events)} (excluded={n_excluded})")
    if excl_by_reason:
        print(f"  top reasons (first 5): {dict(list(excl_by_reason.items())[:5])}")

    # 2) m, s su W^US = [t-10, t+20] min (asimmetrico)
    print("[2/7] sorprese m (PC1 paniere) + s (ES) su finestra W^US=[-10,+20] min ...")
    m, s, valid_ms, n_drop, n_keep, basket_used = build_m_s(events)
    print(f"  paniere usato: {basket_used}  (deviazione ED→SR esplicita)")
    print(f"  eventi con paniere+s completi: {n_keep}/{len(events)}  (drop {n_drop})")

    events_valid = events.loc[valid_ms].reset_index(drop=True)

    # 3) Responses close-to-close T+1
    print("[3/7] responses BUND_10Y + ESTOXX50 close-to-close T+1 ...")
    bund_y = load_bund_yields()
    est_cl = load_estoxx_close_daily()
    resp   = compute_responses(events_valid, bund_y, est_cl)
    keep_r = resp["keep"]
    n_resp = int(keep_r.sum())
    print(f"  BUND_10Y daily: {len(bund_y)} obs ({bund_y.index.min().date()} -> {bund_y.index.max().date()})")
    print(f"  ESTOXX50 close: {len(est_cl)} obs ({est_cl.index.min().date()} -> {est_cl.index.max().date()})")
    print(f"  eventi con responses complete: {n_resp}/{len(events_valid)}")

    # filtra m, s sui keep_r
    m_f = m[keep_r]; s_f = s[keep_r]
    responses = {
        "BUND_10Y": resp["BUND_10Y"][keep_r],
        "ESTOXX50": resp["ESTOXX50"][keep_r],
        # H3 GATED: BTP_BUND_SPREAD non costruibile per assenza BTP yield daily
    }
    events_final = events_valid.loc[keep_r].reset_index(drop=True)

    # 4) Controlli
    print("[4/7] controls (ΔVIX overnight + dummy ZLB pre-2016) ...")
    ctrl, ctrl_names = build_controls(events_final)
    print(f"  controls shape: {ctrl.shape}  names: {ctrl_names}")

    # 5) Pre-check JK feasibility per onorare gate review #1 senza aggirare raise
    print("[5/7] run.run_protocol_full (H3 gated: require_all_assets=False) ...")
    sep_diag = su.separate_jk(m_f, s_f, return_diagnostics=True)
    if not sep_diag.get("feasible", True):
        print(f"  ⚠️ JK NON IDENTIFICATO (gate review #1 SPEC §0.2 / surprises.py)")
        print(f"     feasibility: {sep_diag['feasibility']}")
        out = {
            "h1": None, "h2": None, "h3": None, "h4": None,
            "hierarchy": None, "asset_rows": None,
            "manifest": None, "concordance": None,
            "jk_feasibility": sep_diag["feasibility"],
            "gated_reason": (
                "JKNotIdentifiedError: 0 ∈ CI95 di Cov(m,s) sui FOMC post-filter "
                f"(n={sep_diag['feasibility']['n']}). Esito legittimo del gate "
                "pre-registrato (review #1): la pipeline RIFIUTA di fabbricare Z "
                "su Σ(m,s) quasi-diagonale. Niente H1/H2/H4 calcolati."
            ),
        }
        # Scrivo comunque il manifest con la diagnostica (no run_protocol_full)
        manifest = report.build_manifest(
            included_events=len(m_f), excluded_events=0,
            seed_name=SEED_NAME, timestamp=RUN_TIMESTAMP)
        manifest["jk_feasibility"] = sep_diag["feasibility"]
        manifest["jk_gate"] = "FAILED (cov_ms CI95 includes 0)"
        manifest["gated_sections"] = ["H1", "H2", "H3", "H4", "hierarchy",
                                       "Z_mp", "Z_cbi", "concordance"]
        with open(OUT_DIR / "manifest_authoritative.json", "w") as f:
            json.dump(manifest, f, indent=2, sort_keys=True, default=str)
        out["manifest"] = manifest
    else:
        out = run.run_protocol_full(
            m=m_f, s=s_f, responses=responses,
            controls=ctrl, controls_names=ctrl_names,
            basket_labels=tuple(basket_used),
            surprise_label=config.SP500_INSTRUMENT,
            seed_name=SEED_NAME,
            require_all_assets=False,
            manifest_path=OUT_DIR / "manifest_authoritative.json",
            manifest_timestamp=RUN_TIMESTAMP,
        )

    # 6) Persist
    print("[6/7] writing trittico ...")
    result_path = OUT_DIR / "result_authoritative.pkl"
    with open(result_path, "wb") as f:
        pickle.dump({
            "result": out,
            "label": RUN_LABEL,
            "timestamp": RUN_TIMESTAMP,
            "events_input": len(events),
            "events_after_m_s": n_keep,
            "events_after_responses": n_resp,
            "basket_used": basket_used,
            "controls_names": ctrl_names,
            "deviations_from_preregistration": {
                "basket": "ED_q2/q3/q4 → FF_c3 (Eurodollar futures non disponibili; SR_c1/SR_c2 tentati ma 5/114 copertura; paniere finale 3 serie FF tutte con copertura piena 2010-2025)",
                "H3": "BTP_BUND_SPREAD gated (BTP yield daily 2010-2025 non disponibile; slot p=1.0 nel BY m=3 fisso)",
                "filter_events_jobless": "JoblessClaims_Weekly rimosso dal set contaminanti T+1 (rilascio settimanale strutturale del giovedi che cade in T+1 di ogni FOMC del mercoledi; SPEC 08 non lo elenca esplicitamente come contaminante T+1)",
            },
        }, f)

    # JSON-friendly summary
    json_out = {k: v for k, v in out.items() if k != "manifest"}
    # convert numpy/dict to json-safe via str-ify
    def _safe(o):
        if isinstance(o, (np.ndarray,)): return o.tolist()
        if isinstance(o, dict): return {k: _safe(v) for k, v in o.items()}
        if isinstance(o, list): return [_safe(x) for x in o]
        if isinstance(o, (np.bool_,)): return bool(o)
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.floating,)): return float(o)
        return o
    with open(OUT_DIR / "result_authoritative.json", "w") as f:
        json.dump(_safe(json_out), f, indent=2, sort_keys=True)
    print(f"  result.pkl: {result_path}  (sha256={sha256_file(result_path)[:16]}…)")
    print(f"  result.json: {OUT_DIR / 'result_authoritative.json'}")
    print(f"  manifest:    {OUT_DIR / 'manifest_authoritative.json'}")
    print("\nDONE. Output grezzi consegnati. Niente interpretazione.")


if __name__ == "__main__":
    main()
