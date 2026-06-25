# Sintesi dei findings — Tesi HFI Equity-Bond Comovement

Quattro findings autenticamente robusti, ciascuno con catena di custodia
verificabile via `config_hash` + sha256 di input/codice/manifest.

---

## Finding 1 — NFP/neg: canale strutturale identificato

| | |
|---|---|
| Cella | NFP/neg (n_e=141 finestre evento, n_c=136 finestre controllo post-dedup) |
| β_str centrale | −1.40 (puntuale; SE bootstrap 0.16 sul β_H rendimenti grezzi) |
| F-MOP | 39.04 (cv pre-reg 23.1085 → PASS) |
| shrink | 0.535 (≥ floor 0.05 → PASS) |
| banda costruzione | 0.000 (a ±15) / 0.087 (a ±30 min — sopravvive) |
| precheck Nagel-Xu | PASS (p=0.174) |
| verdetto pacchetto 12 | **`identified_robust`** |

**Robustezza testata (sessione 2026-06-24)**: la cella NFP/neg sopravvive a:
- ±15 min ✓ baseline
- ±30 min ✓ (banda 0.087, F=24.20, shrink=0.66)
- Δy_bond = delta_rate_3 baseline (C) ✓
- Δy_bond = ΔDGS10 daily (A) ✓
- Δy_bond = multi-curva DGS2/5/10 (B) ✓
- Δy_bond = β-per-leg scaling (E) ✓
- Δy_bond = multivariata β_1d1+β_2d2+β_3d3 (F) ✓

**Unica cella robusta in 4/6 specifiche del bond piece.**

---

## Finding 2 — ECB: trasmissione QE→curva Bund lunga, monotonica e viva a 30Y

| scadenza | β_QE | p-value HC1 | BY rejected (q=0.10, m=15) |
|---|---:|---:|:---:|
| DE2Y | +0.40 | 0.0 | ✓ |
| DE3Y | +0.57 | 0.0 | ✓ |
| DE5Y | +0.84 | 0.0 | ✓ |
| DE10Y | **+1.14** | 0.0 | ✓ |
| DE15Y | +1.13 | 0.0 | ✓ |
| DE20Y | +0.97 | 0.0 | ✓ |
| **DE30Y** | **+1.07** | **0.0** | **✓** |

n=129 eventi ECB post-2010 con T/P/QE pieno. **12/15 scadenze BY-rejected**.
La pendenza dello shock QE cresce monotonicamente fino a 10Y e resta viva a 30Y.

Coerente con la fattorizzazione Altavilla et al. (2019) — Target/Path/QE estratti
in questa sessione via rotazione canonica dei dati EA-MPD (vedi
`scripts/extract_altavilla.py`).

---

## Finding 3 — Terzo canale residuo (L, V, C): NON identificato a q=0.10

Sui residui delle 4 ROBUST_CELLS del 12, sotto la sign rule §3 RIVISTA
"antisymmetric" (risoluzione della patologia §2/§3: i residui ũ_e e ũ_b come
definiti hanno carichi antisimmetrici per costruzione, coef_b = −coef_e/β):

| candidato | proxy | risultato |
|---|---|---|
| L (liquidità funding) | Δ(bid-ask spread) intraday ES+TY in bps | 0/4 |
| V (volatilità) | ΔVIX daily | 0/4 |
| C (correlation expected) | corr 5-min ES~TY sul giorno trading precedente | 0/4 |
| **Totale** | | **0/12** |

A q=0.10 pre-registrato, BY family size = 12, **nessun pair (cell, candidate)
sopravvive a comunalità + sign rule + BY**. È un risultato di NON-evidenza
**onesto**: la sostituzione di m_e con sorprese specifiche (req08 surprise_yoy
per CPI, MP1 JK per FOMC) non ravviva alcun PASS. La sostituzione del TED daily
con proxy intraday Δbid-ask dissolve il singolo segnale borderline pre-test
(CPI/pos|L da p=0.0037 a p=0.78).

---

## Finding 4 — Identificazione non implica predicibilità OOS

Il finding strutturale del 12 (NFP/neg) e quello sulla curva ECB (Finding 2)
sono robusti a livello identificativo. La domanda derivata — **se questi
findings si traducano in profittabilità out-of-sample** — è stata testata
nel pacchetto 14 (strategie event-driven) con disciplina pre-registrata
(seed, config_hash, split temporale, regola di posizione fissa a priori).

### Risultati pre-registrati senza filtri ex-post

| strategia | n_train | Sharpe train | n_OOS | **Sharpe OOS** | p_boot OOS |
|---|---:|---:|---:|---:|---:|
| CPI/neg (sign rule pre-reg) | 96 | +0.03 | 53 | **−0.22** | 0.086 |
| NFP/neg (sign rule pre-reg) | 87 | +0.23 | 49 | **+0.21** | **0.155 — NON significativo** |
| FOMC/neg (sign rule pre-reg) | — | — | — | sotto-campione JK ≤ 2024-01 | — |
| **Portafoglio equal CPI+NFP+FOMC** | — | +0.06 | 416 | **−0.02** | — |

**Lettura onesta**: il portafoglio pre-registrato non rende OOS, e NFP da sola
ha Sharpe +0.21 con p_boot = 0.155 (non rigetta H0: Sharpe = 0). CPI **inverte
segno** fra training (+0.03) e OOS (−0.22): la regola di posizione fissa è
incompatibile con la dinamica state-dependent della risposta equity-bond ai
CPI prints (vedi Cieslak-Schrimpf 2019, Boyd-Hu-Jagannathan 2005).

### Esplorazione con filtri (non pubblicata come finding)

Filtri sulla magnitudine della sorpresa (`|surprise| ≥ p75_training`) + VIX
(`VIX ≤ p75_training_VIX`) producono Sharpe OOS più alti su 10–14 eventi per
strategia (Sharpe per-evento +1.28, p_boot < 0.01). Questi numeri **non sono
riportati come finding** della tesi perché:

- La scelta del filtro (`p75`) è soggetta a sensitivity p70/p75/p80 con
  Sharpe che oscilla +0.63/+1.28/+1.26 → instabile a soglia più larga.
- n_OOS = 24 per il portafoglio: sample troppo piccolo per inferenza robusta
  sul Sharpe (CI 95% [+0.96, +1.82], errore standard ~0.22).
- Il filtro `|surprise| ≥ p75` seleziona ex-ante eventi "informativi", ma è
  comunque una scelta tecnica che riduce drasticamente n.
- Sostituire un proxy intraday onesto per L (Δbid-ask spread) dissolve il
  singolo segnale borderline di terzo canale (Finding 3): coerente con il
  pattern generale che i filtri stretti **trasformano rumore in finto segnale**
  quando applicati a sample piccoli.

### Conclusione (allineata alla tesi)

**Identificazione strutturale non implica predicibilità out-of-sample.**
Il portafoglio event-driven pre-registrato non genera Sharpe OOS significativo,
e i Sharpe più alti ottenuti con filtri post-2010 sono fragili sotto
sensitivity e sample size. Il finding è **negativo onesto** e separa
chiaramente la dimensione *identificativa* (in cui la pipeline produce
robusto NFP/neg + ECB QE) da quella *predittiva* (in cui non si registra
alpha sistematico replicabile).

### Vedi
- `09_risultati/strategie_event_driven/manifest.json` — run pre-registrato
- `09_risultati/strategie_event_driven/concentrated/results_tests.json` — esplorazione filtri (caveat)

---

## Findings rifiutati / non confermati (per onestà)

- **CPI/pos `identified_robust` a ±15** → cade a `channel_not_identified` a
  ±30 min, e a 0/4 varianti del bond piece su 6.
- **CPI/neg e FOMC/neg `identified_robust` a ±15** → cadono a `fragile` a ±30
  (banda 0.61 e 1.20). Robustezza per insensibilità della banda di costruzione,
  non strutturale.
- **ECB/neg sopravvive con curva Altavilla** → ma con shrink 22 000+: artefatto
  da netting fittizio (ΔDE10Y daily ortogonale a r_b intraday FGBL).
- **Sign-flip post-hoc su CPI/FOMC** (sessione esplorativa): Sharpe portafoglio
  +0.13/+0.09. NON pubblicabile come finding, è fitting sul segno osservato.

Tutte queste osservazioni sono documentate in `09_risultati/decomp_canali_curva_vera/`
e `09_risultati/window_30min/`.
