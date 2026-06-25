"""genera_fig_robustezza_proxy.py — Grafico 1: robustezza β_str alla proxy di tasso.

Output: figure/fig_robustezza_proxy.pdf

Mostra come β_str delle 4 celle robuste si sposta al variare della proxy
con cui si costruisce la componente di tasso del bond.

Dati:
- Baseline (proxy front money-market FFc3): results/02_decomposition/baseline/
- Variant C_baseline (front MM puro): results/02_decomposition/true_curve_variants/
- Variant A_DGS10 (curva cash 10Y giornaliera): true_curve_variants/
- Variant B_multi (multi-curva 2/5/10Y): true_curve_variants/

Python 3.11.15, matplotlib >= 3.7.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "figure" / "fig_robustezza_proxy.pdf"

# Stile B/N coerente con la tesi
mpl.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 11,
    "axes.labelsize": 11,
    "axes.titlesize": 11,
    "legend.fontsize": 9.5,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "axes.linewidth": 0.8,
    "lines.linewidth": 1.4,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})


def load_data():
    baseline = json.loads((ROOT / "results/02_decomposition/baseline/decomp_canali.report.json").read_text())
    tcv = json.loads((ROOT / "results/02_decomposition/true_curve_variants/results.json").read_text())

    # Estraggo β_str baseline (proxy autoritativa: delta_rate_3 / "bordo 10Y via future")
    base = {}
    for row in baseline["table_section_6_per_cell"]:
        cell_raw = row["cell"]
        # cella ha formato "leg/reg/reg" — normalizzo
        parts = cell_raw.split("/")
        cell = f"{parts[0]}/{parts[1]}"
        if row.get("beta_str_central") is not None:
            base[cell] = row["beta_str_central"]

    # Variants
    variants = tcv["results_per_variant"]

    # Estraggo β_str per le 4 celle e le 4 proxy
    CELLS = ["NFP/neg", "CPI/neg", "FOMC/neg", "CPI/pos"]
    PROXY_ORDER = [
        ("Bordo 10Y\n(rif.)", base),            # baseline autoritativo
        ("Tratto breve\n(FFc3)", variants["C_baseline"]),
        ("Multi-scadenza\n(2/5/10Y)", variants["B_multi"]),
        ("Curva 10Y\ngiorn.", variants["A_DGS10"]),
    ]

    data = {}
    for cell in CELLS:
        vals = []
        for label, source in PROXY_ORDER:
            v = source.get(cell)
            if isinstance(v, dict):
                v = v.get("beta_str_central")
            vals.append(v)
        data[cell] = vals
    labels = [p[0] for p in PROXY_ORDER]
    return data, labels, CELLS


def main():
    data, labels, cells = load_data()

    fig, ax = plt.subplots(figsize=(6.4, 4.3))

    # Stili B/N distinti per cella
    styles = {
        "NFP/neg":   {"linestyle": "-",  "marker": "o", "markersize": 7, "markerfacecolor": "black",
                       "markeredgecolor": "black", "linewidth": 2.0, "color": "black"},
        "CPI/neg":   {"linestyle": "--", "marker": "s", "markersize": 6, "markerfacecolor": "white",
                       "markeredgecolor": "black", "linewidth": 1.2, "color": "black"},
        "FOMC/neg":  {"linestyle": "-.", "marker": "^", "markersize": 7, "markerfacecolor": "white",
                       "markeredgecolor": "black", "linewidth": 1.2, "color": "black"},
        "CPI/pos":   {"linestyle": ":",  "marker": "D", "markersize": 6, "markerfacecolor": "white",
                       "markeredgecolor": "black", "linewidth": 1.2, "color": "black"},
    }

    x = np.arange(len(labels))
    for cell in cells:
        ys = data[cell]
        ys_arr = np.array([np.nan if y is None else y for y in ys])
        ax.plot(x, ys_arr, label=cell, **styles[cell])

    # Linea orizzontale a 0 (cambio segno)
    ax.axhline(0, color="gray", linewidth=0.7, linestyle="-", alpha=0.7, zorder=0)

    # Banda di sampling solo per NFP/neg (cella robusta, dal baseline)
    baseline = json.loads((ROOT / "results/02_decomposition/baseline/decomp_canali.report.json").read_text())
    nfp_sb_low, nfp_sb_high = None, None
    for row in baseline["table_section_6_per_cell"]:
        if row["cell"].startswith("NFP/neg"):
            nfp_sb_low = row["sampling_band_low"]
            nfp_sb_high = row["sampling_band_high"]
            break
    if nfp_sb_low is not None:
        ax.errorbar([0], [data["NFP/neg"][0]],
                     yerr=[[data["NFP/neg"][0] - nfp_sb_low], [nfp_sb_high - data["NFP/neg"][0]]],
                     fmt="none", ecolor="black", elinewidth=1.0, capsize=4, alpha=0.6, zorder=1)

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_xlabel("Proxy per la componente di tasso del bond")
    ax.set_ylabel(r"$\beta_{\mathrm{str}}$")
    ax.set_ylim(-2.0, 3.0)
    ax.grid(True, which="major", linestyle=":", alpha=0.4, linewidth=0.5)
    ax.set_axisbelow(True)

    leg = ax.legend(loc="upper right", frameon=True, framealpha=0.92,
                     edgecolor="black", fancybox=False, ncol=1,
                     handlelength=2.8, handletextpad=0.5)
    leg.get_frame().set_linewidth(0.6)

    plt.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUT, format="pdf", bbox_inches="tight")
    print(f"  Saved {OUT}")

    # Diagnostica numerica
    print("\n  Valori usati (β_str per cella × proxy):")
    print(f"  {'Cell':12s}  " + "  ".join(f"{l[:18]:>20s}" for l in labels))
    for cell in cells:
        row = "  ".join(f"{'n/a' if v is None else f'{v:+.4f}':>20s}"
                          for v in data[cell])
        print(f"  {cell:12s}  {row}")


if __name__ == "__main__":
    main()
