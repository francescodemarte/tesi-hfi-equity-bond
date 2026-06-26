# PROTOCOL — Vol-target NFP overlay (risk-management derivative)

Pre-registrazione integrale di un sovrapposto di gestione del rischio sui giorni d'annuncio NFP/neg, basato sul finding intraday r̂=15.4 del Capitolo 6.

## Status: PRODOTTO DERIVATO, non finding nativo

Questa strategia **NON è un finding diretto della tesi**. È un **trasferimento cross-orizzonte** del finding intraday (r̂=15.4 = var(±15min)/var(controllo) per NFP/neg) a un'applicazione di risk-management su orizzonte daily. La giustificazione del trasferimento è **strutturalmente specifica a NFP/neg**: dal Capitolo 7.2 (Audit del bridge), NFP/neg è l'unica cella che passa **Check 1** (var window = 44.8% var daily ≥ 40%). Per CPI/FOMC il Check 1 fallisce e l'overlay analogo NON è giustificato. **Filtro ex-post DICHIARATO**.

## Razionale

Il salto di varianza intraday r̂=15.4 dice che durante NFP la varianza del bond è 15× quella di un giorno normale. Per un trader che tiene posizione overnight (chiusura T-1 → chiusura T), il rendimento daily ingloba quel salto. Tagliare la size del portafoglio bond × 1/√r̂ = 0.255 in T-1 close prima dell'annuncio dovrebbe portare la varianza event-day **alla stessa scala dei giorni di controllo**, eliminando la concentrazione di tail-risk.

## Specifica

| Parametro | Valore | Fonte |
|---|---|---|
| **Universo** | tutti i giorni di trading 2010-2025, ~5000 obs | `data_processed/{TYc1,ESc1}_1min.csv` |
| **Trigger overlay** | giorni classificati come NFP/neg (110 nel sample) | `events_with_regime_classifier.csv` |
| **Regola** | `size_total *= 1/√r̂` nei NFP-day, baseline 1.0 altrove | pre-registrato |
| **r̂** | 15.389 (varianza intraday bond evento/controllo) | `results/01_protocol_v2/beta_H_robust_cells_w15.json` riga NFP/neg, campo `r_hat` |
| **size factor** | 1/√15.389 = 0.2549 | calcolato |
| **Costi** | 0.3 bp/round-trip bond, 0.5 bp/round-trip equity | pre-registrato |
| **Split** | train 2010-2019, OOS 2020-2025 | pre-registrato |

## 4 strategie a confronto

| ID | Strategia | Descrizione |
|---|---|---|
| A | Baseline long bond | Long TY direzionale, size 1.0 sempre |
| B | Vol-target NFP-only su bond | A + size cut × 0.255 nei soli NFP-day |
| C | Baseline 60/40 | 60% equity + 40% bond, ribilanciato giornaliero |
| D | 60/40 + vol-target NFP-only | C + size totale × 0.255 nei soli NFP-day |

## Metriche valutate

- Sharpe annualizzato (full, train, OOS)
- VaR99 daily (full, NFP-only)
- Max drawdown
- % perdite > 1% nei NFP-day
- # perdite > 1% assoluto nei NFP-day

## Soglia di passaggio

- Sharpe full sample ≥ baseline − 0.05 (no degrade material)
- VaR99 NFP-day ridotto ≥ 40%
- # perdite > 1% in NFP-day ridotte a ≤ 1

## Caveat onesti

1. **Filtro ex-post DICHIARATO**: l'overlay è applicato SOLO a NFP perché è l'unica cella che passa Check 1 del bridge. Generalizzazione cross-cella ESCLUSA esplicitamente.
2. **Trasferimento cross-orizzonte**: finding nativo è intraday ±15 min; applicazione è daily close-to-close. Vale solo per chi tiene posizione overnight, NON per trader strettamente intraday che chiudono entro la finestra evento.
3. **NON è alpha**: il Sharpe full sample non migliora — il valore operativo è nella distribuzione delle code (VaR99, # perdite, max DD).
4. **r̂ fisso dal Capitolo 6**: stimato sui rendimenti grezzi intraday, non re-stimato per regime macro. Robustezza al cambio regime: indiretta (passa via Check 1, che è full sample 2010-2025).
5. **Costi inclusi**: 0.3 bps bond + 0.5 bps equity round-trip nei NFP-day. In stress (2022) lo slippage TY salirà ma l'overlay riduce turnover, non aumenta.

## Cliente target

- ✅ Bond desk direzionale / ALM
- ✅ Multi-asset 60/40 con vincolo VaR
- ✅ Pension fund / insurance VaR-constrained
- ✅ Risk desk bancario (overlay su qualsiasi book a tassi USA)
- ❌ Strategia direzionale long-only equity (l'overlay sul bond non aiuta)
- ❌ Trader intraday che chiudono entro la finestra evento (l'orizzonte daily non è il loro)

## Determinismo

`MASTER_SEED = 20260621`. Niente bootstrap nel backtest (metriche deterministiche dai rendimenti realizzati). Riproduzione bit-per-bit garantita.
