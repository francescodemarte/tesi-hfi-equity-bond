# Cancello canale tasso dalla struttura a termine — report esecutore

- timestamp: `2026-06-22T22:27:11Z`
- eventi in ambito: ['FOMC', 'CPI', 'NFP'] (561 totali; ECB FUORI per pre-registrazione)
- contratti: ['FEIc1', 'FEIc2', 'FEIc3', 'FEIc4']
- finestra: ±15 min (edge mediana 5 min)
- seed: `ts_gate_run_2026-06-23` (master 20260622)
- soglie a priori (congelate): var_PC2 ≥ 0.1; |Δc3|>0 e |Δc4|>0 in ≥ 0.3; min_cell = 30; |cos| < 0.95.
- config_hash: `6e8b44e66732888f967e5b54d247d2ef96d11cb17bc314870a519279a78c1847`
- pickle_auth sha256: `a9c13a7b86789b3159c82fa5f5aa4a2a8de596b9054bf9a336ef27931ad21a9d`

## ESITO: **FAIL_GATE_1**

- gate-1 passed: **False**
  - (i) var_explained(PC2) = 0.03387 (soglia 0.1) → FAIL
  - (ii) frazioni di movimento c3/c4: {'FEIc3': 0.6146, 'FEIc4': 0.6634} (soglia 0.3) → PASS
  - (iii) partition |PC2| (n_high=105, n_low=100) → PASS
- factor_PC1: success=False, partial=True
- factor_PC2: success=False, partial=False

## PCA — struttura a termine (pooled Fed events)

- n_events_used = 205
- var_explained = [0.9426, 0.0339, 0.0141, 0.0094]
- PC1 loadings (livello attesa: tutti concordi):
  - FEIc1: 0.2056
  - FEIc2: 0.3916
  - FEIc3: 0.5512
  - FEIc4: 0.7075
- PC2 loadings (pendenza attesa: segno opposto tra c1 e c4):
  - FEIc1: -0.4996
  - FEIc2: -0.6503
  - FEIc3: -0.0791
  - FEIc4: 0.5668

## Fattore PC1 — criterio (d)

- partition median |PC1| = 0.004662, n_high = 103, n_low = 102
- fraction near zero (≤ q05 di |score|) = 0.06341 (threshold q05 = 0.000833788)
- cell counts (regime × intensity):
  - ('negativo', 'high'): 52
  - ('negativo', 'low'): 70
  - ('positivo', 'high'): 51
  - ('positivo', 'low'): 32
- Δ_rate (positivo) = ['8.516e-05', '2.431e-05', '3.931e-05']
- Δ_rate (negativo) = ['9.426e-06', '7.949e-06', '4.958e-06']
- Δ_regime (high)   = ['8.273e-05', '1.785e-05', '3.768e-05']
- Δ_regime (low)    = ['6.997e-06', '1.497e-06', '3.324e-06']
- distinctness @ positivo: cos = 0.99821, angle = 3.428°, rank = 2 → non collineare: False
- distinctness @ negativo: cos = 0.89968, angle = 25.884°, rank = 2 → non collineare: True
- passa (d) in ENTRAMBI i regimi: **False**

## Fattore PC2 — criterio (d)

- partition median |PC2| = 0.001377, n_high = 105, n_low = 100
- fraction near zero (≤ q05 di |score|) = 0.2244 (threshold q05 = 4.01161e-05)
- cell counts (regime × intensity):
  - ('negativo', 'high'): 50
  - ('negativo', 'low'): 72
  - ('positivo', 'high'): 55
  - ('positivo', 'low'): 28
  - **celle sotto soglia** (30): [('positivo', 'low')]
- Δ_rate (positivo) = ['5.233e-05', '1.552e-05', '2.472e-05']
- Δ_rate (negativo) = ['7.503e-06', '4.197e-06', '1.735e-07']
- Δ_regime (high)   = ['6.849e-05', '1.589e-05', '3.357e-05']
- Δ_regime (low)    = ['2.366e-05', '4.559e-06', '9.027e-06']
- distinctness @ positivo: cos = 0.998292, angle = 3.349°, rank = 2 → non collineare: False
- distinctness @ negativo: cos = 0.895904, angle = 26.375°, rank = 2 → non collineare: True
- passa (d) in ENTRAMBI i regimi: **False**

## Note dell'esecutore

- ECB fuori scope (briefing). `events_df` letto dal pickle autoritativo del v2.
- PCA pooled sui Fed events con Δ valido su tutti e 4 i contratti (filtro NaN dichiarato).
- Convenzione di segno PC1/PC2 fissata e validata su test sintetico (45/45 verdi).
- Riportati entrambi i fattori, in entrambi i regimi. Nessuna scelta ex-post. L'identificabilità (lettura dell'esito) è del ricercatore.
