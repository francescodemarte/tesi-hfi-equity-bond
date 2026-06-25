# Cancello canale tassi — gruppo ECB_FEIc1 (movement)

- timestamp: `2026-06-22T22:06:48Z`
- gruppo: legs = ['ECB'], contratto = `FEIc1`
- partition_mode: `movement` (x>0 → 'high', x=0 → 'low')
- finestra: ±15 min (edge mediana 5 min)
- seed: `gate_run_movement_2026-06-23` (master 20260622)
- soglie a priori: η²≤0.2 (a), |κ|≤0.2 (b), min_cell=30 (c), |cos|<0.95 (d)
- config_hash: `fd558d698d8212f5673acba1dadc2af14ddb2ca3081a806b1e867872ce4cc0a8`
- eventi nel gruppo: 281
- eventi con intensità valida: 259  (high=138, low=121)

## Verdetti per criterio

- **(a) within-regime ampia** (η² ≤ 0.2): `True`
- **(b) dimensioni distinte** (|κ_aligned| ≤ 0.2): `True`
- **(c) celle popolate** (n ≥ 30): `False`
- **(d) vettori di cambiamento non-collineari** (|cos| < 0.95): `False`

## (a) η² intensità ~ regime
- overall η² = 0.00137527, n = 259
- by_leg ECB: η² = 0.00137527, n = 259

## (b) Kappa allineato
- κ_aligned overall = 0.140757
- κ_aligned by_leg ECB = 0.1407568238213401

## (c) Popolamento celle regime × intensità (soglia 30)

  - (negativo, high): 101
  - (negativo, low): 105
  - (positivo, high): 37
  - (positivo, low): 16
- **CELLE SOTTO SOGLIA:** [('positivo', 'low')]

## (d) Vettori di cambiamento

- Δ_rate (positivo) = [7.516777060515687e-06, 8.462651674862371e-06, 6.199920562324018e-06]
- Δ_rate (negativo) = [3.807811372715415e-05, 2.7502858371886223e-06, 7.671586615173706e-07]
- Δ_regime (high)   = [-3.562248952105434e-05, 5.807656600990437e-06, 6.108977759855727e-06]
- Δ_regime (low)    = [-5.061152854415873e-06, 9.529076331668764e-08, 6.762158590490792e-07]
- distinctness @ positivo: cos = -0.382583, angle = 112.494°, rank = 2
- distinctness @ negativo: cos = -0.984241, angle = 169.815°, rank = 2

## Note dell'esecutore

- `events_df` letto dall'`accounting` del pickle autoritativo del v2 (sola lettura, input datato).
- Rendimenti r_e/r_b sulla stessa finestra ±15 min, log-return = log(post/pre).
- Partition `movement`: split su `x>0 vs x=0` — pre-registrato per coerenza con la massa in 0 di |Δprice|.
- Nessuna soglia / contratto / leg / sample è stato cambiato dopo il run.
