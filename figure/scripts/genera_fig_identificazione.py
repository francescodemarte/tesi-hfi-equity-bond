"""genera_fig_identificazione.py — Grafico 3: identificazione per eteroschedasticità.

Output: figure/fig_identificazione.pdf

Livello 1: scatter dei rendimenti a livello di singolo evento per NFP/neg,
sovrapposto alle finestre di controllo, con le due rette di regressione e le
ellissi di covarianza al 95%. La differenza di dispersione tra evento e
controllo (firma di Rigobon-Sack) si vede dal salto della varianza r_hat.

NOTA — momenti 2x2: i numeri delle matrici di covarianza (var_b, var_e,
cov_be per evento e controllo) sono depositati nel file
  results/01_protocol_v2/full_moments_2x2/nfp_neg_moments_2x2.json
con validazione a tol=1e-9 contro beta_H_robust_cells_w15.json. Questo
script ricalcola i punti scatter dai cluster intraday (richiede Refinitiv),
ma i momenti aggregati che servono per le ellissi e le rette OLS sono
disponibili anche solo dal file di deposito (vedi nfp_neg_moments_2x2.json).

Dati intraday Refinitiv (proprietary, fuori dalla repo pubblica):
  /home/francesco/TESI/Dati/data_processed/ESc1_1min.csv (equity)
  /home/francesco/TESI/Dati/data_processed/TYc1_1min.csv (bond)

Pipeline (riuso del codice del pacchetto protocol_v2):
  - data.load_events: calendario eventi v2
  - run.compute_regimes: regime equity-bond corr 63gg lag t-1
  - run.assemble: cluster evento+controlli per NFP/neg
  - windows.dedup_shared_controls: dedup contaminanti tra regimi opposti

Python 3.11.15, matplotlib >= 3.7, MASTER_SEED = 20260621.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "figure" / "fig_identificazione.pdf"

# Aggiungo il path del pacchetto protocol_v2 per riusare la pipeline
sys.path.insert(0, str(ROOT / "src/hfi/protocol_v2"))
import config as cfg07
import data as data07
import run as run07
import windows as win07

# Dati intraday Refinitiv (fuori dalla repo pubblica)
INTRADAY = Path("/home/francesco/TESI/Dati/data_processed")
EVENTS_CSV = ROOT / "data/events/events_with_regime_classifier.csv"
CONT_CSV = Path("/home/francesco/TESI/Dati/calendari/contaminants_build_2026-06-22/"
                "contaminants_v2_2026-06-22.csv")

MASTER_SEED = 20260621

mpl.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 11,
    "axes.labelsize": 11,
    "legend.fontsize": 9.5,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "axes.linewidth": 0.8,
    "lines.linewidth": 1.2,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})


def load_clusters_nfp_neg():
    """Riusa la pipeline del pacchetto 07 per ottenere i cluster NFP/neg."""
    print("  Caricamento intraday + assemblaggio cluster NFP/neg ...")
    events = data07.load_events(EVENTS_CSV)
    # Forzo l'INTRADAY_DIR del config 07 perché i CSV sono fuori dalla repo
    cfg07.INTRADAY_DIR = INTRADAY
    prices = run07.load_prices()
    regs = run07.compute_regimes(prices)
    cont = set()
    with open(CONT_CSV) as f:
        for r in csv.DictReader(f):
            cont.add(pd.Timestamp(r["center_utc"]))
    ev_centers = set(pd.to_datetime(events["timestamp"], utc=True))
    reject = run07.build_calendar_reject(ev_centers, cont)
    per_type, _ = run07.assemble(events, prices, regs, reject)
    per_type, _ = win07.dedup_shared_controls(per_type)
    return per_type["NFP"]["neg"]


def extract_returns(clusters):
    """Estrae (r_e_event, r_b_event) e (r_e_ctrl, r_b_ctrl) come array piatti."""
    re_e, rb_e, re_c, rb_c = [], [], [], []
    for cl in clusters:
        ev = cl["event"]
        if ev.get("r_e") is None or ev.get("r_b") is None:
            continue
        re_e.append(float(ev["r_e"]))
        rb_e.append(float(ev["r_b"]))
        for ct in cl.get("controls", []):
            if ct.get("r_e") is not None and ct.get("r_b") is not None:
                re_c.append(float(ct["r_e"]))
                rb_c.append(float(ct["r_b"]))
    return (np.array(re_e), np.array(rb_e), np.array(re_c), np.array(rb_c))


def confidence_ellipse(x, y, ax, n_std=1.96, **kwargs):
    """Ellissi di covarianza al livello n_std (default 95%) dalle (x, y)."""
    if x.size < 3 or y.size < 3:
        return None
    cov = np.cov(x, y, ddof=1)
    # Eigendecomposizione: assi principali
    vals, vecs = np.linalg.eigh(cov)
    # Ordinamento decrescente
    idx = vals.argsort()[::-1]
    vals = vals[idx]; vecs = vecs[:, idx]
    angle = np.degrees(np.arctan2(vecs[1, 0], vecs[0, 0]))
    width, height = 2 * n_std * np.sqrt(np.maximum(vals, 0))
    ellipse = mpatches.Ellipse(
        xy=(x.mean(), y.mean()), width=width, height=height,
        angle=angle, fill=False, **kwargs)
    ax.add_patch(ellipse)
    return ellipse


def ols_slope(x, y):
    """Pendenza OLS y = a + b·x."""
    cov = np.cov(x, y, ddof=1)
    return cov[0, 1] / cov[0, 0]


def main():
    np.random.seed(MASTER_SEED)
    clusters = load_clusters_nfp_neg()
    print(f"  NFP/neg cluster: n={len(clusters)}")

    re_e, rb_e, re_c, rb_c = extract_returns(clusters)
    print(f"  Eventi:   n_event = {len(re_e)}")
    print(f"  Controlli: n_ctrl = {len(re_c)}")

    # Conversione in bps per leggibilità
    re_e_bps = re_e * 1e4
    rb_e_bps = rb_e * 1e4
    re_c_bps = re_c * 1e4
    rb_c_bps = rb_c * 1e4

    # Pendenze (in scala bps, invariata: b_OLS_e su rendimenti = stessa su bps)
    b_event = ols_slope(rb_e_bps, re_e_bps)
    b_ctrl = ols_slope(rb_c_bps, re_c_bps)
    print(f"  pendenza evento  (b_OLS_e) = {b_event:+.4f}")
    print(f"  pendenza controllo (b_OLS_c) = {b_ctrl:+.4f}")
    print(f"  differenza               = {b_event - b_ctrl:+.4f}")
    # var_e e var_c
    var_e_b = np.var(rb_e_bps, ddof=1)
    var_c_b = np.var(rb_c_bps, ddof=1)
    print(f"  Var(r_b) evento  = {var_e_b:.1f} bps²")
    print(f"  Var(r_b) ctrl    = {var_c_b:.1f} bps²")
    print(f"  rapporto         = {var_e_b/var_c_b:.2f}")

    # Figura
    fig, ax = plt.subplots(figsize=(6.4, 5.0))

    # Punti controllo (vuoti, grigio chiaro)
    ax.scatter(rb_c_bps, re_c_bps, marker="x", s=14,
                color="0.55", linewidths=0.6, alpha=0.55,
                label=f"controlli (n={len(re_c)})", zorder=2)
    # Punti evento (pieni, neri)
    ax.scatter(rb_e_bps, re_e_bps, marker="o", s=20,
                facecolors="black", edgecolors="black", alpha=0.78,
                label=f"eventi NFP/neg (n={len(re_e)})", zorder=3)

    # Linee asse zero
    ax.axhline(0, color="gray", linewidth=0.5, linestyle="-", alpha=0.4, zorder=1)
    ax.axvline(0, color="gray", linewidth=0.5, linestyle="-", alpha=0.4, zorder=1)

    # Rette di regressione
    xmin = min(rb_c_bps.min(), rb_e_bps.min()) * 1.05
    xmax = max(rb_c_bps.max(), rb_e_bps.max()) * 1.05
    xs = np.linspace(xmin, xmax, 100)
    # Retta evento: y = a_e + b_e·x, intercetta su mean(x), mean(y)
    a_e = re_e_bps.mean() - b_event * rb_e_bps.mean()
    a_c = re_c_bps.mean() - b_ctrl * rb_c_bps.mean()
    ax.plot(xs, a_e + b_event * xs, color="black", linestyle="-",
             linewidth=1.7, zorder=5,
             label=fr"retta evento ($b_{{\mathrm{{OLS}},e}}={b_event:+.3f}$)")
    ax.plot(xs, a_c + b_ctrl * xs, color="black", linestyle="--",
             linewidth=1.3, zorder=5, dashes=(6, 3),
             label=fr"retta controllo ($b_{{\mathrm{{OLS}},c}}={b_ctrl:+.3f}$)")

    # Ellissi di covarianza 95% — evento spessa, controllo tratteggiata fitta
    # La dispersione molto piu' grande dell'evento (var 15.4x maggiore) e' la
    # firma dell'identificazione di Rigobon-Sack.
    confidence_ellipse(rb_e_bps, re_e_bps, ax, n_std=1.96,
                        edgecolor="black", linewidth=1.7, linestyle="-",
                        zorder=4)
    confidence_ellipse(rb_c_bps, re_c_bps, ax, n_std=1.96,
                        edgecolor="black", linewidth=1.2, linestyle="--",
                        zorder=4)

    ax.set_xlabel(r"$\Delta r_b$ — rendimento bond, finestra ±15 min (bps)")
    ax.set_ylabel(r"$\Delta r_e$ — rendimento equity, finestra ±15 min (bps)")

    # Limiti scelti per evidenziare la dispersione differenziale.
    # Uso percentili (5-95) della distribuzione evento, con cap per non perdere
    # outlier eventi rilevanti ma evitando "schiacciamento" della nuvola controllo.
    q_e = np.percentile(np.abs(np.concatenate([rb_e_bps, re_e_bps])), 99)
    lim = float(q_e) * 1.08
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_aspect("equal", adjustable="box")
    # Annotazione delle due dispersioni
    ax.annotate(
        f"Var($r_b$) evento = {var_e_b:.0f} bps²\n"
        f"Var($r_b$) controllo = {var_c_b:.0f} bps²\n"
        f"rapporto $\\hat{{r}}$ = {var_e_b/var_c_b:.1f}",
        xy=(0.02, 0.97), xycoords="axes fraction",
        ha="left", va="top",
        fontsize=9.5, color="black",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                   edgecolor="black", linewidth=0.6, alpha=0.95))
    ax.grid(True, which="major", linestyle=":", alpha=0.4, linewidth=0.5)
    ax.set_axisbelow(True)

    leg = ax.legend(loc="lower right", frameon=True, framealpha=0.95,
                     edgecolor="black", fancybox=False,
                     handlelength=2.5, handletextpad=0.55)
    leg.get_frame().set_linewidth(0.6)

    plt.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUT, format="pdf", bbox_inches="tight")
    print(f"  Saved {OUT}")


if __name__ == "__main__":
    main()
