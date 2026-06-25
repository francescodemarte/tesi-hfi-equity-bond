"""run.py — Orchestratore della pipeline pre-registrata v2 (T1–T9 + decomposizione daily).

⚠️ Punto d'ingresso per l'ESECUTORE (post-review agente 4) SUI DATI REALI.
L'agente 3 lo scrive e lo verifica per *import* e *smoke sintetico* (test_smoke.py);
NON lo esegue sui dati reali — preserva la pre-registrazione. Ogni cifra prodotta
entra nel manifest di provenienza (script+input+seed+config + diagnostica C0.2/T*).

Flusso:
  C0  load intraday + eventi → ricalcolo regime dal raw (corr 63gg, lag t-1, segno)
      → assemblaggio finestre evento+controllo (DST-aware) con reject C0.2 + drop-log
  T1  routing per cella (ΔVar gate, F-MOP, n≥n_min)
  T4/T5  Δ_H (χ²₁) + sign-flip (AR, gerarchia BY) — CENTRALE
  T2  Lewbel (gated)   T3  b_OLS−b_H   T6  NFP-vs-CPI + Cochran Q
  T7  regimi esogeni   T8  robustezza lista-4   T9  meccanismo (gated)
  decomposizione canali DAILY (secondaria, etichettata)
  → manifest con control_accounting + shared_control diagnostic
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import config
import data
import decomposition
import estimators             # noqa: F401
import inference              # noqa: F401
import mechanism
import provenance
import regimes
import surprises              # noqa: F401
import tests_protocol as tp
import weakiv
import windows

_ET = ZoneInfo("America/New_York")
_US_TYPES = ("FOMC", "CPI", "NFP")


def beta_grid():
    return np.arange(config.AR_BETA_LOW,
                     config.AR_BETA_HIGH + config.AR_STEP / 2, config.AR_STEP)


# --- C0.2: reject del calendario (parte deterministica + calendario contaminanti) ---

def is_jobless_thursday(center: pd.Timestamp) -> bool:
    """Finestra di controllo di giovedì alle 08:30 ET = jobless claims (escludi, §13bis)."""
    loc = center.tz_convert("America/New_York")
    return loc.weekday() == 3 and loc.hour == 8 and loc.minute == 30


def build_calendar_reject(event_centers, contaminant_centers=None):
    """reject(center) per C0.2: esclude i centri-evento, i jobless-Thursday (08:30 ET)
    e — se fornito — i contaminanti dal calendario CONGELATO (input a tempo di
    esecuzione, decisione A: FRED releases + aste Treasury major + testimonianze Fed).
    """
    ev = set(event_centers)
    cont = set(contaminant_centers or [])

    def reject(center):
        return (center in ev) or (center in cont) or is_jobless_thursday(center)
    return reject


# --- C0: caricamento e assemblaggio ---

def load_prices() -> dict:
    """Carica le serie prezzo intraday per simbolo (ES, TY, STXE, FGBL)."""
    out = {}
    for sym, (fname, col) in config.INTRADAY_FILES.items():
        out[sym] = data.load_minute(config.INTRADAY_DIR / fname, price_col=col)
    return out


def compute_regimes(prices: dict) -> dict:
    """Regime ricalcolato dal RAW (correzione #2): corr mobile 63gg dei rendimenti
    daily, lag t-1, segno. US su ES~TY, EU su STXE~FGBL. Ritorna {'US':..,'EU':..}."""
    out = {}
    for area, (eq, bo) in {"US": ("ES", "TY"), "EU": ("STXE", "FGBL")}.items():
        re = data.daily_log_returns_from_minute(prices[eq]).rename("eq")
        rb = data.daily_log_returns_from_minute(prices[bo]).rename("bond")
        daily = pd.concat([re, rb], axis=1).dropna()
        out[area] = regimes.rolling_sign_regime(daily, "eq", "bond")["regime"]
    return out


def assemble(events: pd.DataFrame, prices: dict, regime_by_area: dict,
             reject) -> tuple[dict, list]:
    """Assembla i cluster per cella (tipo × regime) e raccoglie il drop-log.

    Ritorna (per_type_clusters, accounting) dove per_type_clusters[tipo][reg] = lista
    di cluster {event, controls, meta:{year, magnitude}} e accounting è la lista dei
    record di provenienza dei controlli (verify-2).
    """
    per_type = {t: {"pos": [], "neg": []} for t in config.EVENT_TYPES}
    accounting = []
    ev_centers = set(pd.to_datetime(events["timestamp"], utc=True))

    # mappa regime per ogni evento (segno corr area, as-of ≤ data evento)
    area_of = lambda t: "EU" if t == "ECB" else "US"
    reg_assign = {}
    for area in ("US", "EU"):
        mask = events["event_class"].map(area_of) == area
        reg_assign[area] = regimes.assign_regime(events.loc[mask, "date"], regime_by_area[area])

    for area in ("US", "EU"):
        sub = events[events["event_class"].map(area_of) == area].reset_index(drop=True)
        labels = reg_assign[area]
        for i, row in sub.iterrows():
            t = row["event_class"]
            reg = labels[i]
            if reg not in ("positivo", "negativo"):
                continue
            eq_sym, bo_sym = config.INSTRUMENT_MAP[t]
            tzname = config.EVENT_TZ[t]
            asm = windows.assemble_event_controls(
                row["timestamp"], tzname, prices[eq_sym], prices[bo_sym],
                is_calendar_excluded=reject)
            ev = asm["event"]
            if ev["r_e"] is None or ev["r_b"] is None:
                continue
            year = pd.Timestamp(row["date"]).year
            cluster = {"event": ev, "controls": asm["controls"],
                       "meta": {"year": year, "magnitude": abs(ev["r_b"])}}
            key = "pos" if reg == "positivo" else "neg"
            per_type[t][key].append(cluster)
            accounting.append(provenance.control_accounting_record(
                f"{t}@{row['timestamp']}|{reg}", asm))
    return per_type, accounting


def run_protocol(per_type_clusters: dict, rng, B: int = config.B_BOOT) -> dict:
    """Esegue T1, T4/T5 e T6 sul set di celle assemblato (sezione RS, sempre disponibile)."""
    grid = beta_grid()
    cv = weakiv.mop_critical_value(K=config.MOP_K,
                                   worst_case_size=config.MOP_WORST_CASE_SIZE,
                                   nominal=config.MOP_NOMINAL_LEVEL)
    # R3/E2: dedup dei controlli condivisi tra regimi opposti PRIMA della stima,
    # così il χ²₁ del test centrale è indipendente per costruzione.
    per_type_clusters, dedup_report = windows.dedup_shared_controls(per_type_clusters)
    est = tp.estimate_per_type(per_type_clusters, rng, B=B)

    routing = {}
    for t, cells in est.items():
        routing[t] = {reg: (tp.t1_relevance(cells[reg], cv) if cells.get(reg) else None)
                      for reg in ("pos", "neg")}

    t5 = tp.t5_signflip(est, grid)
    t3 = {t: {reg: (tp.t3_amplitude(cells[reg]) if cells.get(reg) else None)
              for reg in ("pos", "neg")} for t, cells in est.items()}
    est_by_regime = {
        "positivo": {t: est[t]["pos"] for t in est if est[t].get("pos")},
        "negativo": {t: est[t]["neg"] for t in est if est[t].get("neg")},
    }
    t6 = tp.t6_type_specificity(t5, est_by_regime)

    # diagnostica controlli condivisi tra regimi opposti (validità χ²₁, R3)
    shared = {}
    for t, cells in per_type_clusters.items():
        pos_keys = [c["event"]["center"] for c in cells.get("pos", [])]
        neg_keys = [c["event"]["center"] for c in cells.get("neg", [])]
        shared[t] = windows.shared_control_diagnostic(
            [ct["center"] for cl in cells.get("pos", []) for ct in cl["controls"] if "center" in ct],
            [ct["center"] for cl in cells.get("neg", []) for ct in cl["controls"] if "center" in ct])
    return {"cv_mop": cv, "routing": routing, "t3": t3, "t5": t5, "t6": t6,
            "dedup_shared": dedup_report, "shared_control": shared}


# --- T7: ri-stima sotto regimi esogeni (E3) ----------------------------------

def _relabel_per_type_with_regime(per_type_clusters: dict, regime_series: pd.Series) -> dict:
    """Ridistribuisce i cluster di ogni tipo nelle celle pos/neg secondo `regime_series`
    (etichette «alto»/«basso» o «positivo»/«negativo» assegnate as-of evento)."""
    out = {t: {"pos": [], "neg": []} for t in per_type_clusters}
    HI = {"alto", "positivo"}
    for t, cells in per_type_clusters.items():
        for cl in (cells.get("pos") or []) + (cells.get("neg") or []):
            center = cl["event"].get("center")
            if center is None:
                continue
            lab = regimes.assign_regime([pd.Timestamp(center)], regime_series)[0]
            if lab in HI:
                out[t]["pos"].append(cl)
            elif lab in {"basso", "negativo"}:
                out[t]["neg"].append(cl)
    return out


def run_t7_exogenous(per_type_clusters: dict, rng, exogenous_series: dict,
                    B: int = config.B_BOOT) -> dict:
    """E3 T7: ridefinisce i regimi con criteri ESOGENI a ρ (mediana causale 252gg,
    lag t-1) e ri-stima T5 sotto ciascun criterio. `exogenous_series` =
    {nome: pd.Series daily}; almeno T10Y2Y e VIXCLS attesi (config.T7_EXOGENOUS_REQUIRED).
    """
    grid = beta_grid()
    per_criterion_est = {}
    for name, series in exogenous_series.items():
        reg_df = regimes.build_exogenous_regime(
            series, window=config.T7_ROLLING_DAYS, lag=config.T7_LAG_BDAYS)
        relabel = _relabel_per_type_with_regime(per_type_clusters, reg_df["regime"])
        est = tp.estimate_per_type(relabel, rng, B=B)
        per_criterion_est[name] = est
    return tp.t7_exogenous(per_criterion_est, grid)


# --- T8(c): finestra di regime allargata — RICALCOLO a monte (E3) -----------

def run_t8c_widen(events: pd.DataFrame, prices: dict, reject, rng,
                  B: int = config.B_BOOT) -> dict:
    """T8(c): ricalcola `compute_regimes` con la finestra robusta (126gg),
    riassembla le celle e ri-stima T5. Richiede prezzi+eventi+reject (sui dati
    reali); su DGP sintetico si passa prices=None ⇒ gated (None, dichiarato)."""
    if prices is None or events is None:
        return None
    by_area = {}
    for area, (eq, bo) in {"US": ("ES", "TY"), "EU": ("STXE", "FGBL")}.items():
        re = data.daily_log_returns_from_minute(prices[eq]).rename("eq")
        rb = data.daily_log_returns_from_minute(prices[bo]).rename("bond")
        daily = pd.concat([re, rb], axis=1).dropna()
        by_area[area] = regimes.rolling_sign_regime(
            daily, "eq", "bond", window=config.REGIME_WINDOW_DAYS_ROBUST)["regime"]
    ptc, _ = assemble(events, prices, by_area, reject)
    ptc, _ = windows.dedup_shared_controls(ptc)
    est = tp.estimate_per_type(ptc, rng, B=B)
    return tp.t5_signflip(est, beta_grid())


# --- Orchestratore COMPLETO (con manifest) ----------------------------------

def run_protocol_full(per_type_clusters: dict, rng, *,
                      events: pd.DataFrame | None = None,
                      prices: dict | None = None,
                      reject=None,
                      exogenous_series: dict | None = None,
                      cpi_yoy: pd.Series | None = None,
                      surprises_by_type: dict | None = None,
                      decomp_inputs: dict | None = None,
                      manifest_path=None,
                      manifest_timestamp: str | None = None,
                      manifest_inputs: list | None = None,
                      B: int = config.B_BOOT) -> dict:
    """Orchestratore COMPLETO: T1, T2, T3, T4, T5, T6, T7, T8(a/c/d), T9,
    decomposizione daily, + manifest finale. I pezzi con input non disponibili
    sono GATED (None) e dichiarati; il core (T1/T3/T4/T5/T6) è sempre eseguito.
    """
    core = run_protocol(per_type_clusters, rng, B=B)
    grid = beta_grid()

    # T2 — Lewbel (gated su sorprese per-tipo)
    t2 = None
    if surprises_by_type:
        t2 = {}
        for t, payload in surprises_by_type.items():
            re_e = np.asarray(payload["r_e"]); rb_e = np.asarray(payload["r_b"])
            Z = np.asarray(payload["Z"])
            t2[t] = tp.t2_lewbel(re_e, rb_e, Z, rng, B=B,
                                 source_label=surprises.surprise_source(t))

    # T4 (= parte 2 di T5, stesso χ²₁) esposto esplicitamente per leggibilità
    t4 = {}
    for t, cells in core["t5"]["per_type"].items():
        t4[t] = {"delta_p": cells["delta_p"], "testable": cells["testable"]}

    # T7 — regimi esogeni
    t7 = run_t7_exogenous(per_type_clusters, rng, exogenous_series, B=B) if exogenous_series else None

    # T8 — (a) finestre estreme; (c) widen regime window (riassembla); (d) inflazionistico
    t8 = {"baseline": core["t5"]}
    transforms_ab = {"exclude_extreme":
                     tp.per_cell_transform(lambda c: tp.exclude_extreme(c, 0.1))}
    t8_ab = tp.t8_robustness(per_type_clusters, rng, grid, transforms_ab, B=B)
    t8["exclude_extreme"] = t8_ab["exclude_extreme"]
    t8["widen_regime"] = run_t8c_widen(events, prices, reject, rng, B=B)
    if cpi_yoy is not None:
        infl_transform = tp.per_cell_transform(lambda c: tp.t8d_exclude_inflationary(c, cpi_yoy))
        t8_d = tp.t8_robustness(per_type_clusters, rng, grid, {"d": infl_transform}, B=B)
        t8["exclude_inflationary"] = t8_d["d"]
    else:
        t8["exclude_inflationary"] = None

    # T9 — meccanismo due gambe (gated su sorprese s per-regime)
    t9 = None
    if surprises_by_type and all("s_pos" in v and "s_neg" in v for v in surprises_by_type.values()):
        t9 = {}
        for t, payload in surprises_by_type.items():
            t9[t] = mechanism.mechanism(
                {"positivo": {"r_e": payload["r_e_pos"], "r_b": payload["r_b_pos"], "s": payload["s_pos"]},
                 "negativo": {"r_e": payload["r_e_neg"], "r_b": payload["r_b_neg"], "s": payload["s_neg"]}},
                source_label=surprises.surprise_source(t))

    # Decomposizione daily — secondaria, etichettata daily
    decomp = None
    if decomp_inputs is not None:
        decomp = decomposition.bond_channels(**decomp_inputs.get("bond", {})) if "bond" in decomp_inputs else None

    out = {**core, "t2": t2, "t4": t4, "t7": t7, "t8": t8, "t9": t9, "decomposition": decomp}

    # Manifest finale (provenienza)
    if manifest_path is not None:
        if manifest_timestamp is None:
            raise ValueError("manifest_timestamp deve essere passato (no clock interno).")
        manifest = provenance.write_manifest(
            manifest_path,
            entries=manifest_inputs or [],
            timestamp=manifest_timestamp,
            diagnostics={
                "dedup_shared": core["dedup_shared"],
                "shared_control_post_dedup": core["shared_control"],
            },
        )
        out["manifest"] = manifest
    else:
        out["manifest"] = None
    return out


def main():  # pragma: no cover  (eseguito SOLO dall'esecutore sui dati reali)
    raise SystemExit(
        "run.py: esecuzione sui dati reali demandata all'ESECUTORE post-review (agente 4). "
        "L'orchestrazione è in run_protocol/assemble; lo smoke sintetico è in tests/test_smoke.py."
    )


if __name__ == "__main__":
    main()
