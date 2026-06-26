"""extract_qe_steepener_backtest.py — DEPOSITO AUTORITATIVO

Backtest pre-registrato dello steepener Bund 2-10 condizionato al fattore
QE di Altavilla et al. (2019). Riproducibile end-to-end con seed fisso.

PRE-REGISTRAZIONE (vedi PROTOCOL.md per la versione integrale):

1. SEGNO. Posizione di irripidimento (long 10Y, short 2Y) se QE_factor > 0;
   appiattimento altrimenti. Il segno NON e' cercato a posteriori: deriva
   dalla monotonicita' di beta_QE_n lungo la curva Bund (beta_QE_10Y >
   beta_QE_2Y, dal modello autoritativo step1_ecb_curve_symmetry,
   results/05_ecb_curve_qe/results.json).

2. TAGLIA.
   - binaria: ±1 sul solo segno
   - continua: z(QE) = (QE - mu_60) / sigma_60, normalizzato su rolling 60
     eventi precedenti (per eventi con < 60 storia, si usa il prefisso
     disponibile; primi 5 eventi: taglia binaria di fallback).

3. P&L PER EVENTO (in bp di pendenza).
   slope_change = ΔDE10Y - ΔDE2Y  (entrambe nella Press Conference Window)
   pnl_per_event = (+1 se QE>0 else -1) * size * slope_change
   La pendenza si IRRIPIDISCE se QE > 0: ΔDE10Y > ΔDE2Y => slope_change > 0
   e la posizione long-steepener guadagna. Il P&L e' direttamente in bp.

4. COSTI.
   - 0.2 bp per gamba round-trip (slip ordinario) => 0.4 bp totali per
     trade DV01-neutral. La taglia continua paga 0.4*|size|, la binaria
     paga 0.4*1.
   - Sensibilita' calcolata anche a 0.5 bp/gamba (1.0 bp totali).

5. CAPIENZA. Su €100m notional Bund 10Y, DV01 ≈ €10,000/bp. Il P&L per
   evento in bp di pendenza si converte in € moltiplicando per la DV01
   della gamba 10Y (la 2Y e' size-matched in DV01: il P&L per bp di
   slope change e' DV01_10Y).

6. SHARPE ANNUALIZZATO. Eventi/anno = 129/15 ≈ 8.6. Sharpe = mean/std *
   sqrt(8.6).

7. BOOTSTRAP. Clusterizzato per anno, B=2000, MASTER_SEED=20260621.
   Riportato IC 95% percentile e p-value one-sided (mean_boot > 0).

8. SPLIT TRAIN/OOS. Cronologico: primi 86 eventi train (≈2/3), ultimi 43
   OOS (≈1/3). Nessun parametro ottimizzato sul training (segno e taglia
   sono fissati a priori).

UNIVERSO. I 129 eventi ECB 2011-07 → 2025-11 con T/P/QE tutti disponibili
(NaN drop). Coincide con il sample di step1_ecb_curve_symmetry
(n_events=129 nel JSON autoritativo).
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
OUT = ROOT / "results" / "05_ecb_curve_qe" / "strategy_qe_steepener"

ALTAVILLA_XLSX = ROOT / "data" / "events" / "EA-MPD_ECB_Altavilla2019.xlsx"
ALTAVILLA_TPQE = Path(
    "/home/francesco/TESI/Dati/external_data/altavilla_TPQE_factors.csv"
)
ECB_CURVE_RESULTS = ROOT / "results" / "05_ecb_curve_qe" / "results.json"

MASTER_SEED = 20260621
SEED_NAME = "qe_steepener_2010_2025"
B_BOOT = 2000
EVENTS_PER_YEAR = 129 / 15.0  # ≈ 8.6
ROLLING_Z_WINDOW = 60
DV01_PER_100M = 10000.0  # € per bp su €100m Bund 10Y
COST_BP_PER_LEG_BASE = 0.2
COST_BP_PER_LEG_STRESS = 0.5
TASK_TIMESTAMP = (
    datetime.now(timezone.utc).replace(microsecond=0)
    .isoformat().replace("+00:00", "Z")
)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def seed_for(name: str) -> int:
    h = hashlib.sha256(f"{MASTER_SEED}|{name}".encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") & 0x7FFFFFFFFFFFFFFF


def load_data() -> pd.DataFrame:
    tpqe = pd.read_csv(ALTAVILLA_TPQE)
    tpqe["date"] = pd.to_datetime(tpqe["date"])

    pc = pd.read_excel(ALTAVILLA_XLSX, sheet_name="Press Conference Window")
    pc["date"] = pd.to_datetime(pc["date"], dayfirst=False, errors="coerce")
    if pc["date"].isna().any():
        pc.loc[pc["date"].isna(), "date"] = pd.to_datetime(
            pc.loc[pc["date"].isna(), "date"], dayfirst=True, errors="coerce"
        )

    df = tpqe.merge(pc[["date", "DE2Y", "DE10Y"]], on="date", how="inner")
    df = df.dropna(subset=["Target", "Path", "QE", "DE2Y", "DE10Y"])
    df = df.sort_values("date").reset_index(drop=True)
    df["year"] = df["date"].dt.year
    return df


def compute_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["sign"] = np.where(df["QE"] > 0, +1.0, -1.0)

    mu = df["QE"].rolling(ROLLING_Z_WINDOW, min_periods=5).mean().shift(1)
    sd = df["QE"].rolling(ROLLING_Z_WINDOW, min_periods=5).std().shift(1)
    z = (df["QE"] - mu) / sd
    df["z_qe"] = z

    size_cont = z.abs().fillna(1.0)
    size_cont = size_cont.clip(upper=3.0)
    df["size_binary"] = 1.0
    df["size_cont"] = size_cont

    # DE2Y e DE10Y nel file EA-MPD sono GIA' in basis points (vedi Notes:
    # "DE2Y/DE10Y: ... rate change in the relevant window in basis points").
    # Quindi slope_change_bp = DE10Y - DE2Y, senza ulteriore scaling.
    df["slope_change_bp"] = df["DE10Y"] - df["DE2Y"]
    return df


def compute_pnl(df: pd.DataFrame, cost_per_leg_bp: float) -> pd.DataFrame:
    df = df.copy()
    cost_total = 2.0 * cost_per_leg_bp

    pnl_gross_unit = df["sign"] * df["slope_change_bp"]

    df["pnl_gross_binary"] = pnl_gross_unit * df["size_binary"]
    df["pnl_net_binary"] = (
        df["pnl_gross_binary"] - cost_total * df["size_binary"]
    )

    df["pnl_gross_cont"] = pnl_gross_unit * df["size_cont"]
    df["pnl_net_cont"] = (
        df["pnl_gross_cont"] - cost_total * df["size_cont"]
    )
    return df


def annualized_sharpe(pnl: np.ndarray) -> float:
    mu = pnl.mean()
    sd = pnl.std(ddof=1)
    if sd == 0 or not np.isfinite(sd):
        return 0.0
    return float(mu / sd * np.sqrt(EVENTS_PER_YEAR))


def cluster_bootstrap_sharpe(
    pnl: np.ndarray, years: np.ndarray, B: int, seed: int
) -> dict:
    rng = np.random.default_rng(seed)
    unique_years = np.unique(years)
    sh = np.empty(B, dtype=float)
    means = np.empty(B, dtype=float)
    for b in range(B):
        sampled = rng.choice(
            unique_years, size=len(unique_years), replace=True
        )
        boot_pnl = np.concatenate([pnl[years == y] for y in sampled])
        if boot_pnl.size < 2:
            sh[b] = 0.0
            means[b] = 0.0
            continue
        sh[b] = annualized_sharpe(boot_pnl)
        means[b] = boot_pnl.mean()
    lo = float(np.percentile(sh, 2.5))
    hi = float(np.percentile(sh, 97.5))
    p_one_sided = float(np.mean(means <= 0))
    return {
        "ic95_lo": lo, "ic95_hi": hi,
        "p_one_sided_mean_gt0": p_one_sided,
        "n_boot": B,
    }


def run_backtest(
    df: pd.DataFrame, label: str, cost_per_leg_bp: float
) -> dict:
    d = compute_pnl(df, cost_per_leg_bp=cost_per_leg_bp)
    years = d["year"].values
    n = len(d)

    metrics = {"label": label, "n_events": int(n),
               "cost_per_leg_bp": cost_per_leg_bp,
               "cost_total_bp_per_trade": 2.0 * cost_per_leg_bp,
               "events_per_year": EVENTS_PER_YEAR,
               "date_first": str(d["date"].iloc[0].date()),
               "date_last": str(d["date"].iloc[-1].date())}

    seed_b = seed_for(f"{SEED_NAME}_{label}_binary_{cost_per_leg_bp}")
    seed_c = seed_for(f"{SEED_NAME}_{label}_cont_{cost_per_leg_bp}")
    seed_g = seed_for(f"{SEED_NAME}_{label}_gross_{cost_per_leg_bp}")

    for variant_name, pnl_col, seed_v in [
        ("gross_continuous", "pnl_gross_cont", seed_g),
        ("net_binary", "pnl_net_binary", seed_b),
        ("net_continuous", "pnl_net_cont", seed_c),
    ]:
        pnl = d[pnl_col].values
        sh = annualized_sharpe(pnl)
        mean_pnl = float(pnl.mean())
        std_pnl = float(pnl.std(ddof=1))
        boot = cluster_bootstrap_sharpe(pnl, years, B_BOOT, seed_v)
        pnl_per_year_bp = mean_pnl * EVENTS_PER_YEAR
        pnl_per_year_eur_100m = pnl_per_year_bp * DV01_PER_100M
        metrics[variant_name] = {
            "sharpe_ann": sh,
            "pnl_per_event_bp": mean_pnl,
            "pnl_std_event_bp": std_pnl,
            "pnl_per_year_bp_slope": pnl_per_year_bp,
            "pnl_per_year_eur_100m_notional": pnl_per_year_eur_100m,
            "bootstrap": boot,
        }
    return metrics


def main():
    print(f"=== QE-Steepener Backtest — deposit run {TASK_TIMESTAMP} ===")
    OUT.mkdir(parents=True, exist_ok=True)

    print("\n[1/5] Caricamento dati ...")
    df = load_data()
    print(f"  n_events (T/P/QE + DE2Y + DE10Y completi) = {len(df)}")
    assert len(df) == 129, (
        f"Mismatch n_events: atteso 129 (Fork B), trovato {len(df)}."
    )

    print("\n[2/5] Costruzione segnale pre-registrato ...")
    df = compute_signal(df)
    n_steep = int((df["sign"] > 0).sum())
    n_flat = int((df["sign"] < 0).sum())
    print(f"  steepener (QE>0): {n_steep}  flattener (QE<0): {n_flat}")

    print("\n[3/5] Backtest sample completo ...")
    full_base = run_backtest(df, "full_sample", COST_BP_PER_LEG_BASE)
    full_stress = run_backtest(df, "full_sample_stress",
                                COST_BP_PER_LEG_STRESS)
    full_sample_out = {
        "task_timestamp": TASK_TIMESTAMP,
        "seed_name": SEED_NAME,
        "master_seed": MASTER_SEED,
        "B_bootstrap": B_BOOT,
        "results": {
            "base_costs_0p2bp_per_leg": full_base,
            "stress_costs_0p5bp_per_leg": full_stress,
        },
        "comment": (
            "Backtest sample completo con costi base (0.2 bp/leg) e "
            "scenario stress (0.5 bp/leg). 3 varianti per scenario: "
            "gross_continuous (size proporzionale a |z(QE)|), "
            "net_binary (±1 sul segno), net_continuous (z*sign con "
            "costi). DV01 €10k/bp su €100m notional 10Y."
        ),
    }
    (OUT / "backtest_full_sample.json").write_bytes(
        json.dumps(full_sample_out, indent=2, sort_keys=True,
                    default=str).encode("utf-8")
    )

    print("\n[4/5] Split train/OOS cronologico (86/43) ...")
    n_train = 86
    df_train = df.iloc[:n_train].reset_index(drop=True)
    df_oos = df.iloc[n_train:].reset_index(drop=True)
    train_res = run_backtest(df_train, "train_2_thirds",
                              COST_BP_PER_LEG_BASE)
    oos_res = run_backtest(df_oos, "oos_1_third",
                            COST_BP_PER_LEG_BASE)

    def shrinkage(t: float, o: float) -> float:
        if t == 0 or not np.isfinite(t):
            return float("nan")
        return float(o / t)

    shr = {
        v: {
            "train_sharpe": train_res[v]["sharpe_ann"],
            "oos_sharpe": oos_res[v]["sharpe_ann"],
            "shrinkage_oos_to_train": shrinkage(
                train_res[v]["sharpe_ann"], oos_res[v]["sharpe_ann"]
            ),
            "sign_preserved_oos": (
                oos_res[v]["sharpe_ann"] * train_res[v]["sharpe_ann"] > 0
            ),
        }
        for v in ("gross_continuous", "net_binary", "net_continuous")
    }
    train_oos_out = {
        "task_timestamp": TASK_TIMESTAMP,
        "seed_name": SEED_NAME,
        "master_seed": MASTER_SEED,
        "split": {"n_train": int(n_train), "n_oos": int(len(df_oos)),
                   "train_first_date": str(df_train["date"].iloc[0].date()),
                   "train_last_date": str(df_train["date"].iloc[-1].date()),
                   "oos_first_date": str(df_oos["date"].iloc[0].date()),
                   "oos_last_date": str(df_oos["date"].iloc[-1].date())},
        "train": train_res,
        "oos": oos_res,
        "shrinkage_per_variant": shr,
        "comment": (
            "Split cronologico 2/3 (n=86, fino al 86esimo evento) / 1/3 "
            "(n=43). Nessun parametro fittato sul training: segno e "
            "taglia sono fissati a priori dal modello autoritativo "
            "(step1_ecb_curve_symmetry). La shrinkage misura solo "
            "ampiezza media, non flip di segno. 'sign_preserved_oos' "
            "verifica che il segno del Sharpe non si inverta."
        ),
    }
    (OUT / "backtest_train_oos.json").write_bytes(
        json.dumps(train_oos_out, indent=2, sort_keys=True,
                    default=str).encode("utf-8")
    )

    print("\n[5/5] Manifest ...")
    script_path = Path(__file__).resolve()

    ecb_results = json.loads(ECB_CURVE_RESULTS.read_text())
    config_hash_step1 = ecb_results.get("config_hash", "n/a")

    fork_b_baseline = {
        "sharpe_gross_continuous": 1.22,
        "sharpe_net_binary": 0.82,
        "sharpe_net_continuous": 0.78,
        "ic95_net_cont": [0.47, 1.10],
        "p_one_sided_net_cont": 0.0015,
        "shrinkage_train_oos": 0.59,
        "train_sharpe_net_cont": 0.92,
        "oos_sharpe_net_cont": 0.54,
        "pnl_per_year_eur_80k_net_unspecified_variant": True,
    }
    deposited = {
        "sharpe_gross_continuous": full_base["gross_continuous"]["sharpe_ann"],
        "sharpe_net_binary": full_base["net_binary"]["sharpe_ann"],
        "sharpe_net_continuous": full_base["net_continuous"]["sharpe_ann"],
        "ic95_net_cont": [
            full_base["net_continuous"]["bootstrap"]["ic95_lo"],
            full_base["net_continuous"]["bootstrap"]["ic95_hi"],
        ],
        "p_one_sided_net_cont": full_base["net_continuous"]["bootstrap"][
            "p_one_sided_mean_gt0"
        ],
        "train_sharpe_net_cont": train_res["net_continuous"]["sharpe_ann"],
        "oos_sharpe_net_cont": oos_res["net_continuous"]["sharpe_ann"],
        "shrinkage_net_cont": shr["net_continuous"]["shrinkage_oos_to_train"],
        "pnl_per_year_eur_100m_net_binary": full_base["net_binary"][
            "pnl_per_year_eur_100m_notional"
        ],
        "pnl_per_year_eur_100m_net_continuous": full_base["net_continuous"][
            "pnl_per_year_eur_100m_notional"
        ],
        "pnl_per_year_eur_100m_gross_continuous": full_base[
            "gross_continuous"
        ]["pnl_per_year_eur_100m_notional"],
    }

    manifest = {
        "task": "deposit_qe_steepener_bund_2_10_backtest",
        "task_timestamp": TASK_TIMESTAMP,
        "seed_name": SEED_NAME,
        "master_seed": MASTER_SEED,
        "seed_int": seed_for(SEED_NAME),
        "executor": {
            "script_path": str(script_path),
            "script_sha256": sha256_file(script_path),
        },
        "inputs": {
            "altavilla_xlsx": {
                "path": str(ALTAVILLA_XLSX),
                "sha256": sha256_file(ALTAVILLA_XLSX),
            },
            "altavilla_tpqe_csv": {
                "path": str(ALTAVILLA_TPQE),
                "sha256": sha256_file(ALTAVILLA_TPQE),
                "status": (
                    "EXTERNAL: fuori repo (built da scripts/extract_altavilla.py)"
                ),
            },
            "ecb_curve_results_for_config_hash": {
                "path": str(ECB_CURVE_RESULTS),
                "sha256": sha256_file(ECB_CURVE_RESULTS),
                "config_hash_referenced": config_hash_step1,
            },
        },
        "outputs": {
            "backtest_full_sample.json": {
                "path": str(OUT / "backtest_full_sample.json"),
                "sha256": sha256_file(OUT / "backtest_full_sample.json"),
            },
            "backtest_train_oos.json": {
                "path": str(OUT / "backtest_train_oos.json"),
                "sha256": sha256_file(OUT / "backtest_train_oos.json"),
            },
        },
        "validation_vs_fork_b": {
            "fork_b_baseline_session_only": fork_b_baseline,
            "deposited_authoritative": deposited,
            "interpretation": (
                "Confronto numerico vs il Fork B della sessione esecutore "
                "precedente. Lo scarto fra i due e' atteso in misura modesta "
                "(diversa estrazione di z(QE), diversa procedura di "
                "bootstrap), ma il segno e l'ordine di grandezza dei "
                "Sharpe devono combaciare. Cifre depositate sono ora "
                "l'autoritative reference per la tesi."
            ),
        },
        "references": {
            "altavilla_2019": (
                "Altavilla, C., Brugnolini, L., Gürkaynak, R. S., Motto, R., "
                "and Ragusa, G. (2019). Measuring Euro Area Monetary Policy. "
                "Journal of Monetary Economics, 108, 162-179."
            ),
            "step1_ecb_curve_symmetry": (
                "results/05_ecb_curve_qe/results.json — step1, 15 maturities "
                "Bund DE3M..DE30Y, beta_QE monotonically increasing from "
                "+0.40 (2Y) to plateau ~+1.14 (10Y stable to 30Y). "
                "12/15 BY-rejected at q=0.10."
            ),
        },
        "notes_for_reader": (
            "Il P&L per evento e' in bp di pendenza (ΔDE10Y - ΔDE2Y). La "
            "conversione in € usa DV01 = 10000 €/bp su €100m notional 10Y. "
            "La gamba 2Y e' size-matched in DV01, quindi il P&L per bp di "
            "slope change e' direttamente la DV01 della 10Y."
        ),
    }
    (OUT / "manifest.json").write_bytes(
        json.dumps(manifest, indent=2, sort_keys=True,
                    default=str).encode("utf-8")
    )

    print("\n  DONE ↓ output:")
    for name in ("backtest_full_sample.json",
                  "backtest_train_oos.json", "manifest.json"):
        p = OUT / name
        print(f"    {p.relative_to(ROOT)}  (sha256 {sha256_file(p)[:16]}...)")

    print("\n  SINTESI numerica (base costs 0.2 bp/leg):")
    print(f"    Sharpe gross continuous: "
          f"{full_base['gross_continuous']['sharpe_ann']:+.3f}")
    print(f"    Sharpe net binary:       "
          f"{full_base['net_binary']['sharpe_ann']:+.3f}")
    print(f"    Sharpe net continuous:   "
          f"{full_base['net_continuous']['sharpe_ann']:+.3f}")
    print(f"    IC95 net cont: ["
          f"{full_base['net_continuous']['bootstrap']['ic95_lo']:+.3f}, "
          f"{full_base['net_continuous']['bootstrap']['ic95_hi']:+.3f}]")
    print(f"    p one-sided (net cont): "
          f"{full_base['net_continuous']['bootstrap']['p_one_sided_mean_gt0']:.4f}")
    print(f"    P&L gross/yr €100m: "
          f"€{full_base['gross_continuous']['pnl_per_year_eur_100m_notional']:,.0f}")
    print(f"    P&L net_binary/yr €100m: "
          f"€{full_base['net_binary']['pnl_per_year_eur_100m_notional']:,.0f}")
    print(f"    P&L net_cont/yr €100m: "
          f"€{full_base['net_continuous']['pnl_per_year_eur_100m_notional']:,.0f}")
    print(f"\n  SINTESI train/OOS:")
    print(f"    Train Sharpe net cont:   "
          f"{train_res['net_continuous']['sharpe_ann']:+.3f}")
    print(f"    OOS Sharpe net cont:     "
          f"{oos_res['net_continuous']['sharpe_ann']:+.3f}")
    print(f"    Shrinkage:               "
          f"{shr['net_continuous']['shrinkage_oos_to_train']:+.3f}")
    print(f"    Sign preserved OOS:      "
          f"{shr['net_continuous']['sign_preserved_oos']}")


if __name__ == "__main__":
    main()
