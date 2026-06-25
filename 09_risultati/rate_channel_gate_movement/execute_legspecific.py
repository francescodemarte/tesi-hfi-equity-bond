"""execute_legspecific.py — Cancello canale tassi LEG-SPECIFIC, partizione "movement".

Pre-registrazione (decisione del ricercatore prima del run):
  - dicotomizzazione `partition_mode = "movement"` (x > 0 → "high",
    x = 0 → "low"). È coerente con la natura del segnale |Δ|, che ha massa
    puntuale in 0 — non è una scelta ex-post sui risultati del run median.
  - Contratto tasso CANONICO per leg:
      ECB                  → FEIc1 (front Euribor 3M)
      FOMC, CPI, NFP       → FFc2  (front-2 Fed Funds, copertura piena)
  - Tutto il resto invariato (finestra ±15 min, soglie congelate, seed,
    `events_df` dallo stesso pickle autoritativo del v2 protocol).

Output: due sub-namespace separati, uno per gruppo:
  - 09_risultati/rate_channel_gate_movement/ECB_FEIc1/
  - 09_risultati/rate_channel_gate_movement/Fed_FFc2/

In ciascuno: verdicts.json, numbers.json, manifest.json, report.md.
"""
from __future__ import annotations

import hashlib
import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/francesco/TESI/tesi-hfi-equity-bond")
PKG = ROOT / "CODICI_TESI" / "10_diagnostica_canale_tassi"
sys.path.insert(0, str(PKG))

import config        # noqa: E402
import diagnostics as D  # noqa: E402
import gate          # noqa: E402
import manifest as mf    # noqa: E402
import rate_shock    # noqa: E402

OUT_ROOT = ROOT / "09_risultati" / "rate_channel_gate_movement"
OUT_ROOT.mkdir(parents=True, exist_ok=True)

PICKLE_AUTH = ROOT / "09_risultati" / "v2_signflip" / "result_authoritative.pkl"
INTRADAY_DIR = Path("/home/francesco/TESI/Dati/data_processed")

ES_CSV = INTRADAY_DIR / "ESc1_1min.csv"
TY_CSV = INTRADAY_DIR / "TYc1_1min.csv"
STXE_CSV = INTRADAY_DIR / "STXE_continuous_1min.csv"
FGBL_CSV = INTRADAY_DIR / "FGBLc1_1min.csv"

SEED_NAME = "gate_run_movement_2026-06-23"
TASK_TIMESTAMP = (
    datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
)

# Definizione gruppi leg-specific (pre-registrata).
GROUPS = [
    {
        "name": "ECB_FEIc1",
        "legs": ("ECB",),
        "rate_csv": INTRADAY_DIR / "FEIc1_1min.csv",
        "rate_contract": "FEIc1",
        "rate_price_col": "PX_LAST",
        "eq_csv": STXE_CSV,
        "eq_price_col": "Mid_raw",
        "bo_csv": FGBL_CSV,
        "bo_price_col": "PX_LAST",
    },
    {
        "name": "Fed_FFc2",
        "legs": ("FOMC", "CPI", "NFP"),
        "rate_csv": INTRADAY_DIR / "FFc2_1min.csv",
        "rate_contract": "FFc2",
        "rate_price_col": "PX_LAST",
        "eq_csv": ES_CSV,
        "eq_price_col": "PX_LAST",
        "bo_csv": TY_CSV,
        "bo_price_col": "PX_LAST",
    },
]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_intraday(path: Path, price_col: str) -> pd.Series:
    df = pd.read_csv(path, usecols=["Datetime_UTC", price_col])
    df["Datetime_UTC"] = pd.to_datetime(df["Datetime_UTC"], utc=True)
    s = df.set_index("Datetime_UTC")[price_col].astype(float)
    return s[~s.index.duplicated(keep="first")].sort_index().dropna()


def load_events_from_pickle(pkl_path: Path) -> tuple[pd.DataFrame, str, dict]:
    sha = sha256_file(pkl_path)
    with open(pkl_path, "rb") as f:
        obj = pickle.load(f)
    rows = []
    for a in obj["accounting"]:
        s = a["event"]
        leg, rest = s.split("@", 1)
        ts, regime = rest.rsplit("|", 1)
        rows.append({"timestamp": pd.Timestamp(ts), "leg": leg, "regime": regime})
    return pd.DataFrame(rows), sha, {"label": obj["label"], "timestamp": obj["timestamp"]}


def log_return_window(prices: pd.Series, t: pd.Timestamp) -> float:
    w = rate_shock.extract_event_window(prices, t)
    pre, post = w["pre"], w["post"]
    if np.isnan(pre) or np.isnan(post) or pre <= 0 or post <= 0:
        return float("nan")
    return float(np.log(post / pre))


def compute_cell_moments(df: pd.DataFrame, regime_col="regime",
                          intensity_col="intensity_label") -> dict:
    out = {}
    valid = df.dropna(subset=["r_e", "r_b"]).copy()
    for (r, i), sub in valid.groupby([regime_col, intensity_col]):
        re = sub["r_e"].to_numpy(dtype=float)
        rb = sub["r_b"].to_numpy(dtype=float)
        if len(re) < 2:
            out[(str(r), str(i))] = {"var_e": float("nan"), "var_b": float("nan"),
                                       "cov_eb": float("nan"), "n": int(len(re))}
            continue
        out[(str(r), str(i))] = {
            "var_e": float(np.var(re, ddof=1)),
            "var_b": float(np.var(rb, ddof=1)),
            "cov_eb": float(np.cov(re, rb, ddof=1)[0, 1]),
            "n": int(len(re)),
        }
    return out


def run_group(g: dict, events_full: pd.DataFrame, pkl_sha: str, pkl_meta: dict) -> dict:
    out_dir = OUT_ROOT / g["name"]
    out_dir.mkdir(parents=True, exist_ok=True)

    # Filtra events_df sui leg del gruppo
    ev = events_full[events_full["leg"].isin(g["legs"])].reset_index(drop=True).copy()
    print(f"\n=== group {g['name']} ===  legs={g['legs']}  contract={g['rate_contract']}")
    print(f"  events nel gruppo: {len(ev)}")

    # Carica prezzi
    rate_prices = load_intraday(g["rate_csv"], g["rate_price_col"])
    eq_prices = load_intraday(g["eq_csv"], g["eq_price_col"])
    bo_prices = load_intraday(g["bo_csv"], g["bo_price_col"])

    # Intensità tasso + rendimenti equity/bond
    ev_intensity = rate_shock.build_event_intensity_table(
        ev, rate_prices, contract_label=g["rate_contract"])
    ev["r_e"] = [log_return_window(eq_prices, t) for t in ev["timestamp"]]
    ev["r_b"] = [log_return_window(bo_prices, t) for t in ev["timestamp"]]
    merged = ev.copy()
    merged["intensity_raw"] = ev_intensity["intensity_raw"].values
    merged["contract"] = ev_intensity["contract"].values

    # Dicotomizza in modalità "movement" (x>0 → high, x=0 → low) sui validi
    valid_mask = merged["intensity_raw"].notna()
    valid = merged[valid_mask].copy()
    valid["intensity_label"] = D.dichotomize(valid["intensity_raw"].to_numpy(),
                                              mode="movement")
    merged["intensity_label"] = pd.Series(
        index=valid.index, data=valid["intensity_label"].values
    ).reindex(merged.index)

    n_high = int((valid["intensity_label"] == "high").sum())
    n_low = int((valid["intensity_label"] == "low").sum())
    print(f"  intensity valid: {len(valid)} / {len(merged)}  (high={n_high}, low={n_low})")

    event_moments = compute_cell_moments(valid)
    print(f"  event_moments cells: { {k: v['n'] for k, v in event_moments.items()} }")

    # Esegui gate con partition_mode='movement'
    out_gate = gate.run_gate(merged, event_moments=event_moments,
                              partition_mode="movement")
    print(f"  verdicts: {out_gate['verdicts']}")

    # File output
    verdicts = {**out_gate["verdicts"],
                "n_events_total": out_gate["n_events_total"],
                "n_events_with_intensity": out_gate["n_events_with_intensity"]}
    (out_dir / "verdicts.json").write_bytes(
        json.dumps(verdicts, indent=2, sort_keys=True).encode("utf-8"))

    def jsonify(x):
        if isinstance(x, dict):
            return {(f"{k[0]}|{k[1]}" if isinstance(k, tuple) else str(k)): jsonify(v)
                    for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [jsonify(v) for v in x]
        if isinstance(x, (np.floating, np.integer)):
            return x.item()
        return x

    numbers = jsonify(out_gate)
    numbers["event_moments_raw"] = jsonify(event_moments)
    (out_dir / "numbers.json").write_bytes(
        json.dumps(numbers, indent=2, sort_keys=True, default=str).encode("utf-8"))

    # Manifest
    input_paths = [PICKLE_AUTH, g["rate_csv"], g["eq_csv"], g["bo_csv"]]
    m = mf.build_gate_manifest(
        rate_contract=g["rate_contract"],
        window_half_min=config.HALF_MIN_WINDOW,
        partition_mode="movement",
        min_cell=config.MIN_CELL_EVENTS,
        seed_name=SEED_NAME,
        timestamp=TASK_TIMESTAMP,
        input_paths=input_paths,
        thresholds=out_gate["thresholds_used"],
    )
    m["pickle_auth"] = {"path": str(PICKLE_AUTH), "sha256": pkl_sha,
                         "run_label": pkl_meta["label"], "run_timestamp": pkl_meta["timestamp"]}
    m["executor"] = {
        "script_path": str(Path(__file__).resolve()),
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "package_path": str(PKG),
        "package_module_sha256": {p.name: sha256_file(p) for p in sorted(PKG.glob("*.py"))},
        "namespace_output_dir": str(out_dir),
        "preregistration_note": (
            "Run leg-specific con partition_mode='movement'. Pre-registrato dal "
            "ricercatore prima del run, motivato dalla massa puntuale in 0 di "
            "|Δprice| sul futures-tasso (non scelta ex-post sui risultati del run "
            "'median' precedente)."
        ),
    }
    m["group"] = {"name": g["name"], "legs": list(g["legs"])}
    m["n_events"] = {
        "in_group_total": int(len(ev)),
        "with_intensity_valid": int(verdicts["n_events_with_intensity"]),
        "high": n_high,
        "low": n_low,
        "by_leg_regime": {f"{l}|{r}": int(c) for (l, r), c in
                          ev.groupby(["leg", "regime"]).size().items()},
        "with_returns_valid": int(merged[["r_e", "r_b"]].notna().all(axis=1).sum()),
    }
    mf.write_manifest(out_dir / "manifest.json", m)

    # Report
    th = out_gate["thresholds_used"]
    a = out_gate["criterion_a"]
    b = out_gate["criterion_b"]
    c = out_gate["criterion_c"]
    d = out_gate["criterion_d"]
    lines = [
        f"# Cancello canale tassi — gruppo {g['name']} (movement)",
        "",
        f"- timestamp: `{TASK_TIMESTAMP}`",
        f"- gruppo: legs = {list(g['legs'])}, contratto = `{g['rate_contract']}`",
        f"- partition_mode: `movement` (x>0 → 'high', x=0 → 'low')",
        f"- finestra: ±{config.HALF_MIN_WINDOW} min (edge mediana {config.MEDIAN_EDGE_MIN} min)",
        f"- seed: `{SEED_NAME}` (master {config.MASTER_SEED})",
        f"- soglie a priori: η²≤{th['eta2_low']} (a), |κ|≤{th['kappa_low']} (b), min_cell={th['min_cell']} (c), |cos|<{th['cosine_high']} (d)",
        f"- config_hash: `{config.config_hash()}`",
        f"- eventi nel gruppo: {verdicts['n_events_total']}",
        f"- eventi con intensità valida: {verdicts['n_events_with_intensity']}  (high={n_high}, low={n_low})",
        "",
        "## Verdetti per criterio",
        "",
        f"- **(a) within-regime ampia** (η² ≤ {th['eta2_low']}): `{verdicts['a']}`",
        f"- **(b) dimensioni distinte** (|κ_aligned| ≤ {th['kappa_low']}): `{verdicts['b']}`",
        f"- **(c) celle popolate** (n ≥ {th['min_cell']}): `{verdicts['c']}`",
        f"- **(d) vettori di cambiamento non-collineari** (|cos| < {th['cosine_high']}): `{verdicts['d']}`",
        "",
        "## (a) η² intensità ~ regime",
        f"- overall η² = {a['overall']['eta_squared']:.6g}, n = {a['overall']['n']}",
    ]
    for leg, v in a["by_leg"].items():
        eta = v.get("eta_squared", float("nan"))
        lines.append(f"- by_leg {leg}: η² = {eta:.6g}, n = {v.get('n','-')}")
    lines += [
        "",
        "## (b) Kappa allineato",
        f"- κ_aligned overall = {b['overall_kappa']:.6g}",
    ]
    for leg, k in b["by_leg_kappa"].items():
        lines.append(f"- κ_aligned by_leg {leg} = {k}")
    lines += [
        "",
        f"## (c) Popolamento celle regime × intensità (soglia {th['min_cell']})",
        "",
    ]
    for (r, i), n in sorted(c["counts_overall"].items()):
        lines.append(f"  - ({r}, {i}): {n}")
    if c["below_overall"]:
        lines.append(f"- **CELLE SOTTO SOGLIA:** {c['below_overall']}")
    lines += ["", "## (d) Vettori di cambiamento", ""]
    if isinstance(d, dict) and d.get("status") == "missing_cells":
        lines.append(f"- status: `{d['status']}` (celle mancanti: {d['missing']})")
    else:
        lines += [
            f"- Δ_rate (positivo) = {d['delta_rate_pos']}",
            f"- Δ_rate (negativo) = {d['delta_rate_neg']}",
            f"- Δ_regime (high)   = {d['delta_regime_hi']}",
            f"- Δ_regime (low)    = {d['delta_regime_lo']}",
            f"- distinctness @ positivo: cos = {d['distinctness_at_regime_pos']['cosine']:.6g}, angle = {d['distinctness_at_regime_pos']['angle_deg']:.3f}°, rank = {d['distinctness_at_regime_pos']['rank_numerical']}",
            f"- distinctness @ negativo: cos = {d['distinctness_at_regime_neg']['cosine']:.6g}, angle = {d['distinctness_at_regime_neg']['angle_deg']:.3f}°, rank = {d['distinctness_at_regime_neg']['rank_numerical']}",
        ]
    lines += [
        "",
        "## Note dell'esecutore",
        "",
        "- `events_df` letto dall'`accounting` del pickle autoritativo del v2 (sola lettura, input datato).",
        "- Rendimenti r_e/r_b sulla stessa finestra ±15 min, log-return = log(post/pre).",
        "- Partition `movement`: split su `x>0 vs x=0` — pre-registrato per coerenza con la massa in 0 di |Δprice|.",
        "- Nessuna soglia / contratto / leg / sample è stato cambiato dopo il run.",
    ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"name": g["name"], "verdicts": out_gate["verdicts"],
            "n_high": n_high, "n_low": n_low, "out_dir": str(out_dir)}


def main() -> int:
    print(f"=== execute_legspecific.py — {TASK_TIMESTAMP} ===")
    events_full, pkl_sha, pkl_meta = load_events_from_pickle(PICKLE_AUTH)
    print(f"events_df: {len(events_full)} (pickle sha256={pkl_sha[:16]}...)")

    results = [run_group(g, events_full, pkl_sha, pkl_meta) for g in GROUPS]

    # Summary index
    summary = {
        "timestamp": TASK_TIMESTAMP,
        "partition_mode": "movement",
        "seed_name": SEED_NAME,
        "config_hash": config.config_hash(),
        "pickle_auth_sha256": pkl_sha,
        "groups": results,
    }
    (OUT_ROOT / "summary.json").write_bytes(
        json.dumps(summary, indent=2, sort_keys=True).encode("utf-8"))
    print("\n=== SUMMARY ===")
    for r in results:
        print(f"  {r['name']}: verdicts={r['verdicts']}  (high={r['n_high']}, low={r['n_low']})")
    print(f"\nDONE → {OUT_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
