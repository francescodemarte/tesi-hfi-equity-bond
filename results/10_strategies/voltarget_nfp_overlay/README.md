# Vol-target NFP overlay — risk-management derivative

Sovrapposto di gestione del rischio NFP-only, **prodotto derivato** del finding intraday r̂=15.4 della tesi. NON è un finding nativo: trasferimento cross-orizzonte intraday→daily, giustificato dal Check 1 del bridge che passa solo per NFP/neg.

## Riproduzione

```bash
cd <repo_root>
python3 results/10_strategies/voltarget_nfp_overlay/extract_voltarget_backtest.py
```

Dipendenze: numpy, pandas. Dati Refinitiv proprietari (TYc1, ESc1) NON ridistribuiti.

## Output

| File | Cosa contiene |
|---|---|
| `backtest_combined.json` | Tutte e 4 strategie A/B/C/D, full/train/OOS, riduzioni VaR |
| `backtest_baseline_long_bond.json` | Sola baseline A (per documentazione) |
| `backtest_baseline_60_40.json` | Sola baseline C (per documentazione) |
| `manifest.json` | Provenance + validazione vs Fork Q |

## Test

```bash
cd results/10_strategies/voltarget_nfp_overlay/
python3 -m pytest tests/ -v
```

3 test: determinismo seed, formula size factor, coerenza filtro NFP-only.

## Numeri chiave (osservati nel run di deposito)

| Strategia | VaR99 NFP-day full | Riduzione | Sharpe full |
|---|---:|---:|---:|
| A baseline long-bond | 0.915% | — | +0.01 |
| B vol-target bond NFP-only | 0.236% | **−74%** | +0.02 |
| C 60/40 baseline | 1.629% | — | +0.68 |
| D 60/40 + overlay | 0.418% | **−74%** | +0.69 |

Vedi `PROTOCOL.md` per pre-registrazione integrale, motivazione strutturale, caveat onesti, cliente target.

## Distinzione dalla tesi

| | Finding tesi (Cap. 6) | Questa strategia |
|---|---|---|
| Orizzonte | intraday ±15 min | daily close-to-close |
| Cosa misura | identificazione strutturale (β_str, β_H, r̂) | gestione rischio overnight |
| Generalizzabile cross-cella | sì (4 celle robuste) | **NO** (solo NFP — Check 1 passa solo lì) |
| Status | finding scientifico | applicazione derivata |
