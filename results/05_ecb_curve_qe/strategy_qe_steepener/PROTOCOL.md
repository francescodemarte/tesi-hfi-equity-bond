# PROTOCOL — QE-Steepener Bund 2–10

Pre-registrazione integrale dello steepener Bund 2–10 sul fattore QE di
Altavilla et al. (2019). Questo documento fissa la specifica della
strategia **prima** che fosse osservato il P&L: nessun parametro è
ottimizzato sui rendimenti.

## 1. Universo e dati

- **Eventi.** I 129 eventi ECB del periodo 2011-07 → 2025-11 in cui i
  tre fattori canonici Target / Path / QE sono tutti disponibili.
  Coincide con il sample del modello autoritativo
  `results/05_ecb_curve_qe/results.json` →
  `step1_ecb_curve_symmetry.n_events`.
- **Fattori.** `Target`, `Path`, `QE` da
  `data/external_public/altavilla_TPQE_factors.csv` (estratto dallo
  `script/extract_altavilla.py` del repo).
- **Variazioni di yield.** `DE2Y` e `DE10Y` dal foglio
  `Press Conference Window` di
  `data/events/EA-MPD_ECB_Altavilla2019.xlsx`. Le variazioni nelle
  finestre OIS standard di Altavilla sono **espresse in basis points
  per costruzione del file EA-MPD** (cfr. foglio `Notes`, voce
  «DE10Y: 10 years German bond rate change in the relevant window in
  basis points»).
- **Finestra.** Press Conference Window di Altavilla, equivalente alla
  $\bigl[-10,+20\bigr]$ minuti dall'inizio della conferenza stampa.

## 2. Segno (direzione)

Per ogni evento $t$:

$$
\mathrm{sign}_t \;=\; +1 \text{ (steepener: long 10Y, short 2Y)}
\quad \text{se } \mathrm{QE}_t > 0, \qquad -1 \text{ (flattener) altrimenti.}
$$

Il segno **deriva** dalla monotonicità di $\beta_{\text{QE},n}$ stimata
nel modello autoritativo $\text{step1\_ecb\_curve\_symmetry}$:
$\beta_{\text{QE},\,2Y} \approx +0.40$, $\beta_{\text{QE},\,10Y}
\approx +1.14$, $\beta_{\text{QE},\,10Y} > \beta_{\text{QE},\,2Y}$ con
margine di $+0.74$. Una sorpresa $\mathrm{QE}^+$ alza il 10Y più del
2Y, quindi un irripidimento della pendenza è il payoff atteso. Il
segno **non è scelto guardando il P&L**.

## 3. Taglia

Due varianti pre-dichiarate, riportate entrambe:

- **Binaria.** $\mathrm{size}^{\text{bin}}_t = 1$ per ogni evento.
- **Continua.** $\mathrm{size}^{\text{cont}}_t = \min\bigl(\bigl|z_t\bigr|, 3\bigr)$,
  dove $z_t = \bigl(\mathrm{QE}_t - \mu^{60}_{t-1}\bigr) / \sigma^{60}_{t-1}$,
  con $\mu^{60}_{t-1}, \sigma^{60}_{t-1}$ media e dev.std. degli ultimi
  60 valori del $\mathrm{QE}$ disponibili **prima** dell'evento $t$
  (rolling shift di una posizione). Per eventi con meno di 5 valori
  storici disponibili, la taglia continua usa $\bigl|z_t\bigr|$ con
  `min_periods=5`; in mancanza, la taglia ricade su $1$ (fallback
  binario). Il cap a $3$ evita esposizione eccessiva su outlier.

## 4. P&L per evento

In basis points di pendenza:

$$
\Delta\text{slope}_t \;=\; \Delta \mathrm{DE10Y}_t - \Delta \mathrm{DE2Y}_t,
\qquad
\pi^{\text{gross}}_t \;=\; \mathrm{sign}_t \cdot \mathrm{size}_t \cdot \Delta\text{slope}_t.
$$

Per costruzione DV01-neutral, le due gambe contribuiscono ad un
risultato per bp di slope change pari a 1 unità di DV01 della 10Y.

## 5. Costi

- **Base.** $c^{\text{base}}_{\text{leg}} = 0.2$ bp per gamba round-trip,
  totale $c^{\text{base}} = 0.4$ bp per trade DV01-neutral.
- **Stress.** $c^{\text{stress}}_{\text{leg}} = 0.5$ bp per gamba,
  totale $c^{\text{stress}} = 1.0$ bp per trade.

Il P&L netto per evento è:

$$
\pi^{\text{net}}_t \;=\; \pi^{\text{gross}}_t - c \cdot \mathrm{size}_t.
$$

La taglia continua paga il costo scalato (i broker quotano lo stesso
slip per round-trip indipendentemente dalla size, ma più volumi
generano più frizione di mercato; lo scaling lineare è la convenzione
conservativa).

## 6. Capienza

Su €100m di nozionale gamba 10Y, DV01 ≈ €10 000 per bp di yield. Il
P&L per evento in bp di pendenza si converte direttamente in €:

$$
\text{P\&L}_t [\euro] \;=\; \pi_t [\text{bp}] \cdot \text{DV01}_{10Y} [\euro/\text{bp}].
$$

Capienza annualizzata = $\bar{\pi} \cdot 8.6 \cdot \text{DV01}_{10Y}$,
con $8.6 = 129 / 15$ eventi/anno.

## 7. Bootstrap

Cluster-by-year, $B = 2000$ ricampionamenti. Per ciascun ricampionamento
si selezionano con rimpiazzo $\#\text{anni}$ anni dal sample e si
concatenano tutti gli eventi degli anni selezionati. Si calcola il
Sharpe annualizzato sul ricampionamento. IC al 95% è l'intervallo
$[\text{p}_{2.5}, \text{p}_{97.5}]$ dei Sharpe bootstrap. p-value
one-sided = $\mathrm{Pr}(\bar{\pi}^* \leq 0)$ sotto bootstrap.

Seed: $\text{MASTER\_SEED} = 20\,260\,621$, derivazione `seed_for(name)`
con `sha256(MASTER_SEED|name)`. Garantisce determinismo perfetto.

## 8. Sharpe annualizzato

$$
\text{Sharpe} \;=\; \frac{\bar\pi}{\sigma_\pi} \cdot \sqrt{N_{\text{eventi/anno}}}, \qquad
N_{\text{eventi/anno}} = 8.6.
$$

## 9. Split train / OOS

- **Train.** Primi 86 eventi cronologici (≈ 2/3 del sample).
- **OOS.** Ultimi 43 eventi (≈ 1/3).

Nessun parametro è fittato sul training. Lo split serve unicamente a
saggiare la persistenza della relazione. Il segno è prefissato dalla
monotonicità di $\beta_{\text{QE},n}$, la $z$-score è calcolata su
rolling 60 eventi **disponibili al momento dell'evento**, quindi la
strategia è già naturalmente fuori campione su ogni evento.

Validazione richiesta: `sign(Sharpe_train) == sign(Sharpe_oos)` e
shrinkage $|S_{\text{oos}}/S_{\text{train}}| > 0.3$ (≈ il segnale non
è dimezzato di colpo).

## 10. Riferimenti

- Altavilla, C., Brugnolini, L., Gürkaynak, R. S., Motto, R., e
  Ragusa, G. (2019). «Measuring Euro Area Monetary Policy». Journal of
  Monetary Economics, 108, 162–179.
- Curva $\beta_{\text{QE},n}$ del modello autoritativo: vedi
  `results/05_ecb_curve_qe/results.json` →
  `results.step1_ecb_curve_symmetry.results_per_maturity`.
- Codice esecutore: `extract_qe_steepener_backtest.py` (questa cartella).
- Output autoritativi: `backtest_full_sample.json`,
  `backtest_train_oos.json`, `manifest.json`.

## 11. Note onesti sul deposito

- Questo backtest **non sostituisce** la versione del Fork B della
  sessione esecutore precedente: la riproduce in modo deterministico,
  e fissa il dato autoritativo per la tesi. Il manifest documenta lo
  scarto numerico tra le due (atteso modesto: diversa procedura di
  bootstrap su uno stesso pre-registrato).
- Le DE2Y/DE10Y di Altavilla sono in bp; non occorre rescaling.
  Una versione preliminare di questo script applicava un fattore 100
  erroneo: corretto nel commit di deposito (vedi `_metadata_refresh`
  nel manifest).
- L'estensione a BTP/OAT/Bonos, al butterfly 5-10-30 (vincolato da 4
  gambe di slippage), e al fattore Path è esplicitamente fuori
  perimetro di questo deposito e richiede pre-registrazione separata.
