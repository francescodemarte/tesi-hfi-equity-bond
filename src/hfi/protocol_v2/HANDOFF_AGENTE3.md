---
title: "Hand-off Esecutore → Agente 3 — buchi orchestratore + pre-registrazione"
data: 2026-06-22
da: Esecutore (post-verifica package, pre-esecuzione sui dati reali)
a: Agente 3 (autore codice congelato)
stato: ESECUZIONE SUI DATI REALI **NON AVVIATA**. Calendario contaminanti (Phase 0) in costruzione in parallelo.
catena_di_custodia: agente 2 → AGENTE 3 → agente 4 (review) → verifica coerenza vs v2 → **ESECUTORE (qui)** → verifica umana finale
---

# Hand-off dell'esecutore

L'esecutore ha completato la ricognizione del package congelato. Il pulsante "run" non si schiaccia perche l'orchestratore end-to-end **non e chiuso** nel codice congelato e perche alcune scelte metodologiche che servirebbero a chiuderlo **non sono pre-registrate**. Esecuzione rimandata ad agente 3 per chiusura. Quando torna verde, l'esecutore riprende.

## Cosa l'esecutore ha verificato (per non rifare)

- `pytest tests/ -q` → **151 passed in 6.85s**.
- Path assoluti hard-coded in `config.py` (`INTRADAY_DIR`, `CALENDAR_DIR`): tutti esistono.
- Contratto-dati (#10):
  - intraday `Datetime_UTC` + `PX_LAST` per ES/TY/FGBL; `Datetime_UTC` + `Mid_raw` per STXE — conforme a `INTRADAY_FILES`.
  - `events_with_regime_classifier.csv`: 855 eventi, `event_class ∈ {FOMC, CPI, NFP, ECB}`, `timestamp` UTC, `date`.
- Sorgenti sorprese disponibili: `req08_cpi_surprise.csv` (193 record 2010→2025), `req12c_nfp_consensus.csv` solo 2024 (12 record) ⇒ T2/T9 NFP non alimentati come da SPEC §8.
- Calendario contaminanti: **in costruzione dall'esecutore** dopo autorizzazione fetch (FRED Releases, TreasuryDirect, Fed testimonies, BCE speeches, aste Bund/BTP/OAT). Output: snapshot congelato con provenienza.

## Blocco 1 — Orchestratore end-to-end non chiuso

`run.run_protocol` esegue **soltanto**: T1 (routing), T3 (ampiezza), T4 (dentro T5), T5 (sign-flip), T6 (specificita) + dedup controlli condivisi + `shared_control_diagnostic`. Restituisce un `dict`, **non emette manifest**.

**Mancano dall'orchestrazione** (i kernel esistono, manca il wrapping):
- **T2 Lewbel** — `tests_protocol.t2_lewbel(re_e, rb_e, Z, rng, source_label=...)` da invocare per tipo×regime con Z da `surprises.surprise_source(t)`. Non c'e nessun loop.
- **T7 regimi esogeni** — `tests_protocol.t7_exogenous(per_type_by_criterion, beta_grid)`: l'orchestratore non costruisce `per_type_by_criterion` perche **i criteri esogeni non sono specificati** (Buco 2.1).
- **T8 robustezza** — `tests_protocol.t8_robustness(per_type_clusters, rng, beta_grid, transforms)`: l'orchestratore non costruisce `transforms`. Le quattro perturbazioni richiedono (a) `exclude_extreme(frac=0.1)`, (b) `leave_year_out` per ogni anno distinto, (c) ri-`compute_regimes()` con `REGIME_WINDOW_DAYS_ROBUST=126` + ri-`assemble()` (NON un `cell_transform`), (d) `exclude_years(years=...)` con anni non specificati (Buco 2.3).
- **T9 meccanismo** — `mechanism.mechanism(per_regime, source_label=...)`: l'orchestratore non costruisce `per_regime = {"positivo": {"r_e":..., "r_b":..., "s":...}, "negativo": {...}}`. Servono mapping eventi↔sorprese.
- **Decomposizione daily** — `decomposition.bond_channels` / `equity_channels` / `twin_cov` / `equity_partial_duration`: l'orchestratore non carica `fred_yields_snapshot.parquet` (DFII5/T5YIE/DGS10), ne `req09_div_futures.csv` / `req11_sda_annual.csv` per i pesi/orizzonti della duration.
- **`provenance.write_manifest`**: mai chiamata. Nessun manifest finale prodotto, contro SPEC §13.8.

**Richiesta:** aggiungere in `run.py` un `run_full(events, prices, regimes, reject, contaminant_centers, rng, surprises_sources, daily_yields, daily_dividends, timestamp_iso) -> dict` che:
1. esegue `run_protocol` (sezione RS);
2. cicla T2 per tipo×regime con `surprise_source(t)`;
3. esegue T8 baseline + le 4 perturbazioni (incluso ri-classificazione regime per T8c);
4. esegue T7 sui criteri esogeni pre-specificati (Buco 2.1);
5. esegue T9 per tipo (cella positivo+negativo);
6. esegue decomp daily per tipo×regime;
7. compone le `entries` (una per cifra) e chiama `provenance.write_manifest` su `OUT_DIR/manifest.json` con `control_accounting` + `shared_control_diagnostic` + `dedup_shared` + decisione di dedup nelle diagnostics.

## Blocco 2 — Decisioni metodologiche NON scritte

Queste vanno fissate **prima** del run reale. Sono scelte di pre-registrazione, non scelte di esecuzione: se le fa l'esecutore mentre vede i dati, sono ex-post.

### 2.1 T7 — quali criteri esogeni di regime?
Il SPEC §6 dice "≥2 criteri esogeni a ρ". Nessuno e nominato in `config.py`. Candidati ricorrenti in letteratura: regime VIX (alta/bassa volatilita su soglia mediana), regime MOVE, term-spread (10y–3m), regime di policy (ZLB vs non-ZLB), recession dummy NBER. **Decidere quali due e come si binarizzano**, scrivere in `config.py` + loader in `regimes.py`.

### 2.2 T8(c) — variazione soglia di regime
`REGIME_WINDOW_DAYS_ROBUST=126` esiste, ma `t8_robustness` accetta solo `transforms: dict[str, callable[per_type_clusters → per_type_clusters]]`. Cambiare la window richiede ri-classificare il regime e **ri-assemblare** le celle (perche cambia l'assegnazione pos/neg degli eventi). Due opzioni:
- (i) Espandere `t8_robustness` per accettare anche transformer a livello di eventi (richiede passaggi di `compute_regimes`/`assemble` come callable);
- (ii) Comporre T8(c) come ramo separato in `run_full`: ri-`compute_regimes(window=126)` → ri-`assemble` → `t5_signflip` → confronto con baseline.

L'opzione (ii) e piu pulita perche tiene `t8_robustness` ai cell-transform. Decidere e cablarlo.

### 2.3 T8(d) — anni inflazionistici
"Esclusione sotto-periodo inflazionistico" senza lista anni. Candidati: {2021, 2022, 2023} (US CPI YoY > 5% per buona parte), oppure solo {2022}, oppure {2021Q2–2023Q2}. **Decidere e scrivere in `config.py`** (`INFLATIONARY_YEARS: tuple[int, ...]`).

### 2.4 Decomp daily — loader duration equity
`equity_partial_duration(weights, horizons)` esiste come kernel ma il metodo per derivare `(weights, horizons)` per data evento da `req09_div_futures.csv` / `req11_sda_annual.csv` non e scritto. Decidere:
- struttura dei pesi (cap-weighted? equally-weighted? dividend strip-weighted?);
- orizzonti (1y, 2y, ..., 10y? o continuum?);
- frequenza (daily? as-of evento?).
Aggiungere `decomposition.load_equity_duration(date, dividend_futures_path)` in modo deterministico.

### 2.5 FOMC m_e — PC1 money-market
SPEC §8: "m_e = PC1 variazioni money-market <1y (ricalcolo da futures tassi se fattibile)". Codice non presente. I futures tassi sono in `INTRADAY_DIR`: `FFc1/c2/c3`, `SRc1/c2`. Decidere:
- finestra di calcolo PCA (intraday ±15 min come per gli eventi? daily?);
- quale tenor set entra (FFc1-c3 + SRc1-c2?);
- standardizzazione (z-score sui pre-evento?).
Scrivere `surprises.compute_fomc_me(event_ts, intraday_dir) -> float` deterministico, testato.

### 2.6 ECB LEVEL/PATH — parser Altavilla
`EA-MPD_ECB_Altavilla2019.xlsx` ha il primo foglio non-tabulare (intestazione "Euro Area Monetary Policy event study Database (EA-MPD)", 65 righe ma una sola colonna). I dati veri stanno in un foglio interno (verificare via `pd.ExcelFile(...).sheet_names`). Scrivere `surprises.load_altavilla_level_path(xlsx_path) -> pd.DataFrame` con colonne `[date, level, path, ...]` deterministico, testato.

## Cosa NON va toccato (gia chiuso e verificato)

- `estimators.py`, `weakiv.py`, `inference.py`, `mechanism.py`, `decomposition.py`, `provenance.py`, `windows.py`, `regimes.py`, `surprises.py` (eccetto le aggiunte 2.5/2.6/2.4), `synthetic.py`, `tests_protocol.py` (eccetto eventuale espansione 2.2).
- Parametri congelati in `config.py` (non si toccano i valori esistenti; si **aggiungono** quelli mancanti 2.1/2.3).
- I 151 test unit/smoke verdi.

## Stato del calendario contaminanti (Phase 0)

In costruzione dall'esecutore in parallelo. Output atteso: snapshot CSV/parquet in `/home/francesco/TESI/Dati/calendari/contaminants_v1_<data>.csv` con colonne `[center_utc, source, kind, label, fetch_date, source_version]`. Verra passato a `build_calendar_reject(event_centers, contaminant_centers)` quando l'esecutore riprendera.

## Quando il pulsante e di nuovo schiacciabile

Quando agente 3 ha:
1. esteso `config.py` con: criteri T7, `INFLATIONARY_YEARS`, parametri PCA money-market, struttura duration equity;
2. aggiunto loaders/parsers (2.4/2.5/2.6) con test;
3. scritto `run.run_full(...)` end-to-end + chiamata `provenance.write_manifest`;
4. lanciato il smoke synthetic di nuovo verde (i 151 test piu eventuali nuovi per i loader).

A quel punto l'esecutore: (i) verifica che il SHA del package sia diverso da quello attuale; (ii) ri-lancia il smoke; (iii) riceve dall'autorita umana l'ok per il run reale; (iv) esegue `run.run_full(...)` con il calendario contaminanti gia pronto; (v) consegna il manifest senza interpretazioni.
