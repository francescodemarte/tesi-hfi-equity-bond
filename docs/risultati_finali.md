---
title: "Risultati finali — sintesi 1-2 pagine"
tags: [risultati, sintesi, ground_truth_pointer]
data: "2026-06-20"
ultima_revisione: "2026-06-20"
---

# Risultati finali — sintesi (Cap. 6 del draft)

> **Ground truth.** I numeri qui sotto sono **puntatori** alle tabelle e
> ai paragrafi di `10_tesi/draft_ita/` (Cap. 6 del corpo e Appendice
> A.6 del toolkit). In caso di discrepanza, il draft vince. Per il
> framing concettuale dell'archivio vedi [[README]].

I sei finding family-wide BY-significant attuali (con $m=6$ conferme di
secondo livello) sono raggruppati per sezione del capitolo Risultati,
nell'ordine in cui compaiono.

---

## §6.1 — Quanto spiega il canale dei tassi

Confronto tra il $\beta^{EB}$ osservato e il *null* di Beltratti-Shiller
$\beta^{PV} = -D_{eq}/D_{bond}$, regime per regime, sulle 855 finestre
evento (FOMC + CPI + NFP + BCE, 2010-2025).

- Il canale dei tassi spiega una quota **non trascurabile** del
  comovimento, con magnitudine eterogenea per classe di evento e regime.
- La quota residua $\Delta\beta = \beta^{EB} - \beta^{PV}$ è
  significativamente non nulla in più sottocampioni (BY-survival su
  $m=6$); è il dominio di indagine del resto del capitolo.

Riferimento: Cap. 6 §6.1, Tabella 6.1; derivazione del null in
Appendice B.1-B.2.

---

## §6.2 — CPI: evento o stato (FULCRO)

**Asimmetria HFI sui due bracci della sorpresa CPI.** È il risultato più
forte del capitolo e dimostra il **morso del metodo**: il braccio basso
viene **falsificato** come trasmissione dell'evento, e questo è un
risultato positivo, non un fallimento.

### Braccio alto — identificazione a doppio canale

Regressione HFI con shock di policy ortogonalizzato e fattore globale
net-of-policy:

- **Intercetta:** $\alpha = -0.0047$, $t = -12.65$
- **Slope:** $\beta = +0.0034$, $t = +7.15$
- **Bontà di fit:** $R^2 = 0.85$
- **Triangolazione TY/Bund:** $\text{corr}(\Delta y_{TY}, \Delta y_{Bund}) = 0.91$
  $\Rightarrow$ co-movimento globale del fattore tasso, non idiosincratico
  US.

Riferimento: Cap. 6 §6.2, Tabella 6.2a; figura
`cpi_surprise_vs_breakeven.png`.

### Braccio basso — falsificato come evento

Triangolazione di **quattro test indipendenti**, tutti concordi nel
**non-eccesso**:

- **Tre misure HFI** (CPI surprise basso, finestra 30 min):
  $p_{\text{placebo}} \approx 0.999$;
  Bund$^\perp$ **esatto** $\Rightarrow$ il braccio basso è
  indistinguibile dal controllo di stato sui giorni non-evento del
  medesimo regime.
- **Una misura giornaliera** $\Delta\text{breakeven}$:
  $p_{\text{placebo}} = 0.72$.

La concordanza dei quattro test su una stessa direzione (non-eccesso) è
la dimostrazione che il toolkit § 5.3 separa correttamente trasmissione
dell'evento da co-movimento di stato del regime.

Riferimento: Cap. 6 §6.2, Tabella 6.2b; saldatura formale
placebo-Rigobon-Sack in Appendice B.6.

---

## §6.3 — Canale informativo regime-dipendente

Identificazione di un **canale informativo** nel residuo del present-value
(Nakamura-Steinsson 2018, Jarociński-Karadi 2020, Cieslak-Schrimpf 2019)
**ma con regime-dipendenza** come contributo originale.

- Test di permutazione cross-regime: $p_{\text{perm}} = 0.003$.
- La componente informativa è attiva nei regimi $\tilde\rho$ medio/alto e
  spenta nel regime basso.
- Sopravvive a BY family-wide su $m=6$ a $\alpha=0.05$.

Riferimento: Cap. 6 §6.3, Tabella 6.3.

---

## §6.4 — Spillover transatlantico regime-dipendente

Spillover Treasury $\to$ Bund noto in letteratura (Ehrmann-Fratzscher
2005); **la regime-dipendenza** è il contributo originale.

- **Coefficienti netti per regime** $(\tilde\rho_{low},
  \tilde\rho_{mid}, \tilde\rho_{high})$:
  $-2.21$ / $-1.04$ / $+0.92$.
- **Placebo p-values:** $0.002$ / $0.017$ / $0.008$.
- **BY family-wide:** il braccio medio sopravvive **al margine**
  $p_{\text{adj}}^{BY} = 0.042$.

L'asimmetria di segno conferma il sign-flip in funzione del regime di
correlazione stock-bond.

Riferimento: Cap. 6 §6.4, Tabella 6.4.

---

## §6.5 — Estensione area euro (EA-MPD)

Replica del framework su decisioni BCE via Euro Area Monetary Policy
Database (Altavilla et al. 2019). Conferma qualitativa della
regime-dipendenza, con magnitudini coerenti.

- Decomposizione *LEVEL/PATH/QE* sotto HFI 30 min.
- Conferma family-wide su $m=6$ a $\alpha=0.05$.

Riferimento: Cap. 6 §6.5, Tabella 6.5.

---

## §6.6 — Sintesi delle robustezze

Sintesi nel corpo (non più in Appendice) delle 8 voci di robustezza
continua (finestra, frequenza, classificatori, SVAR Cieslak-Pang 2021,
specifiche di equity duration, sub-campione, ordering, estensioni
degeneri). Le tre voci salite al corpo principale (eteroscedasticità RS
$\to$ §5.3, placebo temporale $\to$ §5.4, triangolazione TY/Bund $\to$
§6.2) **non** rientrano qui.

Riferimento: Cap. 6 §6.6 + Appendice C.

---

## Quadro inferenziale e caveat trasversali

- **Famiglia BY** su $m=6$ conferme di secondo livello, $\alpha=0.05$:
  **tutte sopravvivono**. Il braccio medio dello spillover (§6.4) è al
  margine ($p_{\text{adj}}^{BY} = 0.042$).
- **DSR per CPI:** robustezza al multiple testing, **non** prova di
  replicabilità futura. Caveat esplicito nel testo.
- **Implicazioni operative:** Kalman di §7.1 è attribuzione **ex post**,
  non predizione ex ante; le strategie di §7.2 sono presentate con onestà
  in-sample.

---

*Pointer puntuali. Numeri da `10_tesi/draft_ita/` — Cap. 6 e Appendice A.6.*
*Ultima revisione: 2026-06-20.*
