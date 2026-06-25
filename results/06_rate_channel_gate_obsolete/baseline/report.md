# Cancello canale tassi — report esecutore

> **ALERT — partizione degenerata sui dati reali.** La mediana within-sample di
> `|Δ FFc2|` su 832 eventi è esattamente **0** (565/832 = 67.9% degli eventi
> hanno `|Δ FFc2|` = 0 sulla finestra ±15 min: l'attività di FFc2 è quasi
> nulla fuori dai meeting FOMC, e spesso nulla anche dentro le finestre di altri
> annunci). `D.dichotomize("median")` etichetta `x >= median` → con median = 0
> tutti gli 832 eventi (intensità ≥ 0 per costruzione) finiscono nella categoria
> **`high`**; le celle `(positivo, low)` e `(negativo, low)` sono vuote.
>
> Conseguenze sui verdetti:
>
> - **(a) True** — η² è basso ma calcolato su un fattore in cui un regime
>   include solo eventi a intensità positiva e l'altro idem; il risultato è
>   matematicamente corretto, ma sulla scala dei numeri originali (non binari).
> - **(b) True** — `κ_aligned = 0` *per costruzione*: con una sola categoria di
>   intensità non c'è alcuna partizione su quella dimensione, l'accordo atteso
>   sotto indipendenza coincide con l'osservato. **Non significa indipendenza
>   strutturale**; significa che la partizione binaria è degenere.
> - **(c) True** — `cells_below_threshold` opera sulle celle *presenti*. Le due
>   celle `*|high` superano 30; le due celle `*|low` mancano del tutto e non
>   sono considerate dal kernel. Il verdetto vero "tutte e 4 le celle ≥ 30" qui
>   **non è soddisfatto**.
> - **(d) None** — celle `(positivo, low)` e `(negativo, low)` assenti →
>   vettori di cambiamento non calcolabili (`status = missing_cells`).
>
> Per il presidio anti-fabbricazione (PROMPT §"Se un numero esce strano…"),
> NON ho cambiato soglie, modalità di partizione né contratto ex-post. La
> consegna è il run letterale; un'analisi alternativa va riconsegnata alla
> filiera (vedi `HANDOFF.md` accanto a questo report).

- timestamp (esterno): `2026-06-22T21:43:30Z`
- contratto tassi: `FFc2`
- finestra: ±15 min (edge mediana 5 min)
- modalità partizione: `median` (mediana = 0 — degenera, v. ALERT)
- seed dichiarato: `gate_run_2026-06-22` (master 20260622, schema in `config.make_rng`)
- soglie a priori: η² ≤ 0.2 (a) — |κ_aligned| ≤ 0.2 (b) — min_cell = 30 (c) — |cos| < 0.95 (d). NON modificate ex-post.
- config_hash: `fd558d698d8212f5673acba1dadc2af14ddb2ca3081a806b1e867872ce4cc0a8`
- eventi totali (events_df): 842
- eventi con intensità valida: 832

## Verdetti per criterio

- **(a) within-regime ampia** (η² ≤ 0.2 overall E per ogni leg): `True`
- **(b) dimensioni distinte** (|κ_aligned| ≤ 0.2 overall): `True`
- **(c) celle popolate** (n ≥ 30 per ogni cella regime×intensità): `True`
- **(d) vettori di cambiamento non collineari** (|cos| < 0.95 in entrambe le fette): `None`

## (a) Variance decomposition dell'intensità sul regime

- overall: η² = 0.0109143, n = 832
- by_leg CPI: η² = 0.0670466, n = 186
- by_leg ECB: η² = 9.50244e-06, n = 275
- by_leg FOMC: η² = 0.000641247, n = 187
- by_leg NFP: η² = 0.0229048, n = 184

## (b) Allineamento partizioni (kappa con label-alignment)

- κ_aligned overall = 0
- κ_aligned by_leg CPI = nan
- κ_aligned by_leg ECB = nan
- κ_aligned by_leg FOMC = nan
- κ_aligned by_leg NFP = nan

## (c) Popolamento celle regime × intensity (soglia 30)

- counts overall (regime, intensità) → n:
  - (negativo, high): 654
  - (positivo, high): 178

## (d) Vettori di cambiamento dei momenti (var_e, var_b, cov_eb)

- status: `missing_cells` (celle mancanti: [('positivo', 'low'), ('negativo', 'low')])

## Note dell'esecutore

- events_df costruito dall'`accounting` del run autoritativo del protocollo v2 (`09_risultati/v2_signflip/result_authoritative.pkl`), input datato in sola lettura. Non è stato eseguito altro codice del repo all'interno di questo run.
- Rendimenti r_e/r_b calcolati sulla stessa finestra ±15 min con edge mediana 5 min (`rate_shock.extract_event_window`), log-return = log(post/pre). NFP/CPI/FOMC su ES/TY, ECB su STXE/FGBL (stesso INSTRUMENT_MAP del protocollo v2).
- Nessun evento scartato dall'esecutore: eventi senza intensità o senza rendimenti validi vengono filtrati nei criteri rispettivi (run_gate / compute_cell_moments). Conteggi nel manifest (`dropped_events_disclosure`).
- L'identificabilità complessiva del canale tassi NON è oggetto di questo report (vincolo dell'esecutore). I verdetti a/b/c/d sopra sono i soli output deliberativi.
