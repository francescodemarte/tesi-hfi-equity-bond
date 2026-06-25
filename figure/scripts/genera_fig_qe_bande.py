"""genera_fig_qe_bande.py — Grafico 2: trasmissione QE lungo curva Bund + bande.

Output: figure/fig_qe_bande.pdf

Dati: results/05_ecb_curve_qe/results.json, campo step1_ecb_curve_symmetry.
n_events = 129 (post-2010 con T/P/QE pieno); 12/15 scadenze BY-rejected.

Python 3.11.15, matplotlib >= 3.7.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "figure" / "fig_qe_bande.pdf"

mpl.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 11,
    "axes.labelsize": 11,
    "legend.fontsize": 9.5,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "axes.linewidth": 0.8,
    "lines.linewidth": 1.4,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})


def load_data():
    r = json.loads((ROOT / "results/05_ecb_curve_qe/results.json").read_text())
    step1 = r["results"]["step1_ecb_curve_symmetry"]
    rows = step1["results_per_maturity"]
    years, betas, ses, rejected, ps, mats = [], [], [], [], [], []
    for row in rows:
        if row.get("beta_QE") is None:
            continue
        years.append(row["years"])
        betas.append(row["beta_QE"])
        ses.append(row["se_QE"])
        rejected.append(bool(row["by_rejected"]))
        ps.append(row["p_QE"])
        mats.append(row["maturity"])
    return {
        "years": np.array(years), "beta": np.array(betas), "se": np.array(ses),
        "by_rejected": np.array(rejected), "p": np.array(ps), "mats": mats,
        "n_events": step1["n_events"], "n_by": step1["n_qe_significant_BY"],
    }


def main():
    d = load_data()

    fig, ax = plt.subplots(figsize=(6.6, 4.3))

    yrs = d["years"]
    beta = d["beta"]
    ci_low = beta - 1.96 * d["se"]
    ci_high = beta + 1.96 * d["se"]

    # Banda di confidenza grigia (95%)
    ax.fill_between(yrs, ci_low, ci_high, color="0.78", alpha=0.55,
                     linewidth=0, label=r"banda 95% ($\pm 1.96\,\mathrm{SE}$)")

    # Linea centrale
    ax.plot(yrs, beta, color="black", linewidth=1.4, linestyle="-", zorder=3)

    # Marcatori distinti per significatività BY
    rej_mask = d["by_rejected"]
    # Significativi: marker pieno nero
    ax.plot(yrs[rej_mask], beta[rej_mask], "o", markerfacecolor="black",
             markeredgecolor="black", markersize=6.5, linestyle="none",
             label=r"BY-rigettato ($q=0.10$)", zorder=5)
    # Non significativi: marker vuoto bordo nero
    ax.plot(yrs[~rej_mask], beta[~rej_mask], "o", markerfacecolor="white",
             markeredgecolor="black", markersize=6.5, linestyle="none",
             markeredgewidth=1.2, label="non significativo", zorder=5)

    # Linea di riferimento β=1
    ax.axhline(1.0, color="black", linewidth=0.7, linestyle="--", alpha=0.6, zorder=1)
    # Linea zero
    ax.axhline(0.0, color="gray", linewidth=0.5, linestyle="-", alpha=0.5, zorder=0)

    # Tick e scala asse x
    ax.set_xscale("function", functions=(lambda x: np.sqrt(x), lambda x: x**2))
    tick_yrs = [0.25, 1, 2, 5, 10, 15, 20, 30]
    ax.set_xticks(tick_yrs)
    ax.set_xticklabels([str(t) if t >= 1 else f"{t:.2f}" for t in tick_yrs])
    ax.set_xlim(0.15, 32)

    ax.set_xlabel("Scadenza Bund (anni)")
    ax.set_ylabel(r"$\beta_{\mathrm{QE}}$")
    ax.set_ylim(-0.3, 1.45)
    ax.grid(True, which="major", linestyle=":", alpha=0.45, linewidth=0.5)
    ax.set_axisbelow(True)

    leg = ax.legend(loc="lower right", frameon=True, framealpha=0.92,
                     edgecolor="black", fancybox=False,
                     handlelength=2.4, handletextpad=0.55)
    leg.get_frame().set_linewidth(0.6)

    plt.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUT, format="pdf", bbox_inches="tight")
    print(f"  Saved {OUT}")
    print(f"  n_events = {d['n_events']}, BY-rigettate = {d['n_by']}/15")
    print()
    print("  Scadenze (yrs, β_QE, se, p, BY):")
    for i, mat in enumerate(d["mats"]):
        print(f"    {mat:6s}  yrs={yrs[i]:5.2f}  β={beta[i]:+.4f}  se={d['se'][i]:.4f}  p={d['p'][i]:.4f}  BY={rej_mask[i]}")


if __name__ == "__main__":
    main()
