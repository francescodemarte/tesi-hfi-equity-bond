# PROTOCOL — FOMC/neg long bond strategy

Pre-registrazione integrale della strategia direzionale `FOMC/neg long bond × |β_str|=0.8748` con stratificazione del backtest.

## Razionale strutturale

Nei giorni FOMC sotto regime equity-bond di correlazione negativa (corr3m_US_z_lag < 0), il bond Treasury 10Y è bid sistematicamente in risposta agli annunci. È la firma operativa del "Fed put" classico, sostenuta dal canale di sconto comune identificato dal Capitolo 6: il β strutturale FOMC/neg = +0.875 misura quanto il bond si muove in covarianza con l'azione durante l'evento. Una posizione long bond dimensionata a |β| sfrutta questo movimento condizionato al regime.

Il segno (+) **non è back-fit** sui rendimenti: discende dal regime classification (corr negativa = flight-to-quality). La taglia (+|β_str|=0.875) **non è ottimizzata**: viene dal Capitolo 6 fissa.

## Specifica

| Parametro | Valore | Fonte |
|---|---|---|
| **Universo** | 105 eventi FOMC del sample 2010-2025 con regime corr eb negativo (colonna `corr3m_US_z_lag < 0`) | `data/events/events_with_regime_classifier.csv` |
| **Segno** | +1 (long bond) | derivato dal regime, fisso |
| **Taglia** | |β_str_FOMC/neg| = 0.8748 (arrotondato a 0.875 nel manuscript) | `results/02_decomposition/baseline/decomp_canali.report.json` |
| **Finestra** | T-1 close → T close (daily close-to-close) | pre-registrato |
| **Strumento** | future Treasury 10Y (`TYc1`, daily close) | pre-registrato |
| **Costi** | 0.3 bp round-trip bond | pre-registrato |
| **Annualizzazione** | 8 eventi/anno | calendario FOMC tipico |

## Stratificazione del backtest — 3 esercizi pre-registrati

### Esercizio 1: within-regime k-fold k=5 stratified by year
- Tutti i 105 eventi sotto regime negativo
- 5 fold, anni assegnati round-robin dopo shuffle deterministico con seed `seed_for("fomc_kfold")`
- Per ogni fold: train su 4 fold, valutazione sul fold-test, Sharpe annualizzato
- Bootstrap CI95 sulla media dei 5 fold (B=2000)
- **Soglia PASS**: Sharpe mean > 0.3 AND IC95 > 0 AND min_fold > -0.5

### Esercizio 2: cross-regime pre-2022 vs post-2022
- Train su eventi 2010-2021 (n≈91), test su 2022-2025 (n≈14)
- Sharpe post-2022 + bootstrap clusterizzato per anno (B=2000)
- p-value one-sided sull'ipotesi Sharpe_post ≤ 0
- **Soglia PASS**: Sharpe positivo AND p < 0.10
- **Caveat**: n_post=14 è fragile per detection statistica; il claim è "tenuta cross-regime", non "conferma".

### Esercizio 3: cross-celle con β_sister (NFP)
- Stessi 105 eventi FOMC, ma posizione dimensionata con |β_NFP|=1.404 invece di |β_FOMC|=0.875
- Test di robustezza: il segnale dipende dal parametro esatto o resta positivo importando da una cella sorella?
- Bootstrap CI95 sulla media (B=2000)
- **Soglia PASS**: Sharpe positivo AND IC95 > 0

## Determinismo

- `MASTER_SEED = 20260621`
- `seed_for(name) = sha256(MASTER_SEED|name)` int 16-hex
- Bootstrap B=2000 per ogni IC; K-fold shuffle ha seed dedicato
- Riproduzione bit-per-bit garantita dato lo stesso script + stessi input

## Capienza

Su €100m notional 10Y, DV01 ≈ €10 000/bp. P&L per evento (in bp di rendimento bond × |β|): vedi `backtest_full_sample.json` campo `pnl_per_event_bp_bond`. Frequenza ~8 eventi/anno. La strategia è capacity-bound dalla liquidità FOMC-day del TY future (abbondante fino a 5k contratti).

## Caveat onesti

1. **Sample post-2022 fragile**: n=14 limita la potenza statistica del Cross-regime; va presentato come "indizio robusto", non "conferma".
2. **β_str fisso dal Capitolo 6**: non re-stimato fold-by-fold per evitare overfit di parametro.
3. **Costi 0.3 bp**: in stress (2022 sell-off TY) lo slippage può raddoppiare; il manifest dichiara sensitività.
4. **Discrepanza con il Fork P di scoperta**: il deposit riproduce la struttura del test ma il min_fold dipende dal seed dello shuffle K-fold. Il manifest dichiara esplicitamente il confronto vs Fork P.

## Riferimenti

- Capitolo 6 della tesi, sezione decomposizione (pacchetto 12)
- `results/02_decomposition/baseline/decomp_canali.report.json` (β_str autoritativo)
- `results/01_protocol_v2/beta_H_robust_cells_w15.json` (β_H per confronto)
