# Decomposizione dell'eccesso di comovimento in canali — doppio cancello

Stima di **β_str** (canale strutturale) sui rendimenti netti dal canale di
tasso, **per cella (regime × gamba)**, con due cancelli empirici che
decidono se la decomposizione regge.

## Stato

**40 test verdi** (su DGP sintetici a verità nota — coder, prima dei dati reali).

## Allineamento al run autoritativo `a9c13a7b`

Stessi parametri di protocollo:
- `MASTER_SEED = 20260621`, `B_BOOT = 10_000`
- `MOP_CV = 23.1085` (Nagar bias, K=1, Patnaik conservativa)
- `BY_Q = 0.10` (FDR Benjamini–Yekutieli)

## Moduli

| File | Ruolo |
|---|---|
| `config.py` | Parametri congelati: griglia coda 4 × ρ 3 = 12 punti per evento; `SHRINK_FLOOR=0.05` (cancello a aux.) |
| `bond_pb.py` | ΔP^B_bond = −D · Δy (lettura diretta, niente coda) |
| `equity_pb.py` | ΔP^B_eq = −Σ ρ^(n−1)·Δf_n; coda da griglia {T0, TC, TD_0.5, TD_0.8}; `rho_from_dp_bar`, `delta_pb_equity_full_grid` |
| `netting.py` | Passo 2: r̃_e = r_e − ΔP^B_e ; r̃_b = r_b − ΔP^B_b |
| `estimator.py` | Passo 3: β_str = ΔCov(r̃_e,r̃_b)/ΔVar(r̃_b); `shrink_ratio` |
| `gates.py` | Cancello (a): F-MOP ≥ cv **AND** shrink ≥ floor; (b) `construction_band`, `total_band`; `tail_border_precheck` con surprise (Nagel–Xu) |
| `cell_pipeline.py` | Orchestratore per cella: 12-point profile + bootstrap clusterizzato + verdetto |
| `synthetic.py` | DGP §7 (4 casi obbligatori) |

## I due cancelli (per cella)

**(a) Strumento debole sul bond netto:**
- F-MOP effettivo su ΔVar(r̃_b) ≥ `MOP_CV = 23.1085`, **AND**
- `shrink = ΔVar(r̃_b)/ΔVar(r_b) ≥ SHRINK_FLOOR = 0.05` (default).
- Aggiunta dello shrink-floor: F-MOP da solo può essere numericamente alto su quantità minuscole (caso "bond svuotato"). La spec dice esplicitamente `shrink → 0 ⇒ FAIL atteso`.

**(b) Banda di costruzione propagata in β_str:**
- 12 punti = 4 code × 3 ρ. `banda_costruzione = [min, max]` di β_str sulla griglia.
- `banda_campionaria`: CI percentile bootstrap su β_str al punto centrale (T0, ρ calibrato), B=10000, seed dichiarato.
- `banda_totale` = inviluppo delle due.

**Pre-check §3.3 (Nagel–Xu Tab A.1):** Δf_m al bordo della curva comova con la sorpresa monetaria (`surprise_per_event` opzionale). Se passa la sorpresa, regressione Δf_m ~ surprise con t sulla slope; p < α ⇒ `WARN`. Senza sorpresa, fallback t-test sulla media (limitazione documentata: bassa potenza per movimenti simmetrici).

## Verdetto per cella

| gate(a) | precheck | banda costruzione | verdetto |
|---|---|---|---|
| FAIL | — | — | `channel_not_identified` |
| PASS | WARN | qualsiasi | `identified_fragile` |
| PASS | PASS | width > soglia | `identified_fragile` |
| PASS | PASS | width ≤ soglia | `identified_robust` |

## DGP §7 — 4 casi obbligatori (tutti GREEN sui test)

| Caso | Atteso | Verificato |
|---|---|---|
| §7.1 bond con struttura (γ_b=1, δ_b=0.5) | gate(a) PASS, banda copre γ_e/γ_b=2.0 | ✓ |
| §7.2 bond quasi puro tasso (γ_b=0.05) | gate(a) FAIL via shrink-floor, verdict=`channel_not_identified` | ✓ |
| §7.3 coda informativa (c_n=0.95^n) | precheck WARN (slope vs s_r), verdict `identified_fragile` | ✓ |
| §7.4 canale singolo (δ≡0) | banda costruzione degenere (width=0) | ✓ |

## Anti-fabrication audit

- 0 stub `return <costante>`.
- 0 fetch di rete.
- 10 `raise` espliciti per input invalidi (duration negativa, tail sconosciuto, N<m, ρ fuori (0,1), F-MOP NaN, mismatch dim, ecc.).
- Seed dichiarato e intero esposto via `config.seed_for(name)`.

## Convenzioni esplicite (REVIEW #3/#4)

- **"Bootstrap clusterizzato per evento" — terminologia del 12.** Qui un
  cluster è una RIGA (un evento col suo control matchato), NON "evento + 3-10
  controlli" come nel 07. `_bootstrap_dvar` e `_bootstrap_beta_sampling_band`
  ricampionano indipendentemente `n_e` indici evento e `n_c` indici controllo.
- **Controlli con ΔP^B = 0 by construction.** Il control window non ha
  l'annuncio ⇒ niente componente di tasso da sottrarre. L'asimmetria è voluta:
  l'evento è "depurato" dal canale di tasso, il controllo conserva il rumore
  di tasso non legato all'annuncio. Esplicitato anche nel manifest
  (`replicability_assumption`).

## Manifest

`manifest.build_manifest(cell_outputs, input_paths, code_paths, seed_name,
timestamp)` produce il dict di provenienza con: `config_hash`, `config_snapshot`,
`seed.value` (intero dichiarato via `config.seed_for(name)`), hash input/codice,
`cell_counts`, `verdicts_per_cell`, `gate_a_per_cell`, e
`replicability_assumption` esplicita (Campbell-Shiller log-lin + ρ_a da dp_bar
esterno + griglia coda discreta + convenzione controlli). `write_manifest`
serializza con sort_keys. Pattern uniforme con 07/08/11.

## Cosa NON è in questo modulo

- Esecuzione sui dati reali — è dell'esecutore (prossimo anello).
- Inferenza aggregata cross-cell (BY) — l'esecutore aggrega i verdetti per-cella.
- Tabella §6 finale serializzata — l'esecutore la produce dal dict di `run_cell`
  e la rende riproducibile col manifest.

## Come si esegue

```bash
python3 -m pytest tests/ -q     # 40 passed (sintetico)
```

L'esecutore importa `cell_pipeline.run_cell(events, dp_bar, N, ...)` su eventi
reali congelati, una cella alla volta, e produce la tabella §6.
