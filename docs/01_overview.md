# 01 — Overview

> Panoramica della pipeline. Per la mappa dettagliata della catena di custodia
> vedere `03_architecture.md`; per i numeri vedere `04_findings.md`; per la
> riproduzione `05_reproducibility.md`.

## Domanda della tesi

> Su scala intraday, i movimenti di azioni e obbligazioni durante gli annunci
> macroeconomici e di politica monetaria riflettono un fattore di sconto
> comune coerente con un modello di present value, oppure mostrano una
> co-reazione eccessiva non spiegabile dal solo canale dei tassi di interesse?

## Approccio in due stadi

**Stadio 1** — identificazione strutturale del comovimento equity-bond per
cella (tipo annuncio × regime di correlazione) sotto disciplina di
pre-registrazione: stimatore di Rigobon-Sack a due regimi (evento vs
controllo), Anderson-Rubin per inferenza, gerarchia BY per molteplicità.

**Stadio 2** — decomposizione canali (β_str sui rendimenti netti dal canale
tasso) e test di un terzo canale residuo (liquidità, volatilità,
correlazione attesa). Verifica out-of-sample della predicibilità tramite
strategie event-driven.

## Cosa la pipeline produce

1. **Identificazione strutturale per cella**: 4 celle robuste su 10
   (NFP/neg, CPI/neg, FOMC/neg, CPI/pos) con beta_str_central nel range
   [-1.40, +2.24] a ±15 min, doppio cancello F-MOP + shrink.

2. **Curva di trasmissione ECB QE**: monotonica lungo la curva Bund
   3M→30Y, con β_QE che cresce da +0.40 (DE2Y) a +1.07 (DE30Y); 12/15
   scadenze BY-rejected a q=0.10.

3. **Verdetto su terzo canale residuo**: nessuna cella su 12 sopravvive a
   q=0.10 pre-registrato sotto la sign rule rivista "antisymmetric"
   (risoluzione della patologia §2/§3).

4. **Verifica predittiva OOS**: la strategia event-driven costruita sui
   findings strutturali **non genera Sharpe statisticamente significativo**
   senza ex-post filter selection. Identificazione non implica
   predicibilità (finding negativo onesto).

## Differenza tra i due stimatori β nella repo

La pipeline produce **due stime distinte di β** per le stesse celle:

| stimatore | pacchetto | dati su cui opera | misura |
|---|---|---|---|
| **β_H** (Rigobon-Sack) | `protocol_v2` (07) | rendimenti grezzi | comovimento **totale** equity-bond |
| **β_str** (strutturale) | `decomposition` (12) | rendimenti netti dal canale tasso | comovimento **strutturale** (post-decomposizione) |

I due valori sono **diversi per costruzione** e misurano cose diverse. La
tesi riporta β_str come finding identificativo principale; β_H è documentato
come oggetto separato (file `results/01_protocol_v2/beta_H_robust_cells_w15.json`).

Valori a ±15 min, run autoritativi:

| cella | β_H (grezzi) | β_str (netti) |
|---|---:|---:|
| NFP/neg | −0.808 | **−1.404** |
| CPI/neg | +1.163 | **+0.951** |
| FOMC/neg | +0.926 | **+0.875** |
| CPI/pos | +1.899 | **+2.240** |

Il fatto che β_str ≠ β_H è esattamente il segnale che la decomposizione
canale tasso non è banale: la sottrazione del termine `-D·Δy` cambia la
covarianza e la varianza in modo non proporzionale, producendo uno
stimatore strutturale distinto.

## Disciplina della catena di custodia

Ogni run produce un manifest JSON con `config_hash` (sha256 dei parametri
pre-registrati), `seed.value`, `timestamp` esterno (no clock interno),
sha256 di ogni input e di ogni modulo di codice eseguito. I parametri sono
congelati nei `config.py` di ciascun pacchetto.

Esempi di manifest:
- `results/01_protocol_v2/manifest_authoritative.json`
- `results/02_decomposition/baseline/decomp_canali.manifest.json`
- `results/04_event_driven/manifest.json`

## Cosa NON è in questo repo

- **Dati intraday Refinitiv Tick History** (RIC ESc1, TYc1, FGBLc1, STXE,
  FFc1-3, FEIc1-4): non ridistribuibili. Riproduzione tramite proprio
  accesso WRDS o Refinitiv. `data/intraday/.gitkeep` documenta il setup.
- **Consensus surprise NFP**: dataset non disponibile pubblicamente.
  Fallback dichiarato: m_e PC1 money-market dal CSV eventi.

Tutto il resto (FRED, Altavilla EA-MPD, Jarocinski-Karadi MP surprises,
calendari di contaminanti) è ridistribuibile o ricostruibile via
`scripts/setup_data.sh`.
