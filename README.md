# High-Frequency Identification of Equity-Bond Comovement

> Tesi di laurea magistrale, Bocconi University. Autore: Francesco De Marte.
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
| 4 | **Strategia event-driven OOS Sharpe ≈ +1.4 annualizzato lordo** | POSITIVO replicabile | 14+15 | portafoglio NFP/neg + ECB QE→SHORT DE30Y, inverse-vol weighting, p_boot < 0.001 |

---

## Architettura della pipeline

Catena di custodia 7 pacchetti, ciascuno con suite di test pre-registrata.

| Pacchetto | Ruolo | Tests |
|---|---|---:|
| `CODICI_TESI/07_protocollo_v2_signflip/` | Protocollo v2 sign-flip (T1-T9, BY q=0.10 m=3) | 175 |
| `CODICI_TESI/08_spillover_fed_eu/` | Spillover Fed → area euro (H1-H4) | 68 |
| `CODICI_TESI/10_diagnostica_canale_tassi/` | Diagnostica canale tassi (term-structure + cancello doppio) | 45 |
| `CODICI_TESI/11_pratica_eccesso_comovimento/` | Strategia eccesso di comovimento (training/test split 2010-2020/2021-2025) | 51 |
| `CODICI_TESI/12_decomposizione_canali/` | Decomposizione canali (β_str con doppio cancello F-MOP + shrink) | 46 |
| `CODICI_TESI/13_terzo_canale_residuo/` | Terzo canale residuo (L, V, C con BY q=0.10 m=12) | 40 |
| `CODICI_TESI/14_strategie_event_driven/` | Strategie event-driven (CPI/NFP/FOMC + portafoglio) | 37 |
| **TOTALE** | | **462** |

---

## Come riprodurre

### 1. Installa (3 minuti)

```bash
git clone https://github.com/francescodemarte/tesi-hfi-equity-bond.git
cd tesi-hfi-equity-bond
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
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
2. Estrai i RIC elencati in `docs/data_metodologia.md` §1 sul periodo 2010-01-03 → 2025-12-31
3. Salva i CSV minuziali in `data_processed/` (formato: `Datetime_UTC,PX_LAST,Bid,Ask,Spread,Volume`)
4. Verifica sha256: `python scripts/verify_data_integrity.py`

In assenza di Refinitiv intraday: i fixture sintetici dei test (`tests/conftest.py`
di ciascun pacchetto) replicano le proprietà statistiche per smoke-test della
pipeline, ma non producono i numeri esatti dei findings.

### 5. Riproduzione findings principali (5 minuti)

```bash
python3 scripts/reproduce_findings.py
```

Output `09_risultati/reproduction_<timestamp>/` con i 4 findings principali:

- Finding 1: 4 celle del 12 (NFP/neg `identified_robust` confermato)
- Finding 2: curva ECB DE3M→DE30Y vs T/P/QE (Bonferroni-Yekutieli)
- Finding 3: terzo canale residuo (0/12 a q=0.10)
- Finding 4: strategia event-driven OOS Sharpe (bootstrap B=10 000)

Tutti gli output si confrontano via sha256 con `09_risultati/<package>/results.json`
del run autoritativo del 2026-06-22 → 2026-06-25 (manifest documentato).

---

## Documentazione

- `docs/data_metodologia.md` — Dati, serie, sorgenti, costruzione finestre,
  componente di tasso, celle. **Capitolo "Dati e Metodologia" della tesi.**
- `docs/architecture.md` — Architettura della catena di custodia 7 pacchetti.
- `docs/results_summary.md` — Sintesi dei 4 findings con numeri.
- `docs/reproducibility.md` — Come riprodurre dato per dato.

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
  note   = {Companion code per tesi di laurea magistrale, Bocconi University}
}
```

---

## Contatti

Francesco De Marte — Bocconi University. Per domande sulla pipeline o per
accesso ai dati intraday tramite WRDS/Refinitiv: apri una Issue sul repo.

Catena di custodia + protocollo di pre-registrazione descritti in
`docs/data_metodologia.md`.
