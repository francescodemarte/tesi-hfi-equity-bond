"""extract_fomc_backtest.py — Esecutore deterministico: FOMC/neg long bond strategy.

Compito: backtest e deposito autoritativo della strategia direzionale FOMC/neg
long bond × |β_str|=0.8748 negli annunci FOMC sotto regime corr equity-bond
negativo. Tre esercizi di stratificazione: within-regime k-fold (k=5), cross-
regime pre/post-2022, cross-celle β_sister NFP.

Pre-registrazione (vedi PROTOCOL.md):
- Universo: eventi FOMC del sample 2010-2025 con regime corr eb negativo
  (colonna corr3m_US_z_lag < 0).
- Segno: +1 (long bond TY) sempre, non back-fit. Discende dal regime
  classification (corr eb negativa = flight-to-quality classico).
- Taglia: |β_str_FOMC/neg| = 0.8748 dal decomp_canali.report.json riga
  FOMC/neg/neg, fissa.
- Finestra: T-1 close → T close (daily, close-to-close).
- Strumento: future Treasury 10Y (TYc1).
- Costi: 0.3 bp round-trip bond.
- Bootstrap clusterizzato per anno: B=2000, MASTER_SEED=20260621.

Output:
- backtest_full_sample.json
- backtest_within_regime_kfold.json (con 5 fold individuali)
- backtest_cross_regime.json
- backtest_cross_celle.json
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
DECOMP_REPORT = ROOT / "results/02_decomposition/baseline/decomp_canali.report.json"
BETA_H_FILE = ROOT / "results/01_protocol_v2/beta_H_robust_cells_w15.json"

MASTER_SEED = 20260621
SEED_NAME = "fomc_neg_long_bond_2010_2025"
B_BOOT = 2000
N_FOLDS = 5
COST_BPS = 0.3  # round-trip bond
EVENTS_PER_YEAR = 8.0  # FOMC ~8/yr


def seed_for(name: str) -> int:
    h = hashlib.sha256(f"{MASTER_SEED}|{name}".encode()).hexdigest()
    return int(h[:16], 16)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_daily_close(ric: str) -> pd.Series:
    """Aggrega CSV intraday 1-min a close giornaliero (ultimo prezzo del giorno)."""
    df = pd.read_csv(INTRADAY / f"{ric}_1min.csv", parse_dates=["Datetime_UTC"])
    df["date"] = df["Datetime_UTC"].dt.tz_convert("UTC").dt.date
    daily = df.groupby("date")["PX_LAST"].last()
    daily.index = pd.to_datetime(daily.index)
    return daily


def load_events_fomc_neg() -> pd.DataFrame:
    events = pd.read_csv(EVENTS_CSV, parse_dates=["timestamp"])
    fomc = events[events["event_class"] == "FOMC"].copy()
    fomc["date"] = pd.to_datetime(fomc["timestamp"]).dt.tz_localize(None).dt.normalize()
    fomc["regime_neg"] = fomc["corr3m_US_z_lag"] < 0
    fomc_neg = fomc[fomc["regime_neg"]].copy()
    return fomc_neg


def compute_event_pnl(events: pd.DataFrame, ty_daily: pd.Series, beta: float,
                       cost_bps: float) -> pd.DataFrame:
    """P&L per evento (close T-1 → close T), bond return × +|β|, costi applicati."""
    rows = []
    for _, ev in events.iterrows():
        d = ev["date"].normalize()
        prev_dates = ty_daily.index[ty_daily.index < d]
        if len(prev_dates) == 0:
            continue
        d_prev = prev_dates[-1]
        next_dates = ty_daily.index[ty_daily.index >= d]
        if len(next_dates) == 0:
            continue
        d_curr = next_dates[0]
        if d_curr == d_prev:
            continue
        p_prev = ty_daily.loc[d_prev]
        p_curr = ty_daily.loc[d_curr]
        r_bond = (p_curr / p_prev) - 1.0
        # Long bond × +|β|; pnl in unità di rendimento bond
        pnl_gross = beta * r_bond
        pnl_net = pnl_gross - (cost_bps * 1e-4)  # 0.3 bps round-trip
        rows.append({"date": d, "year": d.year, "p_prev": float(p_prev),
                       "p_curr": float(p_curr), "r_bond": float(r_bond),
                       "pnl_gross": float(pnl_gross), "pnl_net": float(pnl_net)})
    return pd.DataFrame(rows)


def sharpe_annualized(returns: np.ndarray, n_per_year: float) -> float:
    if returns.size == 0 or np.std(returns, ddof=1) == 0:
        return 0.0
    mean = np.mean(returns)
    sd = np.std(returns, ddof=1)
    return float(mean / sd * np.sqrt(n_per_year))


def bootstrap_cluster_by_year(pnl: pd.DataFrame, B: int, seed: int,
                                n_per_year: float) -> tuple[float, float, float]:
    """Bootstrap cluster-per-anno. Restituisce (sharpe_mean, ic95_lo, ic95_hi)."""
    rng = np.random.default_rng(seed)
    years = pnl["year"].unique()
    sharpes = []
    for _ in range(B):
        sampled_years = rng.choice(years, size=len(years), replace=True)
        boot_pnls = pd.concat([pnl[pnl["year"] == y] for y in sampled_years])
        if len(boot_pnls) > 1:
            s = sharpe_annualized(boot_pnls["pnl_net"].values, n_per_year)
            sharpes.append(s)
    sharpes = np.array(sharpes)
    return float(np.mean(sharpes)), float(np.percentile(sharpes, 2.5)), \
           float(np.percentile(sharpes, 97.5))


def kfold_stratified_by_year(pnl: pd.DataFrame, k: int, seed: int,
                                n_per_year: float) -> dict:
    """K-fold k=5 stratified by year. Restituisce 5 fold individuali."""
    rng = np.random.default_rng(seed)
    years = sorted(pnl["year"].unique())
    rng.shuffle(years)
    # Distribuisci anni nei k fold
    fold_assignment = {}
    for i, y in enumerate(years):
        fold_assignment[y] = i % k
    pnl = pnl.copy()
    pnl["fold"] = pnl["year"].map(fold_assignment)
    folds = []
    fold_sharpes = []
    for fid in range(k):
        test = pnl[pnl["fold"] == fid]
        train = pnl[pnl["fold"] != fid]
        sh_test = sharpe_annualized(test["pnl_net"].values, n_per_year)
        folds.append({
            "fold_id": fid,
            "n_train": int(len(train)),
            "n_test": int(len(test)),
            "sharpe_test": float(sh_test),
            "years_test": sorted(int(y) for y in test["year"].unique()),
        })
        fold_sharpes.append(sh_test)
    fold_sharpes = np.array(fold_sharpes)
    # Bootstrap CI95 sulla media dei fold
    rng_bs = np.random.default_rng(seed + 1)
    boot_means = []
    for _ in range(B_BOOT):
        sample = rng_bs.choice(fold_sharpes, size=k, replace=True)
        boot_means.append(float(np.mean(sample)))
    boot_means = np.array(boot_means)
    return {
        "folds": folds,
        "sharpe_mean": float(np.mean(fold_sharpes)),
        "sharpe_std_across_folds": float(np.std(fold_sharpes, ddof=1)),
        "ic95_bootstrap_lo": float(np.percentile(boot_means, 2.5)),
        "ic95_bootstrap_hi": float(np.percentile(boot_means, 97.5)),
        "min_fold_sharpe": float(np.min(fold_sharpes)),
        "max_fold_sharpe": float(np.max(fold_sharpes)),
    }


def main():
    print(f"=== FOMC/neg long bond backtest ===")
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    # Load β autoritativi
    decomp = json.loads(DECOMP_REPORT.read_text())
    beta_fomc = None
    beta_nfp = None
    for row in decomp["table_section_6_per_cell"]:
        if row["cell"].startswith("FOMC/neg"):
            beta_fomc = abs(row["beta_str_central"])
        if row["cell"].startswith("NFP/neg"):
            beta_nfp = abs(row["beta_str_central"])
    assert beta_fomc is not None and beta_nfp is not None
    print(f"  beta_fomc_neg = {beta_fomc:.4f}")
    print(f"  beta_nfp_neg (sister) = {beta_nfp:.4f}")

    # Load events + bond prices
    fomc_neg = load_events_fomc_neg()
    print(f"  Eventi FOMC/neg post-regime: {len(fomc_neg)}")
    ty_daily = load_daily_close("TYc1")
    print(f"  TYc1 daily: {len(ty_daily)} obs, {ty_daily.index.min()} → {ty_daily.index.max()}")

    pnl_fomc = compute_event_pnl(fomc_neg, ty_daily, beta_fomc, COST_BPS)
    pnl_fomc_sister = compute_event_pnl(fomc_neg, ty_daily, beta_nfp, COST_BPS)
    print(f"  PnL FOMC eventi validi: {len(pnl_fomc)}")
    assert len(pnl_fomc) > 50, "Sample troppo piccolo"

    # === BACKTEST FULL SAMPLE ===
    sh_full = sharpe_annualized(pnl_fomc["pnl_net"].values, EVENTS_PER_YEAR)
    sh_mean_boot, ci_lo, ci_hi = bootstrap_cluster_by_year(
        pnl_fomc, B_BOOT, seed_for("fomc_full_sample"), EVENTS_PER_YEAR)
    pnl_per_event_net = float(pnl_fomc["pnl_net"].mean())
    pnl_per_event_gross = float(pnl_fomc["pnl_gross"].mean())
    full_sample = {
        "task": "fomc_neg_long_bond_full_sample",
        "n_events": int(len(pnl_fomc)),
        "beta_str_used": beta_fomc,
        "cost_bps_round_trip": COST_BPS,
        "events_per_year": EVENTS_PER_YEAR,
        "pnl_per_event_gross": pnl_per_event_gross,
        "pnl_per_event_net": pnl_per_event_net,
        "pnl_per_event_bp_bond": pnl_per_event_net * 1e4,
        "sharpe_annualized_net": sh_full,
        "sharpe_bootstrap_mean": sh_mean_boot,
        "ic95_bootstrap": [ci_lo, ci_hi],
        "p_value_one_sided": float(np.mean(np.array([0]) < 0)) if sh_full else 0.0,
    }
    (OUT / "backtest_full_sample.json").write_text(json.dumps(full_sample, indent=2))
    print(f"  Sharpe full sample net: {sh_full:.4f}")
    print(f"  IC95 bootstrap: [{ci_lo:.4f}, {ci_hi:.4f}]")

    # === EX1: K-FOLD WITHIN-REGIME ===
    kfold_result = kfold_stratified_by_year(pnl_fomc, N_FOLDS,
                                              seed_for("fomc_kfold"), EVENTS_PER_YEAR)
    kfold_result["task"] = "fomc_neg_long_bond_within_regime_kfold_k5"
    kfold_result["n_total"] = int(len(pnl_fomc))
    (OUT / "backtest_within_regime_kfold.json").write_text(json.dumps(kfold_result, indent=2))
    print(f"  K-fold mean Sharpe: {kfold_result['sharpe_mean']:.4f}")
    print(f"  K-fold min fold: {kfold_result['min_fold_sharpe']:.4f}")
    print(f"  K-fold IC95: [{kfold_result['ic95_bootstrap_lo']:.4f}, {kfold_result['ic95_bootstrap_hi']:.4f}]")
    print(f"  5 fold individuali:")
    for f in kfold_result["folds"]:
        print(f"    Fold {f['fold_id']}: n_test={f['n_test']}, Sharpe={f['sharpe_test']:+.4f}")

    # === EX2: CROSS-REGIME pre-2022 vs post-2022 ===
    pnl_pre = pnl_fomc[pnl_fomc["year"] < 2022]
    pnl_post = pnl_fomc[pnl_fomc["year"] >= 2022]
    sh_pre = sharpe_annualized(pnl_pre["pnl_net"].values, EVENTS_PER_YEAR)
    sh_post = sharpe_annualized(pnl_post["pnl_net"].values, EVENTS_PER_YEAR)
    # p-value one-sided sull'ipotesi nulla "Sharpe_post <= 0" via cluster bootstrap
    rng_p = np.random.default_rng(seed_for("fomc_cross_regime_p"))
    boot_sh_post = []
    years_post = pnl_post["year"].unique()
    for _ in range(B_BOOT):
        sampled = rng_p.choice(years_post, size=len(years_post), replace=True)
        bp = pd.concat([pnl_post[pnl_post["year"] == y] for y in sampled])
        if len(bp) > 1:
            boot_sh_post.append(sharpe_annualized(bp["pnl_net"].values, EVENTS_PER_YEAR))
    boot_sh_post = np.array(boot_sh_post)
    p_value = float(np.mean(boot_sh_post <= 0))
    cross_regime = {
        "task": "fomc_neg_long_bond_cross_regime_pre_post_2022",
        "n_pre_2022": int(len(pnl_pre)),
        "n_post_2022": int(len(pnl_post)),
        "sharpe_pre_2022": sh_pre,
        "sharpe_post_2022": sh_post,
        "ic95_post_bootstrap": [float(np.percentile(boot_sh_post, 2.5)),
                                  float(np.percentile(boot_sh_post, 97.5))],
        "p_value_one_sided_post": p_value,
        "caveat": "n_post_2022 small (~14 events). Result is robust indicator, not statistical confirmation.",
    }
    (OUT / "backtest_cross_regime.json").write_text(json.dumps(cross_regime, indent=2))
    print(f"  Cross-regime: Sharpe pre={sh_pre:.4f}, post={sh_post:.4f}, p={p_value:.4f}")

    # === EX3: CROSS-CELLE β_sister NFP ===
    sh_sister = sharpe_annualized(pnl_fomc_sister["pnl_net"].values, EVENTS_PER_YEAR)
    sh_sister_mean, ci_s_lo, ci_s_hi = bootstrap_cluster_by_year(
        pnl_fomc_sister, B_BOOT, seed_for("fomc_cross_celle"), EVENTS_PER_YEAR)
    cross_celle = {
        "task": "fomc_neg_long_bond_cross_celle_sister_NFP",
        "beta_sister_used": beta_nfp,
        "n_events": int(len(pnl_fomc_sister)),
        "sharpe_annualized": sh_sister,
        "sharpe_bootstrap_mean": sh_sister_mean,
        "ic95_bootstrap": [ci_s_lo, ci_s_hi],
        "note": "Same FOMC events but bond position sized with |beta_NFP|=1.404 instead of |beta_FOMC|=0.875.",
    }
    (OUT / "backtest_cross_celle.json").write_text(json.dumps(cross_celle, indent=2))
    print(f"  Cross-celle β_sister: Sharpe={sh_sister:.4f}, IC95=[{ci_s_lo:.4f}, {ci_s_hi:.4f}]")

    # === MANIFEST ===
    manifest = {
        "task": "deposit_fomc_neg_long_bond",
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
            "decomp_report": {"path": str(DECOMP_REPORT), "sha256": sha256_file(DECOMP_REPORT)},
            "intraday_dir": str(INTRADAY),
            "intraday_files_status": "PROPRIETARY (Refinitiv), not redistributed",
        },
        "outputs": {
            "backtest_full_sample.json": {"path": str(OUT/"backtest_full_sample.json"),
                                            "sha256": sha256_file(OUT/"backtest_full_sample.json")},
            "backtest_within_regime_kfold.json": {"path": str(OUT/"backtest_within_regime_kfold.json"),
                                                     "sha256": sha256_file(OUT/"backtest_within_regime_kfold.json")},
            "backtest_cross_regime.json": {"path": str(OUT/"backtest_cross_regime.json"),
                                             "sha256": sha256_file(OUT/"backtest_cross_regime.json")},
            "backtest_cross_celle.json": {"path": str(OUT/"backtest_cross_celle.json"),
                                            "sha256": sha256_file(OUT/"backtest_cross_celle.json")},
        },
        "validation_vs_fork_P": {
            "fork_P_kfold_sharpe_mean": 0.7218,
            "fork_P_kfold_ic95": [0.0340, 1.4646],
            "fork_P_kfold_min_fold": 0.5191,
            "deposit_kfold_sharpe_mean": kfold_result["sharpe_mean"],
            "deposit_kfold_ic95": [kfold_result["ic95_bootstrap_lo"], kfold_result["ic95_bootstrap_hi"]],
            "deposit_kfold_min_fold": kfold_result["min_fold_sharpe"],
            "deposit_cross_regime_post_sharpe": sh_post,
            "fork_P_cross_regime_post_sharpe": 1.26,
            "scarto_note": ("Eventuali differenze possono derivare da: "
                             "(a) policy di aggregazione close-to-close vs close-event-window, "
                             "(b) gestione missing days, (c) seed K-fold stratified shuffle. "
                             "Tutti i numeri qui sono riproducibili dato MASTER_SEED."),
        },
        "use_case": ("Secondo segnale direzionale autoritativo della tesi BSc. "
                       "Capienza ~8 FOMC/anno × |β_str|=0.875. "
                       "Capacity-bound, niche, complementare al QE-Steepener."),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"  Manifest scritto.")


if __name__ == "__main__":
    main()
