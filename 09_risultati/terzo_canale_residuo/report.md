# Pacchetto 13 — terzo canale residuo — report esecutore

- timestamp: `2026-06-24T11:03:31Z`
- seed: `terzo_canale_run_2026-06-23` (master 20260621)
- config_hash: `6ee07068d8b8d06efa631e005834f904c360043ec81dbe5981505a546c81af87`
- pickle_07_sha256: `a9c13a7b86789b31…`
- ρ centrale (T0, dp_bar=-3.85): 0.979164
- D_bond = 8.970865529245179
- BY q=0.1, family size=12, crit=None

**Nota — spec §3 RIVISTA (risoluzione patologia §2/§3)**: la sign rule per L è `antisymmetric_pos_eq` (λ_e>0, λ_b<0), per V `antisymmetric_neg_eq` (λ_e<0, λ_b>0), per C `ambiguous`. Una dichiarazione `L=True` NON garantisce contributo indipendente del bond — la spec §2 produce coef_b≈−coef_e/β per costruzione. Vedi `manifest.json → executor.spec_revision_applied`.

## Tabella §8 — terzo canale (12 voci)

| cell | candidate | third_channel | passed_BY | commonality | sign_ok | λ_e | λ_b | p_comm |
|---|---|:---:|:---:|:---:|:---:|---:|---:|---:|
| FOMC/neg | L | False | False | False | None | +nan | +nan | nan |
| FOMC/neg | V | False | False | False | None | -0.0001 | +0.0001 | 0.4816 |
| FOMC/neg | C | False | False | False | None | +0.0017 | -0.0019 | 0.2257 |
| NFP/neg | L | False | False | False | None | +nan | +nan | nan |
| NFP/neg | V | False | False | False | None | -0.0001 | -0.0001 | 0.7822 |
| NFP/neg | C | False | False | False | None | -0.0003 | -0.0002 | 0.8040 |
| CPI/neg | L | False | False | False | None | +nan | +nan | nan |
| CPI/neg | V | False | False | False | None | -0.0002 | +0.0002 | 0.2655 |
| CPI/neg | C | False | False | False | None | +0.0008 | -0.0009 | 0.3414 |
| CPI/pos | L | False | False | False | None | +nan | +nan | nan |
| CPI/pos | V | False | False | False | None | +0.0002 | -0.0001 | 0.8307 |
| CPI/pos | C | False | False | False | None | -0.0056 | +0.0025 | 0.3888 |

## Bianchezza dei residui (per cella, prima della cella L; gli ũ sono comuni)

| cella | autocorr_u_e (p) | autocorr_u_b (p) | regime_dep (p) | is_white |
|---|---:|---:|---:|:---:|
| FOMC/neg | 0.6144 | 0.6144 | n/a | True |
| NFP/neg | 0.0826 | 0.0826 | n/a | True |
| CPI/neg | 0.8113 | 0.8113 | n/a | True |
| CPI/pos | 0.2692 | 0.2692 | n/a | True |

## Sensibilità del gate_a a soglie multiple (F_MOP del 12)

| cella | F_MOP | bias_10pct (23.11) | bias_15pct (17.87) | bias_20pct (15.06) | F10 | robustezza |
|---|---:|:---:|:---:|:---:|:---:|---|
| FOMC/neg | - | - | - | - | - | F_MOP_missing_from_12_report |
| NFP/neg | - | - | - | - | - | F_MOP_missing_from_12_report |
| CPI/neg | - | - | - | - | - | F_MOP_missing_from_12_report |
| CPI/pos | - | - | - | - | - | F_MOP_missing_from_12_report |

## Sezione interpretativa (vincolata dalla patologia §2/§3 — risolta via opzione 2a)

- **L e V** sotto la spec rivista sono identificabili in SENSO (segno di λ_e) ma non in MAGNITUDINE INDIPENDENTE del bond (la patologia §2 forza coef_b=−coef_e/β).
- **C** (ambiguous) si appoggia solo alla comunalità; il sign_ok è True per costruzione.
- Il caso DGP §9.3 (`equity_only`) sotto la sign rule rivista produce L=True come falso positivo strutturale documentato. **Una dichiarazione 'L' in una cella reale NON garantisce che il bond contribuisca indipendentemente al canale.**
- L (proxy_unavailable) ha `z=zeros` per costruzione → comunalità sempre fallisce. I numeri di L sono tecnicamente coerenti col contract API ma NON SONO EVIDENZA.
- Lettura della tabella §8: il risultato del ricercatore.
