# strategy_qe_steepener/ — Steepener Bund 2–10 sul fattore QE

Deposito autoritativo del backtest dell'unica strategia tradabile che la
tesi consegna (cfr. capitolo «Implicazioni operative»).

## Cosa

Steepener Bund 2–10 sul fattore QE di Altavilla et al. (2019),
**pre-registrato** dalla monotonicità di $\beta_{\text{QE},n}$ stimata
nel modello autoritativo $\text{step1\_ecb\_curve\_symmetry}$
(`results/05_ecb_curve_qe/results.json`). Segno e taglia fissati a
priori, nessuna ottimizzazione sui rendimenti.

## File

- [`PROTOCOL.md`](PROTOCOL.md) — pre-registrazione integrale.
- [`extract_qe_steepener_backtest.py`](extract_qe_steepener_backtest.py)
  — esecutore deterministico, run end-to-end.
- `backtest_full_sample.json` — output sample completo (129 eventi,
  2 scenari di costo).
- `backtest_train_oos.json` — split 86/43, sharpe per variante,
  shrinkage.
- `manifest.json` — provenance: sha256 input/codice/output, seed,
  `config_hash` referenziato del modello, confronto vs Fork B.

## Riproduzione

```bash
cd <root_repo>
python3 results/05_ecb_curve_qe/strategy_qe_steepener/extract_qe_steepener_backtest.py
```

Prerequisiti:
- `data/events/EA-MPD_ECB_Altavilla2019.xlsx`: nel repo.
- `data/external_public/altavilla_TPQE_factors.csv`: estraibile con
  `scripts/extract_altavilla.py` (richiede il file Altavilla nel repo;
  il path attualmente puntato dall'esecutore è
  `/home/francesco/TESI/Dati/external_data/altavilla_TPQE_factors.csv`
  e in versione pubblica va spostato su
  `data/external_public/altavilla_TPQE_factors.csv` — TODO marginale).

Output: 3 JSON nella cartella, deterministici a
`MASTER_SEED=20260621`.

## Numeri osservati (run di deposito)

Costi base (0.2 bp per gamba round-trip):

| Variante | Sharpe annualizzato | IC95 bootstrap | P&L per evento (bp slope) | P&L/anno €100m DV01 |
|---|---:|---|---:|---:|
| Lordo (taglia cont.) | +1.01 | — | +1.49 | €128 700 |
| Netto binario (±1)   | +0.99 | — | +0.83 | €71 600 |
| Netto cont. (z·sign) | +0.84 | [+0.58, +1.15] | +1.10 | €94 900 |

Bootstrap p-value one-sided (netto cont.): $0.0000$.

Split train/OOS (86 vs 43 eventi):

| | Train Sharpe | OOS Sharpe | Shrinkage | Segno preservato |
|---|---:|---:|---:|:-:|
| Lordo cont. | +1.10 | +0.81 | +0.74 | sì |
| Netto binario | +1.13 | +0.71 | +0.63 | sì |
| Netto cont. | +0.95 | +0.58 | +0.61 | sì |

Capienza tipica annualizzata su €100m notional 10Y:
- $\approx$ **€72k netto binario** o **€95k netto continuo** (costi
  base 0.2 bp/leg);
- in scenario stress (0.5 bp/leg): vedi `backtest_full_sample.json`,
  sezione `stress_costs_0p5bp_per_leg`.

## Confronto vs Fork B (sessione esecutore precedente)

| | Fork B | Deposito |
|---|---:|---:|
| Sharpe gross continuous | +1.22 | +1.01 |
| Sharpe net binary | +0.82 | +0.99 |
| Sharpe net continuous | +0.78 | +0.84 |
| IC95 net cont (basso) | +0.47 | +0.58 |
| IC95 net cont (alto) | +1.10 | +1.15 |
| Train net cont | +0.92 | +0.95 |
| OOS net cont | +0.54 | +0.58 |
| Shrinkage | 0.59 | 0.61 |
| Cifra capienza /anno €100m | ≈ €80k net | €72k binario / €95k cont |

Convergenza qualitativa: segno preservato, ordine di magnitudine
identico, shrinkage coerente. Scarti minori attribuibili a differenze
nella rolling z-score (Fork B non specificava la finestra esatta) e
nello scheme di bootstrap. **Il deposito è ora la fonte autoritativa
per la tesi.**

## Caveat dichiarati

1. Il modello T/P/QE di Altavilla 2019 è aggiornato (al momento del
   deposito) al 2025-11. Uso in produzione richiede replica e
   aggiornamento periodico della rotazione fattoriale.
2. Il backtest non include butterfly 5-10-30 (alpha gross presente ma
   azzerato dai 4 leg di slippage); estensione meritevole solo su
   asset swap o forward starting swap, fuori scope.
3. Il sample è di 129 eventi, $\approx 8.6$/anno. Estensioni a BTP/OAT/
   Bonos o a curve in USD richiedono pre-registrazione separata.
4. Path: il modello $\beta_{\text{QE},n}$ è stimato sui residui
   orthogonalizzati Path; uno steepener analogo sul fattore Path
   meriterebbe deposito separato (fuori scope).
