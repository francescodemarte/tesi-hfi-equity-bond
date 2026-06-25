# Cancello canale tassi — gruppo Fed_FFc2 (movement)

- timestamp: `2026-06-22T22:06:48Z`
- gruppo: legs = ['FOMC', 'CPI', 'NFP'], contratto = `FFc2`
- partition_mode: `movement` (x>0 → 'high', x=0 → 'low')
- finestra: ±15 min (edge mediana 5 min)
- seed: `gate_run_movement_2026-06-23` (master 20260622)
- soglie a priori: η²≤0.2 (a), |κ|≤0.2 (b), min_cell=30 (c), |cos|<0.95 (d)
- config_hash: `fd558d698d8212f5673acba1dadc2af14ddb2ca3081a806b1e867872ce4cc0a8`
- eventi nel gruppo: 561
- eventi con intensità valida: 557  (high=220, low=337)

## Verdetti per criterio

- **(a) within-regime ampia** (η² ≤ 0.2): `True`
- **(b) dimensioni distinte** (|κ_aligned| ≤ 0.2): `True`
- **(c) celle popolate** (n ≥ 30): `True`
- **(d) vettori di cambiamento non-collineari** (|cos| < 0.95): `False`

## (a) η² intensità ~ regime
- overall η² = 0.0151056, n = 557
- by_leg CPI: η² = 0.0670466, n = 186
- by_leg FOMC: η² = 0.000641247, n = 187
- by_leg NFP: η² = 0.0229048, n = 184

## (b) Kappa allineato
- κ_aligned overall = 0.105861
- κ_aligned by_leg CPI = 0.15910748140586276
- κ_aligned by_leg FOMC = 0.04652644996813253
- κ_aligned by_leg NFP = 0.11011904761904762

## (c) Popolamento celle regime × intensità (soglia 30)

  - (negativo, high): 158
  - (negativo, low): 275
  - (positivo, high): 62
  - (positivo, low): 62

## (d) Vettori di cambiamento

- Δ_rate (positivo) = [7.857559066155626e-05, 1.772481784589083e-05, 3.4393594433191114e-05]
- Δ_rate (negativo) = [3.943820318484033e-06, 2.8480139210093314e-06, 7.666313889201231e-07]
- Δ_regime (high)   = [7.644805725127718e-05, 1.8018767496457477e-05, 3.866159383167191e-05]
- Δ_regime (low)    = [1.8162869082049602e-06, 3.1419635715759746e-06, 5.034630787400914e-06]
- distinctness @ positivo: cos = 0.998511, angle = 3.127°, rank = 2
- distinctness @ negativo: cos = 0.653417, angle = 49.200°, rank = 2

## Note dell'esecutore

- `events_df` letto dall'`accounting` del pickle autoritativo del v2 (sola lettura, input datato).
- Rendimenti r_e/r_b sulla stessa finestra ±15 min, log-return = log(post/pre).
- Partition `movement`: split su `x>0 vs x=0` — pre-registrato per coerenza con la massa in 0 di |Δprice|.
- Nessuna soglia / contratto / leg / sample è stato cambiato dopo il run.
