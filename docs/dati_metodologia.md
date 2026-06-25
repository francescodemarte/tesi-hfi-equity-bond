# Dati e metodologia — capitolo

> Documento descrittivo del campione e della pipeline esistente. Nessuna nuova
> analisi né modifica ai dati. Tutti i numeri provengono da letture dirette
> dei file di dati e dei manifest delle pipeline già eseguite. Dove un dato non
> è disponibile, è marcato esplicitamente `non disponibile`.

---

## 1. Serie e fonti

### 1.1 Indice azionario USA

| campo | valore |
|---|---|
| ticker / RIC | `ESc1` (E-mini S&P 500 future, front month, rolling) |
| sorgente | Refinitiv Tick History (via Bocconi University) |
| frequenza nativa | 1-minute (mid-quote ricostruito) |
| file dato | `/home/francesco/TESI/Dati/data_processed/ESc1_1min.csv` |
| colonna prezzo | `PX_LAST` (mid = (Bid+Ask)/2 da `process_refinitiv_data.py`) |
| span effettivo | 2010-01-03 23:00 UTC → 2025-12-31 22:00 UTC |
| n osservazioni | 5 713 859 |

### 1.2 Indice azionario europeo

| campo | valore |
|---|---|
| ticker / RIC | `STXE` (Euro Stoxx 50 continuous, mid-quote) |
| sorgente | Refinitiv Tick History |
| frequenza nativa | 1-minute |
| file dato | `/home/francesco/TESI/Dati/data_processed/STXE_continuous_1min.csv` |
| colonna prezzo | `Mid_raw` (con anche `Mid_adjusted` e `contract_active`) |
| span effettivo | 2010-01-04 07:00 UTC → 2025-10-03 20:03 UTC |
| n osservazioni | 3 992 697 |

Esiste anche `VG1` con identica span e shape (3 992 697); è la serie equivalente Eurex VG. Convenzione del progetto: STXE è la serie usata nelle pipeline.

### 1.3 Curva Treasury USA

**Intraday**: disponibile **una sola scadenza** tramite futures. **Daily multi-scadenza**: presenti 4 punti via FRED snapshot.

**Intraday (per i rendimenti evento $r_b$)**:

| scadenza | RIC | sorgente | tipo | span |
|---|---|---|---|---|
| ~10Y (CTD 10Y) | `TYc1` (UST 10Y note future, front month) | Refinitiv Tick History | prezzo mid 1-min | 2010-01-03 23:30 → 2025-12-31 22:00 UTC (n=5 439 817) |
| 2Y / 3Y / 5Y / 7Y / 30Y intraday | — | — | — | **non disponibile** (no futures cash multi-scadenza intraday nel filesystem) |

**Daily (FRED snapshot — utili per controlli macro / verifica trasmissione lunga, NON usati per $r_b$ delle finestre evento)**:

| serie | sorgente | span | n_obs |
|---|---|---|---|
| `DGS10` (10Y nominal CMT) | FRED, snapshot in `Dati/external_data/fred_yields_snapshot.parquet` | 2003-01-02 → 2026-06-17 | 5 869 |
| `DFII5` (5Y TIPS) | idem | 2003-01-02 → 2026-06-17 | 5 869 |
| `T5YIE` (5Y breakeven) | idem | 2003-01-02 → 2026-06-18 | 5 870 |
| `T10YIE` (10Y breakeven) | `Dati/external_data/tips_breakeven_10y.csv` | 2003-01-02 → 2026-05-11 | 6 093 |
| `TEDRATE` (TED spread daily) | FRED — scaricato in questa sessione (`Dati/external_data/TEDRATE.csv`, sha256 `291d6007…`) | 1986-01-02 → **2022-01-21** (discontinued) | 9 407 (8 853 non-NaN) |
| 2Y / 30Y cash daily (DGS2, DGS30) | — | — | **non disponibile in questo filesystem** (recuperabile da FRED ma non scaricato) |

Per la curva *short-end money-market USA* (usata per costruire $m_e$ e $\Delta f_n$, non per la duration del bond) le serie effettivamente presenti sono:

| serie | RIC | descrizione | span |
|---|---|---|---|
| Fed Funds front-1 | `FFc1` | tasso atteso scadenza ~1M | 2010-01-03 21:39 → 2025-12-31 22:00 UTC (n=1 658 564) |
| Fed Funds front-2 | `FFc2` | scadenza ~2M | 2010-01-03 23:31 → 2025-12-31 22:00 UTC (n=3 394 255) |
| Fed Funds front-3 | `FFc3` | scadenza ~3M | 2010-01-03 23:30 → 2025-12-31 22:00 UTC (n=3 733 405) |
| SOFR 3M front-1 | `SRc1` | strumento alternativo | 2010-01-04 12:35 → **2013-09-16 15:01 UTC** (n=564 443, **discontinuato**) |
| SOFR 3M front-2 | `SRc2` | idem | 2010-02-08 12:58 → 2013-06-18 02:06 UTC (n=130 868) |

Per Treasury *daily* (FRED, snapshot esterno):

| serie | sorgente | span | n_obs |
|---|---|---|---|
| `DGS10` (10Y nominal) | FRED, snapshot in `/home/francesco/TESI/Dati/external_data/fred_yields_snapshot.parquet` | 2003-01-02 → 2026-06-17 | 5 869 |
| `DFII5` (5Y TIPS) | idem | 2003-01-02 → 2026-06-17 | 5 869 |
| `T5YIE` (5Y breakeven) | idem | 2003-01-02 → 2026-06-18 | 5 870 |
| `T10YIE` (10Y breakeven) | `/home/francesco/TESI/Dati/external_data/tips_breakeven_10y.csv` | 2003-01-02 → 2026-05-11 | 6 093 |

### 1.4 Curva Bund tedesca

**Intraday**: disponibile **una sola scadenza** tramite futures. **Daily event-window-based**: presenti TUTTI i punti 3M→30Y via Altavilla EA-MPD.

**Intraday (per i rendimenti evento $r_b$ ECB)**:

| scadenza | RIC | sorgente | tipo | span |
|---|---|---|---|---|
| ~10Y (CTD 10Y) | `FGBLc1` (Bund 10Y future, front month) | Refinitiv Tick History | prezzo mid 1-min | 2010-01-04 07:01 → 2025-12-31 21:03 UTC (n=4 065 541) |
| 2Y (Schatz, `FGBSc1`) intraday | — | — | — | **non disponibile** |
| 5Y (Bobl, `FGBMc1`) intraday | — | — | — | **non disponibile** |
| 30Y (Buxl, `FGBXc1`) intraday | — | — | — | **non disponibile** |

**Daily curva intera (event-window-based) — Altavilla EA-MPD 2019, estratta in questa sessione**:

| scadenza | colonna | n eventi non-NaN |
|---|---|---:|
| DE3M | `DE3M` | 315/315 |
| DE6M, DE1Y, DE2Y, DE3Y, DE4Y, DE5Y, DE6Y, DE7Y, DE8Y, DE9Y, DE10Y | `DE6M..DE10Y` | 315/315 |
| **DE15Y, DE20Y, DE30Y** | `DE15Y`, `DE20Y`, `DE30Y` | **315/315** |
| OIS curva 1W → 20Y (OIS_SW, OIS_1M, ..., OIS_20Y) | colonne OIS_* | 315/315 (OIS_10Y: 129/315, disponibile post-2007) |
| Indici equity (`STOXX50`, `SX7E`) | — | 315/315 |
| Cash sovereign 2Y/5Y/10Y per FR/IT/ES | `FR*`, `IT*`, `ES*` | 315/315 |

File congelati (3 finestre × CSV + provenance sidecar):

| finestra | path | n eventi | span |
|---|---|---:|---|
| Press Release Window | `Dati/external_data/altavilla_eampd_press_release_window.csv` | 315 | 1999-01-07 → 2025-11-09 |
| Press Conference Window | `Dati/external_data/altavilla_eampd_press_conference_window.csv` | 315 | idem |
| Monetary Event Window (combinata) | `Dati/external_data/altavilla_eampd_monetary_event_window.csv` | 315 | idem |
| **Fattori T/P/QE** (estratti per rotazione canonica) | `Dati/external_data/altavilla_TPQE_factors.csv` (sha256 `5a447263…`) | 315 (Target: 315; Path: 272; QE: 129) | idem |
| sidecar provenance | `altavilla_eampd_press_release_window.provenance.json`, `altavilla_TPQE_factors.provenance.json` | — | — |

**Importante** per il modello: la curva multi-scadenza Bund (3M→30Y) **esiste** come dato (event-window-based, daily); non esiste come **intraday** (solo FGBL 10Y future). Quindi i test sulla "trasmissione lunga" possibili a frequenza-evento ECB usando l'EA-MPD sono **daily** (cambio di yield sulla finestra dell'annuncio), non intraday 1-min.

**Caveat sul "test di simmetria Bund 30Y"**: nessuno script in `09_risultati/` o `CODICI_TESI/` osservato in questa sessione contiene riferimenti a `DE30Y` o `OIS_20Y`. Il dato grezzo è ora congelato, ma **nessun run è stato eseguito su questo asse** nel filesystem osservato.

Per il *short-end money-market in euro* (usato in costruzioni term-structure ECB):

| serie | RIC | descrizione | span |
|---|---|---|---|
| Euribor 3M front-1 | `FEIc1` | scadenza ~3M | 2010-01-04 00:45 → 2025-12-31 12:14 UTC (n=2 066 392) |
| Euribor 3M front-2 | `FEIc2` | ~6M | 2010-01-04 01:00 → 2025-12-31 12:14 UTC (n=2 050 358) |
| Euribor 3M front-3 | `FEIc3` | ~9M | 2010-01-04 00:45 → 2025-12-31 12:14 UTC (n=1 915 472) |
| Euribor 3M front-4 | `FEIc4` | ~12M | 2010-01-08 10:30 → 2025-12-31 12:14 UTC (n=1 881 376) |

### 1.5 Proxy di liquidità e volatilità

Proxy effettivamente usate nel pacchetto 13 (terzo canale residuo):

| candidato | proxy effettiva | sorgente | frequenza |
|---|---|---|---|
| **L** (liquidità funding) | $\Delta$ bid-ask spread post−pre, in bps, media ES + TY (pre-window [t-15,t-10] min; post-window [t+10,t+15] min) | Refinitiv Tick History (colonne `Bid`, `Ask` di `ESc1_1min.csv` e `TYc1_1min.csv`) | **intraday 1-min** |
| **L** (proxy alternativa, esplorativa) | $\Delta$ TED daily | FRED `TEDRATE`, `/home/francesco/TESI/Dati/external_data/TEDRATE.csv` (sha256 `291d6007…`) | daily; **discontinuato 2022-01-21** |
| **V** (volatilità) | $\Delta$ VIX daily | FRED `VIXCLS`, `CODICI_TESI/07_protocollo_v2_signflip/external_data/snapshots/VIXCLS.csv` | daily (span 1990-01-02 → 2026-06-17, n=9 210) |
| **V** intraday | — | — | **non disponibile** (VIX intraday non in filesystem; MOVE proprietary non recuperabile) |
| **C** (correlation) | correlazione realizzata 5-min ES~TY sul **giorno trading precedente** l'evento, con back-step fino a 7 gg | Refinitiv Tick History (`ESc1`/`TYc1` 1-min, aggregato a 5-min) | intraday (sul giorno trading precedente) |

### 1.6 Span complessivo del campione

Inizio: 2010-01-03 (data più antica fra le intraday).
Fine: 2025-12-31 (con caveat su STXE/VG1 che si fermano a 2025-10-03).

---

## 2. Campione di eventi

### 2.1 Calendario eventi — conteggi totali per classe

Dal file `DATASET_TESI/01_eventi_hfi/events_with_regime_classifier.csv` (sha256 `92215e6f…`):

| classe evento | n totali | prima data | ultima data | sorgente del calendario |
|---|---:|---|---|---|
| FOMC | 189 | 2010-01-27 | 2025-12-10 | `gemaf` (calendario interno integrato; non disponibile riferimento a fonte ufficiale singola) |
| CPI | 190 | 2010-01-15 | 2025-12-10 | `BLS` (Bureau of Labor Statistics, calendario rilasci) |
| NFP | 189 | 2010-02-05 | 2025-12-05 | `algorithmic` (primo venerdì del mese 12:30 UTC, validato vs BLS) |
| ECB | 287 | 2010-01-14 | 2025-09-11 | `ECB` (calendario monetary policy decisions, https://www.ecb.europa.eu/press/calendars/) |

### 2.2 ECB — finestra-decisione vs finestra-conferenza

Dal CSV (colonna `subtype`):

| subtype | n | prima data | ultima data | orari `time_utc` osservati |
|---|---:|---|---|---|
| `decision` (decisione di politica monetaria) | 143 | 2010-01-14 | 2025-09-11 | 12:45 UTC (principale), 11:45 / 12:15 / 13:15 (varianti DST/historical) |
| `press` (conferenza stampa successiva) | 144 | 2010-01-14 | 2025-09-11 | 13:30 UTC (principale), 12:30 / 12:45 / 13:45 (varianti DST/historical) |

### 2.3 Eventi entrati nelle celle del run autoritativo 07

Dopo l'algoritmo di assemblaggio (regime ricalcolato dal raw via rolling sign 63gg con lag 1; reject calendar contaminanti applicato), il pickle autoritativo
`09_risultati/v2_signflip/result_authoritative.pkl` (sha256 `a9c13a7b…`, label `v2_signflip_run_authoritative_2026-06-22_post_bug2`) riporta:

| classe | n positivo | n negativo | totale celle |
|---|---:|---:|---:|
| FOMC | 45 | 142 | 187 |
| CPI | 37 | 150 | 187 |
| NFP | 42 | 145 | 187 |
| ECB (decision + press aggregati) | 54 | 227 | 281 |
| **totale** | **178** | **664** | **842** |

I 13 eventi mancanti rispetto ai 855 del CSV grezzo sono quelli senza regime assegnabile (warm-up della finestra di 63 sedute) o respinti per dati mancanti.

### 2.4 Osservazioni di controllo (giorni non-evento)

I controlli sono ricostruiti per ciascun cluster del 07 ("regola 5/3/10": 5 sedute trading precedenti l'evento alla **stessa ora locale di mercato**, fallback se < 3 sopravvivono, tetto 10; reject calendar contaminanti applicato; DST-aware). Per cella, conteggio totale dei centri di controllo **post-dedup**:

| classe | n controlli (pos) | n controlli (neg) |
|---|---:|---:|
| FOMC | 223 | 688 |
| CPI | 139 | 562 |
| NFP | 153 | 574 |
| ECB | 256 | 994 |

Definizione operativa di "giorno non-evento": le stesse ore di mercato (08:30 ET per US events, 12:45 / 13:30 UTC per ECB) nei 5 giorni di trading precedenti l'evento, escludendo: (i) le date-evento stesse; (ii) i `jobless-Thursday` 08:30 ET; (iii) il calendario contaminanti aggregato (5 151 centri unici) in
`/home/francesco/TESI/Dati/calendari/contaminants_build_2026-06-22/contaminants_v2_2026-06-22.csv` (sha256 `0f69caa3…`), che include: FRED Releases (2 750), ECB speeches (944), aste BTP (656), aste Treasury (385), aste Bund (299), Fed testimonies (117).

Aste OAT francesi: **non disponibile** (`AUCTION_DATA_NOT_AVAILABLE_AFTER_FALLBACK` nel manifest del calendario contaminanti).

---

## 3. Costruzione delle finestre e dei rendimenti

### 3.1 Finestra evento (intraday)

| campo | valore |
|---|---|
| ampiezza | **±15 minuti** centrati sull'annuncio (finestra totale 30 min) |
| `HALF_MIN_WINDOW` | 15 (`CODICI_TESI/07_protocollo_v2_signflip/config.py:29`) |
| `MEDIAN_EDGE_MIN` | 5 (mediana dei prezzi nei primi/ultimi 5 minuti) |
| centraggio | `t_center = timestamp dell'annuncio in UTC` (CSV colonna `timestamp`) |

Il prezzo pre-evento è la **mediana** dei prezzi nei primi 5 minuti $[t-15, t-10]$; il post-evento è la mediana nei ultimi 5 minuti $[t+10, t+15]$. Convenzione tempo-based, non riga-based.

### 3.2 Rendimenti

| serie | formula |
|---|---|
| equity ($r_e$) | $\log(\text{post}/\text{pre})$ sui prezzi mid 1-min, finestra ±15 min |
| bond ($r_b$) | $\log(\text{post}/\text{pre})$ sui prezzi futures TY (US) / FGBL (EU) |
| forward rate ($\Delta f_n$, n=1,2,3) | $\text{post}-\text{pre}$ sui prezzi FF (US) / FEI (ECB), in punti percentuali (×$10^{-4}$ per conversione a decimale nelle pipeline 12/13) |

### 3.3 Deviazione dalla media condizionale

Nel pacchetto 13 ("terzo canale residuo"), la proxy $Z$ candidato viene
**ortogonalizzata** alla sorpresa specifica della cella (via OLS-residual) prima
della regressione sui residui $u_e, u_b$:

$$
\Delta Z_\perp = Z - \hat\beta_\text{OLS}(Z \mid \text{sorpresa}, \text{controlli})
$$

Funzione `proxies.orthogonalize(z, surprise=..., extra_controls=None)` del pacchetto 13. La "deviazione dalla media condizionale" è dunque applicata solo a Z, non a $r_e, r_b$ separatamente.

Sull'altro asse (residui equity-bond *strutturali*): la decomposizione del pacchetto 12 produce
$\tilde r_e = r_e - \Delta P^B_e$ e $\tilde r_b = r_b - \Delta P^B_b$ (cf. §5),
e il residuo "terzo canale" è $u_e = \tilde r_e - \beta_\text{str}\tilde r_b$,
$u_b = \tilde r_b - \tilde r_e/\beta_\text{str}$ (`residual.residuals`).

---

## 4. Sorprese

### 4.1 Mappa per pacchetto / test — distinzione critica

Le sorprese non sono usate uniformemente: ciascun pacchetto usa quella che gli serve. La tabella seguente è la mappa onesta cosa-usa-cosa.

| pacchetto / test | usa la sorpresa? | quale sorpresa | per cosa |
|---|---|---|---|
| 07 — T1 (gate forza/cv) | NO | — | gate basato su $\Delta\text{Var}/\Delta\text{Cov}$, niente $Z$ esogeno |
| 07 — T3 (ampiezza) | NO | — | $b_\text{OLS} - b_H$, descrittivo |
| 07 — T4 / T5 (sign-flip) | NO | — | proiezione AR su $\Delta_H$, niente $Z$ esogeno |
| 07 — T6 (specificità + Cochran Q) | NO | — | eterogeneità su $b_H$ per tipo |
| 07 — **T2 (Lewbel)** | **sì** | **CPI: `surprise_yoy` da req08** (vedi sotto); FOMC: PC1 money-market `m_e`; NFP: gated; ECB: gated | strumento generato per identificazione Lewbel |
| 07 — T9 (meccanismo 2 gambe) | sì | stessa di T2 (gated dove T2 è gated) | regressione per gamba |
| 12 — gate (a) F-MOP+shrink | NO | — | identificazione via varianza, niente $Z$ esogeno |
| 12 — gate (b) banda costruzione | NO | — | griglia coda × $\rho$, niente $Z$ esogeno |
| 12 — pre-check Nagel–Xu | sì | `surprise_per_event` (esecutore passa $m_e$ PC1) | verifica significatività della coda forward |
| 13 — terzo canale residuo | sì | **CPI: req08 `surprise_yoy`; FOMC: MP1 JK; NFP: $m_e$ (fallback dichiarato)** | ortogonalizzazione di $Z$ |

Quindi le **4 celle robuste** identificate dal pacchetto 12 (FOMC/neg, NFP/neg, CPI/neg, CPI/pos) **NON dipendono da $m_e$** per la classificazione `identified_robust`. Il gate (a) opera sui momenti $\Delta\text{Var}(\tilde r_b)$ e shrink, calcolati dai rendimenti netti, non dalla sorpresa. Quindi il "PASS tautologico da $m_e$ cieco al tratto lungo" temuto **non si applica al verdetto di robustezza del 12**.

### 4.2 Sorpresa per classe evento — dataset effettivamente disponibili

| classe | sorpresa primaria | costruzione | sorgente | span | n match con eventi |
|---|---|---|---|---|---|
| **CPI** | $\Delta\pi^{\text{srpr}}_{YoY}$ = `surprise_yoy` = `cpi_yoy_actual − cpi_yoy_consensus` | actual vs consensus mensile (BLS actual + survey consensus economisti) | `/home/francesco/TESI/tesi-hfi-equity-bond/bridge/data/req08_cpi_surprise.csv` (193 righe mensili, span 2010-01-31 → ...; sha256 `8021823f…`) | 2010-01-31 → ult. mese disponibile | **usata in T2 Lewbel 07** e in 13 (proper_surprises) per la cella CPI |
| **CPI** (alternativa) | $m_e$ = PC1 money-market | PC1 di $\Delta$FFc1, $\Delta$FFc2, $\Delta$FFc3 nella finestra evento | colonna `m_e` del CSV eventi | come eventi CPI | 170/190 (fallback, non più usato per CPI dopo correzione) |
| **FOMC** | MP1 (Jarociński–Karadi) | PC1 dei movimenti dei money-market futures in $[t-15, t+20]$ min, decomposto in target rate factor | `/home/francesco/TESI/Dati/external_data/jk_surprises_fomc.csv` | 1988-02-04 → **2024-01-31** | **114/189** (60.3% del campione); eventi FOMC 2024-09 → 2025-12 fuori dataset JK |
| FOMC (alternativa) | $m_e$ PC1 money-market | come CPI alternativa | colonna `m_e` del CSV | come eventi FOMC | 173/189; usata nel T2 Lewbel 07 (T2 FOMC: `feedable=False` per cancello copertura) |
| **NFP** | actual − consensus | survey consensus payrolls (Bloomberg/Action Economics) | **NON DISPONIBILE** nel filesystem | — | **0 / 189** |
| NFP (fallback dichiarato) | $m_e$ PC1 money-market | come sopra | colonna `m_e` | come eventi NFP | 182/189; **NFP T2 GATED** nel run autoritativo 07: `"consensus NFP non disponibile (SPEC §8)"` |
| **ECB** | **Target / Path / QE** (Altavilla et al. 2019) | rotazione $(\Delta\text{OIS}_{1M}^{\text{PR}}, \Delta\text{OIS}_{1Y}^{\text{PC}\perp T}, \Delta\text{OIS}_{10Y}^{\text{PC}\perp T,P})$ — vedi §1.4 | `DATASET_TESI/01_eventi_hfi/EA-MPD_ECB_Altavilla2019.xlsx`. **Estratto e congelato in questa sessione**: `/home/francesco/TESI/Dati/external_data/altavilla_eampd_*.csv` + `altavilla_TPQE_factors.csv` (sha256 `5a447263…`) | 1999-01-07 → 2025-11-09 (315 eventi) | Target 315/315; Path 272/315; QE 129/315 (OIS_10Y post-2007) |
| ECB nel run 07 attuale | (loader gated) | — | parser `loaders.load_ecb_level` *gated* | — | **ECB T2/T9 GATED** nel pickle autoritativo: `"Altavilla LEVEL parser gated"`. ECB **NON** è in `ROBUST_CELLS` del 13, quindi TPQE non entra nel run baseline del 13. **TPQE è ora disponibile come dato** per estensioni future. |

### 4.3 Riconciliazione con il modello

Il capitolo del modello (modello.tex) dichiara:
- CPI: sorpresa = actual − consensus YoY (o MoM). **Coerenza verificata**: il run autoritativo 07 nel T2 Lewbel usa esattamente `surprise_yoy` da `req08_cpi_surprise.csv` (vedi `execute.py:81` e `:115`); il pacchetto 13 con sorprese corrette (`proper_surprises`) usa la stessa fonte.
- FOMC: sorpresa = MP1 JK (target rate factor). **Coerenza parziale**: 114/189 eventi hanno match; 75/189 (post-2024-01) sono fuori arco JK e nel pacchetto 13 vengono scartati. **Lettura limitata al sottocampione 2010-01 → 2024-01.**
- ECB: sorpresa = Target/Path/QE Altavilla. **Coerenza ripristinata**: TPQE estratti in questa sessione (315 eventi); il parser del 07 resta gated → ECB non entra nei test del 13 finché il loader non è implementato. Il dato grezzo è ora disponibile.
- NFP: sorpresa = actual − consensus payrolls. **Incoerenza dichiarata**: consensus NFP non presente nel filesystem. Il run autoritativo 07 ha NFP T2/T9 gated. Il pacchetto 13 usa $m_e$ come fallback dichiarato.

### 4.4 Verifica osservata della disponibilità di $m_e$ (fallback)

Da letture dirette del CSV eventi (colonna `m_e`), utile per il pre-check Nagel–Xu del 12 e come fallback dichiarato nel 13:

| classe | n con $m_e$ non-NaN | n totale | copertura |
|---|---:|---:|---:|
| FOMC | 173 | 189 | 91.5% |
| CPI | 170 | 190 | 89.5% |
| NFP | 182 | 189 | 96.3% |
| ECB | 270 | 287 | 94.1% |

### 4.5 Esito del run 13 con sorprese specifiche (proper_surprises)

Per onestà del confronto, il pacchetto 13 è stato rieseguito in questa sessione con: CPI → `req08 surprise_yoy`; FOMC → MP1 JK; NFP → $m_e$ (fallback); proxy L intraday; q=0.10 pre-registrato. Output in `09_risultati/terzo_canale_residuo/proper_surprises/`. Sample:

| cella | clusters | scartati (no surprise) | n_finale (post proxy mask) |
|---|---:|---:|---:|
| FOMC/neg | 142 | 16 (no MP1 JK) | 113 |
| NFP/neg | 145 | 0 ($m_e$ fallback copre) | 136 |
| CPI/neg | 150 | 1 (no req08 match) | 133 |
| CPI/pos | 37 | 0 | 33 |

Esito: **0/12 terzo canale dichiarato a q=0.10 pre-registrato**, stesso risultato del run `intraday_L` precedente (che usava $m_e$ ovunque). Quindi la sostituzione di $m_e$ con la sorpresa di consenso corretta (per CPI) e con MP1 JK (per FOMC) non cambia qualitativamente l'esito: nessun "PASS tautologico" da $m_e$ viene scoperto.

---

## 5. Componente di tasso ($\Delta P^B$)

Pacchetto: `CODICI_TESI/12_decomposizione_canali/`.

> **Caveat dichiarativo da inserire nel capitolo metodologico**: il modello promette
> "somma ponderata delle variazioni dei forward lungo la curva". La realtà operativa
> è una somma su **3 punti osservati a brevissimo termine** (front money-market 1/2/3,
> scadenze ~1-3 mesi) **più una coda assunta** $T_0$/$T_C$/$T_{D,\lambda}$ per
> $n > 3$. È una semplificazione drastica rispetto a una curva osservata multi-scadenza,
> e va dichiarata esplicitamente. La banda di costruzione del pacchetto 12 (12 punti =
> 4 code × 3 $\rho$) tenta di propagare l'incertezza di questa scelta in $\beta_\text{str}$,
> ma non sostituisce dati osservati su scadenze lunghe della struttura a termine USA.
>
> Per ECB, la curva DE3M→DE30Y di Altavilla è ora disponibile come dato grezzo
> (§1.4), ma non è ancora cablata nel pacchetto 12.

### 5.1 Componente di tasso equity

$$
\Delta P^B_e = -\sum_{n=1}^{N} \rho^{n-1} \cdot \Delta f_n
$$

| parametro | valore | provenance |
|---|---|---|
| $N$ (orizzonte di troncamento) | 100 | parametro esposto dall'esecutore; valore canonico |
| $\rho$ (fattore Campbell-Shiller) | $\rho_a = 1/(1 + e^{\bar{dp}}) = 0.979164$ | da `equity_pb.rho_from_dp_bar(dp_bar)` |
| $\bar{dp}$ (log dividendo-prezzo) | **−3.85 (canonico esterno, NON calibrato sui dati)** | pre-registrato; corrisponde a $D/P \approx 2.1\%$ media S&P 500 |
| scadenze osservate ($m$) | **3 punti soltanto**: $\Delta f_1, \Delta f_2, \Delta f_3$ — front money-market FFc1/FFc2/FFc3 (USA, scadenze ~1-3 mesi); FEIc1/FEIc2/FEIc3 (ECB) | colonne `delta_rate_1..3` del CSV eventi |
| coda per $n > m$ (4 punti) | $T_0$: zero; $T_C$: costante a $\Delta f_m$; $T_{D,\lambda=0.5}$, $T_{D,\lambda=0.8}$: decadimento $\lambda^{n-m}$ | `config.TAIL_GRID = (T0, TC, TD_0.5, TD_0.8)` |
| griglia $\rho$ (3 offset) | $-0.25, 0.0, +0.25$ su $\bar{dp}$ | `config.RHO_OFFSETS` |
| griglia totale per evento | 4 code × 3 $\rho$ = **12 punti** | `config.GRID_POINTS_PER_EVENT = 12` |

Il "punto centrale" T0, $\rho$ calibrato (cioè offset 0.0) è quello usato per il calcolo di $\beta_\text{str}$ e dei residui $u_e, u_b$ del pacchetto 13.

### 5.2 Componente di tasso bond

$$
\Delta P^B_b = -D_\text{bond} \cdot \Delta y_\text{bond}
$$

| parametro | valore |
|---|---|
| $D_\text{bond}$ (duration UST 10Y) | **8.970866** (costante, dal CSV `events_with_regime_classifier.csv` colonna `D_bond`) |
| $\Delta y_\text{bond}$ (proxy long-end) | `delta_rate_3` (Δ front-3 del paniere money-market) in decimale (÷10 000) — proxy via term structure |
| coda | nessuna (cash-flow finiti — lettura diretta) |

**Convenzione esplicita (asimmetria evento/controllo)**: nelle finestre di controllo $\Delta P^B_e = \Delta P^B_b = 0$ *by construction* (non c'è annuncio → niente componente di tasso da sottrarre). L'evento viene "depurato" dal canale di tasso, il controllo conserva il rumore di tasso non legato all'annuncio. Dichiarata anche nel `replicability_assumption` del manifest del pacchetto 12.

---

## 6. Celle e classificazione

### 6.1 Celle analizzate dal pacchetto 12

Dieci celle (tipo × regime), con ECB separato in decision / press:

| cella | n | F-MOP | shrink | gate (a) | verdetto |
|---|---:|---:|---:|:---:|---|
| FOMC/neg | 117 | 39.183 | 0.648 | **PASS** | `identified_robust` |
| FOMC/pos | 40 | 11.499 | 0.551 | FAIL | `channel_not_identified` |
| NFP/neg | 126 | 39.040 | 0.535 | **PASS** | `identified_robust` |
| NFP/pos | 38 | 19.641 | 0.471 | FAIL | `channel_not_identified` |
| CPI/neg | 126 | 33.230 | 0.595 | **PASS** | `identified_robust` |
| CPI/pos | 33 | 23.545 | 0.491 | **PASS** | `identified_robust` |
| ECB_decision/neg | 70 | 10.110 | 0.972 | FAIL | `channel_not_identified` |
| ECB_decision/pos | 23 | 5.647 | 0.569 | FAIL | `channel_not_identified` |
| ECB_press/neg | 63 | 10.740 | 0.501 | FAIL | `channel_not_identified` |
| ECB_press/pos | 20 | 3.227 | 0.549 | FAIL | `channel_not_identified` |

Fonte: `09_risultati/decomp_canali/decomp_canali.report.json` (campo `table_section_6_per_cell`).

### 6.2 Soglie pre-registrate

| soglia | valore | significato |
|---|---:|---|
| MOP cv (Nagar bias 10%, K=1, Patnaik) | **23.1085** | soglia primaria del gate (a) |
| MOP cv (bias 15%) | 17.8662 | sensitivity riportata, non blocking |
| MOP cv (bias 20%) | 15.0616 | idem |
| F practical | 10.0 | regola pratica Staiger-Stock |
| `SHRINK_FLOOR` | 0.05 | shrink minimo per gate (a) |
| `BAND_WIDTH_THRESHOLD` (b) | 0.30 | larghezza banda per `robust` vs `fragile` |

### 6.3 Celle "robuste" entrate nel pacchetto 13

`config.ROBUST_CELLS = (("FOMC","neg"), ("NFP","neg"), ("CPI","neg"), ("CPI","pos"))`. Sono esattamente le 4 celle con `gate (a) = PASS` e `verdict = identified_robust` nel pacchetto 12. Coerenza inter-pacchetto verificata.

### 6.4 Classificazione finale (pacchetto 12)

- **`identified_robust`** = 4 celle: FOMC/neg, NFP/neg, CPI/neg, CPI/pos.
- **`identified_fragile`** = 0 celle (nessuna cella ha PASS gate(a) + WARN/banda larga sotto le soglie attuali).
- **`channel_not_identified`** = 6 celle: FOMC/pos, NFP/pos, ECB_decision/{pos,neg}, ECB_press/{pos,neg}.

### 6.5 Esito pacchetto 13 (terzo canale residuo, sulle 4 robust cells)

Sotto **q = 0.10 pre-registrato**, sign rule rivista "antisymmetric" (variante 2a), e proxy L intraday vera ($\Delta$ bid-ask spread post−pre, media ES+TY):

| cella × candidato | n | $\lambda_e$ | $\lambda_b$ | $p_\text{comm}$ | comm | sign_ok | terzo canale |
|---|---:|---:|---:|---:|:---:|:---:|:---:|
| FOMC/neg \| L | 113 | +0.0000 | −0.0000 | 0.911 | False | None | False |
| FOMC/neg \| V | 113 | −0.0001 | +0.0001 | 0.502 | False | None | False |
| FOMC/neg \| C | 113 | +0.0018 | −0.0020 | 0.250 | False | None | False |
| NFP/neg \| L | 136 | +0.0027 | +0.0019 | 0.158 | False | None | False |
| NFP/neg \| V | 136 | −0.0004 | −0.0002 | 0.083 | False | None | False |
| NFP/neg \| C | 136 | −0.0001 | −0.0001 | 0.941 | False | None | False |
| CPI/neg \| L | 134 | −0.0006 | +0.0006 | 0.404 | False | None | False |
| CPI/neg \| V | 134 | +0.0000 | −0.0000 | 0.978 | False | None | False |
| CPI/neg \| C | 134 | +0.0007 | −0.0007 | 0.315 | False | None | False |
| CPI/pos \| L | 33 | +0.0013 | −0.0006 | 0.777 | False | None | False |
| CPI/pos \| V | 33 | −0.0004 | +0.0002 | 0.147 | False | None | False |
| CPI/pos \| C | 33 | −0.0011 | +0.0005 | 0.711 | False | None | False |

Totale: **0 / 12** dichiarazioni di terzo canale a soglia pre-registrata, proxy onesta. Fonte: `09_risultati/terzo_canale_residuo/intraday_L/all_with_intraday_L/verdicts.json`.

---

## 7. Software e riproducibilità

### 7.1 Stack

| componente | versione |
|---|---|
| Python | 3.11.15 (`/home/francesco/miniconda3/envs/quant/bin/python3`) |
| numpy, pandas, scipy | usate; versioni esatte **non disponibile in questo documento** (assenti dai manifest, recuperabili da `conda list` nell'ambiente `quant`) |
| pytest | 9.0.3 |

### 7.2 Pacchetti del codice (interno al repository)

| pacchetto | path | test verdi |
|---|---|---:|
| 07 — protocollo v2 sign-flip | `CODICI_TESI/07_protocollo_v2_signflip/` | 175 |
| 08 — spillover Fed → area euro | `CODICI_TESI/08_spillover_fed_eu/` | 68 |
| 10 — diagnostica canale tassi | `CODICI_TESI/10_diagnostica_canale_tassi/` | 45 (39 originali + 6 term-structure) |
| 11 — pratica eccesso di comovimento | `CODICI_TESI/11_pratica_eccesso_comovimento/` | 51 |
| 12 — decomposizione canali (doppio cancello) | `CODICI_TESI/12_decomposizione_canali/` | 46 |
| 13 — terzo canale residuo | `CODICI_TESI/13_terzo_canale_residuo/` | 40 (post-revisione spec §3 "antisymmetric") |
| **totale** | — | **425** |

### 7.3 Seed e schema RNG

- `MASTER_SEED = 20260621` (uguale in tutti i pacchetti del protocollo per coerenza dei bootstrap clusterizzati).
- Schema seeding: `np.random.SeedSequence([MASTER_SEED, blake2b(name)])` → `np.random.default_rng(...)`. La stringa `name` è dichiarata per ciascun run e il valore intero corrispondente è scritto nel manifest (`seed_for(name)`).
- Esempi di nomi-seed osservati nei manifest:
  - `execute_v2_signflip_2026-06-22` (pacchetto 07, seed value 3 993 785 275)
  - `decomp_canali_2026-06-23` (pacchetto 12)
  - `pratica_baseline_2026-06-23` (pacchetto 11)
  - `terzo_canale_intraday_L_2026-06-24` (pacchetto 13, run intraday-L)

Il pacchetto 11 usa `MASTER_SEED = 20260622` (giorno successivo, dedicato per separazione di provenance fra il blocco strategia e il blocco protocollo).

### 7.4 Repository del codice

`/home/francesco/TESI/tesi-hfi-equity-bond/` (locale). Stato di versionamento Git: **non disponibile** in questo documento (l'ambiente è marcato `Is a git repository: false` nel session bootstrap; nessun repository remoto pubblicato è dichiarato nei manifest osservati).

### 7.5 Manifest di provenance

Per ogni run delle pipeline è scritto un manifest JSON che include: `config_version`, `config_hash` (sha256 dello snapshot dei parametri), `seed.value`, `timestamp` esterno (passato dall'invocazione, non da clock interno), `sha256` di ogni file di input, `sha256` di ogni modulo di codice eseguito. I manifest sono in:

- `09_risultati/v2_signflip/manifest_authoritative.json` (pacchetto 07)
- `09_risultati/spillover_fed_eu/manifest_authoritative.json` (pacchetto 08)
- `09_risultati/pratica_eccesso_comov/pratica_baseline.manifest.json` (pacchetto 11)
- `09_risultati/decomp_canali/decomp_canali.manifest.json` (pacchetto 12)
- `09_risultati/terzo_canale_residuo/intraday_L/intraday_L_manifest.json` (pacchetto 13, run finale onesto)

### 7.6 Convenzioni temporali

- Tutti i timestamp sono **UTC**.
- Finestre evento centrate sull'orario UTC dell'annuncio (NOT locale).
- I controlli sono assegnati alla **stessa ora locale di mercato** dei giorni di trading precedenti (DST-aware: stessa ora locale ⇒ UTC diverso a seconda della data; vedi `_same_local_time_utc` in `07_protocollo_v2_signflip/windows.py`).
- Calendario contaminanti: timestamp UTC dei centri (5 151 unici), formato `centro_utc`.

---

## Indice delle "non disponibili" — riassunto (versione aggiornata)

Per trasparenza, l'elenco esplicito di dove un dato non è stato reperito o fissato (e non è stato stimato).

### Effettivamente non disponibile (gap che restano)

1. **Curva Treasury cash multi-scadenza INTRADAY** (2Y, 5Y, 7Y, 30Y intraday): solo TY 10Y future presente. **Daily** è parziale (DGS10, DFII5 via FRED snapshot; mancano DGS2, DGS5, DGS30).
2. **Curva Bund INTRADAY multi-scadenza** (Schatz/Bobl/Buxl): solo FGBL 10Y future presente. *(Daily multi-scadenza DE3M..DE30Y è ora disponibile via Altavilla EA-MPD, vedi §1.4.)*
3. **VIX intraday e MOVE** (intraday e daily): non presenti nel filesystem. ΔVIX **daily** è il fallback dichiarato per V nel pacchetto 13.
4. Aste **OAT francesi** nel calendario contaminanti: `AUCTION_DATA_NOT_AVAILABLE_AFTER_FALLBACK`.
5. **Sorpresa "actual − consensus" NFP** (Bloomberg/Action Economics consensus): non in filesystem. NFP T2 del 07 è gated; il pacchetto 13 usa $m_e$ come fallback dichiarato.
6. **SOFR** (`SRc1`, `SRc2`): discontinuati al 2013, non utilizzabili post-2013.
7. **Sorpresa FOMC MP1 JK post-2024-01-31**: 75/189 eventi FOMC (Sep 2024 → Dec 2025) sono fuori dal dataset JK. Letture FOMC con sorpresa MP1 sono limitate al sottocampione 2010-01 → 2024-01.
8. **Versioni esatte di numpy/pandas/scipy**: non dichiarate nei manifest osservati.
9. **Stato Git e repository remoto**: non disponibile in questa sessione (`Is a git repository: false`).

### Riempiti in questa sessione (ex "non disponibile", ora congelati)

A. **Altavilla EA-MPD 2019 (Target/Path/QE per ECB e curva DE3M..DE30Y)** — il dato grezzo era già in `DATASET_TESI/01_eventi_hfi/EA-MPD_ECB_Altavilla2019.xlsx` ma non era stato estratto. Estratto e congelato come 3 CSV (Press Release / Press Conference / Monetary Event Window) + fattori T/P/QE canonici (Target via OIS_1M PR; Path via OIS_1Y PC orth Target; QE via OIS_10Y PC orth Target+Path) in `Dati/external_data/altavilla_TPQE_factors.csv` (sha256 `5a447263…`). Copertura: Target 315/315; Path 272/315; QE 129/315. **Il parser del 07 resta gated**: integrare TPQE nel T2/T9 del 07 e nel pacchetto 13 richiede un giro coder.

B. **TED daily** (FRED `TEDRATE`) — scaricato e congelato in `Dati/external_data/TEDRATE.csv` (sha256 `291d6007…`). Span 1986-01-02 → **2022-01-21** (discontinued). Usato come proxy L *daily alternativa* nel run esplorativo del 13.

C. **Proxy L intraday vera** (Δ bid-ask spread post-pre, media ES+TY) — costruita dai dati già presenti (colonne `Bid`/`Ask` delle 1-min CSV; l'agente di ricerca dati le aveva sottovalutate). Usata nel run finale onesto del 13.

D. **Esito 13 con sorprese corrette a q=0.10** — eseguito in questa sessione (`09_risultati/terzo_canale_residuo/proper_surprises/`). CPI con req08, FOMC con MP1 JK, NFP con $m_e$ fallback dichiarato. Risultato: 0/12 third_channel — la sostituzione di $m_e$ con la sorpresa corretta non ravviva alcun PASS.

### Riconciliazione modello ↔ pipeline (sintesi)

| asse | modello dichiara | pipeline ha fatto | divergenza | azione presa |
|---|---|---|---|---|
| Sorpresa CPI | actual − consensus YoY | T2 07: req08 surprise_yoy; 13 (intraday_L): $m_e$ → corretto a req08 nel run `proper_surprises` | CPI ok in 07; nel 13 sostituzione applicata | run `proper_surprises` |
| Sorpresa ECB | Target/Path/QE (Altavilla) | T2 07: gated; 13: ECB non in ROBUST_CELLS | parser gated → ECB non testato col 13 | dato TPQE estratto e congelato; integrazione richiede coder |
| Sorpresa NFP | actual − consensus | T2 07: gated; 13: $m_e$ fallback | consensus assente | dichiarazione esplicita; nessun rimedio possibile in questa sessione |
| Sorpresa FOMC | MP1 JK | 13: MP1 JK | OK per 114/189 eventi 2010-01 → 2024-01 | dichiarazione del sottocampione |
| Curva forward $\Delta f_n$ | "lungo la curva" | 3 punti front money-market + coda assunta | drastica semplificazione | dichiarata nel §5 caveat box; curva Bund daily ora disponibile via Altavilla per estensioni future |
