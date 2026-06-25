# data/ — Dataset

> Dati strutturati in 3 categorie per provenance e licenza.

## Struttura

| Cartella | Contenuto | Licenza | Ridistribuibile |
|---|---|---|:---:|
| `events/` | Calendario eventi NFP/CPI/FOMC/ECB con regime classifier + EA-MPD xlsx | MIT (CSV autore), Academic (Altavilla) | ✓ |
| `external_public/` | FRED snapshots (TEDRATE, DGS2/5/10/30, VIXCLS, etc.), TPQE estratti | FRED public domain, Altavilla academic | ✓ via `setup_data.sh` |
| `intraday/` | Refinitiv Tick History 1-min CSVs | Refinitiv proprietary | ✗ user subscription only |

## Setup automatico

```bash
bash scripts/setup_data.sh
python3 scripts/verify_data_integrity.py
```

Scarica FRED + estrae Altavilla TPQE in `external_public/`. Verifica sha256
contro `data_manifest.json`.

## Jarocinski-Karadi: download manuale

Il file `external_public/jk_surprises_fomc.csv` va scaricato manualmente dal
replication package ECB WP2030 (Jarocinski-Karadi 2020 AEJ:Macro). Vedi
`scripts/setup_data.sh` per istruzioni dettagliate.

## Refinitiv intraday: riproduzione separata

I CSV 1-min Refinitiv NON sono ridistribuibili. Per riprodurre:

1. Ottieni accesso WRDS o Refinitiv Tick History via tua istituzione.
2. Estrai i RIC elencati in `docs/02_data_methodology.md` §1 sul periodo
   2010-01-03 → 2025-12-31.
3. Salva i CSV in `data/intraday/` col formato
   `Datetime_UTC,PX_LAST,Bid,Ask,Spread,Volume`.
4. Verifica con `python3 scripts/verify_data_integrity.py`.

I sha256 attesi sono in `data_manifest.json` campo
`data_processed_refinitiv_proprietary[*].sha256_expected`.
