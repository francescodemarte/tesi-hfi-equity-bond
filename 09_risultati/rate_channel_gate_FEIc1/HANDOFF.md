# HANDOFF — Cancello canale tassi (FEIc1), partizione degenerata

> Run gemello del run FFc2 (vedi `09_risultati/rate_channel_gate/HANDOFF.md`)
> con contratto cambiato per richiesta del ricercatore. Esito tecnico identico.

## Sintesi

Eseguito `gate.run_gate` con `contract = "FEIc1"`, finestra ±15 min,
partizione `median`, soglie a priori. La dicotomizzazione **collassa** sui
dati reali con lo stesso meccanismo del run FFc2:

- intensità `|Δ FEIc1|` su 686 eventi validi: **median = 0**, 426/686 (62.1%)
  pari a 0; massimo 0.13875.
- `D.dichotomize("median")` etichetta `x >= median` → tutti gli 686 eventi
  ricadono in `high`. Celle `(positivo, low)` e `(negativo, low)` vuote.

Frequenze degli zeri e copertura per leg (su `events_df` totale 842):

| leg | n eventi totali | NaN intensity | n valid | zeros | % zeros | median | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| CPI | 187 | 32 | 155 | 113 | 72.9% | 0 | 0.020 |
| ECB | 281 | 22 | 259 | 121 | 46.7% | **0.0025** | 0.139 |
| FOMC | 187 | 64 | 123 | 84 | 68.3% | 0 | 0.025 |
| NFP | 187 | 38 | 149 | 108 | 72.5% | 0 | 0.030 |

**Osservazione fattuale (non interpretazione)**: ECB è l'unica leg con mediana
strettamente positiva su FEIc1. Cioè se il cancello fosse ristretto al sotto-
sample ECB, la dicotomizzazione `median` non sarebbe degenere; sugli altri
tre leg sì. Non è una decisione esecutore — è un fatto del dato.

## Differenza vs FFc2

- Copertura più bassa (686/842 = 81.5% vs 832/842 = 98.8%): FEIc1 ha trading
  hours ridotti rispetto a FFc2, e in particolare 64/187 FOMC cadono fuori
  dalla finestra utile (gli FOMC arrivano alle 18:00–20:00 UTC, parte oltre la
  chiusura europea).
- ECB ha la copertura migliore (259/281 = 92.2%) — coerente col fatto che FEIc1
  è il front Euribor 3M.
- Mediana di `|Δ FEIc1|` sul leg ECB = 0.0025 > 0 → ECB sarebbe alimentabile
  con FEIc1 come contratto-tasso strutturalmente coerente.

## Impatto sui verdetti

Letterali dal kernel — **identici al run FFc2**:

| Criterio | Verdetto | Lettura |
|---|---|---|
| (a) η² ≤ 0.20 | **True** | overall 0.0026, by_leg max 0.084 (CPI). Numero corretto ma su fattore degenere. |
| (b) `|κ_aligned|` ≤ 0.20 | **True** | `κ_overall = 0` per costruzione. by_leg NaN per tutti (≤1 categoria intensity). |
| (c) tutte le celle ≥ 30 | **True** (artefatto) | counts: (negativo,high)=525, (positivo,high)=161. Le celle `*|low` non esistono e non sono testate. |
| (d) `|cos|` < 0.95 in entrambe le fette | **None** | `status = missing_cells`. |

## Cosa NON è stato fatto (presidio)

- Nessun cambio di soglia, modalità partizione, sample, o contratto
  *all'interno* di questo run.
- Nessun verdetto interpretato come "indipendenza" o "confusione".
- L'unico cambio rispetto al run FFc2 è il contratto (richiesta esplicita
  ricercatore); tutto il resto è invariato per costruzione (config_hash
  identico — vedi `manifest.json`).

## Cosa potrebbe scegliere il ricercatore/coder (non azioni esecutore)

Le stesse opzioni del run FFc2, ora con un'osservazione utile in più:

1. Cancello **per-leg** invece che overall: per ECB la mediana FEIc1 è > 0 e
   la partizione `median` non degenera; il by-leg ECB potrebbe essere
   l'unico ambiente in cui i 4 criteri sono *tutti* effettivamente valutabili.
   Pre-registrazione: dichiarare a priori che per i leg USA si usa un altro
   contratto (FFc2/FFc3) e per ECB si usa FEIc1.
2. **Dicotomizzazione robusta agli zeri**: p.es. `x > 0` vs `x = 0` come
   prima binaria (movimento sì / no). Già suggerito nel run FFc2.
3. **Restringere il sample** ai soli eventi con `|Δ| > 0`. Sul totale FEIc1:
   260/686 (37.9%); su ECB sotto FEIc1: 138/259 (53.3%). Numeri bassi ma >>
   `min_cell = 30` per ECB.
4. **Cambiare il kernel** del cancello (decisione di chi mantiene il
   package 10): rendere `cells_below_threshold` consapevole delle "celle
   attese ma vuote" e propagare un verdetto (c) coerente.

Nessuna eseguita qui.

## File consegnati

- `verdicts.json` — verdetto letterale del kernel
- `numbers.json` — η², κ, conteggi, vettori, momenti delle celle calcolate
- `manifest.json` — provenance (sha256 input incl. FEIc1, config_hash, soglie, seed)
- `report.md` — report con alert in cima
- `HANDOFF.md` — questo file
- `execute_gate.py` — script esecutore con contract = "FEIc1"

## Provenance

- contratto: `FEIc1` (2 066 392 ticks, span 2010-01-04 → 2025-12-31)
- partition_mode: `median` (mediana = 0)
- seed: `gate_run_2026-06-22` (master 20260622)
- pickle accounting letto: `09_risultati/v2_signflip/result_authoritative.pkl`
  (sha256 `a9c13a7b…`, label `v2_signflip_run_authoritative_2026-06-22_post_bug2`)
- intraday: `Datetime_UTC` UTC; ES/TY/FGBL → `PX_LAST`, STXE → `Mid_raw`
- n eventi totali: 842 — con intensità valida: 686 — con r_e/r_b validi: vedi manifest
