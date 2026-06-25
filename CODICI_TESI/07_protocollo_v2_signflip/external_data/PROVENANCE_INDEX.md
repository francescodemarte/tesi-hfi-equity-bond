---
title: "Indice di provenienza — input esterni congelati"
data: 2026-06-22
stato: FRED autorizzato e congelato · NON-FRED in attesa di autorizzazione
---

# Snapshot FRED (autorizzati e congelati)

Tutti gli snapshot in `external_data/snapshots/`. Provenienza per ciascuno in
`<name>.provenance.json` (campi: `name`, `source_url`, `fetched_at`, `sha256`,
`n_rows`, `date_min`, `date_max`). Fetched at: `2026-06-22T10:00:00Z`.

| Serie       | Scopo                                | Copertura            |
|-------------|--------------------------------------|----------------------|
| T10Y2Y      | E3 T7 — slope curva (regime esogeno) | 1976-06-01..2026-06-18 |
| VIXCLS      | E3 T7 — VIX (regime esogeno)          | 1990-01-02..2026-06-17 |
| CPIAUCSL    | E3 T8(d) — livello, base per YoY      | 1947-01-01..2026-05-01 |
| CPI_YoY     | E3 T8(d) — YoY (derivata 12m pct-change) | 1948-01-01..2026-05-01 |
| PPIACO      | Calendario US — PPI                   | 1913-01-01..2026-05-01 |
| RSAFS       | Calendario US — Retail Sales          | 1992-01-01..2026-05-01 |
| GDP         | Calendario US — GDP                   | 1947-01-01..2026-01-01 |
| PCEPI       | Calendario US — PCE Price Index       | 1959-01-01..2026-04-01 |
| DGORDER     | Calendario US — Durable Goods Orders  | 1992-02-01..2026-04-01 |
| ICSA        | Calendario US — Initial Claims        | 1967-01-07..2026-06-13 |

**Backend di rete:** `wget` (HTTP/1.1, stabile da subprocess).  Fallback documentati:
`curl` (instabile HTTP/2 dal sandbox), `urllib`. La scelta è auto-rilevata in
`fred_fetch._fetch_via_*`.

**MOVE (E3 opzionale):** *non scaricato* — non è una serie FRED gratuita pubblica
(ICE BofA, licensed). L'esecutore lo include solo se autorizzato e disponibile.

---

# Non-FRED — in attesa di autorizzazione

Vedi `NON_FRED_SOURCES_PENDING_AUTHORIZATION.md`:
TreasuryDirect aste US · Federal Reserve Board testimonies · BCE speeches ·
Bundesbank/MEF/AFT aste sovrane EU.

---

# Disciplina di consumo (esecutore)

Le serie vanno **caricate dagli snapshot congelati**, non riscaricate. Il manifest
del run deve includere gli sha256 delle serie usate (provenance.entries[i] →
`{path, sha256}`), così la provenance di una cifra arriva fino alla riga FRED.
