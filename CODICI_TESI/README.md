# CODICI_TESI — Pipeline replicabile

> *"High-Frequency Identification of Equity-Bond Comovement: A Regime-Dependent Version of the Present-Value Test"*
> Tesi LM Finance, Bocconi 2026 — Francesco De Marte

**Ultimo aggiornamento**: 2026-05-12

Tutti i file sono symlink alle versioni di sviluppo in `/home/francesco/TESI/Dati/codes/stage1_v2/`. La struttura segue il piano operativo descritto in `direction_I_synthesis_plan_2026_05_11.md`.

---

## Pipeline operativa (eseguire in ordine)

### 00_helpers/ — Infrastruttura

| File | Cosa fa |
|---|---|
| `gemaf_db.py` | Connection helper a Postgres locale `gemaf_stage` (DB 5433 TimescaleDB Docker). Espone `conn()`, `query(sql)`, `execute(sql)` |
| `load_comp_global_to_gemaf.py` | Carica `query_1.csv.gz` (Compustat Global raw 647k) in `tesi.comp_global_annual` + crea materialized view EU-15 |
| `run_wrds_query.py` | Esegue query SQL su WRDS direttamente via `wrds-python` (richiede credenziali persistent, NON funziona con one-day access Bocconi) |

### 01_yield_decomp/ — Step 1: Gormsen-Lazarus 2026 yield decomposition

| File | Riferimento metodologico | Cosa fa |
|---|---|---|
| `step1_gl_yield_decomp.py` | GL2026 §5.4 eq. (22)-(23), Tabella 5 | Inverte il sistema $\Delta y = \Delta\rho + \gamma\Delta g + \beta\Delta\text{VIX}^2$ e $r^{mkt} = \pi_\rho\Delta\rho + \pi_g\Delta g + \pi_V\Delta\text{VIX}^2$ usando parametri Table B.1+Table 2 GL2026. Output: $\Delta\rho_t$ recovered per ciascun FOMC event. **Risultato attuale**: validation parziale — replica signs di GL Table 5 ma magnitudine off (β·π_ρ amplification post-2010). Richiede ri-calibrazione con SPF data — **TODO** |

### 02_regime_classifier/ — Step 4: BPY 2025 regime conditioning

| File | Riferimento metodologico | Cosa fa |
|---|---|---|
| `step4_regime_classifier_bpy.py` | BPY 2025 §3.1 eq. (2) | Costruisce $\tilde\rho_{t-1}$ = rolling 3-month correlation stock-bond standardized lagged. Test interazione $\beta^{EB}_t \cdot \tilde\rho_{t-1}$ in event-study. **Risultato**: NFP sign flip cross-regime replicato (β: -1.05 low ρ̃ → +0.51 high ρ̃) |
| `step4b_robustness.py` | — | Robustness 3M vs 6M rolling window + US vs EU classifier. **Tutti i findings preservati** |

### 03_pv_test/ — Step 5: PV consistency test (CORE)

| File | Riferimento metodologico | Cosa fa |
|---|---|---|
| `step5_pv_consistency.py` | Beltratti-Shiller 1992 extended HFI + IV identification via BS 2023a | 4 specifiche del PV consistency test: Spec 1 raw $r_{eq}\sim r_{bond}$, Spec 2 H₀ $\beta=1$ normalized, Spec 3 + regime interaction, Spec 4 IV con mps⊥ instrument. **5 findings principali** — vedi `99_validation_outputs/step5_pv_consistency_2026_05_11.md` |

### 04_ecb_extension/ — Step 6: ECB extension via EA-MPD

| File | Riferimento metodologico | Cosa fa |
|---|---|---|
| `step6_ecb_eampd.py` | Altavilla et al. 2019 JME LEVEL/PATH framework + Direction I synthesis | Applica PV consistency test (Step 5) ai 147 ECB events EA-MPD 2010-2025. Test cross-window (Press Release vs Press Conference) e cross-regime. **Findings**: Stoxx duration ≈ 5y NON 18y; Multi-CB asymmetry Fed 2.1× vs ECB 1.5× cross-regime |

### 05_cross_section/ — Step 8: cross-section equity duration

| File | Riferimento metodologico | Cosa fa |
|---|---|---|
| `build_stoxx600_universe.sql` | Offner 2026 + Gormsen-Lazarus 2023, sostituzione IBES LTG con Compustat-based proxies | Costruisce panel firm-year EU non-financial con 4 duration proxies: $D_1=P/D$ (Gordon inverse), $D_2=M/B$, $D_3=$ retention ratio, $D_4=g_{5y}$ historical earnings growth. Composite z-score standardizzato per sector-year. Top 600 firms per avg market cap 2020-2024 → `tesi.stoxx600_universe` |

### 06_legacy_stadio1_stadio2/ — Stadio 1+2 originale settembre-maggio

Andrà in appendice A della tesi come "operational extension". Contiene:
- **Pipeline Stadio 1**: `pipeline.py`, `pipeline_regimes.py`, `identification.py`, `duration.py`, `regression.py`, `placebo.py`, `robustness.py`, `primary_spec.py`
- **Stadio 2 Kalman**: `stage2_kalman.py` (1287 LOC), `stage2_robustness.py`, `stage2_logratio_ekf.py`
- **OOS validation**: `oos_validation.py`, `oos_validation_v2.py`
- **Applicazioni operative**: `application_hedge_ratio.py` (v1,v2,v3), `application_regime_signals.py`, `regime_aware_hedge.py`
- **Robustezze laterali**: `m_e_robustness.py`, `run_freq_robustness.py`

### 99_validation_outputs/ — Report markdown intermedi

Report dei findings di ogni step, da convertire in capitoli LaTeX:
- `direction_I_synthesis_plan_2026_05_11.md` — piano operativo 8 step
- `lit_review_direction_I_2026_05_11.md` — analisi preemption (v3, post-lettura 4 paper)
- `step1_validation_2026_05_11.md` — yield decomposition GL2026
- `step4_regime_bpy_2026_05_11.md` — regime classifier BPY
- `step4b_robustness_2026_05_11.md` — 3M/6M + US/EU robustness
- `step5_pv_consistency_2026_05_11.md` — PV consistency test CORE
- `step6_ecb_eampd_2026_05_12.md` — ECB extension

---

## Riproducibilità

Per ri-eseguire l'intera pipeline da zero (richiede DB `gemaf_stage` attivo su `localhost:5433` + dati in `DATASET_TESI/`):

```bash
# Setup helpers
cd /home/francesco/TESI/tesi-hfi-equity-bond/CODICI_TESI/00_helpers
python3 gemaf_db.py   # test connection

# (One-time) Caricamento dataset Compustat Global
python3 load_comp_global_to_gemaf.py

# (One-time) Setup stoxx600 universe
psql -h 127.0.0.1 -p 5433 -U gemaf_tsdb -d gemaf_stage -f ../05_cross_section/build_stoxx600_universe.sql

# Pipeline analitica
python3 ../01_yield_decomp/step1_gl_yield_decomp.py
python3 ../02_regime_classifier/step4_regime_classifier_bpy.py
python3 ../02_regime_classifier/step4b_robustness.py
python3 ../03_pv_test/step5_pv_consistency.py
python3 ../04_ecb_extension/step6_ecb_eampd.py
```

---

## Dipendenze Python (conda env `quant`)

- `numpy`, `pandas`, `scipy`, `statsmodels`
- `psycopg2-binary`, `sqlalchemy`
- `pypdf` (lettura paper)
- `yfinance` (download index data)
- `openpyxl` (lettura .xlsx)
- `pyarrow` (output parquet)
- `wrds` (solo se WRDS credentials persistenti disponibili)

---

## Note metodologiche

Ciascuno script ha un header dettagliato che documenta:
1. **Riferimento al paper** che implementa/estende
2. **Equazione precisa** del paper riprodotta
3. **Output prodotto** + posizione del salvataggio
4. **Test statistico** + ipotesi nulla
5. **Riferimento al capitolo della tesi** dove i risultati appariranno

Le tabelle e plot prodotti dai questi script entrano direttamente in:
- Cap. 5: `step5_pv_consistency_2026_05_11.md` → naive HFI PV test
- Cap. 7: Steps 5+6 outputs → PV consistency post-decomposition
- Cap. 8: Step 4 + 4b → regime variation
- Cap. 9: Step 6 → multi-CB symmetry
- Cap. 10: Step 8 → cross-section duration
- Cap. 11: Robustness aggregati
- Appendice A: 06_legacy_stadio1_stadio2/
