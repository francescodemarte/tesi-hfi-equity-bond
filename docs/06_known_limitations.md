# 06 — Limiti dichiarati onesti

> Lista esaustiva dei limiti della pipeline. Ogni voce è documentata anche
> nei manifest e nei caveat dei singoli pacchetti.

## Limiti dei dati

### 1. Refinitiv Tick History intraday non ridistribuibile
- Vincolo licenza Refinitiv: non possiamo includere i CSV 1-min nella repo.
- Conseguenza: terzi devono ottenere il proprio accesso WRDS o Refinitiv
  per la riproduzione completa. Smoke test e fixture sintetici comunque
  disponibili.

### 2. Curva intraday solo a 1 scadenza (TY 10Y, FGBL 10Y)
- Disponibili: futures front-month TYc1 (USA 10Y) e FGBLc1 (Bund 10Y).
- Non disponibili intraday: cash multi-scadenza Treasury (2Y, 5Y, 7Y, 30Y),
  Bund cash multi-scadenza (Schatz 2Y, Bobl 5Y, Buxl 30Y).
- Per ECB la curva DE3M→DE30Y daily è disponibile via Altavilla EA-MPD
  (event-window-based, non intraday).
- Conseguenza: la decomposizione ΔP^B usa 3 punti front money-market
  (FFc1/2/3 per US, FEIc1/2/3 per ECB) + coda assunta su griglia
  {T0, TC, TD_0.5, TD_0.8}. È una semplificazione rispetto a una curva
  osservata multi-scadenza, dichiarata in `02_data_methodology.md` §5.

### 3. Sorprese non sempre disponibili
- **CPI**: sorpresa `surprise_yoy` da consensus actual−forecast disponibile
  in `data/events/req08_cpi_surprise.csv` (✓ usata).
- **FOMC**: MP1 Jarocinski-Karadi disponibile fino al **2024-01-31**.
  114 eventi FOMC su 189 hanno match. 75 eventi (Sep 2024 → Dec 2025) sono
  fuori dal dataset JK; le strategie su questi eventi usano fallback m_e PC1
  money-market, ma il finding strutturale del pacchetto 12 è ovviamente
  indipendente dalla sorpresa.
- **NFP**: consensus actual−forecast **NON disponibile** nel filesystem.
  Fallback dichiarato: m_e PC1 money-market dal CSV eventi (`91.5%` copertura).
  Conseguenza: il pacchetto 07 ha NFP T2/T9 gated (`"consensus NFP non
  disponibile (SPEC §8)"`), e il pacchetto 13 usa m_e come Z di
  ortogonalizzazione.
- **ECB**: parser Altavilla LEVEL gated in `loaders.load_ecb_level`. I
  fattori Target/Path/QE sono estratti separatamente via
  `scripts/extract_altavilla.py` su rotazione canonica.

### 4. VIX intraday, MOVE intraday: non disponibili
- VIX disponibile solo daily (FRED VIXCLS). MOVE non in repo (paywall ICE).
- Conseguenza: il pacchetto 13 (terzo canale residuo) usa **ΔVIX daily**
  come proxy V, dichiarato come fallback.

## Limiti metodologici

### 5. Distinzione β_str vs β_H
- I numeri della tesi (`β_str` del pacchetto 12) NON sono confrontabili
  direttamente con i β_H del pacchetto 07. Il primo è sui rendimenti netti
  dal canale tasso, il secondo sui rendimenti grezzi.
- I due file convivono in repo: `results/02_decomposition/baseline/decomp_canali.report.json`
  (β_str) e `results/01_protocol_v2/beta_H_robust_cells_w15.json` (β_H).
- La tesi dichiara nel testo questa distinzione. Vedi anche
  `src/hfi/event_driven/config.py` campo `BETA_STR_PROVENANCE`.

### 6. Banda di costruzione "0" su ±15 min
- Le 4 celle robuste del 12 hanno `banda_costruzione = 0.000` su finestra
  ±15 min: i 12 punti della griglia coda × ρ producono ΔP^B_e
  numericamente identici. È **robustezza per insensibilità**, non
  identificazione strutturale forte: il bond piece via delta_rate_3 + duration
  costante satura il netting e la coda equity diventa irrilevante per β_str.
- A ±30 min le bande si allargano (es. FOMC/neg banda 1.20) — segnale che la
  robustezza a ±15 è in parte tecnica. Dichiarato in
  `02_data_methodology.md` §5 caveat box.

### 7. Patologia residui §2/§3
- I residui `ũ_e = r̃_e − β_str·r̃_b` e `ũ_b = r̃_b − r̃_e/β_str` hanno
  carichi antisimmetrici su Z per costruzione: `coef_b ≈ −coef_e/β` con
  β > 0.
- La sign rule §3 originale ("concordant" per L, "both negative" per V) era
  matematicamente impossibile da soddisfare.
- Risoluzione (variante 2a): sign rule rivista a "antisymmetric_pos_eq" /
  "antisymmetric_neg_eq" / "ambiguous". Vedi
  `src/hfi/third_channel/config.py` e `tests/test_synthetic_validation.py`.
- Conseguenza onesta: sotto la nuova sign rule, una dichiarazione "L" su una
  cella significa attività residua significativa con λ_e > 0 e λ_b < 0; NON
  garantisce che il bond contribuisca indipendentemente al canale. La
  discriminazione di magnitudine indipendente del bond è persa per
  costruzione.

### 8. Strategie event-driven: identificazione ≠ predicibilità
- Il portafoglio pre-registrato (equal weights CPI/NFP/FOMC) ha OOS Sharpe
  −0.02 (event_window) / −0.02 (EOD) sui dati 2010-25.
- NFP/neg pre-registrato OOS Sharpe +0.21 (n=49, p_boot=0.155 NON
  significativo).
- I Sharpe più alti con doppio filtro (|surprise|≥p75 + VIX≤p75) generano
  numeri tra +1.28 e +2.38 annualizzato su n=10-24 eventi OOS. Sono
  esplorazione, **non finding** della tesi (vedi `04_findings.md` §Finding 4).

## Limiti di sample

### 9. Sample finito su celle minoritarie
- CPI/pos: n_e = 37 (per il 12) / 33 dopo dedup. Cella robusta ma con
  sample stretto.
- ECB/pos: n_e tra 20 e 54 a seconda della finestra. Tutte le 4 sub-celle ECB
  hanno verdict `channel_not_identified` per F-MOP sotto cv=23.1085.

### 10. FOMC limitato al sotto-campione 2024-01
- MP1 JK termina 2024-01-31. Eventi FOMC 2024-09 → 2025-12 (10 eventi)
  scartati dai test che richiedono MP1.
- Conseguenza: il finding strutturale FOMC/neg dal 12 (n=117) usa l'intero
  periodo, mentre le strategie del 14 (FOMC) sono limitate al sotto-campione
  pre-2024-02.

## Limiti di softwware e ambiente

### 11. Versioni esatte di numpy / pandas / scipy non dichiarate nei manifest
- I manifest registrano sha256 dei CSV input e dei moduli di codice, ma non
  le versioni delle dipendenze.
- Per coerenza usare le versioni di `requirements.txt` (numpy>=1.24,
  pandas>=2.0, scipy>=1.10, pyarrow>=12.0, openpyxl>=3.1, pytest>=7.4).
- Test su Python 3.11.15 (ambiente Conda `quant` dell'autore).

### 12. Stato Git non integrato nei manifest
- I manifest dei run autoritativi NON registrano il commit SHA del codice.
- Mitigazione: la sha256 di ogni modulo `.py` eseguito è registrata, quindi
  l'integrità del codice è verificabile anche senza git.

## Limiti di portata

### 13. ECB curva: dato daily, non intraday
- La curva Altavilla DE3M→DE30Y è event-window-based daily, non tick 1-min.
- Conseguenza: il finding 2 (trasmissione QE→DE30Y) è su variazioni
  daily-aggregate degli yield, non su movimenti intraday.

### 14. Test trading lordo di costi
- Sharpe riportati (sia pre-registrati sia esplorativi) sono **LORDI** di
  costi di transazione, slippage, leva, vincoli custodia.
- Sui sample piccoli OOS (n=10-24) anche piccoli costi modificano
  drasticamente il Sharpe netto.

## Cose che NON sono state fatte (e perché)

- **Test su Bund 30Y intraday**: dato non disponibile. La trasmissione QE è
  testata sul cambio daily (Altavilla EA-MPD), non sul movimento intraday.
- **Sorpresa CPI mensile vs settimanale**: solo mensile in req08.
- **DGP completi calibrati sui dati**: tutti i DGP nei tests sono a verità
  nota analitica (non calibrati sui dati reali), per garantire oracoli
  indipendenti.
