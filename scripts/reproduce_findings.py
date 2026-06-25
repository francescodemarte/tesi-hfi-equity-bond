"""reproduce_findings.py — Smoke-reproduction dei 4 findings principali.

Verifica che il repo è funzionante. Per i numeri esatti dei findings serve
accesso ai dati intraday Refinitiv (non ridistribuibili). Questo script:

1. Verifica integrità dei dati in-repo via sha256 (data_manifest.json).
2. Esegue le 462 unit-test dei 7 pacchetti.
3. Stampa il riassunto findings dalla cache `09_risultati/`.
4. NON riesegue la pipeline sui dati reali (richiederebbe Refinitiv intraday).

Per riproduzione completa: vedi README.md "Riproduzione findings principali".
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def header(s):
    print(f"\n{'=' * 70}\n  {s}\n{'=' * 70}")


def main() -> int:
    header("Step 1 — Verifica integrità dati in-repo")
    rc = subprocess.run([sys.executable, "scripts/verify_data_integrity.py"],
                          cwd=ROOT)
    if rc.returncode != 0:
        print("  ⚠ Verifica integrità ha anomalie; controllare data_manifest.json")

    header("Step 2 — Test suite (462 test)")
    rc = subprocess.run(["bash", "scripts/run_all_tests.sh"], cwd=ROOT)

    header("Step 3 — Riassunto findings da cache 09_risultati/")
    # Finding 1: 4 celle robuste del 12
    p12 = ROOT / "results/02_decomposition/baseline/decomp_canali.report.json"
    if p12.exists():
        d = json.loads(p12.read_text())
        print("\n  [Finding 1] Pacchetto 12 — celle robuste:")
        for row in d.get("table_section_6_per_cell", []):
            if row.get("verdict") == "identified_robust":
                print(f"    {row['cell']:20s}  n={row.get('n', 'n/a'):>4}  "
                       f"β_str={row.get('beta_str_central', 'n/a'):+.4f}  "
                       f"F={row.get('F_MOP', 'n/a'):.2f}")

    # Finding 2: ECB curva Altavilla
    p_step1 = ROOT / "results/05_ecb_curve_qe/results.json"
    if p_step1.exists():
        d = json.loads(p_step1.read_text())
        step1 = d.get("results", {}).get("step1_ecb_curve_symmetry", {})
        if step1:
            print(f"\n  [Finding 2] ECB curva Bund 3M-30Y vs T/P/QE:")
            print(f"    n eventi post-2010 con T/P/QE pieno: {step1.get('n_events')}")
            print(f"    BY rejected: {step1.get('n_qe_significant_BY')}/15 scadenze")
            print(f"    QE alive at scadenze: {[a[0] for a in step1.get('qe_alive', [])]}")

    # Finding 3: terzo canale
    p13 = ROOT / "results/03_third_channel/intraday_L/all_with_intraday_L/verdicts.json"
    if p13.exists():
        d = json.loads(p13.read_text())
        print(f"\n  [Finding 3] Terzo canale residuo (proxy intraday onesti, q=0.10):")
        print(f"    third_channel=True: {d.get('n_third_channel_True')}/12")
        print(f"    pairs che passano: {d.get('passing_pairs', [])}")

    # Finding 4: strategia event-driven (CAVEAT: numeri esplorativi con filtri ex-post,
    # vedere docs/04_findings.md per la lettura onesta allineata alla tesi)
    p14 = ROOT / "results/04_event_driven/concentrated/results_tests.json"
    if p14.exists():
        d = json.loads(p14.read_text())
        ann = d.get("annualized_oos", {})
        if "Portfolio" in ann:
            p = ann["Portfolio"]
            print(f"\n  [Finding 4] Strategia event-driven (Portafoglio NFP+ECB, OOS):")
            print(f"    n eventi OOS: {d.get('bootstrap_baseline_q75', {}).get('Portfolio', {}).get('oos', {}).get('n', 'n/a')}")
            print(f"    Sharpe per-evento OOS: {p.get('sharpe_oos_per_event', 'n/a'):+.4f}")
            print(f"    Sharpe annualizzato OOS: {p.get('sharpe_oos_annualized', 'n/a'):+.4f}")

    header("Fine — Vedi docs/04_findings.md per il dettaglio completo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
