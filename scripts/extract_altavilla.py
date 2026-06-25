"""extract_altavilla.py — Estrai i 3 fogli + TPQE da EA-MPD_ECB_Altavilla2019.xlsx.

Replica il processo della sessione 2026-06-24 che ha congelato i fattori
canonici T (Target), P (Path, orth Target), QE (orth T+P).
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "events" / "EA-MPD_ECB_Altavilla2019.xlsx"
OUT = ROOT / "data" / "external_public"
OUT.mkdir(parents=True, exist_ok=True)


def main():
    if not SRC.exists():
        raise SystemExit(
            f"File non trovato: {SRC}\n"
            "Scaricare il replication package Altavilla 2019 e copiarlo qui."
        )
    # 3 finestre
    for sheet_name, out_name in (
        ("Press Release Window", "altavilla_eampd_press_release_window.csv"),
        ("Press Conference Window", "altavilla_eampd_press_conference_window.csv"),
        ("Monetary Event Window", "altavilla_eampd_monetary_event_window.csv"),
    ):
        df = pd.read_excel(SRC, sheet_name=sheet_name)
        df["date"] = pd.to_datetime(df["date"])
        df.to_csv(OUT / out_name, index=False)
        print(f"  Estratto: {out_name}  n={len(df)}")

    # Fattori T/P/QE
    pr = pd.read_csv(OUT / "altavilla_eampd_press_release_window.csv")
    pc = pd.read_csv(OUT / "altavilla_eampd_press_conference_window.csv")
    pr["date"] = pd.to_datetime(pr["date"]); pc["date"] = pd.to_datetime(pc["date"])
    m = pr[["date", "OIS_1M"]].rename(columns={"OIS_1M": "OIS_1M_pr"}).merge(
        pc[["date", "OIS_1Y", "OIS_10Y"]].rename(
            columns={"OIS_1Y": "OIS_1Y_pc", "OIS_10Y": "OIS_10Y_pc"}),
        on="date", how="outer")
    m["Target"] = m["OIS_1M_pr"]

    mask_p = m["OIS_1Y_pc"].notna() & m["Target"].notna()
    if mask_p.sum() >= 5:
        x = m.loc[mask_p, "Target"].values
        y = m.loc[mask_p, "OIS_1Y_pc"].values
        beta_p = float(np.dot(x, y) / np.dot(x, x))
        m.loc[mask_p, "Path"] = y - beta_p * x

    mask_q = m["OIS_10Y_pc"].notna() & m["Target"].notna() & m["Path"].notna()
    if mask_q.sum() >= 5:
        X = np.column_stack([m.loc[mask_q, "Target"].values,
                              m.loc[mask_q, "Path"].values])
        y = m.loc[mask_q, "OIS_10Y_pc"].values
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        m.loc[mask_q, "QE"] = y - X @ beta

    out_cols = ["date", "Target", "Path", "QE"]
    m[out_cols].to_csv(OUT / "altavilla_TPQE_factors.csv", index=False)
    print(f"  Estratto: altavilla_TPQE_factors.csv  "
          f"(Target {m['Target'].notna().sum()}, "
          f"Path {m['Path'].notna().sum()}, "
          f"QE {m['QE'].notna().sum()})")


if __name__ == "__main__":
    main()
