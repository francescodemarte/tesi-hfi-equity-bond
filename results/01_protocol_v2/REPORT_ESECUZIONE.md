---
title: "Report di esecuzione — Protocollo v2 sign-flip (Esecutore)"
data: 2026-06-22
ruolo: Esecutore (penultimo anello della catena di custodia)
stato: ESECUZIONE COMPLETATA. Output grezzi consegnati. **Nessuna interpretazione dei risultati.**
catena_di_custodia: agente 2 → agente 3 → agente 4 (review) → verifica coerenza vs v2 → **ESECUTORE (qui)** → verifica umana finale
---

# Report di esecuzione

## Stato (post Bug 2 fix, 2026-06-22T15:00:00Z)

- **Run AUTORITATIVO**: `result_authoritative.pkl` (sha256 `a9c13a7b…`), `manifest_authoritative.json` (sha256 `2a19da6b…`), 2026-06-22T15:00:00Z, seed `3993785275`. FOMC payload via PCA su set fisso 5 serie (FFc1/c2/c3 + SRc1/c2) come da SPEC §8 pre-registrato ("PC1 money-market <1y, se fattibile"). Copertura insufficiente (n=2 su 187 eventi) ⇒ **T2 FOMC e T9 FOMC GATED**, esattamente come NFP ed ECB.
- **Backup pre-Bug2 (conservato per audit)**: `result_authoritative_pre_bug2.pkl` (sha256 `e1a460a0…`), `manifest_authoritative_pre_bug2.json`. Identico al post-fix su T1/T3/T4/T5/T6/T2/T9/decomp/dedup/shared_control bit-by-bit (verificato); differisce SOLO in T7 (era artefatto Bug 2, ora valido) e in micro-fluttuazioni Monte Carlo di T8 delta_p (decisioni `flip_detected` invariate per tutte le 4 perturbazioni).
- **Run ESPLORATIVO (post-hoc, NON pre-registrato)**: `result_exploratory_fomc_variable_k.pkl` (sha256 `45376c62…`). FOMC payload via PCA "cascata-per-gruppi" su set serie variabile per evento — approccio post-hoc. Tenuto per trasparenza, **fuori dal corpo confermativo**. Quando Bug 2 fu corretto questo run non e' stato ri-eseguito (T7 e' lo stesso artefatto Bug 2; per la sezione T7 valida si rimanda all'autoritativo). L'esplorativo resta utile solo per T2/T9 FOMC alimentati a n=186.
- Pacchetto `CODICI_TESI/07_protocollo_v2_signflip/` versione `v2-signflip-2026-06-21` (config_hash `55ccb29a…`), smoke **175/175 verdi** post Bug 2 fix.

## Provenance (manifest_authoritative)

Hash unico per ogni input:

| Input | sha256 (prefisso) |
|---|---|
| events_with_regime_classifier.csv | `92215e6f…` |
| contaminants_v2_2026-06-22.csv | `0f69caa3…` |
| req08_cpi_surprise.csv | `8021823f…` |
| external_data/snapshots/T10Y2Y.csv | `d641a96a…` |
| external_data/snapshots/VIXCLS.csv | `7c18cea3…` |
| external_data/snapshots/CPI_YoY.csv | `17972af2…` |
| execute.py (driver autoritativo post-Bug2) | `342ff38d…` |
| execute.py (driver autoritativo pre-Bug2) | `11658faf…` |
| execute_exploratory.py (driver esplorativo) | `1a44b82c…` |

Seed dichiarato: `execute_v2_signflip_2026-06-22` → `3993785275`.

## Conteggi cella (post-dedup controlli condivisi tra regimi opposti)

| Tipo | n pos | n neg | dedup_shared |
|---|---:|---:|---:|
| FOMC | 45 | 142 | 0 |
| CPI | 37 | 150 | 0 |
| NFP | 42 | 145 | 0 |
| ECB | 54 | 227 | 0 |

`shared_control_diagnostic` post-dedup: `n_shared=0` per tutti i tipi ⇒ indipendenza χ²₁ del test centrale OK by construction (nessun controllo condiviso tra regimi opposti).

## T1 — routing per cella (cv_MOP = 23.108511)

ΔVar > 0 significativo (bound inferiore 95% monolaterale) in TUTTE le 8 celle.

| Cella | F_eff | route | dvar_lb |
|---|---:|---|---|
| FOMC.pos | 14.04 | `ar_only` | 2.93e-06 |
| FOMC.neg | 31.02 | `pointwise` | 1.61e-06 |
| CPI.pos | 18.86 | `ar_only` | 1.57e-05 |
| CPI.neg | 29.72 | `pointwise` | 1.50e-06 |
| NFP.pos | 22.96 | `ar_only` | 9.42e-06 |
| NFP.neg | 53.13 | `pointwise` | 5.49e-06 |
| ECB.pos | 7.77 | `ar_only` | 2.59e-06 |
| ECB.neg | 23.43 | `pointwise` | 1.44e-06 |

## T3 — ampiezza shock comune (b_OLS − b_H, CI 95% bootstrap percentile)

| Cella | diff | CI low | CI high |
|---|---:|---:|---:|
| FOMC.pos | -0.0259 | -0.0697 | -0.0092 |
| FOMC.neg | -0.1132 | -0.1868 | -0.0720 |
| CPI.pos | -0.0305 | -0.0600 | -0.0168 |
| CPI.neg | -0.2979 | -0.4720 | -0.1901 |
| NFP.pos | +0.0039 | -0.0288 | +0.0337 |
| NFP.neg | +0.0223 | -0.0029 | +0.0497 |
| ECB.pos | -0.0392 | -0.2104 | +0.0065 |
| ECB.neg | -0.1791 | -0.3369 | -0.0733 |

## T4 / T5 — sign-flip (inferenza AR, gerarchia BY)

| Tipo | testable | delta_p | opposite_sides | flip_detected |
|---|:-:|---:|:-:|:-:|
| FOMC | True | 0.0560 | False | False |
| CPI | True | 0.0218 | False | False |
| NFP | True | 0.0001 | True | **True** |
| ECB | True | 0.2769 | False | False |

BY: `nfp_reject=True`; `secondary={CPI:False, FOMC:False, ECB:False}`; `m_used=3`.

## T6 — specificita per tipo

- nfp_vs_cpi: `{nfp_flips:True, cpi_flips:False, specific:True}`
- Cochran Q `positivo`: Q=17.4274, df=3, p=5.77e-04, b_pooled=1.291
- Cochran Q `negativo`: Q=74.3587, df=3, p≈4.44e-16, b_pooled=0.239

## T2 — Lewbel (gated per copertura sorprese)

**Run autoritativo** (FOMC PCA set fisso 5 serie):

| Tipo | feedable | n_valid | tau | t_tau | b_L |
|---|:-:|---:|---:|---:|---:|
| CPI | True | 186 | 3.60e-06 | 1.9091 | 3.2398 |
| FOMC | **False** | 2 | -7.42e-09 | -1.9999 | 25.5439 (set fisso 5 serie, n<<N_MIN ⇒ GATED) |
| NFP | — gated (consensus non reperibile, SPEC §8) | | | | |
| ECB | — gated (Altavilla LEVEL parser, loaders.load_ecb_level NotImplementedError) | | | | |

**Run esplorativo** (post-hoc, FOMC cascata-per-gruppi): FOMC `feedable=True, n_valid=186, tau=1.33e-10, t_tau=1.0153, b_L=0.9093`. CPI/NFP/ECB invariati.

## T7 — regimi esogeni (E3) + concordance E3.1

Ridefinizione regime via T10Y2Y e VIXCLS (mediana causale 252gg, lag t-1). Bug 2 (tz-mismatch in `_relabel_per_type_with_regime`) risolto da agente 3 con normalizzazione tz nel kernel `assign_regime` + 3 nuovi test di presidio (smoke 172→175 verde). Ri-esecuzione completa del driver autoritativo post-fix (2026-06-22T15:00:00Z) ha aggiornato `result_authoritative.pkl`.

### flip_detected (T7 post-fix, valido)

| Criterio | NFP | CPI | FOMC | ECB |
|---|:-:|:-:|:-:|:-:|
| T10Y2Y | False | False | False | False |
| VIXCLS | False | False | False | False |

### delta_p per_type sotto regimi esogeni (post-fix)

| Tipo | T10Y2Y delta_p (opp) | VIXCLS delta_p (opp) |
|---|---:|---:|
| FOMC | 0.3816 (False) | 0.4136 (False) |
| CPI | 0.0197 (False) | 0.0115 (False) |
| NFP | 0.8799 (False) | 0.2645 (False) |
| ECB | 0.9085 (False) | 0.1970 (False) |

BY sotto T10Y2Y: `nfp_reject=False`, `secondary={CPI:False, FOMC:False, ECB:False}`.
BY sotto VIXCLS: `nfp_reject=False`, `secondary={CPI:True, FOMC:False, ECB:False}` (CPI supera BY a q=0.10 ma `opposite_sides=False` ⇒ `flip_detected[CPI]=False`).

### Concordance E3.1 (calcolata indipendentemente, invariata)

La concordance e' calcolata indipendentemente in `t7_concordance.py` usando `events["date"]` (colonna tz-naive dal CSV) ⇒ non era affetta da Bug 2.

**Concordance baseline (corr3m, lag t-1) ↔ esogeno**:

| Tipo (n_valid_pairs) | vs T10Y2Y | best mapping | vs VIXCLS | best mapping |
|---|:-:|---|:-:|---|
| FOMC (187/189) | 0.5882 | pos↔alto | 0.5134 | pos↔basso |
| CPI (187/190) | 0.5936 | pos↔alto | 0.5134 | pos↔basso |
| NFP (187/189) | 0.6096 | pos↔alto | 0.5294 | pos↔basso |
| ECB (281/287) | 0.5587 | pos↔alto | 0.5658 | pos↔alto |

Tabelle 2x2 (counts: pos|alto, pos|basso, neg|alto, neg|basso):

| Tipo | T10Y2Y | VIXCLS |
|---|---|---|
| FOMC | 31 / 14 / 63 / 79 | 19 / 26 / 70 / 72 |
| CPI | 22 / 15 / 61 / 89 | 12 / 25 / 71 / 79 |
| NFP | 26 / 16 / 57 / 88 | 16 / 26 / 73 / 72 |
| ECB | 28 / 26 / 98 / 129 | 30 / 24 / 98 / 129 |

**Concordance baseline (corr3m, lag t-1) ↔ esogeno** (E3.1, estratta da `t7_concordance.py`, JSON in `t7_concordance.json`):

| Tipo (n_valid_pairs) | vs T10Y2Y | best mapping | vs VIXCLS | best mapping |
|---|:-:|---|:-:|---|
| FOMC (187/189) | 0.5882 | pos↔alto | 0.5134 | pos↔basso |
| CPI (187/190) | 0.5936 | pos↔alto | 0.5134 | pos↔basso |
| NFP (187/189) | 0.6096 | pos↔alto | 0.5294 | pos↔basso |
| ECB (281/287) | 0.5587 | pos↔alto | 0.5658 | pos↔alto |

Tabelle 2x2 (counts: pos|alto, pos|basso, neg|alto, neg|basso):

| Tipo | T10Y2Y | VIXCLS |
|---|---|---|
| FOMC | 31 / 14 / 63 / 79 | 19 / 26 / 70 / 72 |
| CPI | 22 / 15 / 61 / 89 | 12 / 25 / 71 / 79 |
| NFP | 26 / 16 / 57 / 88 | 16 / 26 / 73 / 72 |
| ECB | 28 / 26 / 98 / 129 | 30 / 24 / 98 / 129 |

## T8 — robustezza (4 perturbazioni)

| Perturbazione | NFP | CPI | FOMC | ECB |
|---|:-:|:-:|:-:|:-:|
| baseline | **True** | False | False | False |
| exclude_extreme (top-10% \|r^b\|) | **True** | False | False | False |
| widen_regime (window=126gg) | **True** | False | False | False |
| exclude_inflationary (CPI YoY ≥ 4%) | False | False | False | False |

**Verifica T8(d) base SA vs NSA** (post-hoc verifica autorizzata, no cherry-picking, vedi `cpi_base_sa_vs_nsa.json`):

- CPIAUCSL (SA, usato nel run autoritativo): 26 mesi 2010-2025 con YoY ≥ 4%, anni inflazionistici {2021, 2022, 2023}.
- CPIAUCNS (NSA, standard ufficiale YoY): 26 mesi 2010-2025 con YoY ≥ 4%, anni inflazionistici {2021, 2022, 2023}.
- **SETS COINCIDONO**: True. Intersezione 26/26, solo-SA 0, solo-NSA 0.
- Conclusione: `exclude_inflationary` **robusto** alla scelta SA vs NSA della base CPI per il calcolo YoY. Il risultato T8(d) e' invariante. Documentato come robustezza dichiarata. CPIAUCNS snapshot congelato in `external_data/snapshots/CPIAUCNS.csv` (sha256 `095ec7cc8d89df78…`, source `api.stlouisfed.org/fred/series/observations`).

## T9 — meccanismo (due gambe, gated)

**Run autoritativo**:

| Tipo | open | equity_leg_inverts | bond_leg_inverts |
|---|:-:|:-:|:-:|
| CPI | False | False | True |
| FOMC | **True** | None | None | (gated per copertura insufficiente set fisso 5 serie — pos n=0) |
| NFP | — gated (consensus non reperibile, SPEC §8) | | |
| ECB | — gated (Altavilla LEVEL parser gated) | | |

CPI: pos {slope_eq=-2.01e-03, slope_bond=-4.45e-05, β_impl=45.094, n=37}; neg {slope_eq=-1.46e-04, slope_bond=+1.59e-04, β_impl=-0.923, n=149}.

FOMC autoritativo: pos None (n=0), neg None (n=2) ⇒ aperto/non determinabile.

**Run esplorativo** (post-hoc, FOMC cascata): FOMC `open=False`, equity_leg_inverts=False, bond_leg_inverts=False. pos {slope_eq=7.231, slope_bond=3.598, β_impl=2.010, n=45}; neg {slope_eq=0.0772, slope_bond=0.8596, β_impl=0.0898, n=141}. CPI invariato.

## Decomposizione canali daily — GATED dichiarato

`None`. Loader eventi→duration equity non implementato (`equity_duration_partial(weights, horizons)` ha il kernel ma nessun mapping eventi → (weights, horizons) da `req09_div_futures.csv`/`req11_sda_annual.csv` e' stato cablato dal pacchetto).

## Calendario contaminanti consumato

`Dati/calendari/contaminants_build_2026-06-22/contaminants_v2_2026-06-22.csv` (sha256 `0f69caa3…`), 5151 centri unici aggregati da 5 fonti:

| Sorgente | Records | Kind |
|---|---:|---|
| FRED | 2750 | macro_release |
| ECB | 944 | speech |
| BdI (BTP) | 656 | auction |
| TreasuryDirect | 385 | auction |
| Bundesbank (Bund) | 299 | auction |
| FedBoard | 117 | testimony |

`build_calendar_reject(event_centers, contaminant_centers)` produce reject pool effettivo di 4282 centri (differenza vs 5151: rimossi i contaminanti che cadono in giorni-evento e/o fuori range temporale prezzi).

## control_accounting / drop-log

842 record (uno per ogni evento assemblato). Totale controlli tenuti: 3589.

| Reason dropped | Count |
|---|---:|
| calendar (contaminante o evento) | 1589 |
| no_data_eq (extract_window None) | 48 |
| no_data_bond (extract_window None) | 17 |

Tutti i record presenti in `result_v2_fomc_variable_k.pkl` chiave `accounting`.

## Caveat dichiarati

1. **OAT (Francia) AUCTION_DATA_NOT_AVAILABLE_AFTER_FALLBACK**: AFT cloudflare-block; BdF Webstat no dataset auction-dates; ECB SDMX endpoint deprecato; ESMA registers non rilevanti; GitHub no dataset pubblico. Contaminanti aste sovrane francesi 2010-2025 NON depurati dai controlli ECB. Bund (Germania) e BTP (Italia) coperti.

2. **FOMC T2/T9 GATED nel run autoritativo per copertura insufficiente**: la SPEC §8 prescrive `m_e = PC1 variazioni money-market <1y (ricalcolo da futures tassi se fattibile)`. Il driver pre-registrato applica PCA al set fisso (FFc1, FFc2, FFc3, SRc1, SRc2). Verificato sui dati reali: SRc1/SRc2 (SOFR futures) hanno tick sparsi negli orari FOMC (es. evento FOMC 2015-03-18 18:00 UTC → SRc1 0 tick in finestra ±15 min). Risultato pre-registrato: 2 eventi su 187 con copertura completa ⇒ n=2 << N_MIN=30 ⇒ T2 FOMC e T9 FOMC **gated per copertura insufficiente**, esattamente come NFP (consensus non reperibile) ed ECB (Altavilla LEVEL parser gated). L'esito "se fattibile" della SPEC e' onorato: la fattibilita e' insufficiente, il gate scatta.

3. **Analisi esplorativa post-hoc FOMC (cascata-per-gruppi)** — `result_exploratory_fomc_variable_k.pkl`: approccio non pre-registrato deciso dopo aver visto il payload autoritativo (n=2). Tenuto per trasparenza, **fuori dal corpo confermativo**. Sign-flip, T1/T3/T4/T5/T6/T7 IDENTICI all'autoritativo. T8 flip_detected identico (decisioni invariate; piccole fluttuazioni Monte Carlo in delta_p per stato rng diverso post-T2). L'unica differenza sostanziale: T2 e T9 FOMC alimentati a n=186 distribuito in 6 gruppi di copertura (149 in FFc1+FFc2+FFc3; minori in altri set).

4. **NFP T2/T9 non alimentati**: SPEC §8 — consensus NFP esteso non reperibile. T2 NFP e T9 NFP assenti dall'output, **gated dal driver per Z/s non disponibili**.

5. **ECB T2/T9 non alimentati**: `loaders.load_ecb_level` solleva `NotImplementedError` (Altavilla 2019 foglio Excel non-tabulare, parser richiede autorizzazione separata). Documentato in `external_data/PROVENANCE_INDEX.md`.

6. **Decomposizione canali daily non alimentata**: vedi sezione dedicata.

7. **Bug 1 risolto** durante il run reale: `regimes.assign_regime` esplodeva su date duplicate negli eventi (FOMC decision+press, ECB decision+press, FOMC+CPI sovrapposti). Hand-off in `CODICI_TESI/07_protocollo_v2_signflip/HANDOFF_AGENTE3_BUG_1.md`; fix applicato dall'agente 3 con 3 nuovi test, smoke 169 → 172 verde. Ri-eseguito sopra.

8. **T7 concordance E3.1 estratta**: vedi sezione T7. La pre-registrazione richiedeva la concordance per distinguere "flip artefatto-classificazione" da "regimi esogeni catturano regime diverso". Calcolata via `t7_concordance.py` riusando esattamente gli stessi kernel (`run.compute_regimes`, `regimes.build_exogenous_regime`, `regimes.assign_regime`). Nessuna ri-esecuzione della pipeline.

9. **T8(d) base CPI verificata**: confronto SA (CPIAUCSL, usato nel run) vs NSA (CPIAUCNS, standard ufficiale YoY). Insieme dei 26 mesi >= 4% YoY identico tra le due basi; anni inflazionistici {2021, 2022, 2023} per entrambe. `exclude_inflationary` robusto alla scelta SA vs NSA. Snapshot CPIAUCNS congelato in `external_data/snapshots/CPIAUCNS.csv`.

10. **Bug 2 risolto** (2026-06-22): `regimes.assign_regime` ora normalizza tz-aware → tz-naive nel kernel, prevenendo il mismatch su event_dates UTC vs `regime_series.index` tz-naive che invalidava T7. Fix coerente con Bug 1 (kernel difensivo). 3 test di presidio aggiunti (`test_regimes.py`), fixture e2e estesa con almeno un `center` tz-aware UTC. Smoke 172 → 175 verde. Driver autoritativo ri-eseguito (timestamp 2026-06-22T15:00:00Z). Verificato bit-by-bit pre vs post: core T1/T3/T4/T5/T6/T2/T9/decomp/dedup/shared_control IDENTICAL; T7 ora valido; T8 con micro-fluttuazioni Monte Carlo (decisioni `flip_detected` invariate per tutte le 4 perturbazioni — `widen_regime` NFP delta_p 1.83e-04 → 1.78e-04, `exclude_extreme` 4.3e-05 → 4.5e-05). Backup pre-fix conservato in `result_authoritative_pre_bug2.pkl` per audit.

## Stato della catena di custodia

- Codice congelato del package: **parametri invariati** (config_hash stabile `55ccb29a…`); modifiche post-handoff applicate dall'agente 3 = Bug 1 fix in `regimes.assign_regime` (3 test + smoke 169 → 172 verde) e Bug 2 fix nello stesso kernel (3 test + smoke 172 → 175 verde, fixture e2e estesa con tz-aware).
- Driver dell'esecutore:
  - **autoritativo post-Bug2** `execute.py` (sha256 `342ff38d…`): pre-registrato, set fisso 5 serie come da SPEC §8.
  - autoritativo pre-Bug2 `execute_exploratory.py` salvato come **history del set-fisso** (sha256 `11658faf…` originario non disponibile dopo edit, ma `result_authoritative_pre_bug2.pkl` conserva l'output con sha256 `e1a460a0…`).
  - **esplorativo** `execute_exploratory.py` (sha256 `1a44b82c…`): post-hoc, cascata-per-gruppi. Solo come analisi di trasparenza.
- Calendario contaminanti: congelato in `Dati/calendari/contaminants_build_2026-06-22/contaminants_v2_2026-06-22.csv`, sha256 nel manifest del calendario stesso.
- Snapshot FRED: 11/11 in `CODICI_TESI/07_protocollo_v2_signflip/external_data/snapshots/` (10 di agente 3 + CPIAUCNS aggiunto dall'esecutore per verifica T8d), `.provenance.json` per ognuno.
- Manifest finale: `09_risultati/v2_signflip/manifest_authoritative.json` (config_hash + 6 input sha256 + seed + timestamp esterno + diagnostics dedup_shared / shared_control). Per il run esplorativo: `manifest_exploratory_fomc_variable_k.json` (stesso schema, script_sha distinto).
- Verifiche aggiuntive post-hoc autorizzate: `t7_concordance.json` (E3.1 estratta dai kernel esistenti, no ri-esecuzione); `cpi_base_sa_vs_nsa.json` (verifica robustezza base CPI).

## Cosa rimane (fuori dal mandato dell'esecutore)

- Verifica umana finale dei numeri grezzi.
- Interpretazione dei risultati (non eseguita qui per disciplina).
- Decisione su come gestire i gate dichiarati (NFP T2/T9, ECB T2/T9, decomp daily, OAT) nella scrittura della tesi.
- Eventuale autorizzazione separata per: parser ECB LEVEL (Altavilla), fonte OAT (e.g. Bloomberg licensed), loader eventi→duration equity.
