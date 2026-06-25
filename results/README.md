# results/ — Risultati dei run autoritativi

> Tutti i risultati delle pipeline pre-registrate. Organizzati per topic, NON
> per data di esecuzione (i timestamp sono nei manifest dei singoli run).

## Indice

| Cartella | Contenuto principale | Pacchetto sorgente |
|---|---|---|
| `01_protocol_v2/` | Run autoritativo del protocollo v2 sign-flip + estrazioni cella CPI + β_H ricalcolati | `src/hfi/protocol_v2` |
| `02_decomposition/baseline/` | **Run autoritativo del 12** — fonte dei β_str della tesi | `src/hfi/decomposition` |
| `02_decomposition/true_curve_variants/` | Robustezze del 12 con curve Treasury vere (DGS daily, multi-scadenza, intraday-scaled) | `src/hfi/decomposition` |
| `02_decomposition/window_30min/` | Sensitivity del 12 alla finestra (±30 vs ±15 min) | `src/hfi/decomposition` |
| `03_third_channel/` | Verdetti terzo canale residuo (L, V, C) sotto sign rule rivista | `src/hfi/third_channel` |
| `04_event_driven/` | Strategie pre-registrate + esplorazione filtri (caveat) | `src/hfi/event_driven` |
| `05_ecb_curve_qe/` | Test simmetria ECB Bund 3M→30Y con T/P/QE Altavilla | (script `extract_altavilla.py` + analisi) |
| `06_rate_channel_gate_obsolete/` | Run obsoleti del cancello canale tassi (FFc2, FEIc1, movement) — superati dal 12 | `src/hfi/rate_channel` |
| `07_strategy_excess/` | Run del pacchetto 11 (pratica eccesso comovimento) | `src/hfi/strategy_excess` |
| `08_decomposition_daily/` | Decomposizione canali daily (evidenza secondaria) | — |
| `09_spillover_eu/` | Run del pacchetto 08 (spillover Fed → euro area) | `src/hfi/spillover_eu` |

## Provenance dei numeri della tesi

### β_str (capitolo identificazione)
**Fonte autoritativa**: `02_decomposition/baseline/decomp_canali.report.json`,
campo `table_section_6_per_cell[*].beta_str_central`. Timestamp del run:
`2026-06-23T22:21:46Z`, seed_name `decomp_canali_2026-06-23`, config_hash 12
`907eb0ff...`.

| cella | beta_str_central | sampling band 95% |
|---|---:|---|
| NFP/neg | **−1.4036** | [−1.893, −0.888] |
| CPI/neg | **+0.9509** | [+0.514, +1.402] |
| FOMC/neg | **+0.8748** | [+0.337, +1.425] |
| CPI/pos | **+2.2404** | [+1.602, +2.856] |

### β_H (capitolo comovimento totale)
**Fonte**: `01_protocol_v2/beta_H_robust_cells_w15.json`. Ricalcolati con
stimatore RS standard, seed `execute_v2_signflip_2026-06-22`, B=10 000,
window ±15 min.

| cella | β_H | se_bH (boot) |
|---|---:|---:|
| NFP/neg | −0.808 | 0.162 |
| CPI/neg | +1.163 | 0.203 |
| FOMC/neg | +0.926 | 0.202 |
| CPI/pos | +1.899 | 0.227 |

### Curva ECB QE→Bund 3M-30Y (Finding 2)
**Fonte**: `05_ecb_curve_qe/results.json` campo `step1_ecb_curve_symmetry`.
12/15 scadenze BY-rejected a q=0.10, m=15. β_QE da +0.40 (DE2Y) a +1.07
(DE30Y), tutti con p≈0 sotto HC1.

### Terzo canale (Finding 3 negativo)
**Fonte**: `03_third_channel/intraday_L/all_with_intraday_L/verdicts.json`.
0/12 third_channel=True a q=0.10 pre-registrato.

### Strategie event-driven (Finding 4 negativo)
**Fonte**: `04_event_driven/manifest.json` (run pre-registrato) e
`04_event_driven/concentrated/results_tests.json` (esplorazione filtri,
caveat). Sharpe pre-registrato NFP/neg event_window: +0.21 (n=49,
p_boot=0.155 NON significativo).

## Convenzione di lettura

- I file `*.report.json` contengono i numeri pronti per la tesi.
- I file `*.manifest.json` contengono provenance (config_hash, seed,
  sha256 di input/codice/output).
- I file `*.log.txt` o `*.md` contengono note dell'esecutore (umane,
  diagnostiche, non da pubblicare).
- I file `execute_*.py` sono gli script esecutori che hanno prodotto i
  risultati.
- I file `*.pkl` sono pickle Python con strutture dati grezze (cluster
  eventi, momenti per cella) — leggibili via `pickle.load()`.
