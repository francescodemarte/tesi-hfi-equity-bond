# 05 — Riproducibilità

> Procedura per riprodurre i 4 findings principali, in ordine di completezza
> crescente.

## Livello 1 — Smoke test (no dati esterni, 1 minuto)

```bash
git clone https://github.com/francescodemarte/tesi-hfi-equity-bond.git
cd tesi-hfi-equity-bond
python3 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
bash scripts/run_all_tests.sh
```

Atteso: 462 test passed in ~10 secondi (tutti su fixture sintetici / DGP a
verità nota, nessun dato reale richiesto).

## Livello 2 — Lettura dei risultati congelati (2 minuti)

I run autoritativi sono presenti in `results/0X_*/`. Per leggere
direttamente i numeri della tesi:

```bash
python3 scripts/reproduce_findings.py
```

Output: estrae da `results/02_decomposition/baseline/decomp_canali.report.json`
le 4 celle robuste con beta_str_central, F-MOP, shrink, banda di
costruzione, banda campionaria. Estrae da `results/05_ecb_curve_qe/results.json`
i β_QE alle 15 scadenze Bund. Estrae da `results/03_third_channel/intraday_L/`
i verdetti delle 12 cell × candidate. Estrae da `results/04_event_driven/`
i Sharpe out-of-sample.

## Livello 3 — Setup dati pubblici (5 minuti)

```bash
bash scripts/setup_data.sh
python3 scripts/verify_data_integrity.py
```

Scarica automaticamente da FRED: TEDRATE, DGS2, DGS5, DGS10, DGS30, VIXCLS,
DFII5, T10YIE, CPIAUCSL. Estrae da `data/events/EA-MPD_ECB_Altavilla2019.xlsx`
i 3 fogli (Press Release, Press Conference, Monetary Event Window) + i
fattori T/P/QE canonici (rotazione Altavilla 2019).

Per Jarocinski-Karadi: download manuale dal replication package ECB WP2030,
istruzioni dentro `scripts/setup_data.sh`.

Verifica sha256 contro `data_manifest.json` per garantire integrità dei dati
pubblici scaricati.

## Livello 4 — Riesecuzione completa (richiede Refinitiv intraday)

I tick 1-min Refinitiv (ESc1, TYc1, FGBLc1, STXE, FFc1-3, FEIc1-4, SRc1-2)
**non sono ridistribuibili**. Per riprodurre i numeri esatti dei findings
1-4:

1. Ottieni i dati intraday tramite il tuo accesso WRDS o Refinitiv Tick
   History. RIC list e periodo (2010-01-03 → 2025-12-31) in
   `docs/02_data_methodology.md` §1.

2. Salva i CSV in `data/intraday/` col formato:
   `Datetime_UTC, PX_LAST, Bid, Ask, Spread, Volume`.

3. Verifica sha256 attesi (`data_manifest.json` campo
   `data_processed_refinitiv_proprietary[*].sha256_expected`):

```bash
python3 scripts/verify_data_integrity.py
```

Atteso: tutti i file `data/intraday/*.csv` con stato `[OK]`.

4. Esegui i run autoritativi pacchetto per pacchetto, in ordine:

```bash
# Pacchetto 07 — produces result_authoritative.pkl (cluster eventi + test sign-flip)
python3 results/01_protocol_v2/execute.py

# Pacchetto 12 — produces decomp_canali.report.json con i 4 beta_str_central
python3 results/02_decomposition/baseline/execute_12.py

# Pacchetto 13 — terzo canale residuo (0/12 a q=0.10 atteso)
python3 results/03_third_channel/execute_13_proper_surprises.py

# Pacchetto 14 — strategie event-driven
python3 results/04_event_driven/execute_14.py

# Step ECB curva 30Y
python3 results/05_ecb_curve_qe/execute_4steps.py
```

Tutti i seed e config_hash sono dichiarati nei manifest e sono identici tra
i run originali e quelli riprodotti.

## Verifica end-to-end della riproducibilità

Per controllare che i numeri prodotti coincidano coi run autoritativi:

```bash
# Confronta sha256 dei risultati
diff <(python3 -c "import hashlib; print(hashlib.sha256(open('results/02_decomposition/baseline/decomp_canali.report.json','rb').read()).hexdigest())") \
     <(echo "<sha256 atteso dal data_manifest.json>")
```

Differenze attese **solo se** la pipeline è stata modificata (in tal caso il
`config_hash` nei manifest cambierà coerentemente).

## Note importanti

1. **Path hard-coded nei manifest storici**: i `manifest_*.json` registrati al
   momento del run autoritativo contengono path assoluti dell'autore
   (`/home/francesco/TESI/...`). Sono provenance storica e **non vanno
   modificati**: testimoniano dove il file era *quando il run è stato
   eseguito*. Lo stato presente del file (sha256, contenuto) è ricalcolato
   con `verify_data_integrity.py`.

2. **MASTER_SEED comuni**: 20260621 per pacchetti 07/10/12/13/14, 20260622
   per 11, 20260623 per 08. Schema riproducibile:
   `np.random.SeedSequence([MASTER_SEED, blake2b(seed_name)])`.

3. **Timestamp esterno**: tutti gli script esecutore accettano timestamp ISO
   da riga di comando o variabile d'ambiente. Mai usato `Date.now()` o
   equivalenti dentro la pipeline.

4. **Pacchetto 13 patologia §2/§3**: i residui ũ_e e ũ_b come definiti hanno
   carichi antisimmetrici per costruzione. La sign rule §3 è rivista a
   "antisymmetric" (variante 2a) — vedi `src/hfi/third_channel/config.py`
   campo `EXPECTED_SIGN` e `src/hfi/third_channel/tests/test_synthetic_validation.py`.
