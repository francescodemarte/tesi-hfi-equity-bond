# Decomposizione daily Campbell-Ammer — applicata agli eventi v2

- timestamp: `2026-06-22T22:37:11Z`
- modulo: `07/decomposition.py` (11/11 test verdi, osservato prima del run)
- pickle autoritativo: `v2_signflip_run_authoritative_2026-06-22_post_bug2` sha256 `a9c13a7b86789b31…`
- eventi: 842 totali
- D_bond = 8.970866; D_eq_partial (Specifica A) = 5.0

## Aritmetica per evento (input giornalieri):

- `delta_r_real` = Δ DFII5 (5Y TIPS, FRED snapshot), da pp a decimale
- `delta_pi`     = Δ T10YIE (10Y breakeven, FRED), da pp a decimale
- `r_b_daily`    = log-return chiusura giornaliera TY (UST 10Y future)
- `r_e_daily`    = log-return chiusura giornaliera ES (S&P 500 future)
- `c_b_rate = −Δr_real · D_bond`, `c_b_pi = −Δπ · D_bond`, `c_b_res = r_b − c_b_rate − c_b_pi`
- `c_e_rate = −Δr_real · D_eq_partial`, `c_e_res = r_e − c_e_rate`

## Validità input (eventi totali = 842)

- bond_channels validi (tutti gli input non-NaN): 836
- equity_channels validi: 836
- max |r_b − Σ canali bond|  = 0.00e+00 (identità additiva)
- max |r_e − Σ canali equity| = 0.00e+00

## twin_cov per cella (regime × leg)

| leg | regime | n | twin_cov | corr | var(c_e_res) | var(c_b_res) |
|---|---|---:|---:|---:|---:|---:|
| CPI | negativo | 150 | 2.8439e-06 | 0.0933 | 1.0534e-04 | 8.8108e-06 |
| CPI | positivo | 37 | -1.7963e-05 | -0.3313 | 1.8469e-04 | 1.5918e-05 |
| ECB | negativo | 225 | 1.8056e-05 | 0.3257 | 2.5096e-04 | 1.2248e-05 |
| ECB | positivo | 54 | 3.2361e-06 | 0.0975 | 1.0382e-04 | 1.0612e-05 |
| FOMC | negativo | 142 | 1.7089e-07 | 0.0036 | 1.4316e-04 | 1.6101e-05 |
| FOMC | positivo | 45 | 3.5684e-06 | 0.0952 | 9.8166e-05 | 1.4318e-05 |
| NFP | negativo | 141 | 1.4010e-05 | 0.3440 | 1.4815e-04 | 1.1197e-05 |
| NFP | positivo | 42 | 9.0557e-06 | 0.1843 | 1.0589e-04 | 2.2796e-05 |

## twin_cov aggregato — leg US (FOMC+CPI+NFP) vs ECB, per regime

| gruppo | regime | n | twin_cov | corr |
|---|---|---:|---:|---:|
| ECB | negativo | 225 | 1.8056e-05 | 0.3257 |
| ECB | positivo | 54 | 3.2361e-06 | 0.0975 |
| US_only | negativo | 433 | 5.4365e-06 | 0.1361 |
| US_only | positivo | 124 | -1.4792e-06 | -0.0310 |

## Note dell'esecutore

- Aritmetica pura: l'identità additiva r = Σ canali è soddisfatta entro la precisione macchina (max |err| dichiarato sopra). Niente fabbricazione.
- Frequenza daily, evidenza secondaria — NON sostituisce b_H eventi.
- Eventi ECB: il canale tasso USA è proxy debole; riportato separato.
- L'interpretazione (es. 'il residuo gemello identifica un terzo fattore?') è del ricercatore.
