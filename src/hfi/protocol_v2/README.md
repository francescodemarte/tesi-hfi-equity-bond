# Protocollo v2 sign-flip — pipeline pre-registrata (codice agente 3)

Traduzione in codice **pre-registrato, con seed fissi, deriverabile** del
[protocollo v2](../../02_metodologia/preregistrazione_v2_protocollo_test.md).
Specifica di controllo: [`SPEC_codice_v2_signflip_2026-06-21.md`](SPEC_codice_v2_signflip_2026-06-21.md).

## Catena di custodia
agente 2 (lista test) → **AGENTE 3 (questo codice)** → agente 4 (review) →
verifica coerenza vs v2 → **esecutore** (run sui dati reali) → verifica umana finale.

**Stato:** codice congelato + **smoke-test sintetico** verde. **Nessuna esecuzione
sui dati reali** è stata fatta (la fa l'esecutore dopo la review): preserva la
pre-registrazione.

## Scope (vedi SPEC §1 e §2bis)
- **In scope:** via descrittivo-strutturale su **b_H** (Rigobon–Sack due regimi),
  con b_OLS e b_L (Lewbel) di confronto; inferenza primaria su **Anderson–Rubin**
  (E2); gerarchia BY; T1–T9; decomposizione canali **daily** come evidenza
  secondaria etichettata.
- **Fuori scope (data-gated):** β-flip strutturale / via del bound a frequenza-evento.
- **Emendamenti pre-test:** **E1** cv MOP = bias relativo di Nagar (23.109, NON "size"),
  **E2** inferenza AR per T4/T5 anche in celle forti (Andrews 2018; ASS 2019).

## Mappa moduli
| Modulo | Ruolo |
|---|---|
| `config.py` | parametri CONGELATI, seeding riproducibile, hash config |
| `provenance.py` | manifest (script+input+seed) + drop-log controlli |
| `data.py` | loader intraday/eventi + rendimenti daily |
| `windows.py` | finestre evento/controllo (DST-aware), assemblaggio + drop-log, diagnostica controlli condivisi |
| `regimes.py` | regime dal raw (corr 63gg, lag t-1, segno) — anti-look-ahead |
| `surprises.py` | mapping Z/s (mai ΔT5YIE) + gate C0.4 |
| `estimators.py` | b_OLS, b_H=ΔCov/ΔVar, b_L Lewbel |
| `weakiv.py` | cv MOP (Nagar, calcolata), F efficace, AR-set, ar_pvalue, delta_ar_pvalue |
| `inference.py` | bootstrap clusterizzato per evento, routing R5, BY gerarchica, Cochran Q |
| `tests_protocol.py` | T1–T8 (T5 centrale: AR, R1, state_dep=testabilità) |
| `mechanism.py` | T9 — due gambe ∂r/∂s, β_impl (gated) |
| `decomposition.py` | canali DAILY (secondaria, etichettata) |
| `synthetic.py` | 3 DGP per lo smoke (flip strutturale / nullo / flip-del-bias) |
| `run.py` | orchestratore per l'ESECUTORE (sui dati reali) |

## Come si esegue
- **Smoke + unit (agente 3 / agente 4):** `python3 -m pytest tests/ -q` → tutti verdi.
  In particolare `tests/test_smoke.py` valida i 3 DGP: A flip rilevato, B nullo
  (size), **C flip-del-bias rilevato ma non identificato** (cardine epistemico).
- **Esecuzione reale (esecutore):** `run.run_protocol(...)` / `run.assemble(...)`
  sui dati in `/home/francesco/TESI/Dati/data_processed/` + `DATASET_TESI/`.
  `run.main()` è volutamente bloccato (l'esecuzione reale è step successivo).

## Cosa deve fornire l'esecutore (decisione C0.2-calendar, SPEC §13bis)
La parte deterministica delle esclusioni controlli è in `run.build_calendar_reject`
(date-evento + jobless-Thursday 08:30 ET). Il **calendario contaminanti completo**
(US: FRED releases + aste Treasury major + testimonianze Fed major; **EU, per le
celle ECB: discorsi BCE pomeridiani + aste sovrane euro pomeridiane — Bund, BTP,
OAT** — non solo i discorsi, altrimenti i controlli euro restano scoperti su quel
fronte) va costruito come snapshot **congelato con provenienza** e passato come
`contaminant_centers` — fetch esterni da autorizzare (§13bis).

**Contratto-dati che l'esecutore conferma (#10):** `event_class` ∈ {FOMC, CPI, NFP,
**ECB**} (non "BCE"); le colonne intraday sono `Datetime_UTC` + il prezzo per simbolo
(`PX_LAST`, `Mid_raw` per STXE) come da `config.INTRADAY_FILES`; `PX_LAST` assunto =
mid-quote (costruzione (Bid+Ask)/2 a monte). Ogni sorgente Z/s va passata via
`surprises.surprise_source(t)` (auto-validante contro ΔT5YIE).

## Disciplina di qualità
- **TDD** su tutta la logica (RED→GREEN); kernel delicati testati contro valori
  analitici/pubblicati (cv MOP → 23.109).
- I kernel sviluppati in parallelo (estimators, inference, mechanism, synthetic,
  decomposition) sono stati **verificati con oracolo indipendente** (ricalcolo per
  via diversa, non una seconda esecuzione della stessa logica).
- Parametri **immutabili** dopo il congelamento; robustezze = i quattro chiusi di T8.
