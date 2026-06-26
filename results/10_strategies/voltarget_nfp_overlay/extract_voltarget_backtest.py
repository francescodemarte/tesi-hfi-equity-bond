"""extract_voltarget_backtest.py — Esecutore deterministico:
Vol-target NFP overlay (risk-management derivative).

Compito: backtest e deposito autoritativo dell'overlay di gestione del rischio
applicato nei soli giorni NFP/neg, basato sul finding intraday r̂=15.4 (var
window / var control) del Capitolo 6. È un PRODOTTO DERIVATO, non un finding
nativo: trasferimento del salto di varianza intraday a un'applicazione di
risk-management su orizzonte daily, condizionata al fatto che NFP/neg sia
l'unica cella che passa Check 1 del bridge intraday→daily (var_window =
44.8% var_daily). Per CPI/FOMC l'overlay NON è giustificato perché il bridge
fallisce.

Pre-registrazione (vedi PROTOCOL.md):
- Regola: nei T-1 close pre-noti dal calendario NFP/neg, ridurre size del
  portafoglio bond × 1/√r̂_NFP = 0.255 (size factor).
- 4 strategie a confronto:
  A) baseline long-bond
  B) vol-target NFP-only (size cut nei NFP-day)
  C) baseline 60/40 (60% equity / 40% bond)
  D) 60/40 + vol-target NFP-only (overlay sul 60/40)

Output:
- backtest_baseline_long_bond.json
- backtest_baseline_60_40.json
- backtest_combined.json (4 strategie A/B/C/D con metriche)
- manifest.json
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
INTRADAY = Path("/home/francesco/TESI/Dati/data_processed")
EVENTS_CSV = ROOT / "data/events/events_with_regime_classifier.csv"
BETA_H_FILE = ROOT / "results/01_protocol_v2/beta_H_robust_cells_w15.json"

MASTER_SEED = 20260621
SEED_NAME = "voltarget_nfp_overlay_2010_2025"
COST_BPS_BOND = 0.3
COST_BPS_EQUITY = 0.5
SPLIT_OOS_DATE = pd.Timestamp("2020-01-01")  # train < 2020, OOS >=
TRADING_DAYS_PER_YEAR = 252


def seed_for(name: str) -> int:
    h = hashlib.sha256(f"{MASTER_SEED}|{name}".encode()).hexdigest()
    return int(h[:16], 16)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_daily_returns(ric: str) -> pd.Series:
    df = pd.read_csv(INTRADAY / f"{ric}_1min.csv", parse_dates=["Datetime_UTC"])
    df["date"] = df["Datetime_UTC"].dt.tz_convert("UTC").dt.date
    daily_close = df.groupby("date")["PX_LAST"].last()
    daily_close.index = pd.to_datetime(daily_close.index)
    return daily_close.pct_change().dropna()


def load_nfp_neg_dates() -> set[pd.Timestamp]:
    ev = pd.read_csv(EVENTS_CSV, parse_dates=["timestamp"])
    nfp = ev[(ev["event_class"] == "NFP") & (ev["corr3m_US_z_lag"] < 0)].copy()
    nfp["date"] = pd.to_datetime(nfp["timestamp"]).dt.tz_localize(None).dt.normalize()
    return set(nfp["date"])


def metric_sharpe(returns: np.ndarray) -> float:
    if returns.size < 2 or np.std(returns, ddof=1) == 0:
        return 0.0
    return float(np.mean(returns) / np.std(returns, ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


def metric_var99(returns: np.ndarray) -> float:
    if returns.size == 0:
        return 0.0
    return float(-np.percentile(returns, 1.0)) * 100  # in %


def metric_maxdd(returns: np.ndarray) -> float:
    if returns.size == 0:
        return 0.0
    cum = np.cumprod(1 + returns)
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    return float(np.min(dd)) * 100  # in %


def metric_pct_loss_gt(returns: np.ndarray, thresh: float) -> float:
    if returns.size == 0:
        return 0.0
    return float(np.mean(returns < -thresh)) * 100


def evaluate_full_train_oos(returns: pd.Series, nfp_dates: set, label: str) -> dict:
    """Calcola metriche full / train / OOS per una serie di rendimenti."""
    nfp_mask = returns.index.isin(nfp_dates)
    train_mask = returns.index < SPLIT_OOS_DATE
    oos_mask = ~train_mask
    out = {"strategy": label}
    for period, mask in [("full", np.ones(len(returns), dtype=bool)),
                          ("train", train_mask),
                          ("oos", oos_mask)]:
        r = returns.values[mask]
        n_nfp_in_period = (nfp_mask & mask).sum()
        r_nfp = returns.values[nfp_mask & mask]
        out[period] = {
            "n_obs": int(mask.sum()),
            "n_nfp_in_period": int(n_nfp_in_period),
            "sharpe": metric_sharpe(r),
            "var99_pct": metric_var99(r),
            "var99_nfp_pct": metric_var99(r_nfp),
            "maxdd_pct": metric_maxdd(r),
            "pct_loss_gt_1pct_nfp": metric_pct_loss_gt(r_nfp, 0.01),
            "pct_loss_gt_2pct_nfp": metric_pct_loss_gt(r_nfp, 0.02),
            "count_loss_gt_1pct_nfp": int(np.sum(r_nfp < -0.01)),
        }
    return out


def main():
    print("=== Vol-target NFP overlay backtest ===")
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    # Load r̂ autoritativo
    beta_h = json.loads(BETA_H_FILE.read_text())
    r_hat = None
    for c in beta_h["robust_cells"]:
        if c["cell"] == "NFP/neg":
            r_hat = c["r_hat"]
            break
    assert r_hat is not None
    SIZE_FACTOR = 1.0 / np.sqrt(r_hat)
    print(f"  r_hat NFP/neg = {r_hat:.4f}")
    print(f"  size_factor = 1/sqrt(r_hat) = {SIZE_FACTOR:.4f}")

    # Load returns + NFP/neg dates
    r_bond = load_daily_returns("TYc1")
    r_eq = load_daily_returns("ESc1")
    nfp_dates = load_nfp_neg_dates()
    print(f"  NFP/neg dates: {len(nfp_dates)}")
    print(f"  Bond returns: {len(r_bond)}, {r_bond.index.min().date()} → {r_bond.index.max().date()}")
    print(f"  Equity returns: {len(r_eq)}, {r_eq.index.min().date()} → {r_eq.index.max().date()}")

    # Align indices
    common_idx = r_bond.index.intersection(r_eq.index)
    r_bond = r_bond.reindex(common_idx)
    r_eq = r_eq.reindex(common_idx)
    nfp_in_idx = sum(1 for d in nfp_dates if d in common_idx)
    print(f"  NFP/neg in common index: {nfp_in_idx}")

    # NFP mask
    nfp_mask = r_bond.index.isin(nfp_dates)
    nfp_turnover_cost_bond = COST_BPS_BOND * 1e-4
    nfp_turnover_cost_eq = COST_BPS_EQUITY * 1e-4

    # === STRATEGIA A: baseline long bond ===
    r_A = r_bond.copy()

    # === STRATEGIA B: vol-target NFP-only su bond ===
    size_B = np.where(nfp_mask, SIZE_FACTOR, 1.0)
    r_B = pd.Series(size_B * r_bond.values, index=r_bond.index)
    # Costi di rebalance: applicati nei NFP-day (size change da 1.0 → 0.255)
    rebalance_cost_B = np.where(nfp_mask, abs(1.0 - SIZE_FACTOR) * nfp_turnover_cost_bond, 0.0)
    r_B = r_B - rebalance_cost_B

    # === STRATEGIA C: baseline 60/40 ===
    r_C = pd.Series(0.60 * r_eq.values + 0.40 * r_bond.values, index=r_bond.index)

    # === STRATEGIA D: 60/40 + vol-target NFP-only (size cut sull'INTERO 60/40 NFP-day) ===
    # Coerente con Fork Q: l'overlay riduce TUTTA la size del portafoglio, non solo bond.
    portfolio_60_40 = 0.60 * r_eq.values + 0.40 * r_bond.values
    size_D = np.where(nfp_mask, SIZE_FACTOR, 1.0)
    r_D = pd.Series(size_D * portfolio_60_40, index=r_bond.index)
    # Costo: ribilanciamento sul bond e equity nei NFP-day
    rebalance_cost_D = np.where(
        nfp_mask,
        abs(1.0 - SIZE_FACTOR) * (0.40 * nfp_turnover_cost_bond + 0.60 * nfp_turnover_cost_eq),
        0.0,
    )
    r_D = r_D - rebalance_cost_D

    # Evaluate metrics per strategy
    metrics = {
        "A_baseline_long_bond": evaluate_full_train_oos(r_A, nfp_dates, "A_baseline_long_bond"),
        "B_vol_target_NFP_only_bond": evaluate_full_train_oos(r_B, nfp_dates, "B_vol_target_NFP_only_bond"),
        "C_baseline_60_40": evaluate_full_train_oos(r_C, nfp_dates, "C_baseline_60_40"),
        "D_60_40_vol_target_NFP_only": evaluate_full_train_oos(r_D, nfp_dates, "D_60_40_vol_target_NFP_only"),
    }

    # Compute reductions
    def reduction_pct(baseline_var, overlay_var):
        if baseline_var == 0:
            return 0.0
        return (baseline_var - overlay_var) / baseline_var * 100

    reductions = {
        "bond_only_full_var99_nfp_reduction_pct": reduction_pct(
            metrics["A_baseline_long_bond"]["full"]["var99_nfp_pct"],
            metrics["B_vol_target_NFP_only_bond"]["full"]["var99_nfp_pct"]),
        "bond_only_oos_var99_nfp_reduction_pct": reduction_pct(
            metrics["A_baseline_long_bond"]["oos"]["var99_nfp_pct"],
            metrics["B_vol_target_NFP_only_bond"]["oos"]["var99_nfp_pct"]),
        "60_40_full_var99_nfp_reduction_pct": reduction_pct(
            metrics["C_baseline_60_40"]["full"]["var99_nfp_pct"],
            metrics["D_60_40_vol_target_NFP_only"]["full"]["var99_nfp_pct"]),
        "60_40_oos_var99_nfp_reduction_pct": reduction_pct(
            metrics["C_baseline_60_40"]["oos"]["var99_nfp_pct"],
            metrics["D_60_40_vol_target_NFP_only"]["oos"]["var99_nfp_pct"]),
    }

    combined = {
        "task": "voltarget_nfp_overlay_full_backtest",
        "size_factor": float(SIZE_FACTOR),
        "r_hat_NFP_neg": float(r_hat),
        "cost_bps_bond": COST_BPS_BOND,
        "cost_bps_equity": COST_BPS_EQUITY,
        "split_oos_date": "2020-01-01",
        "n_obs_total": int(len(common_idx)),
        "n_nfp_days_total": int(nfp_in_idx),
        "strategies": metrics,
        "reductions_summary": reductions,
        "filter_ex_post_declared": ("Overlay applied SOLO ai giorni NFP/neg perché "
                                       "NFP/neg è l'unica cella che passa Check 1 del bridge "
                                       "(var_window=44.8% var_daily). Per CPI/FOMC il bridge "
                                       "non passa → overlay non giustificato. Filtro ex-post "
                                       "dichiarato."),
    }
    (OUT / "backtest_combined.json").write_text(json.dumps(combined, indent=2))
    print(f"  Saved backtest_combined.json")

    # Baseline long-bond standalone (per documentazione)
    bb_out = {
        "task": "voltarget_baseline_long_bond_documentation",
        "metrics": metrics["A_baseline_long_bond"],
    }
    (OUT / "backtest_baseline_long_bond.json").write_text(json.dumps(bb_out, indent=2))

    bb_60_40_out = {
        "task": "voltarget_baseline_60_40_documentation",
        "metrics": metrics["C_baseline_60_40"],
    }
    (OUT / "backtest_baseline_60_40.json").write_text(json.dumps(bb_60_40_out, indent=2))

    # === MANIFEST ===
    manifest = {
        "task": "deposit_voltarget_nfp_overlay",
        "task_timestamp": timestamp,
        "seed_name": SEED_NAME,
        "master_seed": MASTER_SEED,
        "seed_int": seed_for(SEED_NAME),
        "executor": {
            "script_path": str(Path(__file__).resolve()),
            "script_sha256": sha256_file(Path(__file__).resolve()),
        },
        "inputs": {
            "events_csv": {"path": str(EVENTS_CSV), "sha256": sha256_file(EVENTS_CSV)},
            "beta_h_file": {"path": str(BETA_H_FILE), "sha256": sha256_file(BETA_H_FILE)},
            "intraday_dir": str(INTRADAY),
            "intraday_files_status": "PROPRIETARY (Refinitiv), not redistributed",
        },
        "outputs": {
            "backtest_combined.json": {"path": str(OUT/"backtest_combined.json"),
                                         "sha256": sha256_file(OUT/"backtest_combined.json")},
            "backtest_baseline_long_bond.json": {"path": str(OUT/"backtest_baseline_long_bond.json"),
                                                    "sha256": sha256_file(OUT/"backtest_baseline_long_bond.json")},
            "backtest_baseline_60_40.json": {"path": str(OUT/"backtest_baseline_60_40.json"),
                                                "sha256": sha256_file(OUT/"backtest_baseline_60_40.json")},
        },
        "validation_vs_fork_Q": {
            "fork_Q_baseline_long_bond_var99_nfp_full": 0.919,
            "deposit_baseline_long_bond_var99_nfp_full": metrics["A_baseline_long_bond"]["full"]["var99_nfp_pct"],
            "fork_Q_vol_target_var99_nfp_full": 0.240,
            "deposit_vol_target_var99_nfp_full": metrics["B_vol_target_NFP_only_bond"]["full"]["var99_nfp_pct"],
            "fork_Q_60_40_baseline_var99_nfp_full": 1.662,
            "deposit_60_40_baseline_var99_nfp_full": metrics["C_baseline_60_40"]["full"]["var99_nfp_pct"],
            "fork_Q_60_40_overlay_var99_nfp_full": 0.439,
            "deposit_60_40_overlay_var99_nfp_full": metrics["D_60_40_vol_target_NFP_only"]["full"]["var99_nfp_pct"],
            "scarto_note": "Eventuali differenze sub-percentuali sono attese da diversa policy di allineamento date e gestione missing data tra Fork Q e deposit.",
        },
        "use_case": ("Risk-management overlay derivativo del finding intraday r̂=15.4 "
                       "per NFP/neg. NON è un finding nativo della tesi: trasferimento "
                       "cross-orizzonte intraday→daily, giustificato dal CHECK 1 del bridge "
                       "(passa solo per NFP). Cliente target: risk desk, bond direzionale, ALM."),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"  Manifest scritto.")

    # Print summary
    print()
    print("=== Metriche chiave (osservate) ===")
    print(f"  Baseline long bond — VaR99 NFP-day full: {metrics['A_baseline_long_bond']['full']['var99_nfp_pct']:.3f}%")
    print(f"  Vol-target NFP-only — VaR99 NFP-day full: {metrics['B_vol_target_NFP_only_bond']['full']['var99_nfp_pct']:.3f}%")
    print(f"  Riduzione full sample: {reductions['bond_only_full_var99_nfp_reduction_pct']:.1f}%")
    print(f"  60/40 baseline — VaR99 NFP-day full: {metrics['C_baseline_60_40']['full']['var99_nfp_pct']:.3f}%")
    print(f"  60/40 + overlay — VaR99 NFP-day full: {metrics['D_60_40_vol_target_NFP_only']['full']['var99_nfp_pct']:.3f}%")
    print(f"  Riduzione 60/40 full: {reductions['60_40_full_var99_nfp_reduction_pct']:.1f}%")
    print(f"  Sharpe full A bond: {metrics['A_baseline_long_bond']['full']['sharpe']:+.4f}")
    print(f"  Sharpe full B vol-target: {metrics['B_vol_target_NFP_only_bond']['full']['sharpe']:+.4f}")
    print(f"  Sharpe full C 60/40: {metrics['C_baseline_60_40']['full']['sharpe']:+.4f}")
    print(f"  Sharpe full D 60/40 overlay: {metrics['D_60_40_vol_target_NFP_only']['full']['sharpe']:+.4f}")


if __name__ == "__main__":
    main()
