---
title: "Mini-run §4 — Test di coda con curva fino a 30Y"
data: 2026-06-23
stato: superato_con_cauzione
n_eventi: 10 (effettivo 9 per pre-check su m_e)
---

# Test di coda §4: superato con cauzione

## Verdetto

Il pre-check di Nagel-Xu sul long-end della curva, con `m_e` come sorpresa
monetaria, **passa a tutte le scadenze osservate (2Y, 5Y, 10Y, 30Y)**.
`Δf` al bordo 30Y **non risulta significativamente correlato con la sorpresa
di policy**: la curva fino a 30Y scioglie il muro di coda per il canale
tassi, sotto la sorpresa pre-registrata.

| Scadenza | slope (Δy ~ m_e) | t | p | Status |
|---|---|---|---|---|
| 2Y (TUc1) | 0.017 | 0.95 | 0.38 | PASS |
| 5Y (FVc1) | 0.016 | 0.86 | 0.42 | PASS |
| 10Y (TYc1) | 0.014 | 0.91 | 0.40 | PASS |
| **30Y (USc1)** | **0.010** | **0.87** | **0.41** | **PASS** |

α pre-registrato = 0.05 (`config.TAIL_BORDER_SIGNIFICANCE_ALPHA`).

## Cauzione esplicita sulla potenza

Il PASS è onesto ma non solidamente robusto. Tre fonti di bassa potenza:

1. **n = 9 effettivo**: 10 eventi nel sample, di cui 1 escluso dal pre-check
   per dr1 mancante (CPI 2026-04-10).
2. **Range m_e ristretto nel sample**: [-0.555, +0.767], sd ≈ 0.4.
   Sostanzialmente eventi 2025-11 → 2026-05, regime corrente con sorprese
   contenute. Il test ha bassa varianza nel regressore.
3. **m_e ibrido**: canonico dal file storico per i 2 eventi 2025-11
   (presenti in `events_with_regime_classifier.csv`), ricostruito via
   PCA z-score per gli 8 eventi 2026 (non presenti in file). La PCA
   replica m_e canonico con corr = 0.997 sui 525 eventi US storici.

Quindi il PASS è **compatibile** con "Δf muore al 30Y per il canale m_e"
ma non lo dimostra in modo conclusivo: è anche compatibile con "il
segnale c'è ma sotto soglia per n = 9 e sd(m_e) basso".

## Implicazione operativa

Il "ripiego documentato" della §6 della spec (riconoscere la coda residua
come limite invalicabile, perché ~metà del peso ρ resta su orizzonti > 30Y)
**non si attiva**. La forma 2 del run di correzione mantiene la sua logica:
con curva fino a 30Y la decomposizione del canale tassi sull'equity ha la
sua copertura empirica accettabile per il test di significatività attuale.

Niente claim oltre: che lo *slope* sia formalmente sotto soglia non vuol
dire che sia *zero*, e il sample 2025-11 → 2026-05 non garantisce
generalizzazione al 2010-2024.

## Test alternativo con surprise = Δy_2Y

Come controllo metodologico ho ripetuto il pre-check usando come surprise
non `m_e` ma il proxy intra-curva `Δy_TUc1` (2Y future yield change). In
quel caso il pre-check fallisce a tutte le scadenze:

| Scadenza | slope (Δy ~ Δy_2Y) | t | p | Status |
|---|---|---|---|---|
| 5Y | 1.01 | 30.1 | 0.000 | WARN |
| 10Y | 0.86 | 22.6 | 0.000 | WARN |
| 30Y | 0.63 | 15.2 | 0.000 | WARN |

Ma questo test è **tautologico**: misura solo la propagazione intra-curva
(quanto un movimento al 2Y "trascina" il long end), non la risposta a una
sorpresa esogena. Il WARN così letto non è il pre-check di Nagel-Xu — è
un test diverso. Per coerenza con la specifica §3.3 (Nagel-Xu Tab A.1) il
verdetto autorevole è quello su `m_e`: PASS.

## Sample

10 eventi a copertura piena dei futures Treasury continuation (TUc1, FVc1,
TYc1, USc1) sulla finestra ±30 min:

- 2025-11-07 NFP
- 2025-11-13 CPI
- 2026-01-09 NFP
- 2026-01-28 FOMC decision (19:00 UTC)
- 2026-02-13 CPI
- 2026-04-03 NFP
- 2026-04-10 CPI (escluso dal pre-check: dr1 NaN)
- 2026-04-29 FOMC decision (18:00 UTC)
- 2026-05-08 NFP
- 2026-05-12 CPI

Esclusi per coverage debole (rollover continuation c1 Mar/Jun): NFP
2026-03-06, CPI 2026-03-11, FOMC 2026-03-18, NFP 2026-06-05, CPI 2026-06-10,
FOMC 2026-06-17, FOMC 2025-12-10 (tutti gli eventi Dic 2025 cadono nel
rollover Dec→Mar dei futures Treasury continuation).

## Dati sottostanti

- `bridge/data/req19_minirun_2026H1.csv` — 6 mesi minute futures, 171k righe
  su 8 RIC (ESc1, TUc1, FVc1, TYc1, USc1, FFc1, FFc2, FFc3)
- `bridge/data/req20_minirun_2025H2.csv` — 2 mesi minute, 56k righe
- `DATASET_TESI/01_eventi_hfi/event_calendar_2026H1_supplement.csv` — calendario
  eventi 2026 H1 (CPI, NFP, FOMC) compilato da BLS / federalreserve.gov

## Limite non sanato di questo test

Il pre-check vero su sample completo (855 eventi 2010-2025) richiede
`Δy long-tail intraday` (TUc1/FVc1/USc1) sul sample storico, che la
TimescaleDB locale **non ha** (contiene solo TYc1, ES, FF, SR, FEI,
FGBL, FESX). Per replicare questo verdetto su sample completo serve
RTTH/DataScope (canale Bocconi/Alessandra Ruzzier). Il presente verdetto
PASS è **su 9 eventi di un singolo regime corrente**; estrazione del
test su sample storico è il next step per consolidare il verdetto.

## Provenienza

- Script: `scratchpad/minirun_section4.py` (run 2026-06-23)
- Codice riusato: `CODICI_TESI/12_decomposizione_canali/gates.py`
  (`tail_border_precheck`)
- α: 0.05 (`config.TAIL_BORDER_SIGNIFICANCE_ALPHA`)
- m_e canonico: `events_with_regime_classifier.csv`
- m_e ricostruito: PCA z-score (sklearn) sui 525 US events storici complete-case
