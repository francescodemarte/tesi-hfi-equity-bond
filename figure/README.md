# figure/ — Grafici per il capitolo Risultati della tesi

> Tre grafici analitici in B/N, riproducibili dagli script in `scripts/`.

## Output

| File | Cosa mostra | Dati |
|---|---|---|
| `fig_robustezza_proxy.pdf` | β_str delle 4 celle al variare della proxy di tasso bond (4 punti per cella) | `results/02_decomposition/baseline/` + `results/02_decomposition/true_curve_variants/` |
| `fig_qe_bande.pdf` | Trasmissione QE → curva Bund 3M-30Y con banda 95% e flag BY | `results/05_ecb_curve_qe/results.json` |
| `fig_identificazione.pdf` | Identificazione per eteroschedasticità: scatter eventi+controlli + ellissi cov 95% + 2 rette OLS, NFP/neg | Refinitiv intraday (riuso pacchetto `protocol_v2`) |

## Riproduzione

```bash
cd <root_repo>
python3 figure/scripts/genera_fig_robustezza_proxy.py
python3 figure/scripts/genera_fig_qe_bande.py
python3 figure/scripts/genera_fig_identificazione.py  # richiede Refinitiv intraday in /home/francesco/TESI/Dati/data_processed/
```

Dipendenze: `numpy`, `pandas`, `matplotlib >= 3.7`, `pypdfium2` (per la verifica visiva).

## Stile B/N

- Font: serif (Times), 11 pt base.
- Colori: nessuno. Solo scala di grigi (`0.40`, `0.55`, `0.78`, nero).
- Linee: continua / tratteggiata / punto-tratto / punteggiata.
- Marcatori: cerchio / quadrato / triangolo / rombo / croce; pieni vs vuoti per distinzione semantica (es. significatività BY in fig 2).
- Titoli interni: assenti (vanno nelle caption LaTeX).
- Font matematico: serif coerente; numeri con segno esplicito (`+`/`−`).

## Inclusione in Overleaf

Copia i 3 PDF in `figure/` dentro il progetto LaTeX. Il codice LaTeX per
includerli + bozze di caption tecniche è in
`figure/scripts/figure_latex.tex`.

## Determinismo

`MASTER_SEED = 20260621` per coerenza con la pipeline (`config.MASTER_SEED`
del pacchetto `protocol_v2`). I numeri usati dai grafici sono lettura
diretta dei JSON / pickle / CSV — nessun ricampionamento interno alla
generazione delle figure.

## Provenance dei numeri

Tutti i numeri vengono dai file dei run autoritativi, non da prompt né da
documenti narrativi:

- Fig 1, baseline: `decomp_canali.report.json` (config_hash 12 `907eb0ff…`,
  seed `decomp_canali_2026-06-23`, timestamp `2026-06-23T22:21:46Z`).
- Fig 1, varianti A/B/C: `02_decomposition/true_curve_variants/results.json`.
- Fig 2: `05_ecb_curve_qe/results.json`, step1 `step1_ecb_curve_symmetry`.
- Fig 3: ricostruzione live dai cluster del pacchetto `protocol_v2`
  riproducibile con stesso seed `execute_v2_signflip_2026-06-22`; numeri
  combaciano con `beta_H_robust_cells_w15.json` (`b_OLS = -0.7855`,
  `r_hat = 15.39`).
