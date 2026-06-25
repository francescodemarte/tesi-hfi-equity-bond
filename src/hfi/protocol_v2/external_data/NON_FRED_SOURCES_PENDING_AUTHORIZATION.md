---
title: "Fonti non-FRED del calendario contaminanti — elenco in attesa di autorizzazione"
data: 2026-06-22
stato: NON SCARICATE — attendono autorizzazione esplicita di Francesco
contesto: "C0.2 (SPEC §13bis): il calendario contaminanti C0.2 richiede dati che FRED non copre. Procurement non eseguito su queste fonti."
---

# Fonti non-FRED del calendario contaminanti (C0.2)

Il mandato dell'agente 3 autorizza **solo** FRED; le fonti sotto sono **in attesa
di autorizzazione separata**. Per ciascuna è elencata: la fonte, l'endpoint,
quale contaminante copre, le chiamate previste, e cosa serve per congelare lo
snapshot con provenienza.

Ogni snapshot autorizzato dovrà essere depositato in `external_data/snapshots/`
con `<name>.csv` + `<name>.provenance.json` (stesso schema di FRED:
sha256, fetched_at, source_url, date_min/max, n_rows).

---

## 1. US — aste Treasury major (10Y, 30Y, refunding) — 13:00 ET
**Fonte:** TreasuryDirect — Auction Query.
**Endpoint:** `https://www.treasurydirect.gov/TA_WS/securities/search?…&type=Note,Bond` (JSON API pubblica).
**Copre:** contaminanti pomeridiani delle celle FOMC 14:00 ET.
**Chiamate previste:**
- GET securities by `type=Note` filtrato a maturity ∈ {10y}, range `auctionDate=2010-01-01..2025-12-31`.
- GET securities by `type=Bond` filtrato a maturity ∈ {30y}, range idem.
- GET `Treasury Refunding` (announcement + auctions del ciclo quarterly).
**Da congelare:** `auctionDate` (ET), `securityType`, `tenor`, `cusip`.

## 2. US — testimonianze Fed major (presidente, vicechair, board)
**Fonte:** Federal Reserve Board — Speeches & Testimony.
**Endpoint:** `https://www.federalreserve.gov/newsevents/testimony.htm` (HTML scrape; nessuna API).
**Copre:** discorsi/testimonianze programmate ad alta importanza, varie ore del giorno.
**Chiamate previste:**
- HTTP GET delle pagine indice per anno 2010..2025.
- Parse HTML → date, ora ET (se pubblicata), speaker, type∈{testimony, speech}.
**Filtro proposto:** speaker ∈ {Chair, Vice Chair, NY Fed President} e/o testimony al Congress.

## 3. EU — discorsi del board BCE (presidente / vicepresidente)
**Fonte:** European Central Bank — Press, Speeches.
**Endpoint:** `https://www.ecb.europa.eu/press/speeches/html/index.<lang>.html` + RSS/HTML per anno; per la conferenza-stampa: `https://www.ecb.europa.eu/press/pressconf/html/index.<lang>.html`.
**Copre:** contaminanti pomeridiani CET delle celle ECB (≥14:30 CET) **e**, importante, le 8:30 ET sono già coperte da FRED → restano scoperti i discorsi pomeridiani europei.
**Chiamate previste:**
- HTTP GET dei feed annuali 2010..2025; parse → date, ora CET (se presente), speaker, type.
- Filtro proposto: speaker ∈ {President, Vice President, board member} + press conferences.

## 4. EU — aste sovrane pomeridiane (Bund, BTP, OAT) — chiave per le celle ECB
**Fonte (per emittente):**
- **Germania (Bund/Bobl/Schatz):** Deutsche Finanzagentur (Bundesbank) — auction calendar.
  Endpoint: `https://www.deutsche-finanzagentur.de/en/institutional-investors/primary-market/auction-calendar/`.
- **Italia (BTP/CTZ/BOT):** Ministero dell'Economia (MEF/Dipartimento del Tesoro) — calendario emissioni.
  Endpoint: `https://www.mef.gov.it/en/dipartimenti/dt/debito_pubblico/aste_titoli_di_stato/`.
- **Francia (OAT/BTAN):** Agence France Trésor (AFT) — auction calendar.
  Endpoint: `https://www.aft.gouv.fr/en/auction-program-calendar`.
**Copre:** contaminanti pomeridiani CET delle celle ECB; lo strumento bond è FGBL (Bund) quindi le aste Bund sono particolarmente sensibili (DST §13bis).
**Chiamate previste:**
- HTTP GET pagine calendario per anno; parse → date di asta + tenor + emittente.
- Filtro proposto: tenor ≥ 5y per i tre emittenti (rilevanza per FGBL e spillover EU).

---

## Modalità di congelamento (uguale per tutte le fonti)

1. Salvare il payload grezzo in `external_data/snapshots/<source>.<ext>` (HTML/JSON/CSV).
2. Generare `<source>.provenance.json` con: `source_url`, `fetched_at` (ISO,
   passato dall'esterno), `sha256`, `n_records`, `date_min`, `date_max`.
3. Aggiungere uno script `scripts/run_<source>_procurement.py` con la stessa
   forma di `run_fred_procurement.py`.
4. Documentare in `external_data/PROVENANCE_INDEX.md` ogni snapshot congelato.

## Cosa NON è stato fatto (dichiarazione esplicita)

- Nessuna chiamata di rete a TreasuryDirect, Federal Reserve Board, ECB,
  Bundesbank, MEF, AFT. Nessuno scrape, nessuna API.
- Nessuna analisi/aggregazione che usi questi dati.
- L'autorizzazione è bloccante per l'esecutore: senza queste fonti, il
  calendario contaminanti C0.2 resta scoperto su (a) aste Treasury major,
  (b) testimonianze Fed major, (c) discorsi BCE pomeridiani, (d) aste sovrane
  EU (Bund/BTP/OAT).
