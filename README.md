# High-Frequency Identification of Equity-Bond Comovement

> Tesi di laurea triennale (BSc), Bocconi University. Autore: Francesco De Marte.
>
> Companion code repository per:
> *High-Frequency Identification (HFI) of Equity-Bond Comovement:
> A Present-Value Test with Operational Extension*

[![Tests](https://img.shields.io/badge/tests-425%20passed-brightgreen)](#testing)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)

---

## Sintesi

Pipeline pre-registrata per identificare a quali annunci macroeconomici e di
politica monetaria il comovimento equity-bond intraday risponde in modo
strutturalmente robusto, distinguendo il sign-flip dello stimatore RS dal
sign-flip strutturale di β e validando i risultati con multipli proxy di
identificazione (canale tasso) e cancelli di forza pre-registrati.

### Quattro findings autenticamente robusti

| # | Finding | Tipo | Pacchetto | Lettura |
|---|---|---|---|---|
| 1 | **NFP/neg — canale strutturale identificato** | POSITIVO robusto | 12 | β_str = −1.40, robusto in 4/6 specifiche del bond piece + finestra ±30 min |
| 2 | **ECB curva Bund 3M→30Y: QE→long-end vivo** | POSITIVO robusto | step 1 (Altavilla) | 12/15 scadenze BY-rejected (q=0.10); β_QE = +1.07 a DE30Y, p≈0 |
| 3 | **Terzo canale residuo (L, V, C) — NON identificato** | NEGATIVO robusto | 13 | 0/12 a q=0.10 pre-registrato, sotto sign rule rivista "antisymmetric" |
| 4 | **Identificazione ≠ predicibilità OOS** | NEGATIVO onesto | 14 | NFP OOS Sharpe +0.21 (p_boot=0.155 non significativo); CPI inverte segno fra training e OOS; la via del rendimento non regge senza selezione ex-post di filtri su pochi eventi. |

---

## Architettura della pipeline

Catena di custodia 7 pacchetti, ciascuno con suite di test pre-registrata.

| Pacchetto | Ruolo | Tests |
|---|---|---:|
| `src/hfi/protocol_v2/` | Protocollo v2 sign-flip (T1-T9, BY q=0.10 m=3) | 175 |
| `src/hfi/spillover_eu/` | Spillover Fed → area euro (H1-H4) | 68 |
| `src/hfi/rate_channel/` | Diagnostica canale tassi (term-structure + cancello doppio) | 45 |
| `src/hfi/strategy_excess/` | Strategia eccesso di comovimento (training/test split 2010-2020/2021-2025) | 51 |
| `src/hfi/decomposition/` | Decomposizione canali (β_str con doppio cancello F-MOP + shrink) | 46 |
| `src/hfi/third_channel/` | Terzo canale residuo (L, V, C con BY q=0.10 m=12) | 40 |
| `src/hfi/event_driven/` | Strategie event-driven (CPI/NFP/FOMC + portafoglio) | 37 |
| **TOTALE** | | **462** |

---

## Come riprodurre

### 1. Installa (3 minuti)

```bash
git clone https://github.com/francescodemarte/tesi-hfi-equity-bond.git
cd tesi-hfi-equity-bond
python3 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
```

### 2. Verifica installazione (1 minuto)

Esegue le 462 unit-test su DGP sintetici (no dati reali necessari):

```bash
bash scripts/run_all_tests.sh
```

Atteso: 462 passed, 0 failed, 0 xfailed.

### 3. Scarica i dati esterni public (2 minuti)

```bash
bash scripts/setup_data.sh
```

Scarica automaticamente: FRED snapshots (TEDRATE, DGS2/5/10/30, VIXCLS),
Altavilla EA-MPD 2019, Jarociński-Karadi MP surprises. Tutti verificati via
sha256 contro `data_manifest.json`.

### 4. Dati Refinitiv intraday (manuale, licenza richiesta)

I tick 1-min di Refinitiv (ESc1, TYc1, FGBLc1, STXE, FFc1-3, FEIc1-4) **non
sono ridistribuiti** per vincoli di licenza Refinitiv Tick History. Per
riprodurre la pipeline completa serve:

1. Accesso WRDS o Refinitiv Tick History via tua istituzione
2. Estrai i RIC elencati in `docs/02_data_methodology.md` §1 sul periodo 2010-01-03 → 2025-12-31
3. Salva i CSV minuziali in `data/intraday/` (formato: `Datetime_UTC,PX_LAST,Bid,Ask,Spread,Volume`)
4. Verifica sha256: `python scripts/verify_data_integrity.py`

In assenza di Refinitiv intraday: i fixture sintetici dei test (`tests/conftest.py`
di ciascun pacchetto) replicano le proprietà statistiche per smoke-test della
pipeline, ma non producono i numeri esatti dei findings.

### 5. Riproduzione findings principali (5 minuti)

```bash
python3 scripts/reproduce_findings.py
```

Output in `results/reproduction_<timestamp>/` con i 4 findings principali:

- Finding 1: 4 celle del pacchetto `decomposition` (NFP/neg `identified_robust`)
- Finding 2: curva ECB DE3M→DE30Y vs T/P/QE (Bonferroni-Yekutieli)
- Finding 3: terzo canale residuo (0/12 a q=0.10)
- Finding 4: strategia event-driven OOS — risultato negativo onesto (vedi
  `docs/04_findings.md`)

Tutti gli output si confrontano via sha256 con `results/0X_*/results.json`
dei run autoritativi (manifest documentato).

---

## Documentazione

- `docs/01_overview.md` — Sintesi della pipeline e del progetto.
- `docs/02_data_methodology.md` — Dati, serie, sorgenti, costruzione finestre,
  componente di tasso, celle. **Capitolo "Dati e Metodologia" della tesi.**
- `docs/03_architecture.md` — Architettura della catena di custodia 7 pacchetti.
- `docs/04_findings.md` — Sintesi dei 4 findings (allineata alla tesi).
- `docs/05_reproducibility.md` — Come riprodurre dato per dato.
- `docs/06_known_limitations.md` — Limiti dichiarati onesti.
- `docs/07_zenodo_deposit_guide.md` — Guida deposit Zenodo con DOI.

---

## Disciplina della catena di custodia

Ogni run produce un **manifest JSON** con: `config_hash` (sha256 dello snapshot
parametri pre-registrati), `seed.value`, `timestamp` esterno (passato all'invocazione,
non clock interno), sha256 di ogni file di input, sha256 di ogni modulo di codice
eseguito. Esempi in `09_risultati/<package>/manifest_*.json`.

I parametri pre-registrati sono congelati nei `config.py` di ciascun pacchetto.
**Cambiare un parametro cambia `config_hash` ⇒ run tracciato come diverso.**

---

## Licenza

Codice rilasciato sotto licenza MIT (vedi `LICENSE`).

I dati derivati nella cartella `DATASET_TESI/` includono:
- `events_with_regime_classifier.csv` — costruito da Francesco De Marte, MIT
- `EA-MPD_ECB_Altavilla2019.xlsx` — Altavilla et al. 2019, JME, replication
  dataset academic-public
- I CSV in `data_external/` scaricati con `scripts/setup_data.sh` sono regolati
  dalle rispettive licenze FRED (public domain), Altavilla (academic), JK (academic).

I dati intraday Refinitiv Tick History **non sono inclusi** nel repo (licenza
Refinitiv vincola la ridistribuzione). Riproduzione tramite tuo accesso Refinitiv.

---

## Citazione

Vedi `CITATION.cff`. Per citare nel tuo lavoro:

```bibtex
@software{demarte2026hfi_equity_bond,
  author = {De Marte, Francesco},
  title  = {High-Frequency Identification of Equity-Bond Comovement:
            A Present-Value Test with Operational Extension (Companion Code)},
  year   = 2026,
  url    = {https://github.com/francescodemarte/tesi-hfi-equity-bond},
  note   = {Companion code per tesi di laurea triennale (BSc), Bocconi University}
}
```

---

## Contatti

Francesco De Marte — Bocconi University. Per domande sulla pipeline o per
accesso ai dati intraday tramite WRDS/Refinitiv: apri una Issue sul repo.

Catena di custodia + protocollo di pre-registrazione descritti in
`docs/data_metodologia.md`.
