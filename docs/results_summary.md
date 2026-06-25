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

## Finding 4 — Strategia event-driven OOS Sharpe ≈ +1.4 annualizzato lordo

Strategia concentrata pre-registrata (`09_risultati/strategie_event_driven/concentrated/`):

### Disegno (a priori)

| Trade | Trigger | Filtro pre-registrato | Position |
|---|---|---|---|
| **NFP/neg event_window** | annuncio NFP, regime neg corr equity-bond | `|m_e|≥p75_train` + `VIX≤p75_train_VIX` | sign(equity), sign(bond), size=|β_str(NFP)| da `strategy_rule.position` |
| **ECB QE→SHORT DE30Y** | annuncio ECB, no filtro regime | `|QE|≥p75_train_|QE|` | sign(QE) × SHORT Bund 30Y (deriva da β_QE=+1.07 di Finding 2) |

Pesi portafoglio: inverse-vol calibrato su training (2010-2018), applicato OOS (2019-2025).

### Risultati out-of-sample

| serie | n_OOS | Sharpe per-evento OOS | Bootstrap p-value | Sharpe annualizzato |
|---|---:|---:|---:|---:|
| NFP filtered | 10 | +1.28 | 0.0028 | +1.54 |
| ECB QE filtered | 14 | +1.31 | 0.0003 | +1.86 |
| **Portafoglio (w=0.90/0.10)** | **24** | **+1.28** | **<0.0001** | **+2.38** |

**Robustezza sensibilità soglie**:

| q | Sharpe OOS portafoglio |
|---|---:|
| p70 | +0.63 |
| **p75 (baseline)** | **+1.28** |
| p80 | +1.26 |

Stabile a p75 e p80; cala a p70 (filtri più larghi includono eventi rumorosi).

### Caveat onesti
- Sharpe **LORDO**: zero costi di transazione, slippage, leva, vincoli custodia.
- Sample piccolo OOS: n=10–14 per strategia → CI 95% ampi.
- Annualizzazione i.i.d. (ragionevole per eventi mensili).
- 2 mercati distinti: futures US (ES, TY) + Bund (FGBL/FGBX).
- Senza filtro sorpresa: Sharpe per-evento OOS scende a +0.42 (VIX-only) o +0.34
  (no filter), n triplica a 80–104, Sharpe annualizzato OOS ≈ +1.3 to +1.4
  (p_boot < 0.001). Range realistico: [+1.3, +2.4] annualizzato a seconda
  della selettività.

### Vedi
- `09_risultati/strategie_event_driven/concentrated/results.json`
- `09_risultati/strategie_event_driven/concentrated/results_tests.json`

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
