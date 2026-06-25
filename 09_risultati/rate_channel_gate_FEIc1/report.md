# Cancello canale tassi — report esecutore (run FEIc1)

> **ALERT — partizione degenerata sui dati reali (stessa patologia di FFc2).**
> La mediana within-sample di `|Δ FEIc1|` su 686 eventi è esattamente **0**
> (426/686 = 62.1% degli eventi hanno `|Δ FEIc1|` = 0 in ±15 min).
> `D.dichotomize("median")` etichetta `x >= median` → con median = 0 tutti gli
> 686 eventi (intensità ≥ 0 per costruzione) cadono in **`high`**; le celle
> `(positivo, low)` e `(negativo, low)` sono vuote.
>
> Quota di zeri per leg (su eventi con intensità valida):
> CPI 72.9%, NFP 72.5%, FOMC 68.3%, ECB 46.7%. ECB è l'unica leg con mediana
> strettamente > 0 (0.0025) — è il leg per cui FEIc1 è strutturalmente
> rilevante (annunci ECB → Euribor); le altre tre leg vedono FEIc1 fermo nella
> finestra ±15 min nella maggior parte dei casi.
>
> Conseguenze sui verdetti — identiche al run FFc2 (run sibling):
>
> - **(a) True** — η² basso ma calcolato su un fattore degenere; numero corretto.
> - **(b) True** — `κ_aligned = 0` per costruzione (una sola categoria
>   `intensity`). Non è indipendenza, è degenerazione.
> - **(c) True** — `cells_below_threshold` opera solo sulle celle *presenti*;
>   le celle `*|low` mancano del tutto e non vengono testate.
> - **(d) None** — celle `(positivo, low)` e `(negativo, low)` assenti
>   (`status = missing_cells`).
>
> Aggiuntivo per FEIc1: copertura più bassa rispetto a FFc2 (686/842 vs
> 832/842 con intensità valida) — 156 eventi con `intensity_raw = NaN`,
> concentrati su FOMC (NaN=64) per l'orario di chiusura del mercato Euribor;
> ECB ha la copertura migliore (259/281).
>
> Nessuna soglia / modalità di partizione / contratto / sample è stata
> modificata ex-post. Vedi `HANDOFF.md` accanto a questo report.

- timestamp (esterno): `2026-06-22T21:50:20Z`
- contratto tassi: `FEIc1`
- finestra: ±15 min (edge mediana 5 min)
- modalità partizione: `median` (mediana = 0 — degenera, v. ALERT)
- seed dichiarato: `gate_run_2026-06-22` (master 20260622, schema in `config.make_rng`)
- soglie a priori: η² ≤ 0.2 (a) — |κ_aligned| ≤ 0.2 (b) — min_cell = 30 (c) — |cos| < 0.95 (d). NON modificate ex-post.
- config_hash: `fd558d698d8212f5673acba1dadc2af14ddb2ca3081a806b1e867872ce4cc0a8`
- eventi totali (events_df): 842
- eventi con intensità valida: 686

## Verdetti per criterio

- **(a) within-regime ampia** (η² ≤ 0.2 overall E per ogni leg): `True`
- **(b) dimensioni distinte** (|κ_aligned| ≤ 0.2 overall): `True`
- **(c) celle popolate** (n ≥ 30 per ogni cella regime×intensità): `True`
- **(d) vettori di cambiamento non collineari** (|cos| < 0.95 in entrambe le fette): `None`

## (a) Variance decomposition dell'intensità sul regime

- overall: η² = 0.00264403, n = 686
- by_leg CPI: η² = 0.0843321, n = 155
- by_leg ECB: η² = 0.00137527, n = 259
- by_leg FOMC: η² = 0.0413268, n = 123
- by_leg NFP: η² = 0.0480419, n = 149

## (b) Allineamento partizioni (kappa con label-alignment)

- κ_aligned overall = 0
- κ_aligned by_leg CPI = nan
- κ_aligned by_leg ECB = nan
- κ_aligned by_leg FOMC = nan
- κ_aligned by_leg NFP = nan

## (c) Popolamento celle regime × intensity (soglia 30)

- counts overall (regime, intensità) → n:
  - (negativo, high): 525
  - (positivo, high): 161

## (d) Vettori di cambiamento dei momenti (var_e, var_b, cov_eb)

- status: `missing_cells` (celle mancanti: [('positivo', 'low'), ('negativo', 'low')])

## Note dell'esecutore

- events_df costruito dall'`accounting` del run autoritativo del protocollo v2 (`09_risultati/v2_signflip/result_authoritative.pkl`), input datato in sola lettura. Non è stato eseguito altro codice del repo all'interno di questo run.
- Rendimenti r_e/r_b calcolati sulla stessa finestra ±15 min con edge mediana 5 min (`rate_shock.extract_event_window`), log-return = log(post/pre). NFP/CPI/FOMC su ES/TY, ECB su STXE/FGBL (stesso INSTRUMENT_MAP del protocollo v2).
- Nessun evento scartato dall'esecutore: eventi senza intensità o senza rendimenti validi vengono filtrati nei criteri rispettivi (run_gate / compute_cell_moments). Conteggi nel manifest (`dropped_events_disclosure`).
- L'identificabilità complessiva del canale tassi NON è oggetto di questo report (vincolo dell'esecutore). I verdetti a/b/c/d sopra sono i soli output deliberativi.
