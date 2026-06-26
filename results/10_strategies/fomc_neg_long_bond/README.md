# FOMC/neg long bond — secondo segnale direzionale della tesi

Strategia direzionale event-only sulla Federal Reserve, condizionata al regime di correlazione equity-bond negativa, dimensionata da β_str=0.875.

## Riproduzione

```bash
cd <repo_root>
python3 results/10_strategies/fomc_neg_long_bond/extract_fomc_backtest.py
```

Dipendenze: numpy, pandas. Dati intraday Refinitiv proprietari (TYc1_1min.csv) NON ridistribuiti — un lettore senza accesso a Refinitiv non può riprodurre il backtest da zero.

## Output

| File | Cosa contiene |
|---|---|
| `backtest_full_sample.json` | Sharpe full sample, IC95 bootstrap, P&L per evento |
| `backtest_within_regime_kfold.json` | K-fold k=5 stratified by year, **5 fold individuali** |
| `backtest_cross_regime.json` | Sharpe pre-2022 vs post-2022, p-value one-sided |
| `backtest_cross_celle.json` | Test con β_sister NFP |
| `manifest.json` | Provenance (sha256 inputs/code/outputs), seed, validazione vs Fork P |

## Test

```bash
cd results/10_strategies/fomc_neg_long_bond/
python3 -m pytest tests/ -v
```

3 test: determinismo seed, formula P&L, coerenza segno.

## Specifica sintetica

| Parametro | Valore |
|---|---|
| Universo | 105 eventi FOMC sotto regime corr eb negativo, 2010-2025 |
| Segno | +1 (long bond), pre-registrato dal regime |
| Taglia | |β_str|=0.8748 dal Capitolo 6 |
| Strumento | future Treasury 10Y (TYc1) |
| Finestra | T-1 close → T close (daily) |
| Costi | 0.3 bp round-trip |

Vedi `PROTOCOL.md` per pre-registrazione integrale e razionale.
