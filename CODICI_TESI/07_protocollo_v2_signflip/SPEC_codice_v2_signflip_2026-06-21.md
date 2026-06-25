---
title: "Specifica del codice — Pipeline pre-registrata Protocollo v2 (sign-flip evento/stato)"
tags: [spec, codice, preregistrazione, v2, sign-flip, CONGELATO, agente-3]
data: 2026-06-21
stato: CONGELATO + IMPLEMENTATO (agente 3, 2026-06-21). Fix §8/§4 (no ΔT5YIE), §13bis (DST UTC), B=10000, emendamenti §2bis E1/E2. Codice completo (config…run + loaders + fred_fetch), 169 test verdi, smoke 3-DGP ok, kernel dei subagent verificati con oracolo indipendente. **Review agente 4 (2026-06-21): chiusa.** **Kit di completamento agente 3 (2026-06-22): E3 implementato** — T7 regimi esogeni (mediana causale 252gg, lag t-1), T8(d) inflazione (CPI YoY≥4% predeterminato), orchestratore `run_protocol_full` con T1–T9+decomp+manifest, test e2e (presidio completezza), loaders (m_e_pca, equity_duration_partial; ECB LEVEL gated). **Snapshot FRED autorizzati e congelati** (10 serie, sha256-consistenti) in `external_data/snapshots/`. **Non-FRED in attesa di autorizzazione** (TreasuryDirect, Fed testimonies, BCE speeches, Bundesbank/MEF/AFT). PRONTO per agente 4 (review pezzi nuovi) + coerenza-vs-v2 (umana) + esecutore. Nessuna esecuzione sui dati reali.
deriva_da:
  - "Protocollo di test pre-registrato — Modello v2 (output agente 2), 02_metodologia/preregistrazione_v2_protocollo_test.md"
  - "modello.tex (Specifica del modello v2, F. De Marte)"
autorita: "Il protocollo v2 è autorità unica per la LISTA DEI TEST e i parametri. modello.tex è sorgente per il ramo decomposizione/bound (qui solo daily secondaria)."
catena_di_custodia: "agente 2 (lista test) → AGENTE 3 (questo codice, seed fissi) → agente 4 (review) → verifica coerenza vs v2 → esecutore (run sui dati reali) → verifica umana finale"
---

# Specifica del codice — Protocollo v2 sign-flip

> **Mandato (agente 3).** Tradurre il protocollo v2 in codice **pre-registrato, deriverabile, con seed fissi**. Output di questa fase = **codice congelato + smoke-test su dati sintetici**. **Nessuna esecuzione sui dati reali** (la fa l'esecutore dopo la review dell'agente 4). Ogni cifra futura ↔ script versionato + input + seed dichiarato.

---

## 1. Autorità e scope

- **Il protocollo v2 è autorità unica** per *quali* test, *quali* parametri, *quale* routing. I documenti di metodologia (`04b_metodologia.md`, `5.x`) descrivono un disegno **superato** (terzili / placebo-bootstrap / r̂-ratio / BY-su-6) e **NON guidano il codice**. La riconciliazione del testo della tesi col protocollo è lavoro editoriale a valle, fuori da questa spec.
- **In scope:** via **descrittivo-strutturale** sullo stimatore **b_H** (Rigobon–Sack a due regimi), con b_OLS e b_L (Lewbel) di confronto; routing MOP/AR; gerarchia BY; T1–T9; R1–R7. Più **decomposizione canali daily** come **evidenza secondaria esplicitamente etichettata a frequenza giornaliera**, tenuta separata da b_H.
- **Fuori scope (data-gated):** β-flip *strutturale* e via del **bound** a frequenza-evento — le curve reali/breakeven intraday non esistono (nemmeno da FRED), quindi il RAMO DATI del protocollo (§4–5) impone di non condurla. Niente nuova letteratura. Parametri locked invariati (CLAUDE.md §6).

---

## 2. Le tre correzioni vincolanti (post-approvazione design)

1. **Riuso test-gated.** Nessun kernel ereditato per fiducia. Un kernel del codice esistente è riusabile **solo se**: (a) la sua esistenza è accertata al path citato, **e** (b) un test indipendente ne riconferma la correttezza contro un valore analitico o pubblicato. Vale per *ogni* kernel, inclusi `extract_window`, classificatore di regime, BY, Cochran Q. In assenza di test che riconferma → si riscrive.
2. **Regime ricalcolato dal raw.** Non si usano le colonne `corr3m_US`, `corr*_z_lag`, `rho_tilde*` del CSV eventi (potenzialmente derivate dal pipeline scartato). Si **ricalcola** la correlazione mobile a 63 giorni dai **rendimenti daily grezzi** (derivati dall'intraday → chiusura giornaliera), lag 1 giorno lavorativo, **segno** → pos/neg. Coerente con il ricalcolo dei returns.
3. **Smoke-test a 3 DGP** (vedi §10): flip strutturale, nullo, flip-del-bias.

---

## 2bis. Emendamenti pre-test (registrati 2026-06-21, prima dell'esecuzione)

Raffinamenti metodologici emersi in fase di scrittura codice, **prima di vedere
qualsiasi risultato reale** → pre-test, non scelte ex-post. Registrati per integrità.

**E1 — Criterio MOP = bias relativo (Nagar), NON size.** Il criterio di Montiel
Olea–Pflueger è il **bias di Nagar** del 2SLS relativo a un benchmark worst-case.
La cv=23.109 (K=1) è la soglia di **bias relativo worst-case 10%**, non "size 10%"
(l'etichetta del protocollo era imprecisa; il numero ≈23, ≠ Stock–Yogo 16.38, è
corretto). *Nota:* il **mean bias** non è definito nei just-identified (K=1), ma il
**Nagar bias** sì — per questo la soglia ha senso con un solo strumento. La cv è la
forma **semplificata conservativa** (Patnaik, x=1/τ, K_eff=1): a τ=5% dà 37.42 vs
37.105 esatto (weakivtest) — scarto Patnaik-vs-esatto ~0.3, conservativo, non sposta
il routing. Per K=1 la cv è universale (lo scalare di covarianza si cancella nel dof
efficace) → calcolabile senza la matrice application-specific.

**E2 — Inferenza primaria su Anderson–Rubin per T4/T5 (anche celle forti).** Andrews
(2018): un F robusto grande controlla il **bias** ma **non la copertura** (CI di Wald
2SLS distorto ~15% anche con F≈100000). A strumento singolo, Andrews–Stock–Sun (2019)
raccomandano di riportare **sempre** gli AR. Il disegno è ad **alta endogeneità per
costruzione** (σ_eb≠0 è il problema) ⇒ mordente. **Decisione:** base inferenziale di
T4 e del test centrale T5 = **AR**, in tutte le celle; il b_H di Wald resta stima
puntuale/leggibilità, non base del claim di flip. Conseguenze su T5:
- «lati opposti» = **AR-set disgiunti su lati opposti** (AR(pos) interamente da un
  lato di 0, AR(neg) dall'altro), NON CI di Wald;
- «Δ_H significativo» = **proiezione AR**: pos/neg indipendenti ⇒ Δ_H≠0 ⟺
  AR(pos)∩AR(neg)=∅; p-value di Δ_H = il più piccolo α che li rende disgiunti;
- il routing R5 governa se **mostrare** b_H puntuale; l'inferenza resta AR ovunque;
  il cancello F>cv resta qualità (basso bias) della stima esibita, non garanzia di copertura.
Modifica il «motore d'inferenza» di T5/R1 (che prevedeva bootstrap-Wald nelle celle
forti). Registrato pre-esecuzione. Rif.: Andrews (2018, QJE); Andrews–Stock–Sun (2019, ARE).

## 3. Struttura del package

Package nuovo, **isolato** (non affiancato a `09_risultati/scripts/`, che può ancora contenere il vecchio):

```
CODICI_TESI/07_protocollo_v2_signflip/
  SPEC_codice_v2_signflip_2026-06-21.md   # questo documento
  README.md                # come eseguire, mappa moduli, chain-of-custody
  config.py                # parametri congelati + path + seeding
  provenance.py            # manifest: hash script+input, seed per cifra
  data.py                  # caricamento intraday/daily/eventi
  windows.py               # finestre evento + controllo (C0.1, C0.2)
  regimes.py               # regime da raw (C0.3) — RICALCOLATO
  surprises.py             # sorprese Z (Lewbel) e s (T9) + diagnostica (C0.4)
  estimators.py            # b_OLS, b_H, b_L, momenti
  weakiv.py                # F-MOP robusto K=1 (cv calcolato), AR-set/proiezione
  inference.py             # bootstrap clusterizzato per evento, routing R5, BY R7, Cochran Q
  tests_protocol.py        # orchestrazione T1–T9
  decomposition.py         # canali DAILY (secondaria etichettata)
  run.py                   # orchestratore → manifest, NON esegue sui reali di default
  synthetic.py             # DGP sintetici per smoke-test (§10)
  tests/                   # pytest: kernel delicati + smoke-test
    test_estimators.py  test_weakiv.py  test_inference.py
    test_regimes.py  test_windows.py  test_smoke.py
```

- **Input intraday:** `/home/francesco/TESI/Dati/data_processed/` (`ESc1_1min.csv`, `TYc1_1min.csv`, `FGBLc1_1min.csv`, `STXE_continuous_1min.csv`, + futures tassi).
- **Input eventi/daily:** `DATASET_TESI/` e `bridge/data/` del vault.
- **Output:** `09_risultati/v2_signflip/` (tabelle + `manifest.json`). File intermedi in `/tmp/`.
- **Dipendenze:** `numpy`, `pandas`, `scipy`. **No** statsmodels/linearmodels nel core (kernel propri, testabili). `pytest` per i test.

---

## 4. Contratto-dati (canonico)

| Oggetto | Sorgente | Costruzione |
|---|---|---|
| r^e, r^b evento | intraday 1-min raw | finestra **±15 min**; pre = mediana primi 5 min, post = mediana ultimi 5 min; log-return. **Ricalcolati dal raw**, non letti dal CSV. |
| r^e, r^b controllo | intraday 1-min raw | stessa finestra/ora dell'evento, sui giorni di controllo (C0.2). |
| Mappa strumenti | — | FOMC/CPI/NFP → ES (equity) + TY (bond); ECB → STXE + FGBL. |
| Tipi evento, timestamp | `events_with_regime_classifier.csv` | 4 tipi: FOMC, CPI, NFP, ECB; timestamp UTC. |
| Regime pos/neg | **ricalcolato dal raw** (corr #2) | rendimenti daily (da chiusura giornaliera intraday) → corr mobile 63gg (US: ES~TY; EU: STXE~FGBL) → lag 1bd → segno. |
| Sorpresa Z (Lewbel) / s (T9) | FOMC: `m_e` PC1 money-market (da ricalcolare); ECB: LEVEL/PATH (Altavilla); CPI: **actual-vs-consensus** (`req08`); NFP: **actual-vs-consensus se reperibile**. **Mai ΔT5YIE** né altra componente del bond. | mapping in `surprises.py` (§8, C0.4); diagnostica copertura/varianza come gate. |
| Curve daily (solo decomp. secondaria) | `fred_yields_snapshot.parquet` (DFII5/T5YIE/DGS10), `req15b` EU, dividend futures SDA/FEXD | come Fase 6 esistente, **etichettata daily**. |

**Nota provenienza:** dove una colonna del CSV è frutto di calcolo (returns, regime, m_e), la spec impone **ricalcolo dal più-grezzo disponibile** quando fattibile, col CSV usato al più come cross-check.

---

## 5. Parametri congelati (`config.py`)

| Parametro | Valore | Fonte protocollo |
|---|---|---|
| Half-window | 15 min (finestra 30 min) | metodologia/modello (30 min) |
| pre/post | mediana 5 min | metodologia |
| K controlli baseline / min / max | **5 / 3 / 10** (estendi lookback 1 giorno per volta fino a 10) | C0.2 |
| Sensibilità C0.2 | lookback raddoppiato 5→10 (tetto 20), matching orario e calendario esclusioni fissi | C0.2.4 |
| n_min | **30** | C0.5, R5 |
| MOP | K=1, **bias relativo worst-case 10%** (Nagar, NON size), test 5%, **cv calcolata** = 23.109 (Patnaik, x=1/τ, K_eff=1) — vedi E1 | R5 |
| BY secondari | q = **0.10**, famiglia **m = 3 fissa** su {CPI, FOMC, BCE} | R7, T5 |
| NFP | **primario confermativo**, α = 0.05 **non corretto** (giustificato solo da Ip.6) | R7, T5/T6 |
| Bootstrap B | **10000** (dichiarato pre-test; margine su code dei p piccoli e soglie BY fini) | C0bis, R4 |
| Master seed | 20260621 (child-seed per test via spawn) | R4 |
| Regime | corr mobile **63gg** daily, lag 1bd, soglia = **segno (0)** | C0.3 |
| Soglia regime robustezza | 6m (126gg) | T8(c) |
| Griglia AR | β ∈ [−3, 7], passo 0.005; **estremi = aperto/illimitato, non troncati** | R2 |

I parametri sono **immutabili dopo il congelamento**: nessuna soglia scelta dopo i risultati; robustezze = i quattro chiusi di T8, non ampliabili.

---

## 6. Mappa protocollo → moduli

| Protocollo | Modulo / funzione | Stato |
|---|---|---|
| C0.1 finestre & returns | `windows.extract_window`, `windows.event_returns` | riuso **test-gated** del kernel `extract_window` |
| C0.2 controlli stessa-ora 5gg, min3/max10, **esclusioni**, pooling | `windows.control_windows` (esclusione **pluggable**) | **NUOVO** |
| C0.3 regime segno-ρ | `regimes.rolling_regime` | **NUOVO/ricalcolato** (#2) |
| C0.4 sorprese Z, s + diagnostica copertura/varianza | `surprises.*` | **NUOVO** |
| C0.5 celle tipo×regime, conteggi, n_min | `data.build_cells` | **NUOVO** |
| C0.6 provenienza | `provenance.*` | **NUOVO** |
| b_OLS, b_H=ΔCov/ΔVar, b_L | `estimators.*` | riuso test-gated dei kernel |
| **F-MOP robusto K=1, cv calcolato** (R5) | `weakiv.mop_effective_f`, `weakiv.mop_critical_value` | **NUOVO — delicato** |
| **bootstrap clusterizzato per evento**, V̂ con covarianza intra-evento (T1) | `inference.event_cluster_bootstrap` | **NUOVO** |
| **AR-set / proiezione**, se robusto-clusterizzato (R2, R6) | `weakiv.ar_set`, `weakiv.delta_ar_pvalue` (proiezione) | **NUOVO** |
| **routing puntuale vs AR-only** (R5) | `inference.route_cell` | **NUOVO** |
| T1 gate ΔVar | `tests_protocol.t1_relevance` | **NUOVO** |
| T2 Lewbel τ | `tests_protocol.t2_lewbel` | riuso test-gated |
| T3 b_OLS − b_H (misura) | `tests_protocol.t3_amplitude` | **NUOVO** |
| T4 stato-dipendenza | `tests_protocol.t4_state_dep` | **NUOVO** |
| **T5 sign-flip congiunto** (Δ_H sig ∧ **AR-set lati opposti**, inferenza AR — E2) | `tests_protocol.t5_signflip` | **NUOVO — centrale** |
| **T6 NFP-vs-CPI + Cochran Q** | `tests_protocol.t6_typespec` | Q riuso test-gated |
| T7 regimi esogeni | `tests_protocol.t7_exogenous` | **NUOVO** (riferimento Fase 5) |
| **T8 robustezza lista-chiusa (4)** | `tests_protocol.t8_robustness` | **NUOVO** |
| **T9 meccanismo due gambe** | `tests_protocol.t9_mechanism` | **NUOVO** (gated su s) |
| **R7 gerarchia BY** NFP-primario / m=3 fisso / T4-fail=flip-non-rilevato | `inference.hierarchical_by` | **NUOVO** (kernel BY riuso test-gated) |
| decomp. canali daily etichettata | `decomposition.*` | riuso test-gated (Fase 6) |

---

## 7. Politica di riuso (test-gated, correzione #1)

Per ogni kernel candidato al riuso da `09_risultati/scripts/analysis_pipeline.py` o `/home/francesco/TESI/Dati/codes/stage1_v2/`:
1. Si **cita il path e la funzione** sorgente nel docstring.
2. Si **riscrive** nel nuovo package (no import dal vecchio).
3. Si scrive un **test** che riconferma la correttezza contro: un valore analitico chiuso (es. b_OLS su dati lineari noti), una proprietà nota (es. soglia BY = i·q/(m·c_m); idempotenza), o un valore pubblicato (MOP cv).
4. Solo a test verde il kernel entra nella pipeline.

---

## 8. Sorprese: mapping Z e s (C0.4)

| Tipo | Z (Lewbel, T2) | s (meccanismo, T9) |
|---|---|---|
| FOMC | m_e = PC1 variazioni money-market <1y (ricalcolo da futures tassi se fattibile) | stessa m_e |
| ECB | LEVEL (Altavilla 2019) | LEVEL; PATH alimenta z_e |
| CPI | sorpresa **actual-vs-consensus** (`req08_cpi_surprise.csv`) | stessa |
| NFP | sorpresa **actual-vs-consensus** se la fonte esiste; consensus NFP esteso **non reperibile** ⇒ T2/T9 non alimentati per NFP (dichiarato) | stessa |

> **MAI ΔT5YIE (né altra componente del bond) come Z o s.** ΔT5YIE è la *reazione* del breakeven all'annuncio, non una sorpresa: i regimi sono definiti dalla correlazione equity-bond e il breakeven è componente del bond ⇒ usarlo come strumento è quasi tautologico (è il vizio del «CPI direzionale» già demolito). In più è *daily* mentre T2/T9 vivono a *frequenza-evento* (mismatch). **Opzione eliminata alla radice, non gateata a valle.**

**Gate C0.4:** se la copertura/varianza di Z è insufficiente per una cella → T2 registrato come *robustezza fallita dichiarata* (τ≈0, Lewbel muto). Se s è troppo rada/bassa varianza → T9 **non** si riempie per inferenza (resta aperto, dichiarato). Per **NFP** il consensus esteso è noto **non reperibile** ⇒ T2 e T9 non si alimentano per NFP e lo si dichiara — **T1/T5 (RS, variance-based) restano pienamente disponibili per NFP** perché non usano Z/s (NFP resta il primario confermativo di T5).

---

## 9. Kernel delicati — criteri di test (TDD obbligatorio)

1. **`mop_critical_value`** — algoritmo Montiel Olea–Pflueger (**bias relativo Nagar**, NON size — E1), K=1, τ=10%, nominale 5%, **calcolato** via Patnaik (x=1/τ, K_eff=1); NON Stock–Yogo 16.38. *Test (oracolo indipendente = valori pubblicati):* τ=10%→23.109, 5%→37.42, 20%→15.06, 30%→12.05; monotòno decrescente in τ; ≠16.38. ✅ implementato.
2. **`mop_effective_f`** = (ΔVar)²/V̂, con V̂ ai **quarti momenti** di r^b, **robusto e clusterizzato per evento** (annuncio + grappolo controlli non indipendenti). Per K=1 coincide con la Kleibergen–Paap rk Wald F robusta. *Test:* su DGP omoschedastico iid≈cluster≈classico. (Il clustering *corregge* V̂ per la dipendenza intra-evento — può alzare o abbassare F a seconda della struttura; nessun test impone una direzione.) *Caveat:* a n piccolo la V̂ bootstrap di ΔVar sottostima la vera ⇒ F_eff ottimista; impatta solo il display puntuale (routing), non l'inferenza AR (E2).
3. **`event_cluster_bootstrap`** — unità di ricampionamento = **evento** (porta con sé i suoi 3–10 controlli); gestisce il numero variabile di controlli; pooling come da C0.2. *Test:* recupero della varianza nota su DGP; numero controlli variabile non rompe il pooling.
4. **`ar_set` / `delta_ar_pvalue`** (la proiezione su Δ_H è in `delta_ar_pvalue`, non esiste `ar_projection`) — inversione di g(β)/se[g(β)] con g(β)=ΔCov−β·ΔVar e **lo stesso se robusto-clusterizzato**. Se l'insieme accettato tocca un estremo della griglia [−3, 7] si riporta come **aperto/illimitato** su quel lato, **non** troncato all'estremo. *Test:* copertura ~95% su DGP; cella a strumento debolissimo → set **illimitato segnalato** (non [−3,7] finito); coerenza con caveat T1(iii).
5. **`route_cell`** — puntuale sse (ΔVar>0 sig. via lower-bound CI 95%) ∧ (F_eff>cv_MOP) ∧ (n≥30); altrimenti AR-only. *Test:* tutte le combinazioni delle tre condizioni instradano correttamente; cella *rilevante-ma-debole* → AR-only.
6. **`hierarchical_by`** — NFP fuori correzione (α=0.05); {CPI,FOMC,BCE} BY q=0.10 con **m=3 fisso**; T4-fail = flip-non-rilevato (non-rigetto), **non** rimozione dalla famiglia. *Test:* m resta 3 anche con un tipo non testabile; soglia BY = i·q/(m·Σ_{k=1}^m 1/k); BY è **step-up** (può rigettare PIÙ di Bonferroni, NON è un suo sottoinsieme). *Caveat:* la χ²₁ di Δ_H è lievemente liberale in celle sottili omoschedastiche (size ~0.05–0.075 a n≈40–60) ⇒ cautela sui p secondari borderline; mitigata da n_min=30 e dalla congiunzione parte1∧parte2 di T5.
7. **`control_windows` DST-aware** — matching dei controlli sul **tempo locale di mercato** → UTC per-data con DST (§13bis). *Test:* nelle settimane di confine marzo/ottobre (DST US/EU non sincrone, ET–CET=5h) le finestre di controllo restano allineate all'ora locale corretta; un evento a cavallo del cambio DST **non** slitta di un'ora.

---

## 10. Smoke-test sintetico — 3 DGP (correzione #3)

`synthetic.py` genera dati dal modello `r^e = β r^b + u^e`, due regimi, finestre evento + controlli (varianza tassi maggiore in evento). **Nessun dato reale.** Tre scenari con criterio di pass:

| DGP | Costruzione | Comportamento atteso (pass) |
|---|---|---|
| **A. Flip strutturale** | β(pos) e β(neg) di **segno opposto**, σ_eb **invariante** | b_H flippa; T5 **rigetta** (Δ_H sig. ∧ CI lati opposti); routing classifica le celle forti come puntuali; copertura AR ~95% sotto i veri β. |
| **B. Nullo** | β **costante** tra regimi (nessuna stato-dipendenza), σ_eb qualsiasi | b_H **non** flippa; T4/T5 **non rigettano**; controllo della **size** (falsi-positivi ~ α); gerarchia BY non promuove nulla. |
| **C. Flip-del-bias** | β **costante**, ma **Δσ_eb cambia segno** tra regimi | b_H flippa **lo stesso** ⇒ la pipeline riporta un flip **osservato**; il codice **non** lo distingue dal caso A (T3 non discrimina; T5 caveat) ⇒ l'output etichetta il flip come *osservato e non identificato*, **non** come β-flip. Verifica che i caveat di identificazione siano prodotti correttamente. |

Il DGP C è la validazione in codice del cardine epistemico del protocollo: il sign-flip di b_H è prova sullo **stimatore**, non su β; un flip del bias lo genera ed è indistinguibile senza la via del bound (gated-off).

---

## 11. Provenienza e manifest (C0.6, R4)

`provenance.py` produce `manifest.json` con, per ogni tabella/cifra prodotta: hash dello script, hash degli input, **seed dichiarato**, timestamp (passato dall'esterno — niente `Date.now`/random non-seedato), versione config. Il manifest è la prova che ogni numero ha la catena script+input+seed.

---

## 12. Fuori scope esplicito

- β-flip strutturale puntuale e via del **bound** a frequenza-evento (curve intraday assenti).
- Decomposizione canali a frequenza-evento (solo daily, secondaria, etichettata).
- Stadio 2 (Kalman) — non pertinente al protocollo.
- Qualunque esecuzione sui dati reali in questa fase.
- Nuovi riferimenti di letteratura; modifica dei parametri locked.

---

## 13. Piano di consegna (ordine di implementazione)

0. **Fase 0 — ispezione (ESEGUITA 2026-06-21):**
   - ✅ Intraday completo 2010–2025 (`ESc1/TYc1` → 2025-12-31; `STXE` → 2025-10-03; `FGBL` → 2025-12-31). Niente gap "secondo batch".
   - ✅ Rendimenti daily per il regime: `r_ES, r_TY, r_STXE, r_FGBL` in `stock_bond_correlation_3m_6m_daily.csv` (cross-check) + derivabili da chiusura intraday.
   - ⚠️ **Calendario contaminanti: assente.** `events_calendar.csv` ha solo i 4 tipi principali, nessun contaminante, nessun rating ⇒ inservibile per C0.2. **Risolto con la decisione C0.2-calendar (sotto).**
1. `config.py`, `provenance.py`.
2. `data.py`, `windows.py`, `regimes.py`, `surprises.py` (+ test).
3. `estimators.py`, `weakiv.py` (+ test dei kernel delicati §9).
4. `inference.py` (bootstrap clusterizzato, routing, BY) (+ test §9).
5. `tests_protocol.py` (T1→T9).
6. `decomposition.py` (daily, etichettata).
7. `synthetic.py` + `run.py` + smoke-test 3 DGP (§10).
8. `README.md` + manifest.

---

## 13bis. Decisione C0.2-calendar (esclusione controlli) — CONGELATA

L'esclusione contaminanti è **pluggable**: `windows.control_windows` riceve un calendario-contaminanti come input.
- **Implementato in fase di scrittura codice (deterministico, no fonti esterne):** matching per ora del giorno; **esclusione jobless-claims = qualsiasi finestra di controllo che cada di giovedì alle 08:30 ET** (schedule fisso settimanale, "il borderline che pesa di più"); esclusione delle date-evento dei 4 tipi.
- **Input a tempo di esecuzione (da costruire prima del run, fetch esterni da autorizzare):** calendario contaminanti completo da **schedule di rilascio ufficiali** — FRED *releases* API (CPI, PPI, retail sales, GDP, PCE, durable goods + jobless settimanali) per le 08:30 ET; TreasuryDirect per le **aste major** (10/30y, refunding) alle 13:00 ET; testimonianze Fed *major* programmate. Snapshot **congelato** con fonte+data. La «importanza» è data dall'essere un rilascio macro ufficiale / asta major (proxy di rating *ex-ante*, non costruito su quanto l'evento ha mosso i mercati).
- **Razionale:** lo schedule ufficiale è più rigoroso e riproducibile di un rating commerciale, e copre esattamente i co-rilasci alla stessa ora (rischio dominante per le celle US 8:30).
- **Simmetria EU (razionale corretto):** la conferenza stampa BCE del pomeriggio (~14:30–14:45 CET) coincide grosso modo con le **08:30 ET**, ora dei rilasci macro US (NFP, CPI, PPI, retail). I contaminanti **dominanti** per i controlli delle celle ECB sono dunque proprio i rilasci US delle 8:30, **già catturati dal calendario US**. La priorità US è giustificata **da questa coincidenza d'orario**, NON perché dal lato europeo non cada nulla.
- **Contaminanti EU specifici a quell'ora (FRED non li copre → VERIFICARE e AGGIUNGERE per le celle ECB):** discorsi BCE pomeridiani; **aste sovrane euro pomeridiane** (Bund, BTP, OAT); eventuali rilasci EU pomeridiani. Non si saltano.
- **Matching orario DST-aware in UTC (requisito `windows.py`):** l'orario BCE è cambiato (decisione 13:45 → 14:15 CET) e le transizioni di ora legale US/EU **non sono sincrone** ⇒ in alcune settimane di marzo/ottobre la differenza ET–CET è **5 ore anziché 6**. Il matching «stessa ora» dei controlli si fa sul **tempo locale di mercato**, convertito in UTC **per-data con DST** (non tenendo costante l'ora-UTC del giorno), altrimenti le finestre slittano e il matching salta nei periodi di confine. *(`build_events_calendar.py` già converte local→UTC con DST per gli eventi; identico nella costruzione dei controlli.)*
- **Non blocca la scrittura del codice**; lo smoke-test sintetico non usa il calendario reale.

## 14. Rischi/dipendenze aperte

- **Calendario contaminanti C0.2** = input a tempo di esecuzione (vedi §13bis); da costruire con fetch esterni autorizzati prima del run dell'esecutore.
- **Sorpresa s per T9** e **Z per T2** — copertura/varianza potrebbero gateare T9/T2 (atteso e dichiarato).
- **Regime positivo sottile** (172 eventi, episodio inflazionistico) — molte celle pos potrebbero finire **AR-only** per n<30 o F<cv: è un esito previsto del routing, non un bug.
- **B bootstrap** = 10000 (congelato, §5).
- **Dedup controlli condivisi** (R3): chiuso in codice (`windows.dedup_shared_controls`, cablato in `run.run_protocol`) ⇒ indipendenza χ²₁ per costruzione; il manifest riporta sia il `dedup_shared` (quanti rimossi) sia lo `shared_control` post-dedup (atteso 0).
- **Guard ΔT5YIE** (E1/§8): cablato sul percorso reale — `surprises.surprise_source` auto-valida; `t2_lewbel`/`mechanism` accettano `source_label` validato; l'esecutore deve passare la sorgente via `surprise_source(t)`.
