# Pratica: eccesso di comovimento equity-bond agli annunci

Strategia illustrativa che tradeggia l'eccesso ε = (c_i − a_i) / σ²_pre,i del
comovimento equity-bond agli annunci **NFP e CPI**, condizionata al regime a
t−4. **Niente spillover.** Capitolo "implicazioni operative" — non un prodotto
di trading: payoff teorico lordo, no costi, non è uno Sharpe eseguibile.

## Stato

**44/44 test verdi.** Niente esecuzione sui dati reali — l'esecutore importa
`run.run_strategy(events_df, ...)` con eventi congelati e scrive il manifest.

## Confine del compito (vincolante)

- **Anti-fabbricazione:** 0 stub, 0 fetch, 18 raise espliciti. Ogni branch è
  un calcolo onesto o solleva.
- **Congelamento e una sola occhiata al test:** training 2010-2020,
  test 2021-2025. La calibrazione **strutturalmente** rifiuta eventi con date
  ≥ split_date (`calibration.calibrate` solleva su leakage).
- **Niente esecuzione sui dati reali in questo modulo.** `run.main()` solleva.

## Tre finestre disgiunte (presidio anti-look-ahead INTRA-evento)

Per ogni evento i:
- **Regime** g_i: segno della corr equity-bond su 63 sedute fino a **t−4**.
- **Aspettativa** (a_i, σ²_pre,i): media e varianza dei rendimenti su **t−3..t−1**.
- **Evento** t: c_i = r_e,i · r_b,i (covarianza realizzata per-evento).

Disgiunte by construction. Aggiuntivo `windows.assert_no_lookahead(used_indices, event_idx)`.

## Eccesso normalizzato e regola

- ε_i = (c_i − a_i) / σ²_pre,i (adimensionale).
- e_{g,k} = media di ε sui training events della cella (gamba, regime).
- Posizione (base): w_i = sign(e_{g,k}). Soglia `MIN_ABS_E_FOR_POSITION=0` per default.
- Payoff: π_i = w_i · ε_i.
- Benchmark naive: w=+1 sempre, π_bench = ε_i.
- Combinazione gambe: pesi ∝ 1/σ_roll,k con σ_roll,k stimata su eventi PASSATI
  della gamba k, lunghezza congelata (`INV_VOL_ROLLING_EVENTS=20`).

## Split temporale (presidio anti-look-ahead INTER-temporale)

- Training: `[2010-01-01, 2021-01-01)`.
- Test: `[2021-01-01, 2025-12-31]`.
- Calibrazione **STRUTTURALMENTE** train-only (`calibration.calibrate` solleva
  su date ≥ split). I due presidi (intra-evento + inter-temporale) sono **ortogonali**.

**Dichiarazione obbligatoria nel manifest e in tesi:** il test è popolato sul
regime **negativo** (presente in entrambi i periodi) e povero sul **positivo**
(che vive quasi solo nel test e che il training ha visto poco). Sotto la
soglia `MIN_CELL_N_FOR_VERDICT=20` il verdetto è `inconclusive`.

## Moduli

| File | Ruolo |
|---|---|
| `config.py` | parametri CONGELATI: finestre, split dates, inverse-vol window, seed `20260622` |
| `windows.py` | 3 finestre disgiunte + assert_no_lookahead + regime_sign |
| `excess.py` | c_i, a_i, σ²_pre,i, ε_i |
| `calibration.py` | e_{g,k} train-only (presidio strutturale) + position_for(sign) |
| `weighting.py` | rolling_vol_at su eventi PASSATI (lunghezza congelata) + combine_legs inverse-vol |
| `payoff.py` | π = w·ε e π_bench = ε |
| `metrics.py` | mean, Sharpe, hit rate, diff vs benchmark, soglia n inconcludenza |
| `synthetic.py` | 4 DGP a verità nota (signal, noise, lookahead trap, imbalanced) |
| `run.py` | orchestratore `run_strategy(events_df, ...)`; `main()` bloccato |
| `manifest.py` | provenance + replicability note + cell counts + timestamp esterno |

## DGP sintetici validati (i 4 richiesti dalla spec)

| DGP | Atteso | Verificato (44 test) |
|---|---|---|
| **signal** | strategia condizionata batte naive OOS | mean OOS > 0.10 per ogni cella; diff vs naive grande sul regime neg |
| **noise** | nessun payoff sistematico OOS | \|mean OOS\| < 0.06 per cella ben popolata |
| **lookahead trap** | split blocca leakage | e_{g,k} stimato sul training ≈ 0 (training rumore); test sintetico esplicito che `calibrate` raise se mescolato |
| **imbalanced** | regime positivo raro → inconclusivo | n_test pos < soglia in tutte le celle, verdict="inconclusive" |

## Contratto di output (per l'esecutore)

`run.run_strategy` ritorna dict con:
- `calibration` → `e_gk`, `n_train`
- `training_metrics`, `test_metrics` → per cella (leg, regime) e per ("COMBINED", regime):
  - `n`, `strategy` (n/mean/sharpe/hit_rate/verdict), `benchmark` (idem), `diff` (mean_diff vs bench)
- `split_date`, `n_train`, `n_test`, `config_hash`

Manifest (`manifest.build_manifest` + `write_manifest`): config snapshot, hash
input/codice, seed dichiarato, cell_counts, **ASSUNZIONE DI REPLICABILITÀ
covariance-swap dichiarata**, timestamp PASSATO DALL'ESTERNO.

## Come si esegue

```bash
python3 -m pytest tests/ -q     # 44 passed
```

Esecuzione reale: importare `run.run_strategy(events_df, ...)` con
DataFrame esterno (date, leg ∈ {NFP, CPI}, regime ∈ {pos, neg}, epsilon),
e `manifest.write_manifest(...)` con `timestamp` esterno.
