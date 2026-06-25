# Strategie event-driven (CPI, NFP, FOMC) + portafoglio combinato

Pre-registrazione di 4 strategie sulla base dei findings del protocollo:
- **CPI direzionale** (β_str=+0.95, regime neg)
- **NFP** (β_str=-1.40, regime neg)
- **FOMC** (β_str=+0.87, regime neg, sottocampione ≤ 2024-01-31)
- **Portafoglio combinato** (pesi pre-dichiarati: `equal` default o `inverse_vol_on_training`)

## Stato

**35/35 test verdi**. Sharpe ai **due orizzonti riportati ENTRAMBI**
(event_window=±15min, end_of_day) — nessuna selezione del migliore.

## Disciplina anti-overfitting (spec)

- Tutti i parametri (β_str, regime ammesso, orizzonti, pesi) sono **fissati a
  priori** in `config.py` e non variano coi rendimenti.
- Regime classifier: corr 63gg con lag t-1 (anti-look-ahead).
- Sottocampione FOMC: ≤ 2024-01-31 (limite serie Jarociński-Karadi).
- Sharpe **LORDO** di costi di transazione (esplicito).
- `portfolio.compute_weights` SOLLEVA su schemi tipo "maximize_sharpe".
- `run_strategies.main()` bloccato; esecuzione reale è di un altro anello.

## Moduli

| File | Ruolo |
|---|---|
| `config.py` | β_str, regime, orizzonti, sottocampione FOMC, schemi pesi pre-dichiarati |
| `strategy_rule.py` | Attivazione per regime, verso momentum, sizing = \|β_str\| |
| `payoff.py` | Payoff per evento ai due orizzonti |
| `portfolio.py` | Pesi a priori (equal / inverse_vol_on_training) + combinazione |
| `metrics.py` | Sharpe per orizzonte con tolleranza IEEE su std |
| `run_strategies.py` | Orchestratore `run_all(...)` — main bloccato |
| `manifest.py` | Provenance con sharpe_table, seed.value, replicability note |

## Output richiesti (per esecutore)

Per ciascuna strategia e per il portafoglio:
- Sharpe ai due orizzonti
- n eventi attivi
- periodo coperto (date min..max)
- serie dei payoff per evento (`per_strategy[*]["payoffs"][horizon]`)

Manifest: `manifest.build_manifest(run_output, input_paths, code_paths,
seed_name, timestamp)` con timestamp ESTERNO.
