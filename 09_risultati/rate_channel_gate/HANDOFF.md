# HANDOFF — Cancello canale tassi, partizione degenerata

> Presidio PROMPT §"Se un numero esce strano (es. tutte le celle in neg), non
> aggiustare: fermati, segnala, rimanda al coder con un handoff."

## Sintesi del problema

Eseguito `gate.run_gate` con i default congelati (contratto **FFc2**, finestra
±15 min, partizione **median**, soglie a priori). Sui dati reali la
dicotomizzazione **collassa**:

- intensità `|Δ FFc2|` su 832 eventi validi: **median = 0**, 565/832 (67.9%)
  pari a 0; massimo 0.11.
- `D.dichotomize("median")` etichetta `x >= median` → tutti gli 832 eventi
  ricadono in `high`. Le celle `(positivo, low)` e `(negativo, low)` sono
  vuote.

Frequenze degli zeri per leg (su eventi con intensità valida):

| leg | n | zeros | % | median |
|---|---:|---:|---:|---:|
| ECB | 275 | 228 | 82.9% | 0 |
| CPI | 186 | 125 | 67.2% | 0 |
| FOMC | 187 | 112 | 59.9% | 0 |
| NFP | 184 | 100 | 54.3% | 0 |

Questo è un fatto del dato: il contratto Fed Funds front-2 raramente si muove
in una finestra di 30 minuti che NON contenga un meeting FOMC; anche dentro
finestre FOMC, ~60% degli eventi non vede movimento perché molte decisioni
sono fully-priced.

## Impatto sui verdetti

I verdetti scritti in `verdicts.json` sono **matematicamente coerenti col
calcolo del kernel**, ma **non interpretabili come "indipendenza fra regime e
intensità tasso"**:

| Criterio | Verdetto | Lettura tecnica del valore |
|---|---|---|
| (a) η² ≤ 0.20 | **True** | basso ma con un fattore degenere; numericamente vero. |
| (b) `|κ_aligned|` ≤ 0.20 | **True** | `κ = 0` per costruzione (una sola categoria nella partizione `intensity`). Non è indipendenza, è degenerazione. |
| (c) tutte le celle ≥ 30 | **True** (artefatto) | `cells_below_threshold` opera solo sulle celle *presenti*. Le due celle `*|low` sono assenti dal counts dict e non vengono testate. |
| (d) `|cos|` < 0.95 in entrambe le fette | **None** | `status = missing_cells` (assenti `(positivo,low)` e `(negativo,low)`). |

## Cosa NON ho fatto (volutamente)

- **Non ho cambiato soglie** per "salvare" il verdetto.
- **Non ho cambiato modalità di partizione** (es. `tertile_extremes`).
- **Non ho cambiato contratto** (es. FFc3, FEIc1..4).
- **Non ho scartato eventi** oltre quelli filtrati dal kernel sui NaN
  (intensity_raw NaN: 10 eventi; r_e/r_b NaN: registrati nel manifest).

Ognuna di queste opzioni è una decisione *del ricercatore/coder*, non
dell'esecutore. Cambiarle ex-post sui risultati attuali violerebbe la
pre-registrazione del cancello.

## Cosa potrebbe scegliere il ricercatore/coder (non azioni esecutore)

1. **Riformulare la dicotomizzazione** in modo che non degeneri quando
   `|Δprice|` ha massa concentrata in 0:
   - p.es. partizione "movimento sì / no" (`x > 0` vs `x = 0`) come prima
     binaria;
   - o `tertile_extremes` con regola di tie-breaking esplicita (la 33% e 67%
     percentili oggi cadrebbero entrambe in 0; il kernel attuale assegnerebbe
     `drop` a quasi tutti);
   - documentando entrambe come *pre-registered* (non scelte ex-post).
2. **Cambiare contratto** se la patologia è specifica di FFc2:
   - FFc3 o FEIc1..c4 (ECB è scientificamente più appropriato per gli annunci
     ECB su FEI).
3. **Restringere il sample**: cancello calcolato solo sugli eventi *con
   movimento* (`|Δprice| > 0`, 267/832). Reintrodurrebbe variabilità a costo
   di n; va dichiarato a monte.
4. **Cambiare il kernel** (decisione di chi mantiene il package 10): rendere
   `cells_below_threshold` aware di "celle attese ma vuote" e propagare un
   verdetto (c) coerente quando una categoria di intensità è assente.

Nessuna di queste è eseguita qui. Si rimanda al coder con questa nota.

## File consegnati

- `verdicts.json` — verdetto letterale del kernel (vedi alert)
- `numbers.json` — η², κ, conteggi, vettori, momenti delle celle calcolate
- `manifest.json` — provenance (sha256 input, config_hash, soglie, seed)
- `report.md` — report dell'esecutore con alert in cima
- `HANDOFF.md` — questo file

## Provenance del run

- contratto: `FFc2` (default), finestra ±15 min, edge mediana 5 min
- partition_mode: `median`
- seed: `gate_run_2026-06-22` (master 20260622)
- config_hash: vedi `manifest.json → config_hash`
- pickle accounting letto: `09_risultati/v2_signflip/result_authoritative.pkl`
  (sha256 in manifest), label `v2_signflip_run_authoritative_2026-06-22_post_bug2`
- intraday: `Datetime_UTC` UTC, file in `/home/francesco/TESI/Dati/data_processed/`
- n eventi totali: 842 — con intensità valida: 832 — con r_e/r_b validi: vedi manifest
